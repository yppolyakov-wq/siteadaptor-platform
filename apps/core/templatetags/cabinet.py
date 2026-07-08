"""Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы)."""

from django import template
from django.utils.translation import gettext_lazy as _

from apps.core import modules

register = template.Library()


@register.simple_tag
def nav_task_label(nav_key):
    """AB1: подпись пункта сайдбара в языке задач (nav_key → DE-метка) или "" —
    тогда шаблон берёт фолбэк NavItem.label. Реестр — modules.NAV_TASK_LABELS."""
    return modules.nav_task_label(nav_key or "")


# S1/S2 (упрощение кабинета): под-страницы хаба = tab-bar над контентом. Один пункт
# сайдбара → страница-хаб с табами. Кортеж (url_name, метка, nav_key, module_key):
# активный таб по context["nav"]; module_key (или None) — таб виден только при
# is_module_active(tenant, module_key), None = всегда (под-страница ядра). Расширяется
# по мере сведения хабов (Einstellungen/Marketing/Kunden — след. инкременты).
HUB_TABS = {
    # Sortiment: под-страницы каталога (модуль core → всегда, module_key=None).
    "catalog": (
        ("catalog:product-list", _("Produkte"), "catalog", None),
        ("catalog:category-list", _("Kategorien"), "categories", None),
        ("stock", _("Lager"), "stock", None),
        ("catalog:combo-list", _("Kombi"), "combos", None),
        ("imports:start", _("Import"), "imports", None),
    ),
    # Verkäufe: доска (kanban, core) + продажные списки/календари. Табы продаж
    # гейтятся по своему модулю — Friseur без Übernachtung/Tickets их не покажет.
    "board": (
        ("board", _("Board"), "board", "board"),
        ("orders:order-list", _("Bestellungen"), "orders", "orders"),
        ("booking:calendar", _("Termine"), "booking", "booking"),
        ("stays:calendar", _("Übernachtungen"), "stays", "stays"),
        ("events:list", _("Tickets"), "events", "events"),
        ("jobs:list", _("Aufträge"), "jobs", "jobs"),
    ),
}


@register.inclusion_tag("tenant/_hub_tabs.html", takes_context=True)
def hub_tabs(context, hub):
    """Отрисовать tab-bar хаба `hub` (реестр HUB_TABS), подсветив активный по `nav`.

    Табы с module_key прячутся, если модуль не активен у тенанта (fail-open, если
    request/tenant в контексте нет — например простой тест-рендер без запроса)."""
    cur = context.get("nav")
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    tabs = []
    for u, lbl, k, mod in HUB_TABS.get(hub, ()):
        if mod is not None and tenant is not None and not modules.is_module_active(tenant, mod):
            continue
        tabs.append({"url_name": u, "label": lbl, "nav_key": k, "active": k == cur})
    return {"tabs": tabs}
