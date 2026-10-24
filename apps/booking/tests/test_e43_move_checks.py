"""KA-12 E4.3: перенос записи — каникулы жёстко, вне часов только с подтверждением,
новое время = письмо клиенту «verschoben» и новое напоминание."""

from datetime import timedelta

import pytest

from apps.booking import services, tasks, views
from apps.booking.models import AvailabilityRule, Booking, ClosedDate
from apps.booking.state_machine import BookingSM
from apps.booking.tests.test_cabinet import (  # noqa: F401
    _booking,
    _req,
    _resource,
    _slot,
    _tenant_urlconf,
)
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _ruled_booking():
    r = _resource()
    start, end = _slot(days_ahead=7, hour=10)
    for wd in range(7):
        AvailabilityRule.objects.create(
            resource=r, weekday=wd, start_time="09:00", end_time="17:00", slot_minutes=60
        )
    b = _booking(resource=r, slot=(start, end))
    BookingSM().apply(b, "confirmed")
    return b


def test_move_to_closed_day_refused():
    b = _ruled_booking()
    ClosedDate.objects.create(date=(b.start + timedelta(days=1)).date(), reason="Urlaub")
    with pytest.raises(services.ResourceClosed):
        services.move(b, start=b.start + timedelta(days=1), end=b.end + timedelta(days=1))


def test_move_outside_hours_needs_override():
    b = _ruled_booking()
    late = b.start.replace(hour=20)
    with pytest.raises(services.OutsideHours):
        services.move(b, start=late, end=late + timedelta(hours=1))
    services.move(b, start=late, end=late + timedelta(hours=1), override_hours=True)
    b.refresh_from_db()
    assert b.start == late


def test_move_mails_customer_and_rearms_reminder(django_capture_on_commit_callbacks):
    b = _ruled_booking()
    Booking.objects.filter(pk=b.pk).update(reminder_sent_at=b.start - timedelta(days=1))
    b.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        services.move(b, start=b.start + timedelta(hours=2), end=b.end + timedelta(hours=2))
    b.refresh_from_db()
    assert b.reminder_sent_at is None
    assert Notification.objects.filter(type="booking_moved").count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        services.move(b, start=b.start + timedelta(hours=1), end=b.end + timedelta(hours=1))
    assert Notification.objects.filter(type="booking_moved").count() == 2


def test_reminder_again_after_move():
    b = _ruled_booking()
    now = b.start - timedelta(hours=3)
    assert tasks.send_due_reminders(now=now) == 1
    b.refresh_from_db()
    services.move(b, start=b.start + timedelta(hours=1), end=b.end + timedelta(hours=1))
    assert tasks.send_due_reminders(now=now) == 1


def test_manual_booking_outside_hours_needs_override():
    b = _ruled_booking()
    day = b.start.date()
    data = {"resource": str(b.resource_id), "start": f"{day}T20:00", "name": "Spät"}
    before = Booking.objects.count()
    views.booking_create(_req("post", "/dashboard/booking/neu/", data))
    assert Booking.objects.count() == before
    views.booking_create(_req("post", "/dashboard/booking/neu/", {**data, "override_hours": "1"}))
    assert Booking.objects.count() == before + 1
