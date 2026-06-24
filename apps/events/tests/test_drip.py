"""R9: pre/post-event drip-письма (напоминание + post-event), idempotent."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services, tasks
from apps.events.models import Event
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=3),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _confirmed_ticket(event, email="a@test.de"):
    return services.book_ticket(event, name="A", email=email, auto_confirm=True)


# --- reminders -------------------------------------------------------------
def test_reminder_sent_within_window_once():
    ev = _event(starts_at=timezone.now() + timedelta(days=3))  # в окне 7 дней
    ticket = _confirmed_ticket(ev)
    assert tasks.send_due_event_reminders() == 1
    ticket.refresh_from_db()
    assert ticket.reminder_sent_at is not None
    assert Notification.objects.filter(type="ticket_reminder").exists()
    # повторный прогон — ничего (idempotent)
    assert tasks.send_due_event_reminders() == 0


def test_reminder_skips_event_outside_window():
    ev = _event(starts_at=timezone.now() + timedelta(days=30))  # за горизонтом 7 дней
    _confirmed_ticket(ev)
    assert tasks.send_due_event_reminders() == 0


def test_reminder_skips_pending_ticket():
    ev = _event(starts_at=timezone.now() + timedelta(days=2))
    services.book_ticket(ev, name="P", email="p@test.de")  # pending (не auto_confirm)
    assert tasks.send_due_event_reminders() == 0


# --- post-event ------------------------------------------------------------
def test_post_event_sent_after_end_once():
    start = timezone.now() - timedelta(days=2)
    ev = _event(starts_at=start, ends_at=start + timedelta(hours=6))  # закончилось ~2 дня назад
    ticket = _confirmed_ticket(ev)
    assert tasks.send_due_post_event() == 1
    ticket.refresh_from_db()
    assert ticket.post_event_sent_at is not None
    assert Notification.objects.filter(type="ticket_post_event").exists()
    assert tasks.send_due_post_event() == 0  # idempotent


def test_post_event_skips_future_event():
    ev = _event(starts_at=timezone.now() + timedelta(days=5))
    _confirmed_ticket(ev)
    assert tasks.send_due_post_event() == 0


def test_post_event_uses_starts_at_when_no_end():
    ev = _event(starts_at=timezone.now() - timedelta(days=2), ends_at=None)
    _confirmed_ticket(ev)
    assert tasks.send_due_post_event() == 1
