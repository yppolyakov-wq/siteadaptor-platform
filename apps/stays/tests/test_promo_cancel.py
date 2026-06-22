"""H4a (промокод) + H4b (самоотмена брони по политике тарифа)."""

import uuid
from datetime import date, timedelta

import pytest

from apps.loyalty.models import Voucher
from apps.stays import public_views, services
from apps.stays.models import RatePlan, StayBooking, StayUnit
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db

D0 = date(2026, 11, 1)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 10000)
    kwargs.setdefault("max_guests", 4)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, nights=2, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=nights), **kwargs)


# --- H4a промокод -----------------------------------------------------------------


def test_percent_voucher_discounts_lodging_not_kurtaxe():
    from apps.stays.models import StaySettings

    StaySettings.objects.create(kurtaxe_cents=200)  # 2 €/Erw./Nacht
    Voucher.objects.create(code="SOMMER10", label="-10%", discount_percent=10, max_uses=0)
    unit = _unit(price_cents=10000)
    b = _book(unit, nights=2, adults=2, voucher_code="sommer10")  # код регистронезависим
    # проживание 200 €; скидка 10 % = 20 €; Kurtaxe 2×2×2 = 8 € (на неё скидки нет)
    assert b.discount_cents == 2000
    assert b.voucher_code == "SOMMER10"
    assert b.total_cents == 20000 - 2000 + 800


def test_voucher_redeemed_increments_use():
    v = Voucher.objects.create(code="EINMAL", label="-5€", discount_cents=500, max_uses=1)
    unit = _unit()
    _book(unit, voucher_code="EINMAL")
    v.refresh_from_db()
    assert v.used_count == 1


def test_invalid_voucher_raises_and_books_nothing():
    unit = _unit()
    with pytest.raises(services.PromoInvalid):
        _book(unit, voucher_code="GIBTSNICHT")
    assert not StayBooking.objects.filter(unit=unit).exists()


def test_used_up_voucher_not_applied():
    Voucher.objects.create(code="LEER", label="-5€", discount_cents=500, max_uses=1, used_count=1)
    unit = _unit()
    with pytest.raises(services.PromoInvalid):
        _book(unit, voucher_code="LEER")


# --- H4b самоотмена ---------------------------------------------------------------


def _rate(cancellation, free_days=0):
    return RatePlan.objects.create(name="T", cancellation=cancellation, free_cancel_days=free_days)


def test_cancellation_state_flexible_free_before_deadline():
    unit = _unit()
    rp = _rate("flexible", free_days=3)
    # заезд через 10 дней — до дедлайна (3 дня) ещё далеко → бесплатно
    b = services.book_stay(
        unit,
        arrival=date.today() + timedelta(days=10),
        departure=date.today() + timedelta(days=12),
        name="G",
        rate_plan=rp,
    )
    state = services.cancellation_state(b)
    assert state["can_cancel"] and state["free"]


def test_cancellation_state_non_refundable_not_free():
    unit = _unit()
    rp = _rate("non_refundable")
    b = services.book_stay(
        unit,
        arrival=date.today() + timedelta(days=10),
        departure=date.today() + timedelta(days=12),
        name="G",
        rate_plan=rp,
    )
    state = services.cancellation_state(b)
    assert state["can_cancel"] and not state["free"]


def test_cancellation_state_blocks_non_active():
    unit = _unit()
    b = _book(unit)
    StayBookingSM().apply(b, "cancelled")
    assert services.cancellation_state(b)["can_cancel"] is False


def test_cancel_token_roundtrip_and_signature():
    from django.core import signing

    unit = _unit()
    b = _book(unit)
    token = public_views.cancel_token(b)
    assert signing.loads(token, salt=public_views._CANCEL_SALT) == str(b.pk)
    with pytest.raises(signing.BadSignature):
        signing.loads("tampered", salt=public_views._CANCEL_SALT)
