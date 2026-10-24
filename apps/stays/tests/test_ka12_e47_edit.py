"""KA-12 E4.7a: правка брони без «Neu berechnen» — цена за ночь держится, Kurtaxe свежая,
и правка — одно целое (отказ не оставляет половину изменений)."""

from datetime import timedelta

import pytest

from apps.stays import services, views
from apps.stays.models import StaySettings
from apps.stays.tests.test_belegungsplan import (  # noqa: F401
    D0,
    _book,
    _req,
    _tenant_urlconf,
    _unit,
)

pytestmark = pytest.mark.django_db


def _update(booking, **data):
    base = {
        "action": "update",
        "arrival": booking.arrival.isoformat(),
        "departure": booking.departure.isoformat(),
        "adults": str(booking.adults),
        "children": str(booking.children),
        "note": booking.note,
    }
    base.update(data)
    return views.stay_action(_req("post", data=base), pk=booking.pk)


def _kurtaxe(cents):
    s = StaySettings.load()
    s.kurtaxe_cents = cents
    s.save()


def test_more_nights_without_reprice_keeps_nightly_rate():
    unit = _unit(price_cents=10000, max_guests=4)
    booking = _book(unit, 1, 4)  # 3 ночи → 300 €
    _update(booking, departure=(D0 + timedelta(days=5)).isoformat())  # 4 ночи
    booking.refresh_from_db()
    assert booking.nights == 4 and booking.total_cents == 40000


def test_kurtaxe_follows_adults_and_nights_without_reprice():
    _kurtaxe(200)
    unit = _unit(price_cents=10000, max_guests=4)
    booking = _book(unit, 1, 4)
    booking.refresh_from_db()
    lodging = booking.total_cents - booking.kurtaxe_cents
    _update(booking, adults="2")
    booking.refresh_from_db()
    assert booking.kurtaxe_cents == 2 * 3 * 200
    assert booking.total_cents == lodging + 1200
    _update(booking, departure=(D0 + timedelta(days=5)).isoformat())
    booking.refresh_from_db()
    assert booking.kurtaxe_cents == 2 * 4 * 200


def test_drag_same_nights_keeps_total():
    unit = _unit(price_cents=10000, max_guests=4)
    booking = _book(unit, 1, 4)
    before = booking.total_cents
    services.move_stay(
        booking, arrival=D0 + timedelta(days=5), departure=D0 + timedelta(days=8), reprice=False
    )
    booking.refresh_from_db()
    assert booking.total_cents == before


def test_failed_update_rolls_back_guests_and_note():
    unit = _unit(price_cents=10000, max_guests=4, quantity=1)
    booking = _book(unit, 1, 4)
    _book(unit, 6, 9)  # занято
    _update(
        booking,
        adults="3",
        note="neu",
        departure=(D0 + timedelta(days=8)).isoformat(),
    )
    booking.refresh_from_db()
    assert booking.adults != 3 and booking.note != "neu"
    assert booking.departure == D0 + timedelta(days=4)
