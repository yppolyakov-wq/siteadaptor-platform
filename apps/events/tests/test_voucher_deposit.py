"""R4: подарочный/промо-код на билет + частичная оплата (депозит)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import payments, services
from apps.events.models import Event, Ticket
from apps.loyalty.models import Voucher

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
        "price_cents": 10000,  # 100 €
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _voucher(code="GS-ABC123", **kw):
    defaults = {"code": code, "label": "Gift", "discount_cents": 3000, "max_uses": 1}
    defaults.update(kw)
    return Voucher.objects.create(**defaults)


# --- voucher ---------------------------------------------------------------
def test_voucher_applied_reduces_payable():
    ev = _event()
    _voucher(discount_cents=3000)
    ticket = services.book_ticket(ev, name="A", email="a@test.de", voucher_code="GS-ABC123")
    assert ticket.discount_cents == 3000
    assert ticket.voucher_code == "GS-ABC123"
    assert ticket.total_cents == 10000
    assert ticket.payable_cents == 7000


def test_voucher_consumed_once():
    ev = _event()
    v = _voucher(max_uses=1)
    services.book_ticket(ev, name="A", email="a@test.de", voucher_code="GS-ABC123")
    v.refresh_from_db()
    assert v.used_count == 1
    # повторное использование исчерпанного кода → PromoInvalid
    with pytest.raises(services.PromoInvalid):
        services.book_ticket(ev, name="B", email="b@test.de", voucher_code="GS-ABC123")


def test_invalid_voucher_raises():
    ev = _event()
    with pytest.raises(services.PromoInvalid):
        services.book_ticket(ev, name="A", email="a@test.de", voucher_code="NOPE-1")


def test_voucher_covering_full_amount_zero_payable():
    ev = _event(price_cents=5000)
    _voucher(discount_cents=9000)  # больше суммы — капается суммой
    ticket = services.book_ticket(ev, name="A", email="a@test.de", voucher_code="GS-ABC123")
    assert ticket.payable_cents == 0


def test_quote_voucher_readonly():
    _voucher(discount_cents=2500)
    assert services.quote_voucher("GS-ABC123", 10000) == 2500
    assert services.quote_voucher("NOPE", 10000) == 0
    Voucher.objects.get(code="GS-ABC123")  # не погашен (used_count 0)
    assert Voucher.objects.get(code="GS-ABC123").used_count == 0


# --- deposit ---------------------------------------------------------------
def test_deposit_percent_snapshots_partial_amount():
    ev = _event(price_cents=20000, deposit_percent=30)
    ticket = services.book_ticket(ev, name="A", email="a@test.de")
    assert ticket.deposit_cents == 6000  # 30 % от 20000
    assert ticket.amount_due_now_cents == 6000
    assert ticket.balance_cents == 14000


def test_deposit_computed_after_voucher_discount():
    ev = _event(price_cents=20000, deposit_percent=50)
    _voucher(discount_cents=4000)
    ticket = services.book_ticket(ev, name="A", email="a@test.de", voucher_code="GS-ABC123")
    assert ticket.payable_cents == 16000
    assert ticket.deposit_cents == 8000  # 50 % от payable (после скидки)


def test_no_deposit_when_percent_zero_or_full():
    assert services.book_ticket(_event(deposit_percent=0), name="A").deposit_cents == 0
    assert services.book_ticket(_event(deposit_percent=100), name="B").deposit_cents == 0


def test_mark_paid_sets_deposit_state_when_deposit():
    ev = _event(price_cents=20000, deposit_percent=25)
    ticket = services.book_ticket(ev, name="A", email="a@test.de")
    payments.mark_ticket_paid(tenant_schema="public", ticket_id=str(ticket.id))
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_DEPOSIT
    assert ticket.status == Ticket.STATUS_CONFIRMED  # место удержано


def test_mark_paid_sets_paid_state_without_deposit():
    ev = _event(price_cents=10000)
    ticket = services.book_ticket(ev, name="A", email="a@test.de")
    payments.mark_ticket_paid(tenant_schema="public", ticket_id=str(ticket.id))
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_PAID


def test_event_form_saves_deposit_percent():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 20,
            "price_eur": "200",
            "deposit_percent": 30,
        }
    )
    assert form.is_valid(), form.errors
    assert form.save().deposit_percent == 30
