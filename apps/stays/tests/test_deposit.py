"""Track E / E4: депозит за бронь — оплата (вебхук) → paid + авто-confirm /
ручная проверка, идемпотентность, маршрутизация вебхука по kind."""

import uuid
from datetime import date, timedelta

import pytest
from django.db import connection

from apps.billing import webhooks
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit
from apps.stays.payments import mark_stay_paid

pytestmark = pytest.mark.django_db

D0 = date(2026, 11, 1)


def _booking(*, require_manual_confirm=False, status=StayBooking.STATUS_PENDING):
    unit = StayUnit.objects.create(
        name=f"Zimmer {uuid.uuid4().hex[:6]}",
        price_cents=9000,
        deposit_cents=2000,
        require_manual_confirm=require_manual_confirm,
    )
    customer = Customer.objects.create(name="Gast", email="g@test.de")
    return StayBooking.objects.create(
        unit=unit,
        customer=customer,
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=D0,
        departure=D0 + timedelta(days=2),
        status=status,
        price_cents=9000,
        deposit_cents=2000,
        payment_state=StayBooking.PAYMENT_PENDING,
    )


def test_mark_stay_paid_auto_confirms():
    b = _booking()
    assert (
        mark_stay_paid(
            tenant_schema=connection.schema_name, booking_id=str(b.id), payment_intent="pi_1"
        )
        is True
    )
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID
    assert b.stripe_payment_intent == "pi_1"
    assert b.status == StayBooking.STATUS_CONFIRMED  # авто-подтверждение по оплате


def test_mark_stay_paid_manual_stays_pending():
    b = _booking(require_manual_confirm=True)
    mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID
    assert b.status == StayBooking.STATUS_PENDING  # бизнес подтвердит сам


def test_mark_stay_paid_idempotent():
    b = _booking()
    mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    assert mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(b.id)) is True
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_CONFIRMED


def test_mark_stay_paid_unknown_booking():
    assert (
        mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(uuid.uuid4())) is False
    )


def test_webhook_stay_deposit_marks_paid():
    b = _booking()
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "payment_intent": "pi_2",
            "metadata": {
                "kind": "stay_deposit",
                "tenant_schema": connection.schema_name,
                "booking_id": str(b.id),
            },
        },
    )
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID
    assert b.status == StayBooking.STATUS_CONFIRMED
