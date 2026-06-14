"""A6b: кабинет событий — CRUD, действия FSM, ручная запись, CSV-ростер."""

from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import views
from apps.events.models import Event, Ticket

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _req(method, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    return request


def _event(**kw):
    defaults = {
        "title": "Workshop",
        "starts_at": timezone.now() + timedelta(days=5),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 2000,
        "capacity": 10,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_create_event_converts_price_and_questions():
    resp = views.event_create(
        _req(
            "post",
            {
                "title": "Yoga",
                "starts_at": "2026-07-01T18:00",
                "price_eur": "25.00",
                "capacity": "12",
                "questions_text": "Allergien?\nLevel?",
            },
        )
    )
    assert resp.status_code == 302
    event = Event.objects.get(title="Yoga")
    assert event.price_cents == 2500
    assert event.questions == ["Allergien?", "Level?"]


def test_publish_action():
    event = _event(status=Event.STATUS_DRAFT)
    views.event_action(_req("post", {"target": "published"}), pk=event.pk)
    event.refresh_from_db()
    assert event.status == Event.STATUS_PUBLISHED


def test_manual_ticket_add_confirmed():
    event = _event()
    views.ticket_add(_req("post", {"name": "Kunde", "quantity": "2"}), pk=event.pk)
    ticket = Ticket.objects.get(event=event)
    assert ticket.quantity == 2
    assert ticket.status == Ticket.STATUS_CONFIRMED


def test_ticket_mark_paid_confirms_pending():
    event = _event()
    from apps.events.services import book_ticket

    ticket = book_ticket(event, name="K", email="k@test.de")  # pending
    views.ticket_action(_req("post", {"target": "paid"}), pk=event.pk, tid=ticket.pk)
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_PAID
    assert ticket.status == Ticket.STATUS_CONFIRMED


def test_roster_csv_lists_attendees_with_answers():
    event = _event(questions=["Allergien?"])
    from apps.events.services import book_ticket

    book_ticket(
        event, name="Anna", email="a@test.de", answers={"Allergien?": "Nüsse"}, auto_confirm=True
    )
    resp = views.roster_csv(_req("get"), pk=event.pk)
    body = resp.content.decode("utf-8-sig")
    assert "Anna" in body and "Allergien?" in body and "Nüsse" in body
