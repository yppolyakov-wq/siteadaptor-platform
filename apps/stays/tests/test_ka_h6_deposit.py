"""KA-H6 (аудит KA-5d, Z1): онлайн оплачена только Anzahlung — бронь не «bezahlt».

Раньше вебхук ставил `paid`, карточка писала «✓ bezahlt», кнопка оплаты на стойке
гасла, и остаток пропадал из виду (то же у записи по времени)."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.template.loader import render_to_string

from apps.booking.models import Booking, Resource
from apps.booking.payments import mark_deposit_paid
from apps.core import payments_page
from apps.core.tests.dates import future_month_start
from apps.finance import bank
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit
from apps.stays.payments import mark_stay_paid
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)


def _stay(deposit=3000, total=20000, state=StayBooking.PAYMENT_PENDING):
    unit = StayUnit.objects.create(
        name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=10000, deposit_cents=deposit
    )
    return StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=D0,
        departure=D0 + timedelta(days=2),
        status=StayBooking.STATUS_PENDING,
        price_cents=10000,
        total_cents=total,
        deposit_cents=deposit,
        payment_state=state,
    )


def _pay(b):
    mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    b.refresh_from_db()
    return b


def test_webhook_partial_deposit_sets_deposit_state():
    b = _pay(_stay(deposit=3000, total=20000))
    assert b.payment_state == StayBooking.PAYMENT_DEPOSIT
    assert b.balance_cents == 17000 and b.balance_eur == Decimal("170.00")


def test_webhook_full_prepay_sets_paid():
    b = _pay(_stay(deposit=20000, total=20000))
    assert b.payment_state == StayBooking.PAYMENT_PAID and b.balance_cents == 0


def test_webhook_does_not_downgrade_paid():
    b = _pay(_stay(deposit=3000, total=20000, state=StayBooking.PAYMENT_PAID))
    assert b.payment_state == StayBooking.PAYMENT_PAID


def test_payment_card_shows_remaining_and_button():
    b = _stay(deposit=3000, total=20000, state=StayBooking.PAYMENT_DEPOSIT)
    html = render_to_string("stays/_stay_payment.html", {"b": b})
    assert "170" in html and 'value="mark_paid"' in html
    assert "✓" not in html


def test_open_items_and_payments_page_list_deposit_booking():
    tenant = TenantFactory.build(disabled_modules=[])
    b = _stay(deposit=3000, total=20000, state=StayBooking.PAYMENT_DEPOSIT)
    row = next(r for r in bank.open_items(tenant) if r["obj"].pk == b.pk)
    assert row["amount"] == Decimal("170.00")
    assert any(r["pk"] == b.pk for r in payments_page.payment_rows(tenant, "open"))


def test_refund_on_cancel_covers_deposit_state():
    from apps.core import refunds

    assert StayBooking.PAYMENT_DEPOSIT in refunds._refundable_states(StayBooking)
    assert Booking.PAYMENT_DEPOSIT in refunds._refundable_states(Booking)


def _appointment(deposit, price):
    resource = Resource.objects.create(name=f"Platz {uuid.uuid4().hex[:6]}")
    start = timezone_start()
    return Booking.objects.create(
        resource=resource,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"T-{uuid.uuid4().hex[:6].upper()}",
        start=start,
        end=start + timedelta(hours=1),
        price_cents=price,
        deposit_cents=deposit,
        payment_state=Booking.PAYMENT_PENDING,
    )


def timezone_start():
    from django.utils import timezone

    return timezone.now() + timedelta(days=5)


def test_booking_webhook_partial_deposit_sets_deposit_state():
    b = _appointment(deposit=1000, price=6000)
    mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    b.refresh_from_db()
    assert b.payment_state == Booking.PAYMENT_DEPOSIT and b.balance_cents == 5000


def test_booking_webhook_full_price_sets_paid():
    b = _appointment(deposit=6000, price=6000)
    mark_deposit_paid(tenant_schema=connection.schema_name, booking_id=str(b.id))
    b.refresh_from_db()
    assert b.payment_state == Booking.PAYMENT_PAID
