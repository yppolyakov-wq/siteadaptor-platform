"""Пометка «KI-Funktion · USA» у ИИ-кнопок: `{% load ai_notice %}{% ai_notice "task" %}`."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def ai_notice(task: str, audience: str = "owner"):
    from apps.ai import disclosure

    text = disclosure.notice(task, audience=audience)
    if not text:
        return ""
    return format_html('<p class="text-xs text-gray-500" data-ai-notice>ⓘ {}</p>', text)
