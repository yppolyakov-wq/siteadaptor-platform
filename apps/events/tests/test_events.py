"""A6a: ядро событий — анти-овердрафт мест, FSM, выручка в finance."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.events.models import Event, Ticket
from apps.events.services import EventNotBookable, SoldOut, book_ticket
from apps.events.state_machine import TicketSM
from apps.finance.models import RevenueEntry

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Yoga-Retreat",
        "starts_at": timezone.now() + timedelta(days=7),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 5000,
        "capacity": 10,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- бронирование / анти-овердрафт -------------------------------------------------


def test_book_ticket_reduces_seats_left():
    event = _event(capacity=5)
    book_ticket(event, name="K", email="k@test.de", quantity=2)
    assert event.seats_sold == 2
    assert event.seats_left == 3


def test_book_ticket_respects_capacity():
    event = _event(capacity=3)
    book_ticket(event, name="A", email="a@test.de", quantity=2)
    with pytest.raises(SoldOut) as exc:
        book_ticket(event, name="B", email="b@test.de", quantity=2)
    assert exc.value.available == 1


def test_unlimited_capacity_never_sold_out():
    event = _event(capacity=0)
    book_ticket(event, name="A", email="a@test.de", quantity=99)
    assert event.seats_left is None and event.is_sold_out is False


def test_cancelled_ticket_frees_seats():
    event = _event(capacity=2)
    ticket = book_ticket(event, name="A", email="a@test.de", quantity=2)
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    assert event.seats_sold == 0
    book_ticket(event, name="B", email="b@test.de", quantity=2)  # снова влезает


def test_draft_event_not_bookable():
    event = _event(status=Event.STATUS_DRAFT)
    with pytest.raises(EventNotBookable):
        book_ticket(event, name="K", email="k@test.de")


def test_answers_snapshot_stored():
    event = _event(questions=["Allergien?"])
    ticket = book_ticket(event, name="K", email="k@test.de", answers={"Allergien?": "Nüsse"})
    assert ticket.answers == {"Allergien?": "Nüsse"}


# --- выручка через FSM -------------------------------------------------------------


def test_confirm_records_revenue_once():
    event = _event(price_cents=5000)
    ticket = book_ticket(event, name="K", email="k@test.de", quantity=2)
    TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    entry = RevenueEntry.objects.get(source="event", source_ref=str(ticket.id))
    assert entry.amount == Decimal("100.00")  # 2 × 50.00
    assert entry.vat_rate == Decimal("19.00")


def test_auto_confirm_books_and_records():
    event = _event(price_cents=3000)
    ticket = book_ticket(event, name="K", email="k@test.de", quantity=1, auto_confirm=True)
    assert ticket.status == Ticket.STATUS_CONFIRMED
    assert RevenueEntry.objects.filter(source="event", source_ref=str(ticket.id)).count() == 1


def test_free_event_no_revenue():
    event = _event(price_cents=0)
    ticket = book_ticket(event, name="K", email="k@test.de", auto_confirm=True)
    assert not RevenueEntry.objects.filter(source="event", source_ref=str(ticket.id)).exists()
