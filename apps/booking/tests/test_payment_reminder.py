"""B2.2 — напоминание о неоплаченном депозите брони + «Jetzt bezahlen»."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import services, tasks
from apps.booking.models import Booking, Resource
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _pending_booking(hours_ago=8, start_in_days=2):
    start = (timezone.now() + timedelta(days=start_in_days)).replace(
        minute=0, second=0, microsecond=0
    )
    booking = services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="Kim",
        email="kim@test.de",
    )
    Booking.objects.filter(pk=booking.pk).update(
        payment_state=Booking.PAYMENT_PENDING,
        deposit_cents=1000,
        created_at=timezone.now() - timedelta(hours=hours_ago),
    )
    booking.refresh_from_db()
    return booking


def test_deposit_reminder_once_and_filters():
    _pending_booking()
    assert tasks.send_due_payment_reminders() == 1
    n = Notification.objects.get(type="booking_payment_reminder")
    assert "Anzahlung" in n.subject
    assert tasks.send_due_payment_reminders() == 0  # дедуп
    # прошедшая бронь и свежая — не трогаем
    _pending_booking(start_in_days=-1)
    _pending_booking(hours_ago=1)
    assert tasks.send_due_payment_reminders() == 0


def test_termin_pay_regenerates_checkout(monkeypatch):
    import uuid

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    monkeypatch.setattr("apps.billing.connect.is_connect_configured", lambda: True)
    monkeypatch.setattr(
        "apps.booking.payments.deposit_checkout_url", lambda *a, **k: "https://stripe.test/dep"
    )
    booking = _pending_booking()
    r = RequestFactory().get(f"/t/{booking.reference_code}/bezahlen/")
    r.META["REMOTE_ADDR"] = f"10.8.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.tenant = TenantFactory.build(payments_enabled=True)
    resp = public_views.termin_pay(r, code=booking.reference_code)
    assert resp.status_code == 302 and resp.url == "https://stripe.test/dep"
