"""P2.5b: депозит за бронь — оплата (вебхук) → paid + авто-confirm / ручная проверка."""

import uuid
from datetime import datetime, timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.billing import webhooks
from apps.booking.models import Booking, Resource
from apps.booking.payments import mark_deposit_paid
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _booking(*, require_manual_confirm=False, status=Booking.STATUS_PENDING):
    resource = Resource.objects.create(
        name=f"Tisch {uuid.uuid4().hex[:6]}",
        deposit_cents=500,
        require_manual_confirm=require_manual_confirm,
    )
    customer = Customer.objects.create(name="Gast", email="g@test.de")
    start = timezone.make_aware(datetime(2026, 7, 1, 12, 0))
    return Booking.objects.create(
        resource=resource,
        customer=customer,
        reference_code=f"T-{uuid.uuid4().hex[:6].upper()}",
        start=start,
        end=start + timedelta(minutes=60),
        status=status,
        deposit_cents=500,
        payment_state=Booking.PAYMENT_PENDING,
    )


def test_mark_deposit_paid_auto_confirms():
    b = _booking()
    result = mark_deposit_paid(
        tenant_schema=connection.schema_name, booking_id=str(b.id), payment_intent="pi_1"
    )
    assert result is True
    b.refresh_from_db()
    assert b.payment_state == Booking.PAYMENT_PAID
    assert b.stripe_payment_intent == "pi_1"
    assert b.status == Booking.STATUS_CONFIRMED  # авто-подтверждение по оплате


def test_mark_deposit_paid_manual_stays_pending():
    b = _booking(require_manual_confirm=True)
    mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    b.refresh_from_db()
    assert b.payment_state == Booking.PAYMENT_PAID
    assert b.status == Booking.STATUS_PENDING  # ручная проверка — бизнес подтвердит сам


def test_mark_deposit_paid_idempotent():
    b = _booking()
    mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    # повтор (ретрай вебхука) не ломается и не «переподтверждает»
    assert mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(b.id)) is True
    b.refresh_from_db()
    assert b.status == Booking.STATUS_CONFIRMED


def test_mark_deposit_paid_unknown_booking():
    result = mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(uuid.uuid4()))
    assert result is False


def test_webhook_booking_deposit_marks_paid():
    b = _booking()
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "payment_intent": "pi_2",
            "metadata": {
                "kind": "booking_deposit",
                "tenant_schema": connection.schema_name,
                "booking_id": str(b.id),
            },
        },
    )
    b.refresh_from_db()
    assert b.payment_state == Booking.PAYMENT_PAID
    assert b.status == Booking.STATUS_CONFIRMED
