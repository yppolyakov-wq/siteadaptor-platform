"""Единая страница продаж «Verkäufe» — вкладки по kind + виды (2026-08-03).

Решения владельца (план `docs/unified-sales-page-plan-2026-08-03.md §4`):
вкладки (не стек); полные виды, неактивные вкладки не грузятся (переключение —
обычная навигация `?tab=`); первая вкладка = kind primary-модуля и видна
ВСЕГДА, прочие — только при наличии продаж (`transactions.kinds_with_sales`);
`reservation` остаётся в Marketing и сюда не попадает НИКОГДА — кроме
aktionsmarkt-подобных тенантов, где promotions и есть primary-модуль (тогда
секция резервов появляется сама по правилу primary).

Дефолтный вид зависит от АРХЕТИПА, не от kind (рыночная норма: салону —
календарь, Handwerker'у — пайплайн, магазину — список; план §1).
"""

from django.utils.translation import gettext_lazy as _

from . import archetypes, transactions

# Модуль → kind сделки. `_PRIORITY` архетипов оперирует модулями; продажи
# каталога живут в модуле orders (catalog в _PRIORITY — это ОН).
_MODULE_KIND = {
    "events": "ticket",
    "stays": "stay",
    "booking": "booking",
    "jobs": "job",
    "catalog": "order",
    "promotions": "reservation",
}

# kind → доступные виды по порядку отображения. `kalender` есть только там, где
# существует календарный движок (stay: Belegungsplan, booking: Tagesplan,
# order: Auftragsbuch по дате выдачи — V3).
KIND_VIEWS = {
    "stay": ("kalender", "board", "liste"),
    "booking": ("kalender", "board", "liste"),
    "order": ("board", "liste", "kalender"),
    "job": ("board", "liste"),
    "ticket": ("liste", "board"),
    "reservation": ("liste", "board"),
}

VIEW_LABELS = {
    "kalender": _("Kalender"),
    "board": _("Board"),
    "liste": _("Liste"),
}
VIEW_ICONS = {"kalender": "📅", "board": "🧮", "liste": "📃"}

# Архетипный дефолт вида на kind (план §3.3/§3.5): у kind primary-модуля —
# рыночная норма архетипа; у вторичных — собственная норма kind.
_KIND_DEFAULT = {
    "stay": "kalender",
    "booking": "kalender",
    "order": "liste",
    "job": "board",
    "ticket": "liste",
    "reservation": "liste",
}
# Точечные overrides: (business_type, kind) → вид. Гастро-C&C живёт очередью
# (KDS-паттерн), ритейл-заказы — списком.
_ARCHETYPE_DEFAULT = {
    ("restaurant", "order"): "board",
    ("cafe", "order"): "board",
}


def default_view(tenant, kind: str) -> str:
    view = _ARCHETYPE_DEFAULT.get((getattr(tenant, "business_type", ""), kind))
    return view or _KIND_DEFAULT.get(kind, "board")


def visible_kinds(tenant) -> list[str]:
    """Вкладки страницы: primary-kind всегда первым, дальше — kind'ы с
    продажами в порядке `_PRIORITY`. reservation — только как primary (§4.4)."""
    primary = _MODULE_KIND.get(archetypes.primary_module(tenant))
    with_sales = transactions.kinds_with_sales(tenant)
    out = []
    if primary:
        out.append(primary)
    for module in archetypes._PRIORITY:
        kind = _MODULE_KIND[module]
        if kind in out or kind not in with_sales:
            continue
        if kind == "reservation":  # решение владельца: резервы живут в Marketing
            continue
        out.append(kind)
    return out


def resolve_view(tenant, kind: str, requested: str = "") -> str:
    """Вид вкладки: явный `?view=` → сохранённый выбор → архетипный дефолт.
    Недоступный для kind вид молча падает на первый доступный."""
    allowed = KIND_VIEWS.get(kind, ("board",))
    saved = (tenant.site_config or {}).get("sales_views", {})
    for candidate in (
        requested,
        saved.get(kind) if isinstance(saved, dict) else "",
        default_view(tenant, kind),
    ):
        if candidate in allowed:
            return candidate
    return allowed[0]


def tab_descriptors(tenant, active_kind: str) -> list[dict]:
    return [
        {
            "kind": kind,
            "label": transactions.KIND_LABEL.get(kind, kind),
            "active": kind == active_kind,
        }
        for kind in visible_kinds(tenant)
    ]


def view_descriptors(tenant, kind: str, active_view: str) -> list[dict]:
    return [
        {
            "view": view,
            "label": VIEW_LABELS[view],
            "icon": VIEW_ICONS[view],
            "active": view == active_view,
        }
        for view in KIND_VIEWS.get(kind, ("board",))
    ]
