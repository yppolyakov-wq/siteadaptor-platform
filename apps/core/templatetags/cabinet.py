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


# S1 (упрощение кабинета): под-страницы хаба = tab-bar над контентом. Один пункт
# сайдбара → страница-хаб с табами (5→1). (url_name, метка, nav_key); активный таб
# по context["nav"]. Расширяется по мере сведения хабов (Verkäufe/Einstellungen/…).
HUB_TABS = {
    "catalog": (
        ("catalog:product-list", _("Produkte"), "catalog"),
        ("catalog:category-list", _("Kategorien"), "categories"),
        ("stock", _("Lager"), "stock"),
        ("catalog:combo-list", _("Kombi"), "combos"),
        ("imports:start", _("Import"), "imports"),
    ),
}


@register.inclusion_tag("tenant/_hub_tabs.html", takes_context=True)
def hub_tabs(context, hub):
    """Отрисовать tab-bar хаба `hub` (реестр HUB_TABS), подсветив активный по `nav`."""
    cur = context.get("nav")
    tabs = [
        {"url_name": u, "label": lbl, "nav_key": k, "active": k == cur}
        for u, lbl, k in HUB_TABS.get(hub, ())
    ]
    return {"tabs": tabs}
