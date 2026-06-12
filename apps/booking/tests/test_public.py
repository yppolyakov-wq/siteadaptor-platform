"""Track D / D3b: публичная запись /termin/ — сетка слотов, выбор, бронь,
валидация слота по расписанию, гейтинг модуля."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views
from apps.booking.models import AvailabilityRule, Booking, ClosedDate, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = date(2026, 7, 1)  # среда, заведомо в будущем относительно тестов


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _resource(slot_minutes=60, capacity=1):
    resource = Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}", capacity=capacity)
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(10, 0),
        end_time=time(13, 0),
        slot_minutes=slot_minutes,
    )
    return resource


def _req(method="get", path="/termin/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build(business_type="cafe")
    return request


# --- сетка слотов ------------------------------------------------------------------


def _customer():
    from apps.promotions.models import Customer

    return Customer.objects.create(name="Gast")


def test_free_slots_grid_and_occupancy():
    resource = _resource()
    slots = availability.free_slots(resource, DAY)
    assert [(s.hour, e.hour) for s, e in slots] == [(10, 11), (11, 12), (12, 13)]

    # занять середину — слот пропадает из сетки
    start, end = slots[1]
    Booking.objects.create(
        resource=resource,
        customer=_customer(),
        reference_code="T-TEST01",
        start=start,
        end=end,
    )
    remaining = availability.free_slots(resource, DAY)
    assert [(s.hour, e.hour) for s, e in remaining] == [(10, 11), (12, 13)]


def test_free_slots_closed_date_and_other_weekday():
    resource = _resource()
    assert availability.free_slots(resource, DAY + timedelta(days=1)) == []  # нет правила
    ClosedDate.objects.create(resource=None, date=DAY, reason="Feiertag")
    assert availability.free_slots(resource, DAY) == []


# --- публичный флоу ----------------------------------------------------------------


def test_index_redirects_with_single_resource():
    resource = _resource()
    response = public_views.termin_index(_req())
    assert response.status_code == 302 and str(resource.pk) in response.url


def test_slots_page_renders_and_selects():
    resource = _resource()
    start_iso = availability.free_slots(resource, DAY)[0][0].isoformat()
    body = public_views.termin_slots(
        _req(path=f"/termin/{resource.pk}/", data={"tag": DAY.isoformat()}), pk=resource.pk
    ).content.decode()
    assert "10:00" in body and "12:00" in body

    body = public_views.termin_slots(
        _req(
            path=f"/termin/{resource.pk}/",
            data={"tag": DAY.isoformat(), "slot": start_iso},
        ),
        pk=resource.pk,
    ).content.decode()
    assert 'name="start"' in body and "Book now" in body


def test_book_flow_creates_booking():
    resource = _resource()
    start, end = availability.free_slots(resource, DAY)[0]
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "name": "Karla",
            "email": "karla@test.de",
            "party_size": "3",
        },
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302
    booking = Booking.objects.get(customer__email="karla@test.de")
    assert response.url.endswith(f"/t/{booking.reference_code}/")
    assert booking.party_size == 3 and booking.start == start

    body = public_views.termin_confirmation(_req(), code=booking.reference_code).content.decode()
    assert booking.reference_code in body

    # слот исчез из сетки; повторная попытка отбрасывается валидацией
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302 and "/termin/" in response.url
    assert Booking.objects.count() == 1


def test_book_rejects_interval_outside_schedule():
    resource = _resource()
    tz = timezone.get_current_timezone()
    start = datetime.combine(DAY, time(22, 0), tzinfo=tz)  # вне рабочего окна
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "name": "Hacker",
        },
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302 and Booking.objects.count() == 0


def test_booking_module_gated():
    tenant = TenantFactory.build(disabled_modules=["booking"])
    with pytest.raises(Http404):
        public_views.termin_index(_req(tenant=tenant))
    resource = _resource()
    with pytest.raises(Http404):
        public_views.termin_slots(_req(tenant=tenant), pk=resource.pk)
