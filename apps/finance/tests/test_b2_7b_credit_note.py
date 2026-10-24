"""KA-12 B2-7b: Rechnungskorrektur — частичная корректура выставленного счёта.

Счёт после выставления не меняется (GoBD). Уступка в цене (Minderung) или ошибка в
сумме оформляются отдельным документом со своим номером и суммами со знаком минус;
оригинал остаётся как был, а «к оплате» и Offene Posten считают остаток."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext

from apps.billing import connect
from apps.core import money_contract, refunds
from apps.core.models import DealPayment
from apps.finance import services
from apps.finance.models import Invoice, RevenueEntry
from apps.finance.services import CreditError, create_credit, issue_invoice, record_revenue

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(stripe_connect_id="acct_test", owner_email="o@t.de", schema_name="x")


def _issued(lines, vat_rate="19.00"):
    net, vat, gross = services.compute_totals(lines, Decimal(vat_rate))
    inv = Invoice.objects.create(
        lines=lines, vat_rate=Decimal(vat_rate), net=net, vat_amount=vat, gross=gross
    )
    issue_invoice(inv)
    inv.refresh_from_db()
    return inv


MIXED = [
    {"text": "Essen", "qty": 1, "unit_price": "100.00", "vat_rate": "7.00"},
    {"text": "Getränke", "qty": 1, "unit_price": "50.00", "vat_rate": "19.00"},
]


def test_credit_needs_original_and_storno_cannot_correct():
    inv = _issued(MIXED)
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(kind=Invoice.KIND_CREDIT)
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(kind=Invoice.KIND_STORNO, cancels=inv, corrects=inv)
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(kind=Invoice.KIND_INVOICE, corrects=inv)


def test_credit_splits_by_rate_and_hits_the_exact_amount():
    inv = _issued(MIXED)  # 107,00 + 59,50 = 166,50
    credit = create_credit(inv, Decimal("10.00"), reason="Preisminderung", key="k1")
    assert credit.kind == Invoice.KIND_CREDIT and credit.corrects_id == inv.pk
    assert credit.number == inv.number + 1
    assert credit.status == Invoice.STATUS_ISSUED and credit.due_date is None
    assert credit.gross == Decimal("-10.00")
    assert {str(Decimal(ln["vat_rate"])) for ln in credit.lines} == {"7.00", "19.00"}
    net, vat, gross = services.compute_totals(credit.lines, credit.vat_rate)
    assert (net, vat, gross) == (credit.net, credit.vat_amount, credit.gross)
    inv.refresh_from_db()
    assert inv.gross == Decimal("166.50")  # оригинал не тронут


def test_credit_is_idempotent_by_key_and_capped_by_remaining():
    inv = _issued(MIXED)
    first = create_credit(inv, Decimal("10.00"), reason="x", key="k1")
    assert create_credit(inv, Decimal("10.00"), reason="x", key="k1").pk == first.pk
    create_credit(inv, Decimal("50.00"), reason="y", key="k2")
    with pytest.raises(CreditError):  # остаток 106,50 — полная сумма = Storno
        create_credit(inv, Decimal("106.50"), reason="z", key="k3")
    with pytest.raises(CreditError):
        create_credit(inv, Decimal("0"), reason="z", key="k4")


def test_credit_refused_for_draft_and_cancelled():
    draft = Invoice.objects.create(lines=MIXED, gross=Decimal("166.50"))
    with pytest.raises(CreditError):
        create_credit(draft, Decimal("1.00"), reason="x", key="d")
    inv = _issued(MIXED)
    Invoice.objects.filter(pk=inv.pk).update(status=Invoice.STATUS_CANCELLED)
    inv.refresh_from_db()
    with pytest.raises(CreditError):
        create_credit(inv, Decimal("1.00"), reason="x", key="c")


def test_open_amount_subtracts_credits_and_open_items_has_no_n_plus_1():
    from apps.finance.bank import open_items

    tenant = SimpleNamespace(is_module_active=lambda m: False)
    invoices = [_issued(MIXED) for _ in range(3)]
    for i, inv in enumerate(invoices):
        create_credit(inv, Decimal("16.50"), reason="x", key=f"n{i}")
    invoices[0].refresh_from_db()
    assert invoices[0].open_amount == Decimal("150.00")
    with CaptureQueriesContext(transaction.get_connection()) as ctx:
        rows = [r for r in open_items(tenant) if r["kind"] == "invoice"]
    assert {r["amount"] for r in rows} == {Decimal("150.00")}
    assert all(r["obj"].kind == Invoice.KIND_INVOICE for r in rows)
    assert len(ctx.captured_queries) < 10


def _order_with_issued_invoice():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("11.90"), vat_rate=Decimal("19.00"))
    order = create_order(items=[(product, None, 2)], name="Gast", email="g@t.de")
    Order.objects.filter(pk=order.pk).update(status="fulfilled", payment_state="paid")
    order.refresh_from_db()
    record_revenue(source="order", source_ref=str(order.id), amount=order.total)
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=2380,
        stripe_payment_intent="pi_main",
        source="webhook",
    )
    inv = services.invoice_from_order(order)
    Invoice.objects.filter(pk=inv.pk).update(deal_kind="order", deal_id=order.reference_code)
    inv.refresh_from_db()
    issue_invoice(inv)
    return order, inv


def test_minderung_with_issued_invoice_writes_credit_not_refusal(monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "refund", lambda **kw: calls.append(kw))
    order, inv = _order_with_issued_invoice()
    result = refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    assert result == refunds.RefundResult.REFUNDED
    assert calls[-1]["amount_cents"] == 500
    credit = Invoice.objects.get(corrects=inv)
    assert credit.gross == Decimal("-5.00")
    order.refresh_from_db()
    assert order.total == Decimal("18.80")
    # Выручку сторнирует только Minderung — корректура журнал не трогает.
    net = sum(
        r.amount
        for r in RevenueEntry.objects.filter(source="order", source_ref__startswith=str(order.id))
    )
    assert net == Decimal("18.80")
    # Счёт сделки — оригинал, не корректура.
    assert money_contract.invoice_for("order", order).pk == inv.pk


def test_credit_has_no_transitions():
    from apps.core.fsm import IllegalTransition
    from apps.finance.state_machine import InvoiceSM

    credit = create_credit(_issued(MIXED), Decimal("1.00"), reason="x", key="t")
    with pytest.raises(IllegalTransition):
        InvoiceSM().apply(credit, "cancelled")


def test_key_of_another_invoice_is_refused():
    first, second = _issued(MIXED), _issued(MIXED)
    create_credit(first, Decimal("5.00"), reason="x", key="shared")
    with pytest.raises(CreditError):
        create_credit(second, Decimal("5.00"), reason="x", key="shared")


def test_storno_after_credit_reverses_only_the_remaining_amount():
    from apps.finance.state_machine import InvoiceSM

    inv = _issued(MIXED)  # 166,50
    create_credit(inv, Decimal("16.50"), reason="x", key="s")
    inv.refresh_from_db()
    InvoiceSM().apply(inv, "cancelled")
    storno = Invoice.objects.get(cancels=inv)
    assert storno.gross == Decimal("-150.00")
    net, vat, gross = services.compute_totals(storno.lines, storno.vat_rate)
    assert gross == storno.gross


def test_credit_doc_is_not_matched_as_payment():
    from apps.finance.bank import apply_match

    credit = create_credit(_issued(MIXED), Decimal("1.00"), reason="x", key="b")
    tx = SimpleNamespace(amount=Decimal("1.00"))
    assert apply_match(tx, "invoice", credit) is False
