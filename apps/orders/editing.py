"""SH группа B (фидбэк владельца 2026-08-20): правка ЗАКАЗА из кабинета.

План — `docs/sh-order-wave-plan-2026-08-20.md §3`. Решение владельца: править
можно ЛЮБОЙ незакрытый заказ, а склад и леджер пересчитываются ТЕМ ЖЕ движком,
что создание и отмена, — иначе счётчик разойдётся с леджером (класс дефекта T1).

Инварианты модуля:

* Остаток и леджер двигаются в ОДНОЙ atomic (правило UD3-2): либо и то и другое,
  либо ничего. Нехватка остатка → `OutOfStock`, правка не применяется.
* Движения правки пишутся БЕЗ `source_ref` (ручные): дедуп по (source, ref, kind)
  съел бы второе одинаковое изменение количества, а оно законно.
* Терминальный заказ (отменён/возвращён) НЕ правится: его остаток уже возвращён
  FSM, и повторное движение задвоило бы склад.
* Итог заказа всегда пересчитывается одним хелпером `recalc_total` — той же
  формулой, что `create_order` (позиции − скидка + доставка).
"""

from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _

from apps.core import status_registry

from .models import Order, OrderItem
from .services import OutOfStock


class OrderLocked(Exception):
    """Заказ закрыт (терминальный статус) — правка запрещена."""


def is_editable(order, tenant=None) -> bool:
    """Правим всё, что не в терминальной стадии (реестр статусов — с учётом
    кастомных статусов владельца SM-3)."""
    d = status_registry.resolve("order", order.status, tenant)
    return not (d is not None and d.stage == "terminal")


def _require_editable(order, tenant=None):
    if not is_editable(order, tenant):
        raise OrderLocked(_("Ein abgeschlossener Auftrag kann nicht mehr geändert werden."))


def _tracked_row(product, variant):
    """Строка учёта под блокировкой: вариант важнее товара; None — без учёта."""
    from apps.catalog.models import Product, ProductVariant

    if variant is not None:
        row = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    elif product is not None:
        row = Product.objects.select_for_update().get(pk=product.pk)
    else:
        return None
    return row if row.stock_quantity is not None else None


def _move_stock(*, product, variant, delta, order, title):
    """Сдвинуть остаток на `delta` (+вернуть / −списать) и записать в леджер.

    Вызывать ВНУТРИ atomic. delta<0 при нехватке → OutOfStock (правка откатится).
    """
    if not delta or product is None:
        return
    from apps.inventory.services import consume_fefo, has_lots, record_movement, restore_fefo

    row = _tracked_row(product, variant)
    if row is None:
        return  # товар без учёта остатка
    if delta < 0 and row.stock_quantity < -delta:
        raise OutOfStock(title=title, available=row.stock_quantity)
    row.stock_quantity += delta
    row.save(update_fields=["stock_quantity", "updated_at"])
    record_movement(
        product=product,
        variant=variant,
        kind="return" if delta > 0 else "sale",
        delta=delta,
        source="order_edit",
        source_ref="",  # ручная правка: дедуп по ref съел бы законный повтор
        note=order.reference_code,
    )
    # Склад-2 E1.5: партии следуют за остатком (no-op у товаров без партий).
    if has_lots(product, variant):
        if delta > 0:
            restore_fefo(product, variant, qty=delta)
        else:
            consume_fefo(product, variant, qty=-delta)


def recalc_total(order) -> Decimal:
    """Итог = позиции − скидка + доставка (формула create_order, один источник)."""
    items = sum((i.line_total for i in order.items.all()), Decimal("0"))
    shipping = Decimal(order.shipping_cents) / 100 if order.is_delivery else Decimal("0")
    total = items - Decimal(order.discount_cents) / 100 + shipping
    order.total = max(total, Decimal("0"))
    order.save(update_fields=["total", "updated_at"])
    return order.total


