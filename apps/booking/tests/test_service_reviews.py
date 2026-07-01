"""UA4-4b: отзывы об услуге — верификация брони, приём формы, рендер на детали."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import public_views
from apps.booking.models import Booking, Resource, Service
from apps.booking.reviews import has_booked
from apps.promotions.models import Customer
from apps.reviews.models import Review
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="cafe")
    return request


def _service(**kw):
    return Service.objects.create(
        name=kw.pop("name", "Ölwechsel"),
        description=kw.pop("description", "Inkl. Öl und Filter."),
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
        **kw,
    )


def _book(service, email, *, status=Booking.STATUS_CONFIRMED, ref=None):
    resource = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}", capacity=1)
    customer = Customer.objects.create(name="Kunde", email=email)
    start = timezone.now() + timedelta(days=1)
    return Booking.objects.create(
        resource=resource,
        service=service,
        customer=customer,
        reference_code=f"B-{uuid.uuid4().hex[:6].upper()}" if ref is None else ref,
        start=start,
        end=start + timedelta(minutes=30),
        status=status,
    )


# --- верификация брони (fail-closed) ---------------------------------------
def test_has_booked_true_for_customer():
    s = _service()
    _book(s, "gast@test.de")
    assert has_booked(s, "Gast@Test.de") is True  # без регистра


def test_has_booked_false_without_booking():
    assert has_booked(_service(), "nobody@test.de") is False


def test_has_booked_false_for_cancelled():
    s = _service()
    _book(s, "gast@test.de", status=Booking.STATUS_CANCELLED)
    assert has_booked(s, "gast@test.de") is False


def test_has_booked_false_for_no_show():
    s = _service()
    _book(s, "gast@test.de", status=Booking.STATUS_NO_SHOW)
    assert has_booked(s, "gast@test.de") is False


def test_has_booked_true_for_fulfilled():
    s = _service()
    _book(s, "gast@test.de", status=Booking.STATUS_FULFILLED)
    assert has_booked(s, "gast@test.de") is True  # исполненная бронь = был клиентом


def test_has_booked_false_for_other_service():
    s1, s2 = _service(), _service()
    _book(s1, "gast@test.de")
    assert has_booked(s2, "gast@test.de") is False


# --- рендер отзывов на детали услуги ---------------------------------------
def test_service_detail_renders_reviews_and_form():
    s = _service()
    Review.objects.create(
        entity_kind="service",
        entity_id=s.pk,
        rating=5,
        author_name="Petra",
        email="p@t.de",
        comment="Top Service",
    )
    body = public_views.service_detail(_req(path=f"/leistung/{s.pk}/"), pk=s.pk).content.decode()
    assert "Petra" in body and "Top Service" in body
    assert 'id="bewertungen"' in body
    assert f"/leistung/{s.pk}/bewerten/" in body  # action формы


# --- приём формы (POST) -----------------------------------------------------
def test_submit_creates_review_for_verified_customer():
    s = _service()
    _book(s, "gast@test.de")
    data = {"author_name": "Gast", "email": "gast@test.de", "rating": "4", "comment": "Gut"}
    resp = public_views.service_review_submit(
        _req("post", f"/leistung/{s.pk}/bewerten/", data), pk=s.pk
    )
    assert resp.status_code == 302
    r = Review.objects.get(entity_kind="service", entity_id=s.pk, email="gast@test.de")
    assert r.rating == 4 and r.verified and r.is_published


def test_submit_rejected_for_non_customer():
    s = _service()
    data = {"author_name": "Fake", "email": "fake@test.de", "rating": "5", "comment": "x"}
    resp = public_views.service_review_submit(
        _req("post", f"/leistung/{s.pk}/bewerten/", data), pk=s.pk
    )
    assert resp.status_code == 302
    assert not Review.objects.filter(entity_kind="service", entity_id=s.pk).exists()


def test_submit_invalid_rating_rejected():
    s = _service()
    _book(s, "gast@test.de")
    data = {"author_name": "Gast", "email": "gast@test.de", "rating": "9"}
    public_views.service_review_submit(_req("post", f"/leistung/{s.pk}/bewerten/", data), pk=s.pk)
    assert not Review.objects.filter(entity_kind="service", entity_id=s.pk).exists()
