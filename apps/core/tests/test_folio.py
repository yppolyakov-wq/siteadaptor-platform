"""KA-12 B2-3: фолио платежей (`core.DealPayment`) — чтение и запись.

Легаси-сделка без строк читается по-старому (паритет — `test_money_invariant`).
Первая запись в легаси-сделку переносит уже полученное строкой `opening`.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core import folio, money_contract
from apps.core.models import DealPayment

pytestmark = pytest.mark.django_db


def _stay(state="none", deposit=0):
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=5000)
    day = timezone.localdate() + timedelta(days=20)
    stay = services.book_stay(unit, arrival=day, departure=day + timedelta(days=2), name="G")
    stay.payment_state = state
    stay.deposit_cents = deposit
    stay.save(update_fields=["payment_state", "deposit_cents"])
    return stay


def test_legacy_deal_without_rows_reads_as_before():
    stay = _stay(state="deposit", deposit=3000)
    ms = money_contract.money_state("stay", stay)
    assert ms.paid == Decimal("30.00")
    assert ms.due == ms.total - Decimal("30.00")
    assert not DealPayment.objects.exists()


def test_first_record_carries_legacy_deposit_as_opening():
    """Депозит пришёл до фолио, остаток — после: оплачено = оба, не только остаток."""
    stay = _stay(state="deposit", deposit=3000)
    total_cents = stay.total_cents
    folio.record("stay", stay, amount_cents=total_cents - 3000, purpose="balance", method="cash")
    purposes = list(DealPayment.objects.values_list("purpose", "amount_cents"))
    assert purposes == [("opening", 3000), ("balance", total_cents - 3000)]
    ms = money_contract.money_state("stay", stay)
    assert ms.paid == ms.total
    assert ms.due == Decimal("0")


def test_unpaid_legacy_deal_gets_no_opening_row():
    stay = _stay()
    folio.record("stay", stay, amount_cents=2000, purpose="deposit", method="stripe")
    assert list(DealPayment.objects.values_list("purpose", flat=True)) == ["deposit"]
    assert money_contract.money_state("stay", stay).paid == Decimal("20.00")


def test_same_intent_is_recorded_once():
    stay = _stay()
    first = folio.record("stay", stay, amount_cents=2000, purpose="deposit", intent="pi_x")
    again = folio.record("stay", stay, amount_cents=2000, purpose="deposit", intent="pi_x")
    assert first.pk == again.pk
    assert DealPayment.objects.count() == 1


def test_partial_refund_lowers_net_paid_and_raises_due():
    stay = _stay()
    row = folio.record("stay", stay, amount_cents=stay.total_cents, purpose="full")
    DealPayment.objects.filter(pk=row.pk).update(refunded_cents=1000)
    folio.forget(stay)
    ms = money_contract.money_state("stay", stay)
    assert ms.refunded == Decimal("10.00")
    assert ms.due == Decimal("10.00")


def test_prefetch_makes_due_query_free():
    stays = [_stay() for _ in range(3)]
    folio.record("stay", stays[0], amount_cents=1000, purpose="deposit")
    for s in stays:
        folio.forget(s)
    folio.prefetch("stay", stays)
    with CaptureQueriesContext(connection) as ctx:
        dues = [money_contract.due("stay", s) for s in stays]
    assert not [q for q in ctx.captured_queries if "dealpayment" in q["sql"].lower()]
    assert dues[0] == money_contract.due("stay", stays[1]) - Decimal("10.00")


# --- ревью database-reviewer -----------------------------------------------------------


def test_shared_intent_across_deals_records_each_deal():
    """Один Checkout на несколько сделок (групповая запись) — строка у каждой."""
    a, b = _stay(), _stay()
    folio.record("stay", a, amount_cents=1000, purpose="deposit", intent="pi_group")
    folio.record("stay", b, amount_cents=1000, purpose="deposit", intent="pi_group")
    assert DealPayment.objects.filter(stripe_payment_intent="pi_group").count() == 2


def test_opening_does_not_take_the_new_payments_intent():
    stay = _stay(state="deposit", deposit=3000)
    type(stay).objects.filter(pk=stay.pk).update(stripe_payment_intent="pi_new")
    folio.record("stay", stay, amount_cents=2000, purpose="balance", intent="pi_new")
    opening = DealPayment.objects.get(purpose="opening")
    assert opening.stripe_payment_intent == ""
    assert DealPayment.objects.filter(stripe_payment_intent="pi_new").count() == 1


def test_refunded_legacy_deal_keeps_payment_and_refund_in_book():
    stay = _stay(state="refunded", deposit=0)
    folio.record("stay", stay, amount_cents=1500, purpose="full", method="cash")
    opening = DealPayment.objects.get(purpose="opening")
    assert opening.amount_cents == opening.refunded_cents == stay.total_cents


# --- писатели B2-3b ---------------------------------------------------------------------


def test_webhook_then_manual_rest_builds_full_book():
    """Депозит онлайн → остаток «bezahlt»: две строки, оплачено = итог."""
    from apps.stays.payments import mark_stay_paid

    stay = _stay(deposit=3000)
    mark_stay_paid(
        tenant_schema=connection.schema_name, booking_id=str(stay.pk), payment_intent="pi_d"
    )
    stay.refresh_from_db()
    assert stay.payment_state == "deposit"
    money_contract.settle_payment("stay", stay, source="manual")
    stay.refresh_from_db()
    book = list(DealPayment.objects.values_list("purpose", "method", "amount_cents"))
    assert book[0] == ("deposit", "stripe", 3000)
    assert book[1][0] == "balance" and book[1][2] == stay.total_cents - 3000
    folio.forget(stay)
    assert money_contract.money_state("stay", stay).paid == Decimal(stay.total_cents) / 100


def test_repeated_webhook_writes_one_row():
    from apps.stays.payments import mark_stay_paid

    stay = _stay()
    for _ in range(2):
        mark_stay_paid(
            tenant_schema=connection.schema_name, booking_id=str(stay.pk), payment_intent="pi_once"
        )
    assert DealPayment.objects.filter(deal_id=stay.pk).count() == 1


def test_full_card_refund_marks_card_rows_refunded(monkeypatch):
    from apps.core import refunds
    from apps.stays.payments import mark_stay_paid
    from apps.tenants.tests.factories import TenantFactory

    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)
    stay = _stay(deposit=3000)
    mark_stay_paid(
        tenant_schema=connection.schema_name, booking_id=str(stay.pk), payment_intent="pi_r"
    )
    money_contract.settle_payment("stay", stay, source="manual")  # остаток наличными
    stay.refresh_from_db()
    tenant = TenantFactory.build(stripe_connect_id="acct_1", owner_email="o@t.de")
    assert refunds.refund_payment("stay", stay, tenant) == refunds.RefundResult.REFUNDED
    card = DealPayment.objects.get(method="stripe")
    cash = DealPayment.objects.exclude(method="stripe").get()
    assert card.refunded_cents == card.amount_cents == 3000
    assert cash.refunded_cents == 0  # наличные карта не вернула


# --- ревью django-reviewer B2-3 ----------------------------------------------------------


def test_card_refund_of_mixed_deal_retains_nothing(monkeypatch):
    """Депозит картой + остаток наличными, отмена с возвратом карты: «Einbehalten»
    не появляется — карта вернула всё, что получила."""
    from apps.core import refunds
    from apps.finance.models import RevenueEntry
    from apps.stays.models import StayBooking
    from apps.stays.payments import mark_stay_paid
    from apps.tenants.tests.factories import TenantFactory

    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)
    stay = _stay(deposit=3000)
    mark_stay_paid(
        tenant_schema=connection.schema_name, booking_id=str(stay.pk), payment_intent="pi_m"
    )
    money_contract.settle_payment("stay", stay, source="manual")
    stay.refresh_from_db()
    StayBooking.objects.filter(pk=stay.pk).update(status="cancelled")
    stay.refresh_from_db()
    tenant = TenantFactory.build(stripe_connect_id="acct_1", owner_email="o@t.de")
    refunds.refund_on_cancel("stay", stay, "cancelled", "confirmed", tenant)
    assert not RevenueEntry.objects.filter(source_ref=f"{stay.id}:retained").exists()


def test_double_manual_payment_does_not_overbook():
    stay = _stay()
    folio.record("stay", stay, amount_cents=stay.total_cents, purpose="balance")
    assert folio.record("stay", stay, amount_cents=stay.total_cents, purpose="balance") is None
    assert DealPayment.objects.filter(deal_id=stay.pk).count() == 1


def test_late_webhook_after_desk_payment_is_booked():
    """Касса отметила «оплачено», потом пришёл Stripe — онлайн-деньги в книге."""
    from apps.stays.payments import mark_stay_paid

    stay = _stay(state="paid")
    mark_stay_paid(
        tenant_schema=connection.schema_name, booking_id=str(stay.pk), payment_intent="pi_late"
    )
    assert DealPayment.objects.filter(stripe_payment_intent="pi_late").exists()


def test_refunded_state_without_refund_rows_reads_as_refunded():
    """Сбой между захватом и отметкой: состояние «возвращено» — книга не спорит."""
    stay = _stay()
    folio.record("stay", stay, amount_cents=stay.total_cents, purpose="full", intent="pi_c")
    type(stay).objects.filter(pk=stay.pk).update(payment_state="refunded")
    stay.refresh_from_db()
    folio.forget(stay)
    ms = money_contract.money_state("stay", stay)
    assert ms.refunded == ms.paid > 0


def test_order_webhook_does_not_revive_refunded_order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.payments import mark_order_paid
    from apps.orders.services import create_order

    order = create_order(items=[(ProductFactory(base_price=Decimal("8.00")), 1)], name="M")
    type(order).objects.filter(pk=order.pk).update(payment_state="refunded")
    mark_order_paid(
        tenant_schema=connection.schema_name, order_id=str(order.pk), payment_intent="pi_o"
    )
    order.refresh_from_db()
    assert order.payment_state == "refunded"
