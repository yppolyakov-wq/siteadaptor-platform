"""SR-3: шаблонные фильтры ограниченного rich-text (описания).

`rich_text` санитайзит ПРИ РЕНДЕРЕ (fail-closed к легаси-данным и обходным
записям — хранение уже чистит форма, это второй рубеж) и только затем помечает
safe. `is_rich` выбирает ветку рендера: плоский текст остаётся на прежнем
whitespace-pre-line (в HTML его переносы незначимы)."""

from django import template
from django.utils.safestring import mark_safe

from apps.core import richtext

register = template.Library()


@register.filter(name="rich_text")
def rich_text(value):
    return mark_safe(richtext.sanitize(value))  # noqa: S308 — санитайз строкой выше


@register.filter(name="is_rich")
def is_rich(value):
    return richtext.is_rich(value)
