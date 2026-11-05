"""AIS-W W4-0: единый реестр готовности — «что обязательно и что желательно заполнить».

План docs/ais-w4-0-readiness-plan-2026-11-05.md (T-8.32 §3–§4, решения владельца §5.7 плана
AIS-M/AIS-A). Один источник для мастера v4, карточек «Nächster Schritt», экрана «Laden
eröffnen», ИИ-помощника и (за флагом) гейта продажи.

Правила:
* пункт = ключ, направление (пусто — база), уровень `must`/`nice`, проверка, куда вести;
* проверки ленивые и мемоизируются на объекте тенанта (запрос в запросе — один раз);
* модели тенанта читаются ТОЛЬКО в схеме этого тенанта — иначе ответ «unknown» (None), а не
  «не заполнено» (вне схемы нельзя сказать правду);
* ошибка БД → пункт считается выполненным (fail-open: кассу из-за сбоя не закрываем);
* из хрома кабинета реестр НЕ вызывается (замок) — только по месту и в шторке помощника.

Гейт продажи (`sell_allowed`) действует только при `READINESS_SELL_GATE=True`; работающим
магазинам владелец ставит исключение `site_config["readiness"]["exempt"]` командой
`readiness_report --stamp-exempt --apply` (решение владельца: исключение, не закрытие).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

MUST = "must"
NICE = "nice"


@dataclass(frozen=True)
class Item:
    key: str
    direction: str  # "" — база (любой бизнес); иначе ключ apps.core.directions
    level: str
    label: str
    url_name: str
    check: Callable  # (tenant, facts) -> bool | None (None — не можем проверить)
    #: Пункт применим к этому бизнесу (Widerruf — только при доставке и т.п.).
    applies: Callable | None = None


# --- факты (лениво, мемо на тенанте) --------------------------------------------------------


class Facts:
    """Ленивые факты тенанта: каждый считается одним запросом и только при первом обращении."""

    def __init__(self, tenant):
        self.tenant = tenant
        self._cache: dict = {}

    def in_schema(self) -> bool:
        from django.db import connection

        return getattr(connection, "schema_name", None) == self.tenant.schema_name

    def get(self, key: str, compute: Callable):
        if key not in self._cache:
            if not self.in_schema():
                self._cache[key] = None
            else:
                try:
                    self._cache[key] = compute()
                except Exception:  # noqa: BLE001 — fail-open: сбой не закрывает кассу
                    self._cache[key] = True
        return self._cache[key]


def facts_for(tenant) -> Facts:
    cached = getattr(tenant, "_readiness_facts", None)
    if cached is None:
        cached = Facts(tenant)
        try:
            tenant._readiness_facts = cached
        except Exception:  # noqa: BLE001 — неизменяемый тенант — без мемо
            pass
    return cached


def _cfg(tenant) -> dict:
    cfg = getattr(tenant, "site_config", None)
    return cfg if isinstance(cfg, dict) else {}


def _module(tenant, key: str) -> bool:
    try:
        return bool(tenant.is_module_active(key))
    except Exception:  # noqa: BLE001
        return False


# --- проверки ---------------------------------------------------------------------------------


def _contact(t, f) -> bool:
    return bool((t.address or "").strip()) and bool(
        (t.contact_phone or "").strip() or (t.contact_email or "").strip()
    )


def _impressum(t, f):
    from apps.core.lite_cabinet import impressum_missing

    return f.get("impressum", lambda: not impressum_missing(t))


def _email_confirmed(t, f) -> bool:
    return not getattr(t, "email_pending", False)


def _hours(t, f) -> bool:
    return bool(getattr(t, "opening_hours_structured", None) or getattr(t, "opening_hours", ""))


def _home(t, f) -> bool:
    cfg = _cfg(t)
    return bool(cfg.get("hero_title") or cfg.get("hero_image") or cfg.get("gallery"))


def _about(t, f) -> bool:
    cfg = _cfg(t)
    return bool(cfg.get("about_title") or cfg.get("about_text"))


def _priced_product(t, f):
    def q():
        from apps.catalog.models import Product

        return Product.objects.filter(is_active=True, base_price__gt=0).exists()

    return f.get("priced_product", q)


def _agb(t, f):
    def q():
        from apps.core.models import LegalDoc

        texts = LegalDoc.objects.filter(kind="agb").values_list("text", flat=True)
        return any((text or "").strip() for text in texts)

    return f.get("agb", q)


def _prepay_for_delivery(t, f) -> bool:
    """Решение владельца 2026-11-05: при доставке нужен способ оплаты кроме «на месте»."""
    from apps.core import payment_methods

    return any(m != payment_methods.ON_SITE for m in payment_methods.available(t, "order"))


def _food_allergens(t, f):
    def q():
        from apps.catalog.models import Product

        return not Product.objects.filter(is_active=True, allergens=[]).exists()

    return f.get("food_allergens", q)


def _service(t, f):
    def q():
        from apps.booking.models import Service

        return Service.objects.filter(is_active=True).exists()

    return f.get("service", q)


def _booking_hours(t, f):
    if _hours(t, f):
        return True

    def q():
        from apps.booking.models import AvailabilityRule

        return AvailabilityRule.objects.exists()

    return f.get("availability_rules", q)


def _room_with_photo(t, f):
    def q():
        from apps.stays.models import StayUnit

        return (
            StayUnit.objects.filter(is_active=True, price_cents__gt=0, max_guests__gt=0)
            .exclude(images=[])
            .exists()
        )

    return f.get("room_with_photo", q)


def _upcoming_event(t, f):
    def q():
        from django.utils import timezone

        from apps.events.models import Event

        return Event.objects.filter(
            status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
        ).exists()

    return f.get("upcoming_event", q)


def _anfrage_form(t, f) -> bool:
    return bool(_cfg(t).get("anfrage"))


def _selling_goods(t) -> bool:
    return _module(t, "orders")


def _ships(t) -> bool:
    return _selling_goods(t) and bool(getattr(t, "delivery_enabled", False))


def _food(t) -> bool:
    from apps.core.archetypes import FOOD_BUSINESS_TYPES
    from apps.core.directions import MENU_TYPES

    btype = getattr(t, "business_type", "") or ""
    return btype in FOOD_BUSINESS_TYPES or btype in MENU_TYPES


REGISTRY: tuple[Item, ...] = (
    # База: без этого сайт нельзя показать.
    Item("contact", "", MUST, _("Adresse und Telefon oder E-Mail"), "settings", _contact),
    Item("impressum", "", MUST, _("Impressum vollständig"), "legal-docs", _impressum),
    Item("email", "", MUST, _("E-Mail-Adresse bestätigt"), "settings", _email_confirmed),
    Item("hours", "", NICE, _("Öffnungszeiten"), "settings", _hours),
    Item("home", "", NICE, _("Titelbild oder Galerie"), "site-home", _home),
    Item("about", "", NICE, _("Text „Über uns“"), "site-home", _about),
    # Waren: продавать онлайн.
    Item(
        "waren.product",
        "waren",
        MUST,
        _("Mindestens ein Produkt mit Preis"),
        "catalog:product-create",
        _priced_product,
        applies=_selling_goods,
    ),
    Item("waren.agb", "waren", MUST, _("AGB"), "legal-docs", _agb, applies=_selling_goods),
    Item(
        "waren.prepay",
        "waren",
        MUST,
        _("Bei Lieferung: Zahlung per Karte oder Vorkasse"),
        "payment-settings",
        _prepay_for_delivery,
        applies=_ships,
    ),
    Item(
        "waren.allergens",
        "waren",
        NICE,
        _("Allergene bei allen Gerichten angegeben"),
        "catalog:product-create",
        _food_allergens,
        applies=_food,
    ),
    # Termine / Tisch.
    Item(
        "termine.service",
        "termine",
        MUST,
        _("Mindestens eine Leistung"),
        "booking:services",
        _service,
    ),
    Item(
        "termine.hours",
        "termine",
        MUST,
        _("Öffnungszeiten oder Zeiten der Mitarbeiter"),
        "settings",
        _booking_hours,
    ),
    Item(
        "tisch.hours",
        "tisch",
        MUST,
        _("Öffnungszeiten oder Zeiten der Tische"),
        "settings",
        _booking_hours,
    ),
    # Zimmer.
    Item(
        "zimmer.room",
        "zimmer",
        MUST,
        _("Mindestens ein Zimmer mit Preis, Gästezahl und Foto"),
        "stays:unit-new",
        _room_with_photo,
    ),
    # Tickets.
    Item(
        "tickets.event",
        "tickets",
        MUST,
        _("Mindestens eine kommende Veranstaltung"),
        "events:list",
        _upcoming_event,
    ),
    # Anfragen.
    Item(
        "anfragen.form",
        "anfragen",
        NICE,
        _("Anfrageformular angepasst"),
        "ablaeufe",
        _anfrage_form,
    ),
)
_BY_KEY = {item.key: item for item in REGISTRY}


# --- API ---------------------------------------------------------------------------------------


def _url(item: Item) -> str:
    try:
        return reverse(item.url_name)
    except NoReverseMatch:
        return ""


def _active_direction_keys(tenant) -> set[str]:
    from apps.core import directions

    try:
        return {d.key for d in directions.active(tenant)}
    except Exception:  # noqa: BLE001
        return set()


def items_for(tenant, *, direction: str | None = None, level: str | None = None) -> list[dict]:
    """Пункты, применимые к бизнесу: база + активные направления (или одно указанное).

    Строка: key, label, level, direction, done (True/False/None), url.
    """
    facts = facts_for(tenant)
    wanted = _active_direction_keys(tenant) if direction is None else {direction}
    rows = []
    for item in REGISTRY:
        if item.direction and item.direction not in wanted:
            continue
        if level and item.level != level:
            continue
        if item.applies is not None and not item.applies(tenant):
            continue
        rows.append(
            {
                "key": item.key,
                "label": item.label,
                "level": item.level,
                "direction": item.direction,
                "done": item.check(tenant, facts),
                "url": _url(item),
            }
        )
    return rows


def missing(tenant, *, direction: str | None = None, level: str | None = MUST) -> list[dict]:
    """Невыполненные пункты (unknown — None — не считаем невыполненными)."""
    return [r for r in items_for(tenant, direction=direction, level=level) if r["done"] is False]


def is_done(tenant, key: str) -> bool | None:
    item = _BY_KEY.get(key)
    if item is None:
        return None
    return item.check(tenant, facts_for(tenant))


def sell_ready(tenant, direction: str) -> bool:
    """База (обязательное) + обязательное направления выполнены."""
    base = [r for r in missing(tenant, direction="") if not r["direction"]]
    own = [r for r in missing(tenant, direction=direction) if r["direction"] == direction]
    return not base and not own


def is_exempt(tenant) -> bool:
    block = _cfg(tenant).get("readiness")
    return bool(isinstance(block, dict) and block.get("exempt"))


def sell_allowed(tenant, direction: str) -> bool:
    """Гейт продажи: при выключенном флаге — всегда да (поведение прежнее)."""
    if not getattr(settings, "READINESS_SELL_GATE", False):
        return True
    if getattr(tenant, "is_demo", False) or is_exempt(tenant):
        return True
    return sell_ready(tenant, direction)
