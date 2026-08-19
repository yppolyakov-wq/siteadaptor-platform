"""ST-5b → W10-1: архетип-дефолт представления продаж (для главной кабинета).

Сегмент-контрол Канбан⇄Календарь⇄Лента УДАЛЁН (W10-1, аудит 2026-08-05: две
несовместимые модели переключения видов) — легаси-страницы несут только мостик
на единую страницу продаж; выбор вида живёт на Verkäufe (persist `sales_views`,
sales_page). Здесь остаются: архетип-дефолт `resolve_view` (главная кабинета:
отель → Belegungsplan-вид) и `entry_url_name` (якорь/плитка «Verkäufe»).
Прежний персист site_config["orders_view"] удалён ещё в v1 ST-5b.
"""

from django.urls import NoReverseMatch, reverse


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
    # X2b: легаси-доска /dashboard/board/ снесена — канбан живёт вкладкой
    # единой страницы продаж. Раньше отсюда приходил NoReverseMatch-риск для
    # архетипов events/jobs (вызывается с ГЛАВНОЙ, views.dashboard).
    return reverse("verkaeufe")


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
    return reverse(entry_url_name(tenant))


def entry_url_name(tenant):
    """Имя маршрута входа «Verkäufe» — единая страница продаж (W-CL: классик-
    ветка с архетип-дефолтом снесена; вкладка/вид внутри — sales_page)."""
    return "verkaeufe"
