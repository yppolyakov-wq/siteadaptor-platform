"""KA-12 GA-3 (Gastro): места стола — отказ ручной записи с «Trotzdem eintragen»,
отказ онлайн, предупреждение при переносе, правка мест/вместимости без 500."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import public_views, services, table_rules, views
from apps.booking.models import AvailabilityRule, Booking, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _table(seats=2, **kw):
    resource = Resource.objects.create(
        name=f"Tisch {uuid.uuid4().hex[:4]}",
        type=Resource.TYPE_TABLE,
        capacity=1,
        seats=seats,
        **kw,
    )
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(17, 0),
        end_time=time(22, 0),
        slot_minutes=60,
    )
    return resource


def _start():
    return datetime.combine(DAY, time(18, 0), tzinfo=timezone.get_current_timezone())


def _req(path, data):
    request = RequestFactory().post(path, data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.3"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    request.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    return request


def test_seats_exceeded_only_for_tables_with_seats():
    assert table_rules.seats_exceeded(Resource(seats=2), 3) == 2
    assert table_rules.seats_exceeded(Resource(seats=2), 2) is None
    assert table_rules.seats_exceeded(Resource(seats=None), 30) is None
    assert table_rules.seats_exceeded(Resource(seats=2, counts_party_size=True), 30) is None


def test_manual_refused_then_override_allows():
    table = _table()
    with pytest.raises(services.ManualBookingRefused):
        services.create_manual(table, start=_start(), minutes=60, party_size=6, name="G")
    booking, _w = services.create_manual(
        table, start=_start(), minutes=60, party_size=6, name="G", override_seats=True
    )
    assert booking.party_size == 6


def test_cabinet_create_uses_trotzdem_checkbox():
    table = _table()
    data = {
        "resource": str(table.pk),
        "start": _start().isoformat(),
        "party_size": "6",
        "name": "G",
    }
    views.booking_create(_req("/dashboard/booking/new/", data))
    assert not Booking.objects.filter(resource=table).exists()
    views.booking_create(_req("/dashboard/booking/new/", {**data, "override_hours": "1"}))
    assert Booking.objects.filter(resource=table, party_size=6).exists()


def test_online_refuses_party_larger_than_table():
    table = _table()
    data = {
        "start": _start().isoformat(),
        "end": (_start() + timedelta(hours=1)).isoformat(),
        "name": "Gast",
        "email": f"{uuid.uuid4().hex[:6]}@example.com",
        "party_size": "5",
    }
    request = _req(f"/termin/{table.pk}/buchen/", data)
    response = public_views.termin_book(request, pk=table.pk)
    assert response.status_code == 302
    assert not Booking.objects.filter(resource=table).exists()


def test_move_to_small_table_warns_not_refuses():
    big = _table(seats=8)
    small = _table(seats=2)
    booking, _w = services.create_manual(big, start=_start(), minutes=60, party_size=6, name="G")
    request = _req("/x/", {"resource": str(small.pk), "start": _start().isoformat()})
    views._move_booking(request, booking)
    booking.refresh_from_db()
    assert booking.resource_id == small.pk
    texts = [str(m) for m in get_messages(request)]
    assert any("2" in t and "Plätze" in t for t in texts)


def test_resource_settings_edit_seats_and_garbage_capacity():
    table = _table(seats=None)
    data = {
        "action": "resource_settings",
        "resource": str(table.pk),
        "seats_present": "1",
        "capacity": "abc",
        "seats": "4",
        "zone": "Terrasse",
        "sort_order": "3",
    }
    views.resources(_req("/dashboard/booking/resources/", data))
    table.refresh_from_db()
    assert (table.capacity, table.seats, table.zone, table.sort_order) == (1, 4, "Terrasse", 3)
    # старая форма без сентинела места не стирает
    views.resources(
        _req(
            "/dashboard/booking/resources/",
            {"action": "resource_settings", "resource": str(table.pk)},
        )
    )
    table.refresh_from_db()
    assert table.seats == 4


def test_create_with_garbage_capacity_no_500():
    views.resources(
        _req(
            "/dashboard/booking/resources/",
            {"action": "resource", "name": "Tisch X", "capacity": "zwei", "seats": "2"},
        )
    )
    table = Resource.objects.get(name="Tisch X")
    assert table.capacity == 1 and table.seats == 2


def test_seats_enforced_inside_book_for_every_path():
    table = _table()
    with pytest.raises(services.SeatsExceeded):
        services.book(
            table, start=_start(), end=_start() + timedelta(hours=1), name="G", party_size=4
        )
    assert issubclass(services.SeatsExceeded, services.SlotTaken)


def test_garbage_seats_keeps_old_value():
    table = _table(seats=4)
    data = {
        "action": "resource_settings",
        "resource": str(table.pk),
        "seats_present": "1",
        "capacity": "1",
        "seats": "vier",
    }
    views.resources(_req("/dashboard/booking/resources/", data))
    table.refresh_from_db()
    assert table.seats == 4
    views.resources(_req("/dashboard/booking/resources/", {**data, "seats": ""}))
    table.refresh_from_db()
    assert table.seats is None
