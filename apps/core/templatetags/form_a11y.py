"""KA-12 E9.4c: доступность полей форм.

Django 5.1 сам ставит виджету ``aria-invalid="true"`` при ошибке и
``aria-describedby="<auto_id>_helptext"`` при подсказке. Чего он не делает —
не связывает с полем текст ОШИБКИ. Фильтр ``a11y`` дописывает в
``aria-describedby`` id блока ошибок (``<auto_id>_errors``), сохраняя подсказку.
Шаблон обязан отрисовать эти id (подсказка — ``…_helptext``, ошибки — ``…_errors``).

    {% render_field field|a11y class="…" %}
    {{ field|a11y|add_class:"…" }}
"""

from django import template

register = template.Library()


def describedby_ids(bound_field) -> str:
    """id для aria-describedby: подсказка (если есть) + ошибки (если есть)."""
    auto_id = bound_field.auto_id
    if not auto_id or bound_field.is_hidden:
        return ""
    ids = []
    if bound_field.help_text:
        ids.append(f"{auto_id}_helptext")
    if bound_field.errors:
        ids.append(f"{auto_id}_errors")
    return " ".join(ids)


@register.filter
def a11y(bound_field):
    """Связать ошибки поля с виджетом (только когда ошибки есть).

    Без ошибок ничего не трогаем — подсказку Django свяжет сам. Пишем в attrs
    виджета ЭТОГО экземпляра формы (поля формы — глубокие копии), поэтому
    соседние формы не задеваются.
    """
    if not hasattr(bound_field, "field") or not bound_field.errors:
        return bound_field
    # Группы (радио/чекбоксы/MultiWidget): attrs ушли бы в КАЖДЫЙ input — ошибку
    # связывает обёртка <fieldset aria-describedby> в шаблоне.
    if getattr(bound_field.field.widget, "use_fieldset", False):
        return bound_field
    ids = describedby_ids(bound_field)
    if ids:
        bound_field.field.widget.attrs["aria-describedby"] = ids
    return bound_field
