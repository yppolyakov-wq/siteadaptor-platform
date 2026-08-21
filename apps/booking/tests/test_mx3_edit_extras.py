"""MX-3: правка допов записи (Termin) из карточки — action=extras."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services, views
from apps.booking.models import Booking, Resource, Service
from apps.core.models import Extra

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data):
    request = RequestFactory().post("/dashboard/booking/x/action/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    n = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{n}", email=f"o-{n}@test.de", password="pw12345678"
    )
    return request


def _booking():
    resource = Resource.objects.create(name="Platz 1", capacity=1)
    service = Service.objects.create(name="Schnitt", price_cents=3000, duration_minutes=30)
    start = timezone.now() + timedelta(days=3)
    b = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=30),
        name="Kunde",
        service=service,
        price_cents=3000,
    )
    return service, b


def test_extras_action_rebuilds_snapshot():
    service, b = _booking()
    addressed = Extra.objects.create(
        label="Pflege",
        price_cents=900,
        scope=Extra.SCOPE_BOOKING,
        entity_kind="service",
        entity_id=str(service.pk),
    )
    views.booking_action(_req({"action": "extras", "extra": [str(addressed.pk)]}), pk=b.pk)
    b.refresh_from_db()
    assert [e["id"] for e in b.extras] == [str(addressed.pk)]
    assert b.total_cents == 3900


def test_extras_action_rejects_foreign_addressed_option():
    service, b = _booking()
    other = Service.objects.create(name="Farbe", price_cents=5000, duration_minutes=60)
    foreign = Extra.objects.create(
        label="Nur für Farbe",
        price_cents=900,
        scope=Extra.SCOPE_BOOKING,
        entity_kind="service",
        entity_id=str(other.pk),
    )
    views.booking_action(_req({"action": "extras", "extra": [str(foreign.pk)]}), pk=b.pk)
    b.refresh_from_db()
    assert b.extras == []


def test_extras_action_blocked_on_closed_booking():
    service, b = _booking()
    b.status = Booking.STATUS_CANCELLED
    b.save(update_fields=["status"])
    extra = Extra.objects.create(label="X", price_cents=100, scope=Extra.SCOPE_BOOKING)
    views.booking_action(_req({"action": "extras", "extra": [str(extra.pk)]}), pk=b.pk)
    b.refresh_from_db()
    assert b.extras == []  # закрытая сделка не правится
