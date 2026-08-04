"""Слияние товаров в одну карточку (фидбэк владельца 2026-08-04).

«Zusammenführen»: отдельные товары (например «T-Shirt S», «T-Shirt M»)
становятся ВАРИАНТАМИ главного — одна карточка с разными артикулами.
Каждый прочий товар переносит в вариант: имя (label), артикул/EAN, цену,
остаток, EK и первое фото; затем деактивируется (история заказов и леджер
остаются на нём — ничего не переписываем задним числом).

Склад: остаток переезжает В ВАРИАНТ главного двумя леджер-записями
(source="catalog"): +N варианту, −N старому товару → реконсиляция
«счётчик ↔ леджер» сходится с обеих сторон (инвариант T1).
"""

from django.db import transaction

from .models import Product, ProductVariant


def merge_products(main: Product, others, actor: str = "") -> tuple[int, list[str]]:
    """Слить `others` в варианты `main`. → (сколько слито, [имена-отказы]).

    Отказ (в списке ошибок, остальные сливаются): у товара уже есть варианты
    или модификаторы — их не расплющить в один вариант без потери данных."""
    from apps.inventory.services import log_catalog_change

    merged, refused = 0, []
    for other in others:
        if other.pk == main.pk:
            continue
        if other.variants.exists() or other.modifier_groups.exists():
            refused.append(str(other))
            continue
        with transaction.atomic():
            base_label = (str(other) or "Variante")[:100]
            label, n = base_label, 2
            while ProductVariant.objects.filter(product=main, label=label).exists():
                label = f"{base_label} ({n})"[:100]
                n += 1
            variant = ProductVariant.objects.create(
                product=main,
                label=label,
                sku=other.sku,
                gtin=other.gtin,
                price=other.base_price,
                content_amount=other.content_amount,
                stock_quantity=other.stock_quantity,
                cost_price=other.cost_price,
                reorder_point=other.reorder_point,
                reorder_target=other.reorder_target,
                images=list(other.images[:1]) if other.images else [],
            )
            log_catalog_change(
                product=main, variant=variant, old=None, new=variant.stock_quantity, actor=actor
            )
            update_fields = ["is_active", "metadata", "updated_at"]
            if other.stock_quantity is not None:
                log_catalog_change(product=other, old=other.stock_quantity, new=0, actor=actor)
                other.stock_quantity = 0
                update_fields.append("stock_quantity")
            other.is_active = False
            meta = other.metadata if isinstance(other.metadata, dict) else {}
            meta["merged_into"] = str(main.pk)
            other.metadata = meta
            other.save(update_fields=update_fields)
            merged += 1
    return merged, refused
