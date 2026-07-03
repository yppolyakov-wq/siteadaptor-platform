"""B2.3 — напоминание о неоплаченной предоплате проживания."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.stays import tasks
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db


def _pending_stay(hours_ago=8, arrival_in=5):
    unit = StayUnit.objects.create(name="Zimmer 1", price_cents=8000)
    booking = StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Kim", email="kim@test.de"),
        reference_code=f"S-{hours_ago}{arrival_in}X",
        arrival=timezone.localdate() + timedelta(days=arrival_in),
        departure=timezone.localdate() + timedelta(days=arrival_in + 2),
        payment_state=StayBooking.PAYMENT_PENDING,
        deposit_cents=2000,
    )
    StayBooking.objects.filter(pk=booking.pk).update(
        created_at=timezone.now() - timedelta(hours=hours_ago)
    )
    return booking


def test_stay_reminder_once_and_filters():
    _pending_stay()
    assert tasks.send_due_payment_reminders() == 1
    assert Notification.objects.filter(type="stay_payment_reminder").count() == 1
    assert tasks.send_due_payment_reminders() == 0
    _pending_stay(arrival_in=-1)  # заезд прошёл
    _pending_stay(hours_ago=1)  # свежая
    assert tasks.send_due_payment_reminders() == 0
