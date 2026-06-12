"""Track D / D3a: ядро записи по времени — anti-double-book (критичный),
capacity, исключения расписания, FSM, переиспользование Customer."""

import uuid
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking, ClosedDate, Resource
from apps.booking.state_machine import BookingSM
from apps.core.fsm import IllegalTransition
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _resource(**kwargs):
    return Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}", **kwargs)


def _slot(hour=12, minutes=0, duration=60):
    start = timezone.make_aware(datetime(2026, 7, 1, hour, minutes))
    return start, start + timedelta(minutes=duration)


def _book(resource, start, end, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book(resource, start=start, end=end, **kwargs)


# --- anti-double-book -------------------------------------------------------------


def test_overlapping_interval_rejected():
    resource = _resource()
    start, end = _slot(12)
    _book(resource, start, end)
    # точное совпадение, частичное перекрытие слева/справа, вложенный интервал
    for offset_start, offset_end in [(0, 0), (-30, -30), (30, 30), (15, -15)]:
        with pytest.raises(services.SlotTaken):
            _book(
                resource,
                start + timedelta(minutes=offset_start),
                end + timedelta(minutes=offset_end),
            )


def test_adjacent_intervals_allowed():
    resource = _resource()
    start, end = _slot(12)
    _book(resource, start, end)
    _book(resource, end, end + timedelta(hours=1))  # впритык после — ок
    _book(resource, start - timedelta(hours=1), start)  # впритык до — ок
    assert Booking.objects.filter(resource=resource).count() == 3


def test_capacity_allows_parallel_bookings():
    resource = _resource(capacity=2)
    start, end = _slot(18)
    _book(resource, start, end)
    _book(resource, start, end)  # второй параллельный — ок (зал на 2 посадки)
    with pytest.raises(services.SlotTaken):
        _book(resource, start, end)  # третий — нет


def test_cancelled_booking_frees_slot():
    resource = _resource()
    start, end = _slot(12)
    booking = _book(resource, start, end)
    BookingSM().apply(booking, "cancelled")
    _book(resource, start, end)  # слот освободился


def test_closed_date_blocks_booking():
    resource = _resource()
    start, end = _slot(12)
    ClosedDate.objects.create(resource=None, date=start.date(), reason="Feiertag")
    with pytest.raises(services.ResourceClosed):
        _book(resource, start, end)
    # другой день — работает
    _book(resource, start + timedelta(days=1), end + timedelta(days=1))


def test_invalid_interval_rejected():
    resource = _resource()
    start, end = _slot(12)
    with pytest.raises(ValueError):
        _book(resource, end, start)


# --- FSM и клиент -----------------------------------------------------------------


def test_booking_sm_paths():
    resource = _resource()
    start, end = _slot(10)
    booking = _book(resource, start, end)
    assert booking.status == "pending"
    sm = BookingSM()
    booking = sm.apply(booking, "confirmed")
    booking = sm.apply(booking, "fulfilled")
    assert booking.status == "fulfilled"

    other = _book(resource, start + timedelta(hours=2), end + timedelta(hours=2))
    with pytest.raises(IllegalTransition):
        sm.apply(other, "no_show")  # no_show только из confirmed
    other = sm.apply(other, "confirmed")
    assert sm.apply(other, "no_show").status == "no_show"


def test_auto_confirm_and_customer_reuse():
    resource = _resource()
    start, end = _slot(9)
    existing = Customer.objects.create(name="Stamm", email="gast@test.de")
    booking = _book(resource, start, end, email="GAST@test.de", auto_confirm=True)
    assert booking.status == "confirmed"
    assert booking.customer == existing
    assert booking.reference_code.startswith("T-")
