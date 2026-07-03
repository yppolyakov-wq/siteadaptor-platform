"""B2.3 — напоминание о неоплаченном билете."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import tasks
from apps.events.models import Event, Ticket
from apps.notifications.models import Notification
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _pending_ticket(hours_ago=8, price_cents=2500):
    event = Event.objects.create(
        title="Retreat",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
        capacity=10,
        price_cents=price_cents,
    )
    ticket = Ticket.objects.create(
        event=event,
        customer=Customer.objects.create(name="Kim", email="kim@test.de"),
        reference_code=f"E-PR{hours_ago}",
        quantity=1,
        price_cents=price_cents,
        payment_state=Ticket.PAYMENT_PENDING,
    )
    Ticket.objects.filter(pk=ticket.pk).update(
        created_at=timezone.now() - timedelta(hours=hours_ago)
    )
    return ticket


def test_ticket_reminder_once_and_filters():
    _pending_ticket()
    assert tasks.send_due_payment_reminders() == 1
    n = Notification.objects.get(type="ticket_payment_reminder")
    assert "Zahlung" in n.subject
    assert tasks.send_due_payment_reminders() == 0
    _pending_ticket(hours_ago=1)  # свежий
    assert tasks.send_due_payment_reminders() == 0
