"""G5: мультикомнатное бронирование (несколько номеров в одной брони)."""

from datetime import date, timedelta

import pytest

from apps.stays import availability
from apps.stays.models import StayBooking, StayUnit
from apps.stays.services import MaxGuests, StayUnavailable, book_stay

pytestmark = pytest.mark.django_db

D0 = date(2030, 6, 3)  # Montag (будни)


def _unit(**kw):
    defaults = {"name": "Doppelzimmer", "quantity": 3, "price_cents": 10000, "max_guests": 2}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def test_books_multiple_rooms_and_scales_price():
    unit = _unit(quantity=3, price_cents=10000, max_guests=2)
    booking = book_stay(
        unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="Familie",
        email="f@test.de",
        adults=4,  # 2 номера × 2 гостя
        rooms=2,
    )
    assert booking.rooms == 2
    # 2 ночи × 100 € × 2 номера = 400 €
    assert booking.total_cents == 40000


def test_capacity_is_per_room_times_count():
    unit = _unit(quantity=3, max_guests=2)
    # 5 гостей в 2 номерах (вместимость 4) → MaxGuests
    with pytest.raises(MaxGuests):
        book_stay(
            unit,
            arrival=D0,
            departure=D0 + timedelta(days=1),
            name="X",
            adults=5,
            rooms=2,
        )


def test_multi_room_respects_quantity():
    unit = _unit(quantity=2, max_guests=2)
    # запрос 3 номеров при quantity=2 → недоступно
    with pytest.raises(StayUnavailable):
        book_stay(unit, arrival=D0, departure=D0 + timedelta(days=1), name="X", adults=2, rooms=3)


def test_availability_counts_booked_rooms():
    unit = _unit(quantity=3, max_guests=2)
    book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="A", adults=2, rooms=2)
    # 2 из 3 заняты → ещё 1 свободен, 2 — нет
    assert availability.range_available(unit, D0, D0 + timedelta(days=2), needed=1) is True
    assert availability.range_available(unit, D0, D0 + timedelta(days=2), needed=2) is False


def test_overbooking_blocked_across_bookings():
    unit = _unit(quantity=2, max_guests=2)
    book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="A", adults=2, rooms=1)
    book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="B", adults=2, rooms=1)
    # обе ночи теперь заняты обоими номерами → третья бронь падает
    with pytest.raises(StayUnavailable):
        book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="C", adults=2, rooms=1)
    assert StayBooking.objects.filter(unit=unit).count() == 2
