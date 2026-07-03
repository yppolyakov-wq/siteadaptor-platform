"""B1.4 — возврат использования ваучера при отмене: сервис + FSM-хуки
(booking/orders; stays/events — тот же generic-хук по voucher_code)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.loyalty.models import Voucher
from apps.promotions import services as promo_services

pytestmark = pytest.mark.django_db


def test_unredeem_returns_use_and_floors_at_zero():
    v = Voucher.objects.create(code="GS-7", label="G", discount_cents=500, max_uses=1)
    promo_services.redeem_voucher("GS-7")
    assert promo_services.unredeem_voucher("gs-7") is True  # регистр нормализуется
    v.refresh_from_db()
    assert v.used_count == 0
    assert promo_services.unredeem_voucher("GS-7") is False  # ниже нуля не уходим
    assert promo_services.unredeem_voucher("") is False
    assert promo_services.unredeem_voucher("GIBTSNICHT") is False


def test_booking_cancel_returns_voucher_use():
    from apps.booking import services as booking_services
    from apps.booking.models import Resource
    from apps.booking.state_machine import BookingSM

    Voucher.objects.create(code="BK-1", label="G", discount_cents=500, max_uses=1)
    start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    booking = booking_services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="K",
        price_cents=3000,
        voucher_code="BK-1",
    )
    assert Voucher.objects.get(code="BK-1").used_count == 1
    BookingSM().apply(booking, "cancelled")
    assert Voucher.objects.get(code="BK-1").used_count == 0  # использование вернулось


def test_order_cancel_returns_voucher_use():
    from apps.orders import services as order_services
    from apps.orders.state_machine import OrderSM

    Voucher.objects.create(code="OR-1", label="G", discount_cents=500, max_uses=1)
    promo_services.redeem_voucher("OR-1")  # как делает чекаут заказа
    order = order_services.create_order(items=[(ProductFactory(), 1)], name="K")
    order.voucher_code = "OR-1"
    order.save(update_fields=["voucher_code"])
    OrderSM().apply(order, "cancelled")
    assert Voucher.objects.get(code="OR-1").used_count == 0
