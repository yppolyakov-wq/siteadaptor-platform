"""FB-33 M3-5a: окно блока в шаблонах — форма, которую применяют кнопки вкладок, и контракт
полей вкладки «Texte» (`apps/core/block_window.py`)."""

from django import template

from apps.core import block_window

register = template.Library()


@register.filter
def bw_field(field, selected):
    """{max, max_hint, example, hint, described} поля формы «fields»."""
    return block_window.field_meta(selected, field)
