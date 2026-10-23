"""KA-H6 (аудит KA-5d, Z2): питание тарифа — 19 % (Aufteilungsgebot), не 7 %."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core import deal_lines, vat
from apps.core.tests.dates import future_month_start
from apps.finance.models import RevenueEntry
from apps.finance.services import invoice_from_stay
from apps.promotions.models import Customer
from apps.stays import meal
from apps.stays.models import StayBooking, StayUnit
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)
HP = {"meal_plan": "half_board", "meal_label": "Halbpension", "surcharge_cents": 1200}


def _stay(snapshot=HP, nights=2, rooms=1, total=None, auto_discount=0, kurtaxe=0):
    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    meal_total = (snapshot or {}).get("surcharge_cents", 0) * nights * rooms
    return StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=D0,
        departure=D0 + timedelta(days=nights),
        rooms=rooms,
        status=StayBooking.STATUS_CONFIRMED,
        price_cents=8000,
        total_cents=total if total is not None else 8000 * nights * rooms + meal_total + kurtaxe,
        auto_discount_cents=auto_discount,
        kurtaxe_cents=kurtaxe,
        rate_snapshot=snapshot or {},
    )


def test_meal_cents_rooms_and_nights():
    assert meal.meal_cents(_stay(nights=2, rooms=2)) == 4800


def test_meal_share_after_auto_discount():
    # проживание 17 600 после скидки 1 760 (−10 %) → питание −10 % тоже
    booking = _stay(nights=2, total=17600 - 1760, auto_discount=1760)
    assert meal.meal_cents(booking) == 2160


def test_no_meal_plan_unchanged():
    assert meal.meal_cents(_stay(snapshot={"meal_plan": "none", "surcharge_cents": 1200})) == 0
    assert meal.meal_cents(_stay(snapshot={})) == 0


def test_invoice_splits_meal_at_19_and_matches_total():
    booking = _stay(nights=2, kurtaxe=500)  # 16 000 + 2 400 + 500
    invoice = invoice_from_stay(booking, SimpleNamespace(small_business=False))
    rates = {line["vat_rate"] for line in invoice.lines}
    assert "19.00" in rates and "7.00" in rates and "0" in rates
    assert invoice.gross == Decimal(booking.total_cents) / 100


def test_small_business_meal_zero_rate():
    booking = _stay()
    invoice = invoice_from_stay(booking, SimpleNamespace(small_business=True))
    assert {line["vat_rate"] for line in invoice.lines} <= {"0", "0.00"}


def test_deal_vat_rows_include_meal_at_19():
    booking = _stay(nights=2)
    result = vat.deal_vat("stay", booking)
    by_rate = {row["rate"]: row["gross"] for row in result["rows"]}
    assert by_rate[Decimal("19.00")] == Decimal("24.00")
    assert result["gross"] == Decimal(booking.total_cents) / 100


def test_deal_lines_meal_row():
    rows = deal_lines.deal_lines("stay", _stay(nights=2))
    assert any(r["label"] == "Verpflegung" and r["total"] == Decimal("24.00") for r in rows)


def test_revenue_split_on_fulfilled():
    booking = _stay(nights=2)
    StayBookingSM().apply(booking, StayBooking.STATUS_FULFILLED)
    entries = RevenueEntry.objects.filter(source="stay", source_ref__startswith=str(booking.id))
    by_ref = {e.source_ref: e for e in entries}
    assert by_ref[f"{booking.id}:meal"].vat_rate == Decimal("19.00")
    assert by_ref[f"{booking.id}:meal"].amount == Decimal("24.00")
    assert by_ref[str(booking.id)].vat_rate == Decimal("7.00")
    assert sum(e.amount for e in entries) == Decimal(booking.total_cents) / 100


def test_revenue_without_meal_single_entry():
    booking = _stay(snapshot={})
    StayBookingSM().apply(booking, StayBooking.STATUS_FULFILLED)
    assert RevenueEntry.objects.filter(source="stay").count() == 1