@transaction.atomic
def set_item_qty(order, item_pk, qty: int, tenant=None):
    """Изменить количество позиции (0 = удалить). Склад двигается на разницу."""
    _require_editable(order, tenant)
    item = order.items.select_related("product", "variant").get(pk=item_pk)
    qty = max(int(qty), 0)
    delta = item.qty - qty  # положительная разница = возвращаем на склад
    _move_stock(
        product=item.product,
        variant=item.variant,
        delta=delta,
        order=order,
        title=item.title_snapshot,
    )
    if qty:
        item.qty = qty
        item.save(update_fields=["qty", "updated_at"])
    else:
        item.delete()
    return recalc_total(order)


@transaction.atomic
def add_item(order, *, product=None, variant=None, qty=1, title="", unit_price=None, tenant=None):
    """Добавить позицию: товар/вариант из каталога или свободную строку.

    Свободная строка (product=None) склад не трогает — как `custom_lines`
    в `create_order` (LS-3)."""
    _require_editable(order, tenant)
    qty = max(int(qty), 1)
    if product is not None:
        base = variant.price_value if variant is not None else product.base_price
        price = Decimal(str(unit_price)) if unit_price is not None else Decimal(str(base))
        label = variant.label if variant is not None else ""
        name = title or (f"{product} · {label}" if label else str(product))
        sku = (variant.sku if variant is not None and variant.sku else product.sku) or ""
    else:
        if not title or unit_price is None:
            raise ValueError("free line needs title and price")
        price, label, name, sku = Decimal(str(unit_price)), "", title, ""
    _move_stock(product=product, variant=variant, delta=-qty, order=order, title=name)
    OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        variant_label=label,
        sku=sku,
        qty=qty,
        unit_price=price,
        title_snapshot=str(name)[:200],
        # SH-4: снимок ставки НДС — как в create_order (свободная строка = дефолт).
        **({"vat_rate": product.vat_rate} if product is not None else {}),
        # ERP-1: EK-снимок добавленной строки — тот же, что при создании заказа.
        cost_price=(
            variant.cost_value
            if variant is not None
            else (product.cost_price if product is not None else None)
        ),
    )
    return recalc_total(order)


@transaction.atomic
def set_discount(order, *, cents: int, note: str = "", tenant=None):
    """Скидка владельца на заказ (в центах). Промокод не трогаем: `voucher_code`
    остаётся снимком того, что применил клиент."""
    _require_editable(order, tenant)
    order.discount_cents = max(int(cents), 0)
    if note:
        order.voucher_code = note[:12]
    order.save(update_fields=["discount_cents", "voucher_code", "updated_at"])
    return recalc_total(order)


@transaction.atomic
def update_delivery(order, *, fulfillment=None, address=None, shipping_cents=None, tenant=None):
    """Правка доставки: способ получения, адрес, стоимость."""
    _require_editable(order, tenant)
    fields = ["updated_at"]
    if fulfillment in (Order.FULFILLMENT_PICKUP, Order.FULFILLMENT_DELIVERY):
        order.fulfillment = fulfillment
        fields.append("fulfillment")
    if address is not None:
        order.shipping_address = address.strip()[:1000]
        fields.append("shipping_address")
    if shipping_cents is not None:
        order.shipping_cents = max(int(shipping_cents), 0)
        fields.append("shipping_cents")
    order.save(update_fields=fields)
    return recalc_total(order)


def update_customer(order, *, name="", email="", phone=""):
    """Правка контакта клиента с карточки заказа (SH-5, паттерн QF-4 у заявки).

    Пишем в СУЩЕСТВУЮЩЕГО клиента: заказ и его история остаются связаны с тем же
    контактом (в CRM это тот же человек, а не дубль)."""
    customer = order.customer
    fields = []
    for attr, value in (("name", name), ("email", email), ("phone", phone)):
        value = (value or "").strip()
        if value and getattr(customer, attr, None) != value:
            setattr(customer, attr, value)
            fields.append(attr)
    if fields:
        customer.save(update_fields=fields + ["updated_at"])
    return customer
