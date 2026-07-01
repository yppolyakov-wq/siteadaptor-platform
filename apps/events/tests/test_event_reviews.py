"""UA4-4b: отзывы о событии — верификация билета, приём формы, рендер на детали."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views
from apps.events.models import Event, Ticket
from apps.events.reviews import has_ticket
from apps.promotions.models import Customer
from apps.reviews.models import Review
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build()
    return request


def _event(**kw):
    return Event.objects.create(
        title=kw.pop("title", "Konzert"),
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
        price_cents=0,
        capacity=50,
        **kw,
    )


def _ticket(event, email, *, status=Ticket.STATUS_CONFIRMED):
    customer = Customer.objects.create(name="Fan", email=email)
    return Ticket.objects.create(
        event=event,
        customer=customer,
        reference_code=f"E-{uuid.uuid4().hex[:6].upper()}",
        status=status,
    )


# --- верификация билета (fail-closed) --------------------------------------
def test_has_ticket_true_for_attendee():
    e = _event()
    _ticket(e, "fan@test.de")
    assert has_ticket(e, "Fan@Test.de") is True


def test_has_ticket_false_without_ticket():
    assert has_ticket(_event(), "nobody@test.de") is False


def test_has_ticket_false_for_cancelled():
    e = _event()
    _ticket(e, "fan@test.de", status=Ticket.STATUS_CANCELLED)
    assert has_ticket(e, "fan@test.de") is False


def test_has_ticket_true_for_attended():
    e = _event()
    _ticket(e, "fan@test.de", status=Ticket.STATUS_ATTENDED)
    assert has_ticket(e, "fan@test.de") is True


def test_has_ticket_false_for_other_event():
    e1, e2 = _event(), _event()
    _ticket(e1, "fan@test.de")
    assert has_ticket(e2, "fan@test.de") is False


# --- рендер отзывов на детали события --------------------------------------
def test_event_detail_renders_reviews_and_form():
    e = _event()
    Review.objects.create(
        entity_kind="event",
        entity_id=e.pk,
        rating=5,
        author_name="Mara",
        email="m@t.de",
        comment="Toll",
    )
    body = public_views.veranstaltung_detail(
        _req(path=f"/veranstaltung/{e.pk}/"), pk=e.pk
    ).content.decode()
    assert "Mara" in body and "Toll" in body
    assert 'id="bewertungen"' in body
    assert f"/veranstaltung/{e.pk}/bewerten/" in body


# --- приём формы (POST) -----------------------------------------------------
def test_submit_creates_review_for_verified_attendee():
    e = _event()
    _ticket(e, "fan@test.de")
    data = {"author_name": "Fan", "email": "fan@test.de", "rating": "4", "comment": "Super"}
    resp = public_views.event_review_submit(
        _req("post", f"/veranstaltung/{e.pk}/bewerten/", data), pk=e.pk
    )
    assert resp.status_code == 302
    r = Review.objects.get(entity_kind="event", entity_id=e.pk, email="fan@test.de")
    assert r.rating == 4 and r.verified


def test_submit_rejected_for_non_attendee():
    e = _event()
    data = {"author_name": "Fake", "email": "fake@test.de", "rating": "5"}
    public_views.event_review_submit(
        _req("post", f"/veranstaltung/{e.pk}/bewerten/", data), pk=e.pk
    )
    assert not Review.objects.filter(entity_kind="event", entity_id=e.pk).exists()
