"""KA-12 E11.1: серверный золотой путь направления «Termine».

Запись → подтверждение → исполнение → выручка в журнале → счёт из записи с той же
суммой; неявка → Anzahlung остаётся бизнесу; повторная запись того же e-mail — тот
же клиент (счётчик неявок E6.4 видит всю его историю). Браузерный двойник — GP-3
в `scripts/golden_paths.py`."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking
from apps.booking.state_machine import BookingSM
from apps.booking.tests.test_services import _resource, _service
from apps.finance.models import RevenueEntry
from apps.finance.services import invoice_from_booking

pytestmark = pytest.mark.django_db


def _book(svc, hours=48, email="gp@t.de"):
    start = timezone.now() + timedelta(hours=hours)
    return services.book(
        _resource(),
        start=start,
        end=start + timedelta(hours=1),
        name="Gast",
        email=email,
        service=svc,
        price_cents=4500,
    )


def test_book_confirm_fulfil_revenue_and_invoice_agree():
    b = _book(_service(price_cents=4500))
    assert b.status == "pending"
    BookingSM().apply(b, "confirmed", actor=None)
    BookingSM().apply(b, "fulfilled", actor=None)
    b.refresh_from_db()
    entry = RevenueEntry.objects.get(source="booking", source_ref=str(b.id))
    assert entry.amount == Decimal(b.total_cents) / 100
    invoice = invoice_from_booking(b)
    # Известный дефект (roadmap §Отложено «Bruttomethode»): НДС считается от нетто в
    # центах, и часть брутто-цен недостижима (45,00 € @19 % → 45,01 €). Расхождение —
    # не больше цента; точное равенство — замок ниже (xfail strict).
    assert abs(invoice.gross - entry.amount) <= Decimal("0.01")


@pytest.mark.xfail(strict=True, reason="Bruttomethode: 45,00 € @19 % недостижимы от нетто")
def test_invoice_gross_equals_deal_total_exactly():
    b = _book(_service(price_cents=4500))
    assert invoice_from_booking(b).gross == Decimal("45.00")


def test_no_show_keeps_deposit():
    b = _book(_service(price_cents=4500))
    Booking.objects.filter(pk=b.pk).update(
        payment_state=Booking.PAYMENT_DEPOSIT, deposit_cents=1000, stripe_payment_intent="pi_x"
    )
    b.refresh_from_db()
    BookingSM().apply(b, "confirmed", actor=None)
    BookingSM().apply(b, "no_show", actor=None)
    b.refresh_from_db()
    assert b.status == "no_show" and b.payment_state != Booking.PAYMENT_REFUNDED


def test_same_email_same_customer():
    svc = _service(price_cents=4500)
    first = _book(svc, hours=48)
    second = _book(svc, hours=96)
    assert first.customer_id == second.customer_id
