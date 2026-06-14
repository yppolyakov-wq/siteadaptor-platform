"""A6c: витрина событий — список/детали, покупка билета, оплата, гейтинг."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views
from apps.events.models import Event, Ticket
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/veranstaltung/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Konzert",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 50,
        "questions": ["Anmerkung?"],
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_index_requires_module():
    tenant = TenantFactory.build(disabled_modules=["events"])
    with pytest.raises(Http404):
        public_views.veranstaltung_index(_req("get", tenant=tenant))


def test_index_lists_published_future():
    _event(title="Sichtbar")
    _event(title="Entwurf", status=Event.STATUS_DRAFT)
    _event(title="Vergangen", starts_at=timezone.now() - timedelta(days=1))
    body = public_views.veranstaltung_index(_req("get")).content.decode()
    assert "Sichtbar" in body
    assert "Entwurf" not in body and "Vergangen" not in body


def test_free_event_books_confirmed_with_answers():
    event = _event(price_cents=0)
    resp = public_views.veranstaltung_book(
        _req("post", {"name": "Anna", "email": "a@test.de", "quantity": "2", "q0": "Vegan"}),
        pk=event.pk,
    )
    assert resp.status_code == 302
    ticket = Ticket.objects.get(event=event)
    assert ticket.quantity == 2
    assert ticket.status == Ticket.STATUS_CONFIRMED  # бесплатное → сразу
    assert ticket.answers == {"Anmerkung?": "Vegan"}


def test_honeypot_blocks():
    event = _event()
    public_views.veranstaltung_book(_req("post", {"name": "Bot", "website": "spam"}), pk=event.pk)
    assert Ticket.objects.filter(event=event).count() == 0


def test_paid_event_without_payments_stays_pending():
    event = _event(price_cents=2500)
    tenant = TenantFactory.build()  # payments_enabled False
    resp = public_views.veranstaltung_book(
        _req("post", {"name": "K", "email": "k@test.de"}, tenant=tenant), pk=event.pk
    )
    assert resp.status_code == 302
    assert Ticket.objects.get(event=event).status == Ticket.STATUS_PENDING


def test_sold_out_blocks_booking():
    event = _event(capacity=1)
    from apps.events.services import book_ticket

    book_ticket(event, name="A", email="a@test.de", quantity=1, auto_confirm=True)
    public_views.veranstaltung_book(_req("post", {"name": "B", "email": "b@test.de"}), pk=event.pk)
    assert event.tickets.count() == 1
