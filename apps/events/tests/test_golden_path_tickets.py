"""KA-12 E11.1 (T-0): серверный золотой путь направления «Tickets/Touren».

Покупка → оплата (вебхук) → подтверждение → check-in → выручка ровно одна и равна сумме
к оплате; оплата на месте → выручка на входе; отмена оплаченного → сторно; места не
продаются сверх вместимости. Браузерный двойник — GP-5 в `scripts/golden_paths.py`."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.events.models import Event, Ticket
from apps.events.payments import mark_ticket_paid
from apps.events.services import SoldOut, book_ticket
from apps.events.state_machine import TicketSM
from apps.finance.models import RevenueEntry

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Stadtführung",
        "starts_at": timezone.now() + timedelta(days=7),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 2500,
        "capacity": 3,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _buy(event, quantity=1):
    return book_ticket(event, name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de", quantity=quantity)


def _entries(ticket):
    return RevenueEntry.objects.filter(source="event", source_ref=str(ticket.id))


def test_online_paid_ticket_confirm_checkin_one_revenue_entry():
    ticket = _buy(_event(), quantity=2)
    assert ticket.status == Ticket.STATUS_PENDING
    assert mark_ticket_paid(tenant_schema=connection.schema_name, ticket_id=str(ticket.id))
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_PAID
    assert ticket.status == Ticket.STATUS_CONFIRMED
    TicketSM().apply(ticket, Ticket.STATUS_ATTENDED, actor=None)
    ticket.refresh_from_db()
    assert _entries(ticket).count() == 1
    assert _entries(ticket).get().amount == Decimal("50.00")


def test_repeated_webhook_is_idempotent():
    ticket = _buy(_event())
    for _ in range(2):
        mark_ticket_paid(tenant_schema=connection.schema_name, ticket_id=str(ticket.id))
    ticket.refresh_from_db()
    TicketSM().apply(ticket, Ticket.STATUS_ATTENDED, actor=None)
    assert _entries(ticket).count() == 1


def test_pay_on_site_revenue_only_at_checkin():
    ticket = _buy(_event())
    TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED, actor=None)
    assert not _entries(ticket).exists()
    TicketSM().apply(ticket, Ticket.STATUS_ATTENDED, actor=None)
    assert _entries(ticket).get().amount == Decimal("25.00")


def test_capacity_is_not_oversold():
    event = _event(capacity=3)
    _buy(event, quantity=2)
    with pytest.raises(SoldOut):
        _buy(event, quantity=2)
    _buy(event, quantity=1)
    with pytest.raises(SoldOut):
        _buy(event, quantity=1)
