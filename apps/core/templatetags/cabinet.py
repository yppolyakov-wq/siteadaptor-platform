"""Шаблонные теги кабинета (AB1 анти-Битрикс: язык задач в навигации)."""

from django import template

from apps.core import modules

register = template.Library()


@register.simple_tag
def nav_task_label(nav_key):
    """AB1: подпись пункта сайдбара в языке задач (nav_key → DE-метка) или "" —
    тогда шаблон берёт фолбэк NavItem.label. Реестр — modules.NAV_TASK_LABELS."""
    return modules.nav_task_label(nav_key or "")
