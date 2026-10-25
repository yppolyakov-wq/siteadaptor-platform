"""KA-12 T-6 (EV-4): счёт по билету.

Было: у билета не было кнопки «Rechnung» — владелец ретрита/курса выписывал счёт
вручную в Finanzen, перенося места, допы и размещение. Стало: тот же общий
приёмник `deal-invoice`, что у брони/записи: места × цена тира, допы своей
ставкой, размещение, скидка; сертификат — оплата, черновик переиспользуется."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core import deal_card
from apps.core.deal_invoice import invoice_for_deal, supports
from apps.events.models import Event, Ticket
from apps.events.services import book_ticket
from apps.finance import services as finance_services

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(small_business=False, is_module_active=lambda name: True)


def _ticket(**kw):
    event = Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=20),
        status=Event.STATUS_PUBLISHED,
        price_cents=10000,
        capacity=10,
    )
    ticket = book_ticket(event, name="Anna", email="anna@t.de", quantity=2, auto_confirm=True)
    for k, v in kw.items():
        setattr(ticket, k, v)
    ticket.save()
    return ticket


def test_ticket_kind_supported_and_lines_match_payable():
    t = _ticket(
        extras=[{"label": "Matte", "price_cents": 1190, "vat_rate": "19.00"}],
        accommodation_cents=5000,
        discount_cents=1000,
    )
    assert supports("ticket")
    inv, created = invoice_for_deal("ticket", t, tenant=TENANT)
    assert created and inv.deal_kind == "ticket" and inv.deal_id == t.reference_code
    labels = [line["text"] for line in inv.lines]
    assert labels[0] == "Yoga-Retreat" and "Matte" in labels and "Übernachtung" in labels
    assert inv.gross == Decimal(t.payable_cents) / 100
    assert inv.service_date == timezone.localtime(t.event.starts_at).date()


def test_draft_reused_and_card_finds_it():
    t = _ticket()
    inv, _ = invoice_for_deal("ticket", t, tenant=TENANT)
    again, created = invoice_for_deal("ticket", t, tenant=TENANT)
    assert not created and again.pk == inv.pk
    assert deal_card._invoice_id("ticket", t, TENANT) == inv.pk


def test_paid_ticket_prepaid_and_small_business_zero_rate():
    t = _ticket(payment_state=Ticket.PAYMENT_PAID)
    inv = finance_services.invoice_from_ticket(t, tenant=TENANT)
    assert inv.prepaid_cents == t.payable_cents
    small = SimpleNamespace(small_business=True)
    inv0 = finance_services.invoice_from_ticket(t, tenant=small)
    assert inv0.vat_amount == 0 and inv0.gross == Decimal(t.payable_cents) / 100


def test_unpaid_ticket_has_no_prepaid():
    t = _ticket()
    assert finance_services.invoice_from_ticket(t, tenant=TENANT).prepaid_cents == 0


def test_deposit_installment_and_refund_prepaid():
    from apps.events.models import InstallmentCharge, InstallmentPlan

    dep = _ticket(payment_state=Ticket.PAYMENT_DEPOSIT, deposit_cents=5000)
    assert finance_services.invoice_from_ticket(dep, tenant=TENANT).prepaid_cents == 5000

    inst = _ticket(payment_state=Ticket.PAYMENT_INSTALLMENT)
    plan = InstallmentPlan.objects.create(ticket=inst, total_cents=20000, count=2)
    InstallmentCharge.objects.create(
        plan=plan, sequence=1, due_date=timezone.now().date(), amount_cents=10000, status="paid"
    )
    InstallmentCharge.objects.create(
        plan=plan, sequence=2, due_date=timezone.now().date(), amount_cents=10000
    )
    assert finance_services.invoice_from_ticket(inst, tenant=TENANT).prepaid_cents == 10000

    back = _ticket(payment_state=Ticket.PAYMENT_REFUNDED)
    assert finance_services.invoice_from_ticket(back, tenant=TENANT).prepaid_cents == 0


def test_certificate_is_payment_not_rabatt():
    t = _ticket(discount_cents=3000, voucher_paid_cents=3000, voucher_code="GS-1")
    inv = finance_services.invoice_from_ticket(t, tenant=TENANT)
    assert not any(line["text"] == "Rabatt" for line in inv.lines)
    assert inv.gross == Decimal(20000) / 100 and inv.prepaid_cents == 3000


def test_prepaid_refreshed_on_issue():
    t = _ticket()
    inv, _ = invoice_for_deal("ticket", t, tenant=TENANT)
    assert inv.prepaid_cents == 0
    Ticket.objects.filter(pk=t.pk).update(payment_state=Ticket.PAYMENT_PAID)
    assert finance_services._refresh_prepaid(inv) and inv.prepaid_cents == 20000
