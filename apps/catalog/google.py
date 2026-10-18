"""Отбор товаров для фида Google Merchant Center (M23b.1, план docs/m23b-merchant-feed-plan-2026-10-18.md).

Одна точка истины для фида и экрана кабинета (M23b.2): что уходит в Google и почему остальное нет.
Причины исключения (жёсткие) — товар в фид не попадает; предупреждения — попадает, но Google
может показать хуже. Старый `/feed/google.xml` (общий с Meta) этим модулем не фильтруется."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch

_MAX_DEPTH = 10  # предохранитель от цикла parent в данных

REASONS = ("hidden", "category_hidden", "no_image", "no_price")
WARNINGS = ("no_identifier", "no_description")


def _hidden_category_ids() -> set:
    """id категорий, чья ветка не уходит в Google: своя галочка, галочка предка, неактивна
    или удалена. Один запрос на весь каталог (категорий у бизнеса — десятки)."""
    from .models import Category

    rows = {
        pk: (parent_id, hide or not active or deleted is not None)
        for pk, parent_id, hide, active, deleted in Category.all_objects.values_list(
            "pk", "parent_id", "hide_in_google", "is_active", "deleted_at"
        )
    }
    hidden = set()
    for pk in rows:
        current, depth = pk, 0
        while current is not None and depth <= _MAX_DEPTH:
            row = rows.get(current)
            if row is None or row[1]:
                hidden.add(pk)
                break
            current, depth = row[0], depth + 1
    return hidden


def _variants(product) -> list:
    cached = getattr(product, "feed_variants", None)
    return cached if cached is not None else list(product.active_variants)


def _positive(value) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def eligibility(product, *, hidden_categories: set | None = None) -> tuple[bool, list, list]:
    """(уходит ли в фид, причины исключения, предупреждения). У исключённого товара
    предупреждений нет — экран показывает ему только то, что его исключило."""
    if product.hide_in_google:
        return False, ["hidden"], []
    if hidden_categories is None:
        hidden_categories = _hidden_category_ids()
    reasons = []
    if product.category_id and product.category_id in hidden_categories:
        reasons.append("category_hidden")
    img = product.primary_image
    if not (img and img.get("url")):
        reasons.append("no_image")
    variants = _variants(product)
    prices = [v.price_value for v in variants] if variants else [product.base_price]
    if not any(_positive(p) for p in prices):
        reasons.append("no_price")
    if reasons:
        return False, reasons, []
    warnings = []
    has_id = product.gtin or product.sku or product.brand or any(v.gtin or v.sku for v in variants)
    if not has_id:
        warnings.append("no_identifier")
    if not product.description_text:
        warnings.append("no_description")
    return True, [], warnings


def _active_products():
    from .models import Product, ProductVariant

    return (
        Product.objects.filter(is_active=True)
        .select_related("category")  # KAT-3: SEO-ссылка товара без N+1
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True),
                to_attr="feed_variants",
            )
        )
        .order_by("-created_at")
    )


def _evaluated():
    hidden = _hidden_category_ids()
    for product in _active_products():
        yield product, eligibility(product, hidden_categories=hidden)


def merchant_products() -> list:
    """Активные товары, годные для фида (с предзагруженными активными вариантами)."""
    return [product for product, (ok, _r, _w) in _evaluated() if ok]


def summary() -> dict:
    """{"included": N, "excluded": {причина: N}} — исключённый считается по первой причине,
    чтобы сумма совпадала с числом товаров."""
    included, excluded = 0, Counter()
    for _product, (ok, reasons, _w) in _evaluated():
        if ok:
            included += 1
        else:
            excluded[reasons[0]] += 1
    return {"included": included, "excluded": dict(excluded)}
