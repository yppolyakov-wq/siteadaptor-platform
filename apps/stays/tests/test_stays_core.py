"""Track E / E1: ядро date-range-брони — anti-overbook по ночам (критичный),
quantity, блоки, min_nights/max_guests, FSM, переиспользование Customer."""

import uuid
from datetime import date, timedelta

import pytest

from apps.core.fsm import IllegalTransition
from apps.promotions.models import Customer
from apps.stays import availability, services
from apps.stays.models import StayBooking, StayUnit, UnitBlock
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db

# Базовая дата — заезд D0; ночи отсчитываем смещениями от неё.
D0 = date(2026, 8, 1)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 8000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, arr_off, dep_off, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book_stay(
        unit,
        arrival=D0 + timedelta(days=arr_off),
        departure=D0 + timedelta(days=dep_off),
        **kwargs,
    )


# --- anti-overbook по ночам -------------------------------------------------------


def test_overlapping_range_rejected():
    unit = _unit()
    _book(unit, 0, 3)  # занимает ночи D0, D0+1, D0+2 (выезд D0+3 свободен)
    # точное совпадение, частичное слева/справа, вложенный интервал
    for arr, dep in [(0, 3), (-1, 1), (2, 5), (1, 2)]:
        with pytest.raises(services.StayUnavailable):
            _book(unit, arr, dep)


def test_checkout_day_is_free():
    unit = _unit()
    _book(unit, 0, 3)  # ночи D0..D0+2; выезд D0+3
    _book(unit, 3, 5)  # заезд в день выезда предыдущего — ок
    _book(unit, -2, 0)  # выезд в день заезда предыдущего — ок
    assert StayBooking.objects.filter(unit=unit).count() == 3


def test_quantity_allows_parallel_stays():
    unit = _unit(quantity=2)
    _book(unit, 0, 3)
    _book(unit, 0, 3)  # второй параллельный — ок (2 одинаковых юнита)
    with pytest.raises(services.StayUnavailable):
        _book(unit, 0, 3)  # третий — нет


def test_cancelled_stay_frees_nights():
    unit = _unit()
    booking = _book(unit, 0, 3)
    StayBookingSM().apply(booking, "cancelled")
    _book(unit, 0, 3)  # ночи освободились


def test_block_blocks_booking():
    unit = _unit()
    # блок ВКЛЮЧИТЕЛЬНО: ночи D0, D0+1, D0+2 недоступны
    UnitBlock.objects.create(
        unit=unit, start_date=D0, end_date=D0 + timedelta(days=2), reason="Renovierung"
    )
    with pytest.raises(services.StayUnavailable):
        _book(unit, 0, 3)
    _book(unit, 3, 5)  # после блока — ок


def test_min_nights_enforced():
    unit = _unit(min_nights=2)
    with pytest.raises(services.MinStay):
        _book(unit, 0, 1)  # одна ночь < 2
    _book(unit, 0, 2)  # две ночи — ок


def test_max_guests_enforced():
    unit = _unit(max_guests=2)
    with pytest.raises(services.MaxGuests):
        _book(unit, 0, 2, guests=3)
    _book(unit, 0, 2, guests=2)


def test_invalid_range_rejected():
    unit = _unit()
    with pytest.raises(ValueError):
        _book(unit, 3, 1)  # выезд раньше заезда
    with pytest.raises(ValueError):
        _book(unit, 1, 1)  # ноль ночей


# --- перенос (move) ---------------------------------------------------------------


def test_move_stay_respects_occupancy():
    unit = _unit()
    first = _book(unit, 0, 3)
    second = _book(unit, 5, 7)
    # перенос second на занятый диапазон — нельзя
    with pytest.raises(services.StayUnavailable):
        services.move_stay(second, arrival=D0, departure=D0 + timedelta(days=2))
    # на свободный — ок, и собственные ночи себе не мешают
    services.move_stay(first, arrival=D0 + timedelta(days=10), departure=D0 + timedelta(days=12))
    first.refresh_from_db()
    assert first.arrival == D0 + timedelta(days=10)


# --- FSM и клиент -----------------------------------------------------------------


def test_stay_sm_paths():
    unit = _unit()
    booking = _book(unit, 0, 3)
    assert booking.status == "pending"
    sm = StayBookingSM()
    booking = sm.apply(booking, "confirmed")
    booking = sm.apply(booking, "fulfilled")
    assert booking.status == "fulfilled"

    other = _book(unit, 5, 7)
    with pytest.raises(IllegalTransition):
        sm.apply(other, "no_show")  # no_show только из confirmed
    other = sm.apply(other, "confirmed")
    assert sm.apply(other, "no_show").status == "no_show"


def test_auto_confirm_customer_reuse_and_snapshot():
    unit = _unit(price_cents=9500)
    existing = Customer.objects.create(name="Stamm", email="gast@test.de")
    booking = _book(unit, 0, 3, email="GAST@test.de", auto_confirm=True)
    assert booking.status == "confirmed"
    assert booking.customer == existing
    assert booking.reference_code.startswith("S-")
    assert booking.price_cents == 9500  # снимок цены
    assert booking.nights == 3
    assert booking.total_cents == 28500


# --- подбор свободных юнитов -------------------------------------------------------


def test_free_units_filters_busy_and_capacity():
    busy = _unit()
    free = _unit()
    _book(busy, 0, 3)
    result = availability.free_units(D0, D0 + timedelta(days=3))
    assert free in result
    assert busy not in result

    small = _unit(max_guests=2)
    big_party = availability.free_units(D0 + timedelta(days=20), D0 + timedelta(days=22), guests=4)
    assert small not in big_party
