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

AUTO_MARKER = "auto"
DUPLICATE_WINDOW_DAYS = 14
FOREIGN_DUPLICATE_TENANTS = 2  # ещё двое с тем же заголовком → три бизнеса = спам
DUPLICATE_SCAN = 200
MESSAGE_QUOTE_MAX = 80

# Код → причина очереди. Неизвестный код — «Sonstiges».
_REASONS = {
    "kontakt_im_text": ListingReport.REASON_SPAM,
    "grossbuchstaben": ListingReport.REASON_SPAM,
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
}
# Приоритет причины, если кодов несколько: спам важнее «неверных данных».
_REASON_ORDER = (
    ListingReport.REASON_OFFENSIVE,
    ListingReport.REASON_SPAM,
    ListingReport.REASON_WRONG,
    ListingReport.REASON_OTHER,
)


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _base_title(listing) -> str:
    title = listing.title if isinstance(listing.title, dict) else {}
    return str(title.get(settings.LANGUAGE_CODE) or "")


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
        quote=quote[:MESSAGE_QUOTE_MAX],
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
        .values_list("title", flat=True)[:DUPLICATE_SCAN]
    )
    if any(isinstance(t, dict) and _norm(t.get(settings.LANGUAGE_CODE)) == title for t in own):
        found.append(_hit("duplikat_eigen", _base_title(listing)))
    if listing.city:
        others = (
            AggregatorListing.objects.filter(
                city=listing.city,
                is_active=True,
                **{f"title__{settings.LANGUAGE_CODE}": _base_title(listing).strip()},
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
    codes = sorted({f.code for f in findings})
    quote = next((f.quote for f in findings if f.quote), "")
    text = f"[auto:{source}] " + ", ".join(codes)
    if quote:
        text += f" — „{quote[:MESSAGE_QUOTE_MAX]}“"
    return text[:1000]


def flag(listing, findings, *, source: str = "rule") -> ListingReport | None:
    """Одна машинная пометка на (карточка, набор кодов + цитата); решённая модератором
    не всплывает снова, пока не изменится текст. Карточку НЕ скрывает."""
    if not findings:
        return None
    message = _message(findings, source)
    if ListingReport.objects.filter(listing=listing, message=message).exists():
        return None
    reasons = {_REASONS.get(f.code, ListingReport.REASON_OTHER) for f in findings}
    reason = next(r for r in _REASON_ORDER if r in reasons)
    return ListingReport.objects.create(
        listing=listing, reason=reason, message=message, ip_hash=AUTO_MARKER
    )


def _internal(schema: str) -> bool:
    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=schema, is_internal=True).exists()


def moderate(listing) -> ListingReport | None:
    if listing.is_demo or _internal(listing.tenant_schema):
        return None
    return flag(listing, check_listing(listing))
