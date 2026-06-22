"""H1: тарифы (Rate Plans) — модификатор цены, питание, условия отмены, снимок."""

import uuid
from datetime import date, timedelta

import pytest

from apps.stays import pricing, services
from apps.stays.models import RatePlan, StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 8, 1)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 10000)  # 100 €/Nacht
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, nights=3, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=nights), **kwargs)


# --- pricing.apply_rate_plan ------------------------------------------------------


def test_apply_rate_plan_none_is_identity():
    assert pricing.apply_rate_plan(10000, None) == 10000


def test_apply_rate_plan_percent_then_surcharge():
    rp = RatePlan(percent_adjust=-10, surcharge_cents=1200)  # −10 %, затем +12 €
    assert pricing.apply_rate_plan(10000, rp) == 10200  # 9000 + 1200
    rp2 = RatePlan(percent_adjust=10)
    assert pricing.apply_rate_plan(10000, rp2) == 11000


def test_apply_rate_plan_never_negative():
    rp = RatePlan(percent_adjust=-100)
    assert pricing.apply_rate_plan(5000, rp) == 0


# --- quote_total с тарифом --------------------------------------------------------


def test_quote_total_with_rate_plan():
    unit = _unit(price_cents=10000)
    rp = RatePlan.objects.create(name="Frühstück", surcharge_cents=1200, meal_plan="breakfast")
    # 3 ночи × (100 € + 12 €) = 336 €
    assert pricing.quote_total_cents(unit, D0, D0 + timedelta(days=3), rate_plan=rp) == 33600
    # без тарифа — база
    assert pricing.quote_total_cents(unit, D0, D0 + timedelta(days=3)) == 30000


# --- book_stay снимок -------------------------------------------------------------


def test_book_without_rate_plan_uses_base():
    unit = _unit(price_cents=8000)
    booking = _book(unit, nights=2)
    assert booking.total_cents == 16000
    assert booking.rate_plan_id is None
    assert booking.rate_snapshot == {}


def test_book_with_rate_plan_snapshot_and_total():
    unit = _unit(price_cents=10000)
    rp = RatePlan.objects.create(
        name="Sparpreis",
        percent_adjust=-12,
        cancellation="non_refundable",
        meal_plan="none",
    )
    booking = _book(unit, nights=2, rate_plan=rp)
    assert booking.total_cents == 17600  # 2 × 88 €
    assert booking.rate_plan_id == rp.pk
    snap = booking.rate_snapshot
    assert snap["name"] == "Sparpreis"
    assert snap["cancellation"] == "non_refundable"
    assert snap["percent_adjust"] == -12


def test_book_with_rate_plan_and_extras_sum():
    unit = _unit(price_cents=10000)
    rp = RatePlan.objects.create(name="Frühstück", surcharge_cents=1000)
    extras = [{"label": "Parkplatz", "price_cents": 800}]
    booking = _book(unit, nights=2, rate_plan=rp, extras=extras)
    # 2 × 110 € + 8 € = 228 €
    assert booking.total_cents == 22800


# --- move_stay пересчёт с тарифом -------------------------------------------------


def test_move_recomputes_with_live_rate_plan():
    unit = _unit(price_cents=10000)
    rp = RatePlan.objects.create(name="Frühstück", surcharge_cents=1200)
    booking = _book(unit, nights=2, rate_plan=rp)
    assert booking.total_cents == 22400  # 2 × 112 €
    services.move_stay(booking, arrival=D0, departure=D0 + timedelta(days=3))
    booking.refresh_from_db()
    assert booking.total_cents == 33600  # 3 × 112 €


def test_move_recomputes_from_snapshot_when_rate_deleted():
    unit = _unit(price_cents=10000)
    rp = RatePlan.objects.create(name="Frühstück", surcharge_cents=1200)
    booking = _book(unit, nights=2, rate_plan=rp)
    rp.delete()  # SET_NULL → FK сбросится, но снимок несёт модификаторы
    booking.refresh_from_db()
    assert booking.rate_plan_id is None
    services.move_stay(booking, arrival=D0, departure=D0 + timedelta(days=4))
    booking.refresh_from_db()
    assert booking.total_cents == 44800  # 4 × 112 € из снимка surcharge
