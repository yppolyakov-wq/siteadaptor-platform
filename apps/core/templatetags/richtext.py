"""SR-3: шаблонные фильтры ограниченного rich-text (описания).

`rich_text` санитайзит ПРИ РЕНДЕРЕ (fail-closed к легаси-данным и обходным
записям — хранение уже чистит форма, это второй рубеж) и только затем помечает
safe. `is_rich` выбирает ветку рендера: плоский текст остаётся на прежнем
whitespace-pre-line (в HTML его переносы незначимы)."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.core import richtext

register = template.Library()


@register.filter(name="rich_text")
def rich_text(value):
    return mark_safe(richtext.sanitize(value))  # noqa: S308 — санитайз строкой выше


@register.filter(name="is_rich")
def is_rich(value):
    return richtext.is_rich(value)


@register.simple_tag
def rich_block(text, css="", edit_model="", edit_pk="", edit_field="", mode=""):
    """M21.8: показ длинного текста владельца. С редактора (HTML) — санитайзнутый
    ``<div class="… rich-text">``; легаси-плоский — прежний ``whitespace-pre-line``
    (переносы строк видны). Пустой текст — пусто. ``mode="page"`` — правила своих
    страниц (заголовки, цитата, наши картинки) — для правовых текстов.

    ``edit_*`` — правка прямо на канве Студии (`data-edit-*`) только у ПЛОСКОГО текста:
    инлайн-правка пишет текст и снесла бы форматирование — его правят в форме."""
    text = text or ""
    if not str(text).strip():
        # Пустое поле с правкой на канве: якорь остаётся (дописать описание инлайн).
        if edit_model and edit_field:
            return format_html(
                '<div class="{}" data-edit-model="{}" data-edit-pk="{}" data-edit-field="{}"></div>',
                f"{css} whitespace-pre-line".strip(),
                edit_model,
                edit_pk,
                edit_field,
            )
        return ""
    if richtext.is_rich(text):
        return format_html(
            '<div class="{}">{}</div>',
            f"{css} rich-text".strip(),
            mark_safe(  # noqa: S308 — санитайз здесь же
                richtext.sanitize_page(text) if mode == "page" else richtext.sanitize(text)
            ),
        )
    edit = (
        format_html(
            ' data-edit-model="{}" data-edit-pk="{}" data-edit-field="{}"',
            edit_model,
            edit_pk,
            edit_field,
        )
        if edit_model and edit_field
        else ""
    )
    return format_html(
        '<div class="{}"{}>{}</div>', f"{css} whitespace-pre-line".strip(), edit, text
    )
