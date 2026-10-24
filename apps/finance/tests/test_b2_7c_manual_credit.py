"""KA-12 B2-7c: «Gutschrift erstellen» со страницы счёта.

Корректура — свой документ; деньги не двигаются. У заказа/записи/номера снижается
цена сделки (тот же путь, что Minderung), у заявки сторнируется журнал по ставкам,
у счёта без сделки — только документ."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db.models import Sum

from apps.finance import services
from apps.finance.models import Invoice, RevenueEntry
from apps.finance.services import CreditError, issue_invoice, manual_credit

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(stripe_connect_id="", owner_email="o@t.de", schema_name="x")
MIXED = [
    {"text": "Essen", "qty": 1, "unit_price": "100.00", "vat_rate": "7.00"},
    {"text": "Getränke", "qty": 1, "unit_price": "50.00", "vat_rate": "19.00"},
]


def _issued(lines=MIXED, **kw):
    net, vat, gross = services.compute_totals(lines, Decimal("19.00"))
    inv = Invoice.objects.create(lines=lines, net=net, vat_amount=vat, gross=gross, **kw)
    issue_invoice(inv)
    inv.refresh_from_db()
    return inv


def _job_net(inv):
    total = RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_JOB, source_ref__startswith=f"inv:{inv.pk}:"
    ).aggregate(s=Sum("amount"))["s"]
    return Decimal(total or 0)


def test_free_invoice_gets_document_only():
    inv = _issued()
    credit = manual_credit(inv, Decimal("16.50"), reason="Fehler", key="a")
    assert credit.gross == Decimal("-16.50") and credit.corrects_id == inv.pk
    inv.refresh_from_db()
    assert inv.open_amount == Decimal("150.00")
    assert manual_credit(inv, Decimal("16.50"), reason="Fehler", key="a").pk == credit.pk


def test_job_invoice_credit_reverses_journal_by_rate_and_storno_does_not_overshoot():
    from apps.finance.state_machine import InvoiceSM

    inv = _issued(deal_kind="job", deal_id="J-TEST1")
    assert _job_net(inv) == Decimal("166.50")
    manual_credit(inv, Decimal("16.50"), reason="Minderung", key="j")
    assert _job_net(inv) == Decimal("150.00")
    rates = set(
        RevenueEntry.objects.filter(source_ref__startswith=f"inv:{inv.pk}:c").values_list(
            "vat_rate", flat=True
        )
    )
    assert rates == {Decimal("7.00"), Decimal("19.00")}
    inv.refresh_from_db()
    InvoiceSM().apply(inv, "cancelled")
    assert _job_net(inv) == 0  # не −16,50


def test_order_invoice_credit_lowers_deal_price():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("11.90"), vat_rate=Decimal("19.00"))
    order = create_order(items=[(product, None, 2)], name="Gast", email="g@t.de")
    Order.objects.filter(pk=order.pk).update(status="fulfilled")
    order.refresh_from_db()
    inv = services.invoice_from_order(order)
    Invoice.objects.filter(pk=inv.pk).update(deal_kind="order", deal_id=order.reference_code)
    inv.refresh_from_db()
    issue_invoice(inv)
    credit = manual_credit(inv, Decimal("5.00"), reason="beschädigt", key="o", tenant=TENANT)
    assert credit.gross == Decimal("-5.00")
    order.refresh_from_db()
    assert order.total == Decimal("18.80")


def test_too_much_and_unsupported_kind_are_refused():
    inv = _issued()
    with pytest.raises(CreditError):
        manual_credit(inv, Decimal("166.50"), reason="x", key="b")
    ticket_inv = _issued(deal_kind="ticket", deal_id="E-1")
    with pytest.raises(CreditError):
        manual_credit(ticket_inv, Decimal("1.00"), reason="x", key="c")


def test_view_creates_credit_once_per_form():
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.models import Membership
    from apps.finance.views import invoice_detail

    user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    inv = _issued()
    nonce = uuid.uuid4().hex
    for _ in range(2):  # двойной клик
        request = RequestFactory().post(
            "/x/",
            {"action": "credit", "credit_nonce": nonce, "amount": "16,50", "reason": "Fehler"},
        )
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = user
        request.tenant = TENANT
        invoice_detail(request, inv.pk)
    assert Invoice.objects.filter(corrects=inv).count() == 1
