"""FB-24b/c: сервис типов опций магазина — единственный писатель OptionType/OptionValue/
VariantOption и осей товара (`Product.option_axes`).

Экран «Sortiment › Optionen» и генератор вариантов зовут ТОЛЬКО эти функции; гарантии
(лимиты, уникальность, «стандартный тип не переименовывается в чужой код») — здесь.
"""

from __future__ import annotations

import re

from django.db import transaction
from django.utils.text import slugify

from apps.catalog import option_types as reg
from apps.catalog.models import OptionType, OptionValue, ProductVariant, VariantOption

#: Оси товара без явного выбора — прежнее поведение M4-A.
DEFAULT_AXES = ["size", "color"]
_VALUE_MAX = 60


def shop_types(active_only: bool = True) -> list[OptionType]:
    qs = OptionType.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs.order_by("sort_order", "id"))


def available_codes() -> set[str]:
    """Коды, которые можно выбрать осью товара: размер/цвет всегда + активные типы."""
    return {
        *reg.FIELD_BACKED,
        *OptionType.objects.filter(is_active=True).values_list("code", flat=True),
    }


def product_axes(product) -> list[str]:
    """Оси товара по порядку. Пусто/устарело → размер и цвет (как до FB-24)."""
    axes = reg.clean_axes(product.option_axes, available_codes())
    return axes or list(DEFAULT_AXES)


def set_product_axes(product, codes) -> list[str]:
    axes = reg.clean_axes(codes, available_codes())
    product.option_axes = axes
    product.save(update_fields=["option_axes", "updated_at"])
    return axes


@transaction.atomic
def enable_standard(code: str) -> OptionType | None:
    """Включить стандартный тип магазина (идемпотентно)."""
    if code not in reg.STANDARD:
        return None
    obj, created = OptionType.objects.get_or_create(
        code=code,
        defaults={"standard": code, "sort_order": OptionType.objects.count()},
    )
    if not created and not obj.is_active:
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
    return obj


def _free_code(name: str) -> str:
    base = (slugify(name) or "option")[:32]
    if base in reg.STANDARD:
        base = f"{base}-eigen"
    code, n = base, 2
    while OptionType.objects.filter(code=code).exists():
        code = f"{base}-{n}"[:40]
        n += 1
    return code


@transaction.atomic
def add_custom(name: str) -> OptionType | None:
    """Свой тип магазина. None — пустое имя или превышен лимит типов."""
    name = " ".join((name or "").split())[:60]
    if not name or OptionType.objects.count() >= reg.MAX_TYPES:
        return None
    return OptionType.objects.create(
        code=_free_code(name), name=name, sort_order=OptionType.objects.count()
    )


def split_values(raw) -> list[str]:
    """«Baumwolle, Leinen» / по строкам → значения без пустых и дублей (порядок ввода)."""
    seen, out = set(), []
    for part in re.split(r"[,\n]", raw or ""):
        value = " ".join(part.split())[:_VALUE_MAX]
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            out.append(value)
    return out


@transaction.atomic
def add_values(option_type: OptionType, raw) -> list[OptionValue]:
    """Добавить значения типу (существующие возвращаются как есть). Лимит MAX_VALUES."""
    existing = {v.value.casefold(): v for v in option_type.values.all()}
    out, order = [], len(existing)
    for value in split_values(raw):
        found = existing.get(value.casefold())
        if found is None:
            if len(existing) >= reg.MAX_VALUES:
                break
            found = OptionValue.objects.create(
                option_type=option_type, value=value, sort_order=order
            )
            existing[value.casefold()] = found
            order += 1
        out.append(found)
    return out


def value_in_use(value: OptionValue) -> bool:
    return value.links.exists()


def type_in_use(option_type: OptionType) -> bool:
    return VariantOption.objects.filter(option_type=option_type).exists()


@transaction.atomic
def set_variant_option(variant: ProductVariant, option_type: OptionType, value: str) -> None:
    """Значение своего/стандартного типа у варианта (размер/цвет пишутся в поля)."""
    if option_type.code in reg.FIELD_BACKED:
        setattr(variant, option_type.code, (value or "")[:40])
        variant.save(update_fields=[option_type.code, "updated_at"])
        return
    if not value:
        VariantOption.objects.filter(variant=variant, option_type=option_type).delete()
        return
    values = add_values(option_type, value)
    if not values:
        return
    val = values[0]
    VariantOption.objects.update_or_create(
        variant=variant, option_type=option_type, defaults={"value": val}
    )


def value_input_name(value_pk: int, locale: str) -> str:
    """Имя поля перевода значения в форме «Optionen» (по полю на значение и язык)."""
    return f"val_{value_pk}_{locale}"


def save_translations(option_type, post, tenant) -> None:
    """Переводы подписи своего типа и его значений из POST экрана «Optionen».

    База (немецкий ключ) не меняется — склад, заказы и фильтр держатся за неё; переводится
    только показ. Отсутствующее поле не трогаем, пустое — снимает перевод языка."""
    from apps.core.i18n_input import apply_i18n_overlay, extra_locales

    locales = extra_locales(tenant)
    if not locales:
        return
    if not option_type.standard:
        changed = apply_i18n_overlay(option_type, post, tenant, fields=("name",))
        if changed:
            option_type.save(update_fields=[*changed, "updated_at"])
    for value in option_type.values.all():
        overlay = dict(value.value_i18n or {})
        before = dict(overlay)
        for loc in locales:
            raw = post.get(value_input_name(value.pk, loc))
            if raw is None:
                continue
            text = " ".join(raw.split())[:60]
            if text and text != value.value:
                overlay[loc] = text
            else:
                overlay.pop(loc, None)
        if overlay != before:
            value.value_i18n = overlay
            value.save(update_fields=["value_i18n", "updated_at"])
