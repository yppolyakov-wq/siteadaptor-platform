"""G2: post-stay письмо — отправка после выезда, ровно одно, окно подхвата."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit
from apps.stays.tasks import send_due_post_stay

pytestmark = pytest.mark.django_db


def _booking(dep_days_ago, status=StayBooking.STATUS_CONFIRMED, **kw):
    today = timezone.localdate()
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)
    cust = Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de")
    departure = today - timedelta(days=dep_days_ago)
    return StayBooking.objects.create(
        unit=unit,
        customer=cust,
        reference_code="S-" + uuid.uuid4().hex[:6].upper(),
        arrival=departure - timedelta(days=2),
        departure=departure,
        guests=2,
        adults=2,
        status=status,
        **kw,
    )


def test_post_stay_sent_once_after_checkout():
    b = _booking(dep_days_ago=1)
    assert send_due_post_stay() == 1
    b.refresh_from_db()
    assert b.post_stay_sent_at is not None
    assert Notification.objects.filter(dedupe_key=f"stay:{b.id}:post_stay:customer").exists()
    # повторный прогон — не дублирует
    assert send_due_post_stay() == 0


def test_not_sent_before_checkout_window():
    _booking(dep_days_ago=0)  # выезд сегодня — рано (нужно ≥1 день назад)
    assert send_due_post_stay() == 0


def test_not_sent_for_cancelled():
    _booking(dep_days_ago=2, status=StayBooking.STATUS_CANCELLED)
    assert send_due_post_stay() == 0


def test_old_departure_outside_window_skipped():
    _booking(dep_days_ago=30)  # слишком давно — вне окна подхвата (7 дней)
    assert send_due_post_stay() == 0
