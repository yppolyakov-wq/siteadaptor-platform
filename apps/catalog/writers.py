"""AIS A-4a: писатели «создать» поверх форм экранов кабинета.

Ассистент (и мастер) создаёт товар/категорию ровно так, как их создал бы владелец на экране:
та же форма (i18n, санитайз, НДС по умолчанию, slug, сентинелы), тот же пост-шаг (склад-леджер).
Данные = значения ПУСТОЙ формы создания (её initial) + поля пакета поверх: частичный POST
обнулил бы неотправленные флажки (класс W0 — товар создался бы скрытым). Ошибки формы —
`WriteError(errors)`, ничего не создано.
"""

from __future__ import annotations

from django import forms
from django.http import QueryDict


class WriteError(Exception):
    def __init__(self, errors: dict):
        super().__init__("invalid")
        self.errors = errors


def blank_data(form) -> QueryDict:
    """POST, который отправила бы пустая форма создания (initial всех полей)."""
    data = QueryDict(mutable=True)
    for name, field in form.fields.items():
        value = form[name].value()
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = "on"
            continue
        if value is None:
            continue
        if isinstance(value, list | tuple):
            data.setlist(name, [str(v) for v in value])
        else:
            data[name] = str(value)
    return data


def _bound(form_class, tenant, fields: dict, **kwargs):
    data = blank_data(form_class(tenant=tenant, **kwargs))
    blank = form_class(tenant=tenant, **kwargs)
    for name, value in (fields or {}).items():
        if name not in blank.fields:
            continue  # только поля формы: лишнее из пакета не проходит
        if isinstance(blank.fields[name], forms.BooleanField):
            if value in (True, "on", "1", "true"):
                data[name] = "on"
            else:
                data.pop(name, None)
        else:
            data[name] = "" if value is None else str(value)
    return form_class(data, tenant=tenant, **kwargs)


def after_product_created(product, actor: str = "") -> None:
    """Пост-шаг экрана создания товара (T1): стартовый остаток — в склад-леджер."""
    from apps.inventory.services import log_catalog_change

    log_catalog_change(product=product, old=None, new=product.stock_quantity, actor=actor)


def create_product(tenant, fields: dict, actor: str = ""):
    from apps.catalog.forms import ProductForm

    form = _bound(ProductForm, tenant, fields)
    if not form.is_valid():
        raise WriteError(form.errors.get_json_data())
    product = form.save()
    after_product_created(product, actor)
    return product


def create_category(tenant, fields: dict):
    from apps.catalog.forms import CategoryForm

    form = _bound(CategoryForm, tenant, fields)
    if not form.is_valid():
        raise WriteError(form.errors.get_json_data())
    return form.save()
