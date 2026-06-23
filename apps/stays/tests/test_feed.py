"""G8: фид цен/наличия для метапоиска (Google Hotel Center / channel)."""

import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.stays import public_views
from apps.stays.models import StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db


def _req():
    req = RequestFactory().get("/stays/feed.json")
    req.tenant = type(
        "T",
        (),
        {"is_module_active": lambda self, k: True, "name": "Pension", "address": "", "city": ""},
    )()
    return req


def test_feed_lists_rooms_with_prices_and_availability():
    StayUnit.objects.create(name="Doppelzimmer", quantity=2, price_cents=9000, max_guests=2)
    resp = public_views.stays_feed(_req())
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["property"]["currency"] == "EUR"
    assert data["days"] == public_views.FEED_DAYS
    assert len(data["rooms"]) == 1
    room = data["rooms"][0]
    assert room["name"] == "Doppelzimmer" and room["deeplink"].endswith(f"{room['id']}/")
    assert len(room["nights"]) == public_views.FEED_DAYS
    night = room["nights"][0]
    assert night["price"] == 90.0 and night["units_free"] == 2 and night["available"] is True


def test_feed_reflects_bookings():
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=10000, max_guests=2)
    arrival = timezone.localdate() + timedelta(days=3)
    book_stay(unit, arrival=arrival, departure=arrival + timedelta(days=2), name="A", adults=2)
    data = json.loads(public_views.stays_feed(_req()).content)
    nights = {n["date"]: n for n in data["rooms"][0]["nights"]}
    booked = nights[arrival.isoformat()]
    assert booked["units_free"] == 0 and booked["available"] is False


def test_feed_404_when_stays_off():
    from django.http import Http404

    req = RequestFactory().get("/stays/feed.json")
    req.tenant = type("T", (), {"is_module_active": lambda self, k: False})()
    with pytest.raises(Http404):
        public_views.stays_feed(req)
