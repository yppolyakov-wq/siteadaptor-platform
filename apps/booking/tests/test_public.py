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


# --- G9: групповые курсы (видимая вместимость) ------------------------------------


def test_free_slots_with_spots_counts_remaining():
    resource = _resource(capacity=3)
    slots = availability.free_slots_with_spots(resource, DAY)
    assert slots and all(spots == 3 for _s, _e, spots in slots)
    start, end, _ = slots[0]
    Booking.objects.create(
        resource=resource, customer=_customer(), reference_code="T-GRP001", start=start, end=end
    )
    after = availability.free_slots_with_spots(resource, DAY)
    assert next(sp for s, _e, sp in after if s == start) == 2  # одно место занято


def test_group_slots_page_shows_spots():
    resource = _resource(capacity=3)
    body = public_views.termin_slots(
        _req(path=f"/termin/{resource.pk}/", data={"tag": DAY.isoformat()}), pk=resource.pk
    ).content.decode()
    assert "Group course" in body and "3 spots" in body  # int-счётчик локаль-стабилен


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


# --- P2.5b: депозит ----------------------------------------------------------------


def _resource_with_deposit(cents=1000):
    resource = _resource()
    resource.deposit_cents = cents
    resource.save(update_fields=["deposit_cents"])
    return resource


def test_book_with_deposit_redirects_to_stripe(monkeypatch, settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_x"
    resource = _resource_with_deposit()
    tenant = TenantFactory.build(
        business_type="cafe", payments_enabled=True, stripe_connect_id="acct_1"
    )
    start, end = availability.free_slots(resource, DAY)[0]
    monkeypatch.setattr(
        public_views.payments, "deposit_checkout_url", lambda b, t, **kw: "https://stripe/checkout"
    )
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {"start": start.isoformat(), "end": end.isoformat(), "name": "Karla", "email": "k@test.de"},
        tenant=tenant,
    )
    response = public_views.termin_book(request, pk=resource.pk)
    assert response.status_code == 302
    assert response.url == "https://stripe/checkout"
    booking = Booking.objects.get(customer__email="k@test.de")
    assert booking.payment_state == "pending"
    assert booking.deposit_cents == 1000


def test_book_with_deposit_but_no_payments_is_normal(monkeypatch):
    resource = _resource_with_deposit()
    tenant = TenantFactory.build(business_type="cafe", payments_enabled=False)
    start, end = availability.free_slots(resource, DAY)[0]
    called = {"stripe": False}
    monkeypatch.setattr(
        public_views.payments,
        "deposit_checkout_url",
        lambda b, t, **kw: called.__setitem__("stripe", True) or "x",
    )
    request = _req(
        "post",
        f"/termin/{resource.pk}/buchen/",
        {"start": start.isoformat(), "end": end.isoformat(), "name": "Ben", "email": "b@test.de"},
        tenant=tenant,
    )
    response = public_views.termin_book(request, pk=resource.pk)
    booking = Booking.objects.get(customer__email="b@test.de")
    assert response.url.endswith(f"/t/{booking.reference_code}/")  # обычная бронь
    assert called["stripe"] is False
    assert booking.payment_state == "none"
