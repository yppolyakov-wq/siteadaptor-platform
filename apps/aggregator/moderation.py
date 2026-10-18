"""T-8.10e (D2b-1): проверка карточек каталога города правилами → очередь модератора.

План — docs/d2-ai-text-check-plan-2026-10-17.md §6. Когда карточка появилась или
изменилась (`tasks._upsert_listing` → True), те же правила «Text-Check» в скоупе каталога
плюс поиск дублей кладут сомнительное в существующую очередь `ListingReport` (T-8.6).
Решения владельца: автоматика сама НЕ скрывает (В-2), машинная пометка — не голос
жалоб (В-3: `ip_hash=AUTO_MARKER` исключён из подсчёта в `reports.file_report`).
Демо и внутренние бизнесы не проверяются (иначе сидинг завалит очередь)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core import text_check as tc

from .models import AggregatorListing, ListingReport

logger = logging.getLogger(__name__)

AUTO_MARKER = ListingReport.AUTO_MARKER
DUPLICATE_WINDOW_DAYS = 14
FOREIGN_DUPLICATE_TENANTS = 2  # ещё двое с тем же заголовком → три бизнеса = спам
DUPLICATE_SCAN = 200
MESSAGE_QUOTE_MAX = 80

# Код → причина очереди. Неизвестный код — «Sonstiges».
_REASONS = {
    "kontakt_im_text": ListingReport.REASON_SPAM,
    "duplikat_eigen": ListingReport.REASON_SPAM,
    "duplikat_fremd": ListingReport.REASON_SPAM,
    "statt_ohne_referenz": ListingReport.REASON_WRONG,
    "preis_widerspruch": ListingReport.REASON_WRONG,
    "rabatt_unplausibel": ListingReport.REASON_WRONG,
    "streich_ohne_ende": ListingReport.REASON_WRONG,
    "gratis_mit_preis": ListingReport.REASON_WRONG,
    "dringlichkeit_heute": ListingReport.REASON_WRONG,
    "raeumung": ListingReport.REASON_WRONG,
    "gesundheit": ListingReport.REASON_WRONG,
    # D2b-2: причины ИИ-модерации («illegal» — «Anstößig oder rechtswidrig»).
    "ai_spam": ListingReport.REASON_SPAM,
    "ai_offensive": ListingReport.REASON_OFFENSIVE,
    "ai_illegal": ListingReport.REASON_OFFENSIVE,
    "ai_implausible": ListingReport.REASON_WRONG,
    "ai_misleading": ListingReport.REASON_WRONG,
    "ai_off_topic": ListingReport.REASON_OTHER,
}
# Приоритет причины, если кодов несколько: спам важнее «неверных данных».
_REASON_ORDER = (
    ListingReport.REASON_OFFENSIVE,
    ListingReport.REASON_SPAM,
    ListingReport.REASON_WRONG,
    ListingReport.REASON_OTHER,
)


def _clean_quote(text: str) -> str:
    """Цитата для очереди: без управляющих символов и bidi-меток, в одну строку."""
    import unicodedata

    text = "".join(c for c in str(text or "") if not unicodedata.category(c).startswith("C"))
    return " ".join(text.split())


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _base_title(listing) -> str:
    title = listing.title if isinstance(listing.title, dict) else {}
    return str(title.get(settings.LANGUAGE_CODE) or "")


def _base_teaser(listing) -> str:
    teaser = listing.teaser if isinstance(listing.teaser, dict) else {}
    return str(teaser.get(settings.LANGUAGE_CODE) or "").strip()


def input_from_listing(listing) -> tc.CheckInput:
    from apps.core.archetypes import FOOD_BUSINESS_TYPES

    texts = {}
    for name, value in (("title", listing.title), ("description", listing.teaser)):
        if isinstance(value, dict):
            found = {str(k): v for k, v in value.items() if isinstance(v, str) and v.strip()}
            if found:
                texts[name] = found
    return tc.CheckInput(
        texts=texts,
        new_price=listing.new_price,
        old_price=listing.old_price,
        percent=listing.discount_percent,
        ends_at=listing.ends_at,
        price_condition=listing.price_condition or None,
        mystery=bool(listing.is_surprise),
        is_food=listing.business_type in FOOD_BUSINESS_TYPES,
    )


def _hit(code: str, quote: str) -> tc.Finding:
    return tc.Finding(
        code=code,
        severity="medium",
        field="title",
        locale=settings.LANGUAGE_CODE,
        quote=_clean_quote(quote)[:MESSAGE_QUOTE_MAX],
        message="",
        norm="",
    )


def _duplicates(listing) -> list[tc.Finding]:
    """Свой дубль (тот же заголовок у этого бизнеса за 14 дней) и чужой (тот же
    заголовок ещё у двух бизнесов того же города). Только активные карточки, с LIMIT."""
    title = _norm(_base_title(listing))
    if len(title) < 4:
        return []
    found = []
    since = timezone.now() - timedelta(days=DUPLICATE_WINDOW_DAYS)
    own = (
        AggregatorListing.objects.filter(
            tenant_schema=listing.tenant_schema,
            listing_kind=listing.listing_kind,
            is_active=True,
            created_at__gte=since,
        )
        .exclude(pk=listing.pk)
        .order_by("-created_at")
        .values_list("title", flat=True)[:DUPLICATE_SCAN]
    )
    if any(isinstance(t, dict) and _norm(t.get(settings.LANGUAGE_CODE)) == title for t in own):
        found.append(_hit("duplikat_eigen", _base_title(listing)))
    if listing.city:
        others = (
            AggregatorListing.objects.filter(
                city=listing.city,
                listing_kind=listing.listing_kind,
                is_active=True,
                is_demo=False,  # демо не делают чужую карточку «спамом»
                # Спам = тот же заголовок И тот же тизер: общие имена («Wochenangebot») — нет.
                **{f"teaser__{settings.LANGUAGE_CODE}__iexact": _base_teaser(listing)},
                # Без учёта регистра — как у своих дублей (сравнение по _norm).
                **{f"title__{settings.LANGUAGE_CODE}__iexact": _base_title(listing).strip()},
            )
            .exclude(tenant_schema=listing.tenant_schema)
            .values_list("tenant_schema", flat=True)
            .distinct()[: FOREIGN_DUPLICATE_TENANTS + 1]
        )
        if len(list(others)) >= FOREIGN_DUPLICATE_TENANTS:
            found.append(_hit("duplikat_fremd", _base_title(listing)))
    return found


def check_listing(listing) -> list[tc.Finding]:
    findings = tc.run(input_from_listing(listing), scope=tc.CATALOG)
    findings = [f for f in findings if f.severity in ("high", "medium")]
    return findings + _duplicates(listing)


def _message(findings, source: str) -> str:
    """Метка источника — из самих находок (`rule`, `ai`, `ai+rule`): пометка только
    правилами байт-в-байт прежняя, а общий вызов не даёт ИИ затереть коды правил."""
    codes = sorted({f.code for f in findings})
    label = "+".join(sorted({getattr(f, "source", "") or source for f in findings}))
    rule_quote = next((f.quote for f in findings if f.quote and f.source != "ai"), "")
    ai_quote = next((f.quote for f in findings if f.quote and f.source == "ai"), "")
    quote = _clean_quote(rule_quote or ai_quote)
    text = f"[auto:{label}] " + ", ".join(codes)
    if quote:
        text += f" — „{quote[:MESSAGE_QUOTE_MAX]}“"
    ai_quote = _clean_quote(ai_quote)
    if rule_quote and ai_quote and ai_quote != quote:
        text += f" · KI: „{ai_quote[:MESSAGE_QUOTE_MAX]}“"
    return text[:1000]


def flag(listing, findings, *, source: str = "rule") -> ListingReport | None:
    """Одна ОТКРЫТАЯ машинная пометка на карточку: новый текст обновляет её, а не
    плодит строки (ревью: правки карточки не должны засорять очередь). Решённая
    модератором пометка с тем же текстом не всплывает снова. Карточку НЕ скрывает."""
    if not findings:
        return None
    message = _message(findings, source)
    auto = ListingReport.objects.filter(listing=listing, ip_hash=AUTO_MARKER)
    if auto.filter(message=message).exists():
        return None
    reasons = {_REASONS.get(f.code, ListingReport.REASON_OTHER) for f in findings}
    reason = next(r for r in _REASON_ORDER if r in reasons)
    current = auto.filter(status=ListingReport.STATUS_OPEN).order_by("-created_at").first()
    if current is not None:
        current.message, current.reason = message, reason
        current.save(update_fields=["message", "reason"])
        return current
    return ListingReport.objects.create(
        listing=listing, reason=reason, message=message, ip_hash=AUTO_MARKER
    )


def _internal(schema: str) -> bool:
    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=schema, is_internal=True).exists()


def moderate(listing) -> ListingReport | None:
    # v1 — только акции (ревью: у товаров old_price = UVP без срока, у услуг/номеров/событий
    # другие цены — правила давали бы шум); остальные виды — D2c после замеров точности.
    if listing.listing_kind != AggregatorListing.KIND_PROMOTION:
        return None
    if listing.is_demo or _internal(listing.tenant_schema):
        return None
    rules = check_listing(listing)
    # D2b-2: ИИ только добавляет находки; любой сбой — путь правил как прежде.
    from . import ai_moderation

    try:
        ai = ai_moderation.review(listing)
    except Exception:
        logger.exception("catalog ai moderation failed for listing %s", listing.pk)
        ai = None
    if ai is None and _keeps_ai_codes(listing, rules):
        return None  # вердикта нет — прежние коды ИИ не «теряем» и решённое не всплывает
    return flag(listing, rules + (ai or []))


def _message_codes(message: str) -> set[str]:
    head = message.split("] ", 1)[-1].split(" — ", 1)[0]
    return {c.strip() for c in head.split(",") if c.strip()}


def _keeps_ai_codes(listing, rules) -> bool:
    """Последняя машинная пометка несёт коды ИИ, а правила дают те же коды — без нового
    вердикта ИИ переписывать её нечем (иначе коды ИИ пропали бы, а решённая пометка
    вернулась бы в очередь). Изменились находки правил — пишем как обычно."""
    last = (
        ListingReport.objects.filter(listing=listing, ip_hash=AUTO_MARKER)
        .order_by("-created_at")
        .values_list("message", flat=True)
        .first()
    )
    if not last or not last.startswith("[auto:ai"):
        return False
    old = {c for c in _message_codes(last) if not c.startswith("ai_")}
    return old == {f.code for f in rules}
