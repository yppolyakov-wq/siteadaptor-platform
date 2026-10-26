"""KA-12 GA-4 (Gastro): «Tisch reservieren» — гость выбирает время и число гостей,
стол подбирается сам (наименьший подходящий; занятый уступает следующему)."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import public_views, services, table_rules
from apps.booking.models import AvailabilityRule, Booking, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _table(name, seats, **kw):
    resource = Resource.objects.create(
        name=f"{name} {uuid.uuid4().hex[:4]}",
        type=Resource.TYPE_TABLE,
        capacity=1,
        seats=seats,
        **kw,
    )
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(18, 0),
        end_time=time(20, 0),
        slot_minutes=60,
    )
    return resource


def _start(hour=18):
    return datetime.combine(DAY, time(hour, 0), tzinfo=timezone.get_current_timezone())


def _request(method, path, data=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.4"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="restaurant", site_config={})
    return request


def _book(party, hour=18):
    email = f"{uuid.uuid4().hex[:6]}@example.com"
    data = {
        "start": _start(hour).isoformat(),
        "end": (_start(hour) + timedelta(hours=1)).isoformat(),
        "name": "Gast",
        "email": email,
        "party_size": str(party),
    }
    response = public_views.tisch_book(_request("post", "/termin/tisch/buchen/", data))
    return response, Booking.objects.filter(customer__email=email).first()


def test_fitting_tables_smallest_first_and_filters():
    two = _table("Zwei", 2)
    four = _table("Vier", 4)
    _table("Pool", 4, counts_party_size=True)
    _table("VIP", 4, bookable_online=False)
    _table("Groß", 8, min_seats=5)
    assert [t.pk for t in table_rules.fitting_tables(2)] == [two.pk, four.pk]
    assert [t.pk for t in table_rules.fitting_tables(3)] == [four.pk]
    assert table_rules.fitting_tables(9) == []


def test_slots_merge_tables():
    _table("Zwei", 2)
    _table("Vier", 4)
    slots = table_rules.table_slots(DAY, 2)
    assert [(s.hour, len(t)) for s, _e, t in slots] == [(18, 2), (19, 2)]


def test_booking_takes_smallest_free_table_then_next():
    two = _table("Zwei", 2)
    four = _table("Vier", 4)
    _r, first = _book(2)
    assert first.resource_id == two.pk
    _r, second = _book(2)
    assert second.resource_id == four.pk
    response, third = _book(2)
    assert third is None and response.status_code == 302


def test_race_lost_table_falls_through_to_next(monkeypatch):
    two = _table("Zwei", 2)
    four = _table("Vier", 4)
    real = services.book

    def taken_first(resource, **kw):
        if resource.pk == two.pk:
            raise services.SlotTaken()
        return real(resource, **kw)

    monkeypatch.setattr(services, "book", taken_first)
    _r, booking = _book(2)
    assert booking.resource_id == four.pk


def test_no_fitting_table_no_booking():
    _table("Zwei", 2)
    response, booking = _book(6)
    assert booking is None and response.status_code == 302


def test_slots_page_and_index_card():
    _table("Zwei", 2)
    body = public_views.tisch_slots(
        _request("get", "/termin/tisch/", {"tag": DAY.isoformat(), "gaeste": "2"})
    ).content.decode()
    assert (
        "data-party-picker" in body and "/termin/tisch/buchen/" not in body
    )  # форма — после выбора
    index = public_views.termin_index(_request("get", "/termin/"))
    assert index.status_code == 302 and index.url.startswith("/termin/tisch/")


def test_offline_table_not_bookable_by_pk():
    vip = _table("VIP", 4, bookable_online=False)
    with pytest.raises(Http404):
        public_views.termin_book(_request("post", f"/termin/{vip.pk}/buchen/"), pk=vip.pk)


def test_no_tables_page_404():
    with pytest.raises(Http404):
        public_views.tisch_slots(_request("get", "/termin/tisch/"))


def test_settings_min_seats_clamped_and_online_flag():
    from django.contrib.auth import get_user_model

    from apps.booking import views

    table = _table("Vier", 4)
    request = _request(
        "post",
        "/dashboard/booking/resources/",
        {
            "action": "resource_settings",
            "resource": str(table.pk),
            "seats_present": "1",
            "capacity": "1",
            "seats": "4",
            "min_seats": "9",
        },
    )
    request.user = get_user_model().objects.create_user(username=f"u{uuid.uuid4().hex[:6]}")
    views.resources(request)
    table.refresh_from_db()
    assert table.min_seats == 4 and table.bookable_online is False
