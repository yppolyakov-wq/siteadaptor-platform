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


@register.filter
def i18n_loc(bound_field):
    """E9.10: язык поля перевода (`OverlayI18nFormMixin`) — для `data-i18n-loc`.

    Пусто у обычных полей: их выпадашка языка не скрывает."""
    field = getattr(bound_field, "field", None)
    return getattr(field, "i18n_loc", "") or ""


@register.filter
def i18n_siblings(bound_field):
    """E9.10: поля переводов этого базового поля (`OverlayI18nFormMixin`).

    Партиал поля (`catalog/_pf_field.html`) рисует их сразу под базовым, каждое —
    в своей языковой группе: формы, которые перебирают поля по имени, получают
    переводы без правки каждого места."""
    field = getattr(bound_field, "field", None)
    form = getattr(bound_field, "form", None)
    names = getattr(field, "i18n_siblings", None) or []
    if form is None:
        return []
    return [form[n] for n in names if n in form.fields]
