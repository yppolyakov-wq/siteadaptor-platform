"""T-8.10c: «Was heute starten?» — подсказки акции из СВОИХ данных бизнеса.

План — docs/d1-ai-photo-promo-today-plan-2026-10-17.md §4. Движок правил без ИИ:
каждая подсказка выводится из БД (партия с близким MHD, свободные слоты завтра, короткая
«дыра» между бронями номера, удачная прошлая акция, свободные места события). Тап по
подсказке открывает ЗАПОЛНЕННЫЙ ассистент «Schnell-Aktion» — публикует по-прежнему
владелец. Ссылке не верим: подсказка пересчитывается при открытии (`resolve`).

Цифры — из данных или редактируемые дефолты (лестница скидок): ИИ их не придумывает.
Упавшее правило не роняет остальные (как блоки дайджеста)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

logger = logging.getLogger(__name__)

LIMIT = 3
CACHE_TTL = 15 * 60
DISMISS_TTL = 7 * 24 * 3600

MHD_WITHIN_DAYS = 3
SLOT_SERVICES_MAX = 5
SLOT_MIN_RUN = 3  # столько свободных стартов подряд завтра — повод для Happy Hour
SLOT_MAX_STEP = timedelta(minutes=60)
GAP_MAX_NIGHTS = 3
GAP_HORIZON_DAYS = 21
REPEAT_WINDOW_DAYS = 60
REPEAT_SCAN = 5  # deal_counts — 3 запроса на акцию: смотрим только последние
EVENT_WINDOW_DAYS = 7
EVENT_FREE_SHARE = 0.4

# Дефолты скидок — владелец меняет их в форме (решение В-8).
MHD_PERCENT_SOON = 50  # 0–1 день до MHD
MHD_PERCENT = 30  # 2–3 дня
SLOT_PERCENT = 20
GAP_PERCENT = 15

ACTIVE = ("active", "scheduled")


@dataclass(frozen=True)
class Suggestion:
    key: str
    rule: str
    icon: str
    text: str
    priority: int
    initial: dict = field(default_factory=dict)
    target: tuple | None = None  # ("product"|"service"|"stay_unit", pk)
    target_rules: dict = field(default_factory=dict)
    action: str = "promo"  # promo | repeat | share
    url: str = ""  # repeat: ?von=…; share: публичная страница события


def _safe(fn):
    try:
        return list(fn())
    except Exception:  # noqa: BLE001 — одно правило не роняет остальные
        logger.warning("today suggestion rule failed", exc_info=True)
        return []


def _module(tenant, key: str) -> bool:
    try:
        return bool(tenant is not None and tenant.is_module_active(key))
    except Exception:  # noqa: BLE001 — стаб тенанта
        return False


def _busy(**target) -> bool:
    from .models import Promotion

    return Promotion.objects.filter(status__in=ACTIVE, **target).exists()


def _base_title(message: str, name: str) -> str:
    """Заголовок черновика — на БАЗОВОМ языке (так пишет ассистент), а не языке кабинета."""
    from django.conf import settings

    with translation.override(settings.LANGUAGE_CODE):
        return _(message) % {"name": name}


def _base_name(value) -> str:
    from django.conf import settings

    return (value or {}).get(settings.LANGUAGE_CODE, "") if isinstance(value, dict) else ""


def _day(value) -> str:
    return date_format(value, "D d.m.")


# --- R1 · MHD -------------------------------------------------------------------------


def _rule_mhd(tenant, today):
    from apps.inventory import services as inventory

    if not inventory.lots_enabled(tenant):  # склад — часть каталога (core); гейт — партии
        return
    seen = set()
    for lot in inventory.expiring_lots(within_days=MHD_WITHIN_DAYS, include_expired=False)[:20]:
        product = lot.product
        if product is None or product.pk in seen or not product.is_active:
            continue
        seen.add(product.pk)
        if _busy(product=product):
            continue
        days = (lot.mhd - today).days
        qty = int(lot.qty_remaining or 0)
        name = product.name_text or str(product)  # подпись карточки — язык кабинета
        base_name = _base_name(product.name) or name  # заголовок черновика — базовый язык
        yield Suggestion(
            key=f"mhd:{lot.pk}",
            rule="mhd",
            icon="⏳",
            text=_("%(name)s läuft am %(date)s ab (%(qty)s Stk.) — Rettungs-Deal?")
            % {"name": name, "date": _day(lot.mhd), "qty": qty},
            priority=100 - days,
            initial={
                "title": base_name,
                "percent": MHD_PERCENT_SOON if days <= 1 else MHD_PERCENT,
                "quantity": qty or None,
                "term": "date",
                "until": lot.mhd,
                "perishable": True,
                "product": product.pk,
            },
            target=("product", product.pk),
        )


# --- R2 · freie Termine morgen ---------------------------------------------------------


def _free_run(starts):
    """Самая длинная серия стартов с шагом ≤ SLOT_MAX_STEP: (первый, последний, длина)."""
    best = (None, None, 0)
    run_start, prev, length = None, None, 0
    for start in starts:
        if prev is not None and start - prev <= SLOT_MAX_STEP:
            length += 1
        else:
            run_start, length = start, 1
        prev = start
        if length > best[2]:
            best = (run_start, start, length)
    return best


def _slot_suggestion(service, tomorrow):
    """(подсказка, длина серии) для одной услуги или (None, 0)."""
    from apps.booking.availability import service_slots

    if _busy(service=service):
        return None, 0
    starts = [timezone.localtime(s) for s in service_slots(service, tomorrow)]
    first, last, length = _free_run(starts)
    if length < SLOT_MIN_RUN:
        return None, 0
    hour_from, hour_to = first.hour, min(last.hour + 1, 24)
    name = service.name_localized()
    return (
        Suggestion(
            key=f"slots:{service.pk}:{tomorrow.isoformat()}",
            rule="slots",
            icon="🕑",
            text=_("Morgen %(start)s–%(end)s Uhr noch frei: %(name)s — Happy Hour?")
            % {"start": hour_from, "end": hour_to, "name": name},
            priority=80,
            initial={
                "title": _base_title(gettext_noop("%(name)s – Happy Hour"), service.name),
                "percent": SLOT_PERCENT,
                "term": "date",
                "until": tomorrow,
            },
            target=("service", service.pk),
            target_rules={
                "weekdays": [tomorrow.weekday()],
                "hour_from": hour_from,
                "hour_to": hour_to,
            },
        ),
        length,
    )


def _rule_slots(tenant, today, *, service_pk=None):
    from apps.booking.models import Service

    if not _module(tenant, "booking"):
        return
    tomorrow = today + timedelta(days=1)
    services = Service.objects.filter(is_active=True).order_by("pk")
    if service_pk is not None:
        try:
            services = services.filter(pk=service_pk)
            services.exists()
        except (ValueError, ValidationError):
            return
    best, best_len = None, 0  # на карточке — одна Happy Hour, по самой длинной серии
    for service in services[:SLOT_SERVICES_MAX]:
        item, length = _slot_suggestion(service, tomorrow)
        if item is not None and length > best_len:
            best, best_len = item, length
    if best is not None:
        yield best


# --- R3 · Lücken zwischen Buchungen -----------------------------------------------------


def _rule_gaps(tenant, today):
    from apps.stays import pricing
    from apps.stays.gaps import short_gaps
    from apps.stays.models import StaySettings, StayUnit

    if not _module(tenant, "stays"):
        return
    units = list(StayUnit.objects.filter(is_active=True).order_by("pk")[:10])
    stay_settings = StaySettings.load()
    seen = set()
    for unit, start, nights in short_gaps(
        units, max_nights=GAP_MAX_NIGHTS, horizon=GAP_HORIZON_DAYS
    ):
        if unit.pk in seen:
            continue
        end = start + timedelta(days=nights)
        # Lücken-Deal уже даёт скидку на эту дыру — скидки не суммируются (max), не дублируем.
        if pricing.gap_discount(unit, start, end, stay_settings, today=today)[0]:
            continue
        if _busy(stay_unit=unit):
            continue
        seen.add(unit.pk)
        name = unit.name_localized()
        yield Suggestion(
            key=f"gap:{unit.pk}:{start.isoformat()}",
            rule="gap",
            icon="🛏",
            text=_("Lücke %(start)s–%(end)s in „%(name)s“ — Last-Minute-Angebot?")
            % {"start": _day(start), "end": _day(end), "name": name},
            priority=70,
            initial={
                "title": _base_title(gettext_noop("%(name)s – Last Minute"), unit.name),
                "percent": GAP_PERCENT,
                "term": "date",
                "until": start,
            },
            target=("stay_unit", unit.pk),
            target_rules={"stay_from": start.isoformat(), "stay_to": start.isoformat()},
        )


# --- R4 · erfolgreiche Aktion wiederholen ------------------------------------------------


def _rule_repeat(tenant, today):
    from django.db.models import Sum
    from django.urls import reverse

    from apps.loyalty.models import Voucher

    from .models import Promotion, PromotionDailyView
    from .price_layer import deal_counts

    now = timezone.now()
    ended = list(
        Promotion.objects.filter(
            status="ended", ends_at__gte=now - timedelta(days=REPEAT_WINDOW_DAYS)
        ).order_by("-ends_at")[:REPEAT_SCAN]
    )
    if not ended:
        return
    views = dict(
        PromotionDailyView.objects.filter(promotion__in=ended)
        .values("promotion")
        .annotate(n=Sum("views"))
        .values_list("promotion", "n")
    )
    redeemed = dict(
        Voucher.objects.filter(promotion__in=ended, used_count__gt=0)
        .values("promotion")
        .annotate(n=Sum("used_count"))
        .values_list("promotion", "n")
    )
    best, best_score = None, 0
    for promo in ended:
        deals = deal_counts(promo)
        score = (views.get(promo.pk) or 0) + 3 * sum(deals.values()) + (redeemed.get(promo.pk) or 0)
        if score > best_score:
            best, best_score = promo, score
    if best is None:
        return
    title = best.title_text
    if Promotion.objects.filter(status__in=ACTIVE, title=best.title).exists():
        return
    by_day: dict[int, int] = {}
    for day, n in best.daily_views.values_list("day", "views"):
        by_day[day.weekday()] = by_day.get(day.weekday(), 0) + n
    if by_day:
        weekday = max(by_day, key=by_day.get)
        some_day = today + timedelta(days=(weekday - today.weekday()) % 7)
        text = _("„%(title)s“ lief am %(weekday)s am besten — wiederholen?") % {
            "title": title,
            "weekday": date_format(some_day, "l"),
        }
    else:
        text = _("„%(title)s“ kam gut an — wiederholen?") % {"title": title}
    yield Suggestion(
        key=f"repeat:{best.pk}",
        rule="repeat",
        icon="↻",
        text=text,
        priority=50,
        action="repeat",
        url=reverse("promotions:promotion-quick") + f"?von={best.pk}",
    )


# --- R5 · Restplätze teilen ------------------------------------------------------------


def _rule_events(tenant, today):
    from django.urls import reverse

    from apps.events.models import Event

    if not _module(tenant, "events"):
        return
    now = timezone.now()
    events = Event.objects.filter(
        status=Event.STATUS_PUBLISHED,
        starts_at__gte=now,
        starts_at__lte=now + timedelta(days=EVENT_WINDOW_DAYS),
        capacity__gt=0,
    ).order_by("starts_at")[:10]
    events = list(events)
    from apps.events.listing import attach_seat_counts

    attach_seat_counts(events)  # проданные места одним запросом, без N+1
    for event in events:
        left = event.seats_left
        if not left or left / event.capacity < EVENT_FREE_SHARE:
            continue
        yield Suggestion(
            key=f"event:{event.pk}",
            rule="event",
            icon="🎟",
            text=_("Noch %(n)s Plätze bei „%(name)s“ am %(date)s — teilen?")
            % {
                "n": left,
                "name": event.title_text,
                "date": _day(timezone.localtime(event.starts_at)),
            },
            priority=60,
            action="share",
            url=reverse("storefront-event", args=[event.pk]),
        )
        return  # одна подсказка «teilen» за раз


RULES = (_rule_mhd, _rule_slots, _rule_gaps, _rule_events, _rule_repeat)


def _schema() -> str:
    return getattr(connection, "schema_name", "") or ""


def _dismiss_key(key: str) -> str:
    return f"today-dismiss:{_schema()}:{key}"


def compute(tenant, *, today=None) -> list[Suggestion]:
    """Все подсказки по приоритету (без кэша и без «Nicht jetzt»)."""
    today = today or timezone.localdate()
    found: list[Suggestion] = []
    for rule in RULES:
        found.extend(_safe(lambda rule=rule: rule(tenant, today)))
    return sorted(found, key=lambda s: -s.priority)


def suggestions(tenant, *, today=None, limit=LIMIT) -> list[Suggestion]:
    """Подсказки для карточки: кэш 15 мин на (схема, день, язык), минус «Nicht jetzt»."""
    today = today or timezone.localdate()
    key = f"today:{_schema()}:{today.isoformat()}:{translation.get_language() or ''}"
    try:
        found = cache.get(key)
    except Exception:  # noqa: BLE001 — кэш недоступен: считаем напрямую
        found = None
    if found is None:
        found = compute(tenant, today=today)
        try:
            cache.set(key, found, CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    try:
        hidden = cache.get_many([_dismiss_key(s.key) for s in found])
    except Exception:  # noqa: BLE001
        hidden = {}
    return [s for s in found if _dismiss_key(s.key) not in hidden][:limit]


_KEY_RE = re.compile(r"^(mhd|slots|gap|repeat|event):[0-9A-Za-z:-]{1,100}$")
_PROMO_RULES = {"mhd": "_rule_mhd", "slots": "_rule_slots", "gap": "_rule_gaps"}


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key or ""))


def resolve(tenant, key: str) -> Suggestion | None:
    """Подсказка по ключу из ссылки — пересчитанная из БД (ссылке не верим).

    Считается только правило из префикса ключа (не все пять)."""
    if not valid_key(key):
        return None
    rule_name = _PROMO_RULES.get(key.split(":", 1)[0])
    if rule_name is None:
        return None
    rule = globals()[rule_name]
    kwargs = {}
    if rule_name == "_rule_slots":
        parts = key.split(":")
        if len(parts) < 3:
            return None
        kwargs["service_pk"] = parts[1]  # именно эта услуга, не «лучшая»
    for item in _safe(lambda: rule(tenant, timezone.localdate(), **kwargs)):
        if item.key == key and item.action == "promo":
            return item
    return None


def dismiss(key: str) -> None:
    if not valid_key(key):
        return
    try:
        cache.set(_dismiss_key(key), 1, DISMISS_TTL)
    except Exception:  # noqa: BLE001
        pass


def card_context(request) -> list[dict]:
    """Карточка «Was heute starten?» для главной кабинета и списка акций.

    Fail-safe: сбой движка = карточки нет, страница живёт."""
    from urllib.parse import urlencode

    from django.urls import reverse

    from apps.core.share_links import share_targets

    tenant = getattr(request, "tenant", None)
    try:
        items = suggestions(tenant)
    except Exception:  # noqa: BLE001
        logger.warning("today card failed", exc_info=True)
        return []
    out = []
    quick = reverse("promotions:promotion-quick")
    for item in items:
        href, share = "", []
        if item.action == "promo":
            href = f"{quick}?{urlencode({'vorschlag': item.key})}"
        elif item.action == "repeat":
            href = item.url
        elif item.action == "share":
            share = share_targets(item.text, request.build_absolute_uri(item.url))
        out.append(
            {"key": item.key, "icon": item.icon, "text": item.text, "href": href, "share": share}
        )
    return out
