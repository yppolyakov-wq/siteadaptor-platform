"""G7: гибкая предоплата по тарифу (% от итога)."""

from datetime import date, timedelta

import pytest

from apps.stays import pricing
from apps.stays.models import RatePlan, StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db


def test_prepayment_cents_by_percent():
    full = RatePlan(name="Vorkasse", prepayment_percent=100)
    part = RatePlan(name="Anzahlung", prepayment_percent=30)
    none = RatePlan(name="Vor Ort", prepayment_percent=0)
    assert pricing.prepayment_cents(10000, full) == 10000
    assert pricing.prepayment_cents(10000, part) == 3000
    assert pricing.prepayment_cents(10000, none) == 0
    assert pricing.prepayment_cents(10000, None) == 0


def test_prepayment_on_full_booking_total():
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=10000, max_guests=2)
    rate = RatePlan.objects.create(
        name="Sparpreis", cancellation=RatePlan.CANCEL_NONREF, prepayment_percent=100
    )
    arrival = date(2030, 6, 3)  # будни (Montag)
    booking = book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="K",
        email="k@test.de",
        rate_plan=rate,
    )
    # 2 ночи × 100 € = 200 € итог, Vorkasse 100 % = весь итог
    assert booking.total_cents == 20000
    assert pricing.prepayment_cents(booking.total_cents, rate) == 20000


def test_partial_prepayment_rounds():
    rate = RatePlan(name="A", prepayment_percent=30)
    assert pricing.prepayment_cents(9999, rate) == 3000  # round(2999.7)
