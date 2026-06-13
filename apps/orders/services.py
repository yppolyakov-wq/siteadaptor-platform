"""Сервис создания заказа Click & Collect (Track D / D2a).

Зеркало promotions.services.reserve по работе с Customer (переиспользование по
email), но клиент из заказа помечается created_source="order". Остаток v1 не
списываем (решение ТЗ: предзаказ без жёсткого лимита; stock — отдельный
инкремент D2c).
"""

import secrets
import string
from decimal import Decimal

from django.db import transaction

from apps.promotions.models import Customer

from .models import Order, OrderItem

_ALPHABET = string.ascii_uppercase + string.digits


class EmptyOrder(Exception):
    """Оформление пустой корзины."""


class OutOfStock(Exception):
    """Не хватает остатка на товар/вариант (R3)."""

    def __init__(self, title="", available=0):
        self.title = title
        self.available = available
        super().__init__(f"out of stock: {title} (available {available})")


def _reserve_stock(norm):
    """Атомарно списать остаток по позициям (R3, паттерн anti-oversell).

    Блокируем строку товара/варианта (select_for_update), проверяем и списываем.
    null = без учёта (не трогаем). Вызывается внутри транзакции create_order;
    при нехватке бросает OutOfStock → заказ не создаётся (откат).
    """
    from apps.catalog.models import Product, ProductVariant

    # Стабильный порядок блокировок — меньше шанс дедлока при конкуренции.
    for product, variant, qty in sorted(norm, key=lambda i: str(i[1].pk if i[1] else i[0].pk)):
        if variant is not None:
            row = ProductVariant.objects.select_for_update().get(pk=variant.pk)
            title = f"{product} · {variant.label}"
        else:
            row = Product.objects.select_for_update().get(pk=product.pk)
            title = str(product)
        if row.stock_quantity is None:
            continue  # без учёта остатка
        if row.stock_quantity < qty:
            raise OutOfStock(title=title, available=row.stock_quantity)
        row.stock_quantity -= qty
        row.save(update_fields=["stock_quantity", "updated_at"])


def shipping_cost(tenant, subtotal_cents: int) -> int:
    """Стоимость доставки в центах (G4): плоский тариф, бесплатно от порога.

    0, если доставка выключена или сумма ≥ порога бесплатной доставки.
    Mindestbestellwert проверяется на витрине (checkout), не здесь.
    """
    if not getattr(tenant, "delivery_enabled", False):
        return 0
    free = getattr(tenant, "delivery_free_cents", 0) or 0
    if free and subtotal_cents >= free:
        return 0
    return getattr(tenant, "delivery_fee_cents", 0) or 0


def _unique_order_code() -> str:
    for _ in range(10):
        code = "O-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Order.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique order reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(
        name=name, email=email, phone=phone, created_source=Customer.SOURCE_ORDER
    )


@transaction.atomic
def create_order(
    *,
    items,
    name,
    email="",
    phone="",
    note="",
    pickup_slot=None,
    source_channel="",
    fulfillment=Order.FULFILLMENT_PICKUP,
    shipping_address="",
    shipping_cents=0,
):
    """Создать заказ из позиций со снимками цены/названия.

    items — кортежи (product, qty) ИЛИ (product, variant, qty); variant=None =
    товар без вариантов. Для доставки (fulfillment=delivery) total включает
    shipping_cents. Бросает EmptyOrder без позиций и ValueError при qty < 1.
    """
    norm = []
    for item in items:
        product, variant, qty = item if len(item) == 3 else (item[0], None, item[1])
        norm.append((product, variant, int(qty)))
    if not norm:
        raise EmptyOrder()
    if any(qty < 1 for _p, _v, qty in norm):
        raise ValueError("qty must be >= 1")

    _reserve_stock(norm)  # R3: атомарное списание; OutOfStock → откат, заказа нет
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    delivery = fulfillment == Order.FULFILLMENT_DELIVERY
    shipping = int(shipping_cents) if delivery else 0
    order = Order.objects.create(
        customer=customer,
        reference_code=_unique_order_code(),
        note=note,
        pickup_slot=pickup_slot,
        source_channel=(source_channel or "")[:50],
        total=Decimal("0"),
        currency=norm[0][0].currency,
        fulfillment=Order.FULFILLMENT_DELIVERY if delivery else Order.FULFILLMENT_PICKUP,
        shipping_address=(shipping_address or "").strip()[:1000] if delivery else "",
        shipping_cents=shipping,
    )
    total = Decimal("0")
    for product, variant, qty in norm:
        # DecimalField не приводит атрибут у не перезагруженных из БД
        # инстансов — нормализуем явно. Цена варианта: своя или base_price.
        base = variant.price_value if variant is not None else product.base_price
        unit_price = Decimal(str(base))
        label = variant.label if variant is not None else ""
        title = f"{product} · {label}" if label else str(product)
        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            variant_label=label,
            qty=qty,
            unit_price=unit_price,
            title_snapshot=title[:200],
        )
        total += unit_price * qty
    order.total = total + Decimal(shipping) / 100  # G4: доставка в итог
    order.save(update_fields=["total", "updated_at"])
    # письма клиенту/владельцу — Notification в этой же транзакции,
    # доставка после коммита (D2b)
    from .notifications import enqueue_order_email

    enqueue_order_email(order, "created")
    return order
