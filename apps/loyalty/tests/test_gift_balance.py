"""B1.5 (владелец «а») — Wertgutschein с остатком: частичное списание, кап,
исчерпание, возврат остатка при отмене, legacy-промокоды не тронуты."""

import pytest

from apps.loyalty.models import Voucher
from apps.promotions.services import VoucherError, spend_voucher, unredeem_voucher

pytestmark = pytest.mark.django_db


def _gift(cents=10000, code="GS-B1"):
    return Voucher.objects.create(
        code=code, label="Gutschein", discount_cents=cents, balance_cents=cents, max_uses=0
    )


def test_partial_spend_keeps_remainder():
    _gift()
    discount, v = spend_voucher("gs-b1", 3000)  # заказ 30 € по сертификату 100 €
    assert discount == 3000
    assert v.balance_cents == 7000  # остаток живёт (не сгорает)
    assert v.is_redeemable


def test_spend_caps_at_balance_then_exhausts():
    _gift(cents=10000)
    spend_voucher("GS-B1", 3000)
    discount, v = spend_voucher("GS-B1", 8000)  # осталось 70 € — капается остатком
    assert discount == 7000 and v.balance_cents == 0
    assert not v.is_redeemable
    with pytest.raises(VoucherError):
        spend_voucher("GS-B1", 500)  # исчерпан


def test_cancel_returns_balance_and_use():
    _gift(cents=5000)
    discount, _ = spend_voucher("GS-B1", 2000)
    assert unredeem_voucher("GS-B1", amount_cents=discount) is True
    v = Voucher.objects.get(code="GS-B1")
    assert v.balance_cents == 5000 and v.used_count == 0


def test_legacy_percent_voucher_unchanged():
    Voucher.objects.create(code="P10", label="−10 %", discount_percent=10, max_uses=1)
    discount, v = spend_voucher("P10", 4000)
    assert discount == 400 and v.balance_cents is None and v.used_count == 1
    with pytest.raises(VoucherError):
        spend_voucher("P10", 4000)  # max_uses исчерпан — прежняя механика
    # возврат без суммы — только использование (balance нет)
    assert unredeem_voucher("P10") is True
    assert Voucher.objects.get(code="P10").used_count == 0


def test_booking_checkout_partial_gift_and_cancel_roundtrip():
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking import services as booking_services
    from apps.booking.models import Resource
    from apps.booking.state_machine import BookingSM

    _gift(cents=10000, code="GS-RT")
    start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    booking = booking_services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="K",
        price_cents=2500,
        voucher_code="GS-RT",
    )
    assert booking.discount_cents == 2500 and booking.total_cents == 0
    assert Voucher.objects.get(code="GS-RT").balance_cents == 7500
    BookingSM().apply(booking, "cancelled")
    v = Voucher.objects.get(code="GS-RT")
    assert v.balance_cents == 10000 and v.used_count == 0  # остаток вернулся
