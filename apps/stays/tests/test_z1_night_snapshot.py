"""KA-12 Zimmer Z-1: цена сделки — из снимка брони, а не из сегодняшних тарифов.

DF-Z1: скидка владельца (DC-5) пересчитывала проживание по СЕГОДНЯШНИМ ценам и
без числа номеров → после правки сезона или у брони на 2 номера итог «съезжал».
Снимок `night_prices` — цены ночей на момент брони (после тарифа/occupancy, до
авто-скидки, на ОДИН номер): разбивка карточки читает его, а не прайс.
DF-Z2: легаси `stay_to_invoice` (7 % на всё, net) заменён общим счётом из сделки."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core import deal_discount
from apps.core.tests.dates import future_month_start
from apps.stays import pricing, services
from apps.stays.models import RatePlan, SeasonRate, StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 3)
    kw.setdefault("max_guests", 2)
    return StayUnit.objects.create(name=f"DZ {uuid.uuid4().hex[:6]}", **kw)


def _book(unit, nights=3, rooms=1, **kw):
    return services.book_stay(
        unit,
        arrival=D0,
        departure=D0 + timedelta(days=nights),
        name="Gast",
        email=f"{uuid.uuid4().hex[:6]}@t.de",
        adults=2,
        rooms=rooms,
        **kw,
    )


def test_snapshot_written_per_room_and_sums_to_room_total():
    unit = _unit()
    SeasonRate.objects.create(unit=unit, start_date=D0, end_date=D0, price_cents=15000)
    plan = RatePlan.objects.create(name="HP", surcharge_cents=2000)
    b = _book(unit, nights=3, rooms=2, rate_plan=plan)
    assert [row[0] for row in b.night_prices] == [
        (D0 + timedelta(days=i)).isoformat() for i in range(3)
    ]
    per_room = sum(row[1] for row in b.night_prices)
    assert per_room == 17000 + 12000 + 12000
    assert b.total_cents == per_room * 2 - b.auto_discount_cents + b.kurtaxe_cents


def test_owner_discount_uses_snapshot_not_todays_prices():
    """DF-Z1: сезон изменили ПОСЛЕ брони — скидка меняет итог ровно на скидку."""
    unit = _unit()
    b = _book(unit, nights=3, rooms=2)
    before = b.total_cents
    SeasonRate.objects.create(
        unit=unit, start_date=D0, end_date=D0 + timedelta(days=5), price_cents=30000
    )
    deal_discount.set_discount("stay", b, cents=1000)
    b.refresh_from_db()
    assert b.total_cents == before - 1000


def test_owner_discount_change_replaces_previous_discount():
    unit = _unit()
    b = _book(unit, nights=2, rooms=2)
    before = b.total_cents
    deal_discount.set_discount("stay", b, cents=500)
    b.refresh_from_db()
    deal_discount.set_discount("stay", b, cents=1500)
    b.refresh_from_db()
    assert b.total_cents == before - 1500
    deal_discount.set_discount("stay", b, cents=0)
    b.refresh_from_db()
    assert b.total_cents == before


def test_breakdown_reads_snapshot():
    unit = _unit()
    b = _book(unit, nights=2)
    SeasonRate.objects.create(
        unit=unit, start_date=D0, end_date=D0 + timedelta(days=5), price_cents=30000
    )
    rows = pricing.booking_breakdown(b)
    assert [r["cents"] for r in rows] == [10000, 10000]
    assert rows[0]["date"] == D0


def test_breakdown_legacy_booking_without_snapshot_falls_back():
    unit = _unit()
    b = _book(unit, nights=2)
    StayBooking.objects.filter(pk=b.pk).update(night_prices=[])
    b.refresh_from_db()
    assert [r["cents"] for r in pricing.booking_breakdown(b)] == [10000, 10000]


def test_move_reprice_rewrites_snapshot():
    unit = _unit()
    b = _book(unit, nights=2)
    SeasonRate.objects.create(
        unit=unit,
        start_date=D0 + timedelta(days=10),
        end_date=D0 + timedelta(days=20),
        price_cents=20000,
    )
    services.move_stay(b, arrival=D0 + timedelta(days=10), departure=D0 + timedelta(days=13))
    b.refresh_from_db()
    assert [row[1] for row in b.night_prices] == [20000, 20000, 20000]


def test_move_keep_rate_shifts_snapshot_dates():
    unit = _unit()
    b = _book(unit, nights=2)
    services.move_stay(
        b, arrival=D0 + timedelta(days=7), departure=D0 + timedelta(days=9), reprice=False
    )
    b.refresh_from_db()
    assert b.night_prices[0][0] == (D0 + timedelta(days=7)).isoformat()
    assert sum(row[1] for row in b.night_prices) == 20000


def test_cabinet_invoice_action_uses_deal_invoice(monkeypatch):
    """DF-Z2: «Rechnung» из списка броней — общий счёт сделки (Bruttomethode,
    питание 19 %), черновик переиспользуется; легаси-функции больше нет."""
    from apps.stays import services as stay_services

    assert not hasattr(stay_services, "stay_to_invoice")
    from apps.core.deal_invoice import invoice_for_deal

    unit = _unit()
    plan = RatePlan.objects.create(name="HP", meal_plan="half_board", surcharge_cents=2000)
    b = _book(unit, nights=2, rate_plan=plan)
    first, created = invoice_for_deal("stay", b, tenant=None)
    second, created2 = invoice_for_deal("stay", b, tenant=None)
    assert created and not created2 and first.pk == second.pk
    assert first.gross == Decimal(b.total_cents) / 100
    assert "19.00" in {line["vat_rate"] for line in first.lines}


def test_huge_discount_is_capped_and_reversible():
    """Ревью Z-1 (HIGH): скидка больше проживания обрезается до проживания —
    следующая правка восстанавливает проживание точно, итог не раздувается."""
    unit = _unit()
    b = _book(unit, nights=2, rooms=2)
    before = b.total_cents
    deal_discount.set_discount("stay", b, cents=999_999)
    b.refresh_from_db()
    assert b.total_cents == b.kurtaxe_cents
    assert b.discount_cents == before - b.kurtaxe_cents
    deal_discount.set_discount("stay", b, cents=0)
    b.refresh_from_db()
    assert b.total_cents == before


def test_legacy_clamped_discount_falls_back_to_repricing():
    unit = _unit()
    b = _book(unit, nights=2, rooms=2)
    before = b.total_cents
    StayBooking.objects.filter(pk=b.pk).update(discount_cents=999_999, total_cents=b.kurtaxe_cents)
    b.refresh_from_db()
    deal_discount.set_discount("stay", b, cents=0)
    b.refresh_from_db()
    assert b.total_cents == before


def test_breakdown_multiplies_by_rooms():
    unit = _unit()
    b = _book(unit, nights=2, rooms=2)
    rows = pricing.booking_breakdown(b)
    assert sum(r["cents"] for r in rows) == b.total_cents + b.auto_discount_cents - b.kurtaxe_cents
