"""AIS-M M-0: направления продаж — единственный ответ на «как продаёт этот бизнес».

План docs/ais-modules-directions-assistant-plan-2026-11-05.md (§1.2, §5.1 п.1–2).

Направление — это способ продажи (Waren, Termine, Tisch, Zimmer, Tickets, Anfragen) или
показа (Speisekarte). Оно НЕ равно модулю: `catalog` — core у всех, `booking` обслуживает и
мастеров, и столы, `jobs` есть в лёгком пакете ради заявок по акции. Поэтому у каждого
направления свой предикат `active_when` — по типу, модулям и данным.

Здесь же — стартовый набор направлений по типу бизнеса (для экрана «Richtungen &
Funktionen» и мастера v4, M-1). Режим «zeigen/verkaufen» по направлению появится в M-1
(хранение в site_config); M-0 меняет только место, где вычисляется ответ, — поведение
меню прежнее (паритет `nav_registry.direction_active`).

Правило: вычислять направление вне этого модуля нельзя (замок `test_directions`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

#: Типы, у которых Waren есть из коробки (KA-12 E8.1). werkstatt — Teile с остатком (S6b).
WAREN_TYPES: tuple[str, ...] = (
    "bakery",
    "butcher",
    "grocery",
    "retail",
    "clothing",
    "online_shop",
    "werkstatt",
)
#: Бронь стола, а не запись к мастеру (столы/комбинации/Tischplan, GA-3…7).
TABLE_TYPES: tuple[str, ...] = ("restaurant", "cafe")
#: Speisekarte — меню как контент (без склада и доставки).
MENU_TYPES: tuple[str, ...] = ("restaurant", "cafe", "catering")


def _module(tenant, key: str) -> bool:
    from apps.core.modules import is_module_active

    return is_module_active(tenant, key)


def _btype(tenant) -> str:
    return getattr(tenant, "business_type", "") or ""


def _has_products(tenant) -> bool:
    """Есть ли ассортимент (товар или хотя бы категория). Мемо на тенанте — зовётся хромом."""
    cached = getattr(tenant, "_nav_has_products", None)
    if cached is None:
        try:
            from apps.catalog.models import Category, Product

            # Категории без товаров — тоже знак: владелец начал заводить ассортимент.
            cached = Product.objects.filter(is_active=True).exists() or Category.objects.exists()
        except Exception:  # noqa: BLE001 — хром не падает из-за гейта
            cached = True
        try:
            tenant._nav_has_products = cached
        except Exception:  # noqa: BLE001 — неизменяемый тенант (namespace) — без кэша
            pass
    return cached


def _waren(tenant) -> bool:
    return _btype(tenant) in WAREN_TYPES or _module(tenant, "orders") or _has_products(tenant)


def _speisekarte(tenant) -> bool:
    return _btype(tenant) in MENU_TYPES


def _termine(tenant) -> bool:
    return _module(tenant, "booking") and _btype(tenant) not in TABLE_TYPES


def _tisch(tenant) -> bool:
    return _module(tenant, "booking") and _btype(tenant) in TABLE_TYPES


def _zimmer(tenant) -> bool:
    return _module(tenant, "stays")


def _tickets(tenant) -> bool:
    return _module(tenant, "events")


def _anfragen(tenant) -> bool:
    # В лёгком пакете jobs держит заявки по акции (T-8.2) — это не направление продаж.
    if not _module(tenant, "jobs"):
        return False
    from apps.core import packages

    try:
        lite = packages.package_of(tenant).lite
    except Exception:  # noqa: BLE001 — fail-open: полный бизнес не теряет направление
        lite = False
    return not lite or _btype(tenant) in DEFAULT_FOR_TYPE_KEYS.get("anfragen", ())


@dataclass(frozen=True)
class Direction:
    key: str
    label: str
    blurb: str
    icon: str
    #: Модули, которые направление включает (M-1: включить направление = эти модули).
    modules: tuple[str, ...]
    active_when: Callable


REGISTRY: tuple[Direction, ...] = (
    Direction(
        "waren",
        _("Waren"),
        _("Produkte zum Abholen oder Liefern."),
        "🛍️",
        ("orders",),
        _waren,
    ),
    Direction(
        "speisekarte",
        _("Speisekarte"),
        _("Gerichte und Getränke zeigen."),
        "🍽️",
        (),
        _speisekarte,
    ),
    Direction(
        "termine",
        _("Termine"),
        _("Kunden buchen eine Leistung zu einer Uhrzeit."),
        "📅",
        ("booking",),
        _termine,
    ),
    Direction(
        "tisch",
        _("Tisch reservieren"),
        _("Gäste reservieren einen Tisch."),
        "🪑",
        ("booking",),
        _tisch,
    ),
    Direction(
        "zimmer",
        _("Zimmer"),
        _("Gäste buchen Übernachtungen."),
        "🛏️",
        ("stays",),
        _zimmer,
    ),
    Direction(
        "tickets",
        _("Tickets"),
        _("Plätze für Veranstaltungen und Touren."),
        "🎟️",
        ("events",),
        _tickets,
    ),
    Direction(
        "anfragen",
        _("Anfragen"),
        _("Kunden fragen an, Sie schicken ein Angebot."),
        "📝",
        ("jobs",),
        _anfragen,
    ),
)
_BY_KEY = {d.key: d for d in REGISTRY}

#: Стартовые направления по типу бизнеса (план §1.2 + правки ревью §5.3). `other` — нет:
#: направление выбирается в мастере («Wie verkaufen Sie?»).
DEFAULT_FOR: dict[str, tuple[str, ...]] = {
    "bakery": ("waren",),
    "butcher": ("waren",),
    "grocery": ("waren",),
    "retail": ("waren",),
    "clothing": ("waren",),
    "online_shop": ("waren",),
    "cafe": ("speisekarte", "tisch"),
    "restaurant": ("speisekarte", "tisch"),
    "catering": ("speisekarte", "anfragen"),
    "friseur": ("termine",),
    "werkstatt": ("termine", "anfragen", "waren"),
    "handwerker": ("anfragen",),
    "hotel": ("zimmer",),
    "events": ("tickets",),
    "tour_operator": ("tickets", "anfragen"),
    "other": (),
}
#: Обратная карта «направление → типы по умолчанию».
DEFAULT_FOR_TYPE_KEYS: dict[str, tuple[str, ...]] = {
    d.key: tuple(t for t, keys in DEFAULT_FOR.items() if d.key in keys) for d in REGISTRY
}


def get(key: str) -> Direction | None:
    return _BY_KEY.get(key)


def is_active(tenant, key: str) -> bool:
    """Активно ли направление. Неизвестный ключ — False; без тенанта — True (fail-open хрома)."""
    if tenant is None:
        return True
    direction = _BY_KEY.get(key)
    return bool(direction and direction.active_when(tenant))


def active(tenant) -> list[Direction]:
    """Активные направления тенанта в порядке реестра."""
    return [d for d in REGISTRY if d.active_when(tenant)]


def defaults_for(business_type: str) -> tuple[str, ...]:
    """Стартовые направления типа (пусто — спросить в мастере)."""
    return DEFAULT_FOR.get(business_type or "", ())


#: AIS-M M-1: режимы направления (W4-5 «Verkauf öffnen»; в M-1 UI их не шлёт).
MODES = ("zeigen", "verkaufen")


def choices_for(tenant) -> list[Direction]:
    """Направления, осмысленные для типа бизнеса (меню — у гастро, столы — у ресторана/кафе).

    Единственный источник для мастера «Wie verkaufen Sie?» и экрана «Richtungen & Funktionen»."""
    btype = (tenant.business_type if tenant is not None else "") or ""
    out = []
    for d in REGISTRY:
        if d.key == "speisekarte" and btype not in MENU_TYPES:
            continue
        if d.key == "tisch" and btype not in TABLE_TYPES:
            continue
        if d.key == "termine" and btype in TABLE_TYPES:
            continue
        out.append(d)
    return out
