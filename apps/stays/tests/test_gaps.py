"""Д1-0: извлечённый `short_gaps` — паритет с прежним `_has_short_gaps` + точные дыры."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.stays import gaps, services, views
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db

D0 = timezone.localdate()


def _unit():
    return StayUnit.objects.create(
        name=f"Z {uuid.uuid4().hex[:6]}", price_cents=10000, max_guests=4
    )


def _book(unit, a, d):
    services.book_stay(
        unit, arrival=D0 + timedelta(days=a), departure=D0 + timedelta(days=d), name="G"
    )


def test_bounded_short_gap_is_reported_with_start_and_nights():
    unit = _unit()
    _book(unit, 1, 3)
    _book(unit, 6, 9)
    assert gaps.short_gaps([unit]) == [(unit, D0 + timedelta(days=3), 3)]
    assert views._has_short_gaps([unit]) is True


@pytest.mark.parametrize(
    "bookings, expected",
    [
        ([], False),  # ни одной брони — не дыра, просто свободно
        ([(1, 3)], False),  # справа не ограничено
        ([(1, 3), (8, 10)], False),  # 5 ночей > max 3
        ([(1, 3), (4, 6)], True),  # одна ночь
    ],
)
def test_parity_with_bool_helper(bookings, expected):
    unit = _unit()
    for a, d in bookings:
        _book(unit, a, d)
    assert views._has_short_gaps([unit]) is expected
    assert bool(gaps.short_gaps([unit])) is expected
