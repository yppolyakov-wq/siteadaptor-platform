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
def create_order(*, items, name, email="", phone="", note="", pickup_slot=None, source_channel=""):
    """Создать заказ из [(product, qty), …] со снимками цены/названия.

    Бросает EmptyOrder без позиций и ValueError при qty < 1.
    """
    items = [(product, int(qty)) for product, qty in items]
    if not items:
        raise EmptyOrder()
    if any(qty < 1 for _product, qty in items):
        raise ValueError("qty must be >= 1")

    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    order = Order.objects.create(
        customer=customer,
        reference_code=_unique_order_code(),
        note=note,
        pickup_slot=pickup_slot,
        source_channel=(source_channel or "")[:50],
        total=Decimal("0"),
        currency=items[0][0].currency,
    )
    total = Decimal("0")
    for product, qty in items:
        # DecimalField не приводит атрибут у не перезагруженных из БД
        # инстансов — нормализуем явно.
        unit_price = Decimal(str(product.base_price))
        OrderItem.objects.create(
            order=order,
            product=product,
            qty=qty,
            unit_price=unit_price,
            title_snapshot=str(product)[:200],
        )
        total += unit_price * qty
    order.total = total
    order.save(update_fields=["total", "updated_at"])
    return order
