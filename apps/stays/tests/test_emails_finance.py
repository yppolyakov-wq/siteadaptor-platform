"""Track E / E3: письма по статусам (через apps.notifications), запись выручки
на выезд (finance, НДС 7 %) и напоминание о заезде (ровно одно на бронь)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finance.models import RevenueEntry
from apps.notifications.models import Notification
from apps.stays import services, tasks
from apps.stays.models import StayUnit
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db

D0 = date(2026, 10, 1)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"FeWo {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, arr_off=0, dep_off=3, **kwargs):
    kwargs.setdefault("name", "Gast")
    kwargs.setdefault("email", f"{uuid.uuid4().hex[:6]}@t.de")
    return services.book_stay(
        unit,
        arrival=D0 + timedelta(days=arr_off),
        departure=D0 + timedelta(days=dep_off),
        **kwargs,
    )


def test_created_and_status_emails():
    booking = _book(_unit())
    assert Notification.objects.filter(dedupe_key=f"stay:{booking.id}:created:customer").exists()

    booking = StayBookingSM().apply(booking, "confirmed")
    confirmed = Notification.objects.get(dedupe_key=f"stay:{booking.id}:confirmed:customer")
    assert "bestätigt" in confirmed.payload["body"].lower()

    StayBookingSM().apply(booking, "cancelled")
    assert Notification.objects.filter(dedupe_key=f"stay:{booking.id}:cancelled:customer").exists()


def test_fulfilled_records_revenue_at_7_percent():
    booking = _book(_unit(price_cents=9000))  # 3 ночи × 90 € = 270 €
    booking = StayBookingSM().apply(booking, "confirmed")
    StayBookingSM().apply(booking, "fulfilled")

    entry = RevenueEntry.objects.get(source="stay", source_ref=str(booking.id))
    assert entry.amount == Decimal("270.00")
    assert entry.vat_rate == Decimal("7.00")
    assert entry.customer_id == booking.customer_id

    # идемпотентность хука: повторный fulfilled не дублирует (повтор статуса — no-op)
    StayBookingSM().apply(booking, "fulfilled")
    assert RevenueEntry.objects.filter(source="stay", source_ref=str(booking.id)).count() == 1


def test_reminder_sent_once_within_horizon():
    today = timezone.localdate()
    unit = _unit()
    near = services.book_stay(
        unit,
        arrival=today + timedelta(days=1),
        departure=today + timedelta(days=3),
        name="Near",
        email="near@t.de",
    )
    far = services.book_stay(
        unit,
        arrival=today + timedelta(days=30),
        departure=today + timedelta(days=32),
        name="Far",
        email="far@t.de",
    )
    StayBookingSM().apply(near, "confirmed")
    StayBookingSM().apply(far, "confirmed")

    assert tasks.send_due_stay_reminders(today=today) == 1  # только near в горизонте
    near.refresh_from_db()
    assert near.reminder_sent_at is not None
    assert Notification.objects.filter(dedupe_key=f"stay:{near.id}:reminder:customer").exists()
    assert tasks.send_due_stay_reminders(today=today) == 0  # второго нет
