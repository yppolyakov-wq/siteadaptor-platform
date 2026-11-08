"""Пометка «KI-Funktion · USA» у ИИ-кнопок: `{% load ai_notice %}{% ai_notice "task" %}`."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def ai_notice(*tasks: str, audience: str = "owner"):
    """FB-15: несколько задач → ОДНА плашка (текст у всех задач один). Рисуется, если
    хотя бы одна из задач включена и уходит из ЕС; пустые имена задач пропускаются."""
    from apps.ai import disclosure

    text = ""
    for task in tasks:
        if task:
            text = disclosure.notice(task, audience=audience)
            if text:
                break
    if not text:
        return ""
    return format_html('<p class="text-xs text-gray-500" data-ai-notice>ⓘ {}</p>', text)
