"""ST-5b: представление раздела заказов — Канбан ⇄ Календарь ⇄ Лента.

Фидбэк владельца 2026-07-28: маппинг ФИКСИРОВАННЫЙ — «Verkäufe» всегда
открывает архетип-дефолт (отель → Belegungsplan, магазин → лента, прочее →
канбан), сегмент-контрол — чистая навигация между страницами хаба (Board /
календарь booking|stays / список заказов) БЕЗ персиста выбора; третьим пунктом
— «＋ Buchung/Termin» (якорь на форму создания в календаре). Прежний персист
site_config["orders_view"] удалён (v1 ST-5b), ключ больше не нормализуется.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

VIEWS = ("kanban", "calendar", "feed")

_LABELS = {
    "kanban": _("Board"),
    "calendar": _("Kalender"),
    "feed": _("Liste"),
}
_ICONS = {"kanban": "🧮", "calendar": "📅", "feed": "📃"}


def _calendar_order(tenant):
    """Порядок календарей по PRIMARY-архетипу (фикс 2026-07-28: у отеля активны
    ОБА модуля — «Verkäufe» обязан открывать Belegungsplan, не booking)."""
    from apps.core import archetypes

    pairs = [("booking", "booking:calendar"), ("stays", "stays:calendar")]
    if archetypes.primary_module(tenant) == "stays":
        pairs.reverse()
    return pairs


def calendar_url(tenant):
    """URL календарного представления: календарь primary-модуля первым (отель →
    stays/Belegungsplan, услуги → booking). Нет обоих → "" (недоступен)."""
    for module, url_name in _calendar_order(tenant):
        if tenant.is_module_active(module):
            try:
                return reverse(url_name)
            except NoReverseMatch:  # pragma: no cover — модуль без маршрута
                continue
    return ""


def _view_url(tenant, view):
    if view == "calendar":
        return calendar_url(tenant)
    if view == "feed":
        try:
            return reverse("orders:order-list") if tenant.is_module_active("orders") else ""
        except NoReverseMatch:  # pragma: no cover
            return ""
    return reverse("board")


def default_view(tenant):
    """Архетип-дефолт по primary_module: услуги/отель → календарь, магазин →
    лента, прочее (события/заявки/микс) → канбан."""
    from apps.core import archetypes

    primary = archetypes.primary_module(tenant)
    if primary in ("booking", "stays"):
        return "calendar"
    if primary == "catalog":
        return "feed"
    return "kanban"


def resolve_view(tenant):
    """Архетип-дефолт (фиксированный маппинг, фидбэк 2026-07-28); недостижимый
    вариант откатывается на kanban (board есть всегда)."""
    view = default_view(tenant)
    if not _view_url(tenant, view):
        return "kanban"
    return view


def entry_url(tenant):
    """URL «раздела заказов» для точек входа (хаб-плитка Bestellungen)."""
    return _view_url(tenant, resolve_view(tenant)) or reverse("board")


def entry_url_name(tenant):
    """То же — именем маршрута (для плиток, резолвящих {% url %}); resolve_view
    гарантирует достижимость (calendar ⇒ booking|stays активен)."""
    view = resolve_view(tenant)
    if view == "feed":
        return "orders:order-list"
    if view == "calendar":
        for module, url_name in _calendar_order(tenant):
            if tenant.is_module_active(module):
                return url_name
    return "board"


def create_option(tenant, active=False):
    """Третий пункт сегмента (фидбэк 2026-07-28): «＋ Buchung» — ОТДЕЛЬНАЯ
    страница только с формой (stays); для booking — якорь на форму календаря.
    Нет календарного модуля → None."""
    targets = {
        "stays": ("stays:stay-new", "", _("New booking")),
        "booking": ("booking:calendar", "#neu", _("New appointment")),
    }
    for module, _url in _calendar_order(tenant):
        url_name, anchor, label = targets[module]
        if tenant.is_module_active(module):
            try:
                return {
                    "view": "create",
                    "label": label,
                    "icon": "＋",
                    "url": reverse(url_name) + anchor,
                    "active": active,
                }
            except NoReverseMatch:  # pragma: no cover — модуль без маршрута
                continue
    return None


def switch_options(tenant, active=""):
    """Опции сегмент-контрола (только достижимые представления) + «＋ Buchung»
    третьим пунктом. Чистая навигация — выбор больше не персистится."""
    out = []
    for view in VIEWS:
        url = _view_url(tenant, view)
        if not url:
            continue
        out.append(
            {
                "view": view,
                "label": _LABELS[view],
                "icon": _ICONS[view],
                "url": url,
                "active": view == active,
            }
        )
    # Фидбэк 2026-07-30 (отель): активны ОБА календарных модуля — второй
    # календарь (Termine услуг у отеля / Belegungsplan у услуг с номерами)
    # добавляется отдельным пунктом, иначе booking-календарь недостижим из
    # хаба «Verkäufe» (ST-5b показывал только primary).
    if any(o["view"] == "calendar" for o in out):
        order = _calendar_order(tenant)
        if len(order) > 1 and tenant.is_module_active(order[1][0]):
            try:
                alt_url = reverse(order[1][1])
            except NoReverseMatch:  # pragma: no cover — модуль без маршрута
                alt_url = ""
            if alt_url:
                out.append(
                    {
                        "view": "calendar_alt",
                        "label": _("Termine") if order[1][0] == "booking" else _("Belegungsplan"),
                        "icon": "📅",
                        "url": alt_url,
                        "active": active == "calendar_alt",
                    }
                )
    create = create_option(tenant, active=(active == "create"))
    if create:
        out.append(create)
    return out
