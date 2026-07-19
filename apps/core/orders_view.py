"""ST-5b: представление раздела заказов — Канбан ⇄ Календарь ⇄ Лента.

Хранение: плоский ключ site_config["orders_view"] ∈ {"kanban","calendar","feed"},
presence-minimal (отсутствие = дефолт по архетипу; ТЗ D1: «календарь — услуги,
лента — магазин»). Представления НЕ встраиваются друг в друга — сегмент-контрол
навигирует между существующими страницами хаба «Verkäufe» (board / календарь
booking|stays / список заказов) и персистит выбор.
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


def calendar_url(tenant):
    """URL календарного представления: booking приоритетнее (день/ресурсы),
    иначе stays (occupancy). Нет обоих модулей → "" (календарь недоступен)."""
    for module, url_name in (("booking", "booking:calendar"), ("stays", "stays:calendar")):
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
    """Выбранное владельцем представление (валидное и достижимое), иначе
    архетип-дефолт; недостижимый вариант откатывается на kanban (board есть всегда)."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    view = cfg.get("orders_view")
    if view not in VIEWS:
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
        return "booking:calendar" if tenant.is_module_active("booking") else "stays:calendar"
    return "board"


def switch_options(tenant, active=""):
    """Опции сегмент-контрола (только достижимые представления)."""
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
    return out
