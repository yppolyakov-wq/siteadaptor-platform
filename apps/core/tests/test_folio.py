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
