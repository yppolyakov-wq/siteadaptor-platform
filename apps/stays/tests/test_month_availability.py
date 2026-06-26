"""A5/C1: availability.month_availability — occupancy на календарный месяц для
визуального календаря витрины (без UI)."""

from datetime import date

import pytest

from apps.stays import availability
from apps.stays.models import StayUnit, UnitBlock
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db


def _unit(**kw):
    defaults = {"name": "FeWo", "price_cents": 9000, "max_guests": 4, "quantity": 1}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def _by_date(rows):
    return {r["date"]: r for r in rows}


def test_month_returns_all_days_with_fields():
    unit = _unit()
    rows = availability.month_availability(unit, 2027, 2, today=date(2027, 1, 1))
    assert len(rows) == 28  # февраль 2027 (не високосный)
    assert all({"date", "in_past", "free", "is_free"} <= set(r) for r in rows)
    # без броней/блоков и в будущем — все свободны
    assert all(r["is_free"] and r["free"] == 1 for r in rows)


def test_booking_marks_nights_occupied_but_not_checkout_day():
    unit = _unit(quantity=1)
    # бронь 10–13 февраля → заняты ночи 10,11,12; 13 (выезд) снова свободен
    book_stay(unit, arrival=date(2027, 2, 10), departure=date(2027, 2, 13), name="A", adults=2)
    rows = _by_date(availability.month_availability(unit, 2027, 2, today=date(2027, 1, 1)))
    assert rows[date(2027, 2, 10)]["free"] == 0 and rows[date(2027, 2, 10)]["is_free"] is False
    assert rows[date(2027, 2, 12)]["is_free"] is False
    assert rows[date(2027, 2, 13)]["is_free"] is True  # день выезда свободен
    assert rows[date(2027, 2, 9)]["is_free"] is True  # до заезда свободен


def test_quantity_partial_occupancy_still_free():
    unit = _unit(quantity=2)
    book_stay(
        unit, arrival=date(2027, 2, 5), departure=date(2027, 2, 7), name="A", adults=2, rooms=1
    )
    rows = _by_date(availability.month_availability(unit, 2027, 2, today=date(2027, 1, 1)))
    # один из двух номеров занят → free=1, всё ещё доступно
    assert rows[date(2027, 2, 5)]["free"] == 1 and rows[date(2027, 2, 5)]["is_free"] is True


def test_block_marks_day_occupied_inclusive():
    unit = _unit(quantity=1)
    UnitBlock.objects.create(unit=unit, start_date=date(2027, 2, 20), end_date=date(2027, 2, 21))
    rows = _by_date(availability.month_availability(unit, 2027, 2, today=date(2027, 1, 1)))
    # блок [20,21] включительно → оба заняты
    assert rows[date(2027, 2, 20)]["is_free"] is False
    assert rows[date(2027, 2, 21)]["is_free"] is False
    assert rows[date(2027, 2, 22)]["is_free"] is True


def test_past_days_not_selectable():
    unit = _unit(quantity=1)
    today = date(2027, 2, 15)
    rows = _by_date(availability.month_availability(unit, 2027, 2, today=today))
    past = rows[date(2027, 2, 10)]
    assert past["in_past"] is True and past["is_free"] is False  # прошлое — не выбрать
    assert past["free"] == 1  # но физически свободен (для информации)
    future = rows[date(2027, 2, 20)]
    assert future["in_past"] is False and future["is_free"] is True
