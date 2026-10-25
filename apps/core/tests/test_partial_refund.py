"""KA-12 B2-4a (MC-E8): частичный возврат владельцем — карта или наличные.

Раньше вернуть можно было только всё сразу (отменой). Переплату, вернувшуюся по
ошибке сумму и т. п. владелец возвращал мимо системы, и книга врала."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
import stripe

from apps.billing import connect
from apps.core import folio, money_contract, refunds
from apps.core.models import DealPayment
from apps.core.tests import legacy_role_gates as LG
from apps.core.tests.dates import future_month_start
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)
TENANT = SimpleNamespace(stripe_connect_id="acct_test", owner_email="o@t.de", schema_name="x")


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "refund", lambda **kw: calls.append(kw))
    return calls


def _stay(total=3000, state=StayBooking.PAYMENT_PAID, intent="pi_main"):
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=total)
    b = StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=D0,
        departure=D0 + timedelta(days=1),
        status=StayBooking.STATUS_CONFIRMED,
        price_cents=total,
        total_cents=total,
        deposit_cents=total,
        payment_state=state,
        stripe_payment_intent=intent,
    )
    return b


def _card_row(b, cents=5000, intent="pi_main", method="stripe"):
    """Строка фолио напрямую (через record у «оплаченной» сделки встала бы ещё и
    строка «Eröffnung» — деньги посчитались бы дважды)."""
    row = DealPayment.objects.create(
        deal_kind="stay",
        deal_id=b.pk,
        purpose="full",
        method=method,
        amount_cents=cents,
        stripe_payment_intent=intent,
        source="webhook",
    )
    folio.forget(b)
    return row


def test_partial_card_refund_claims_row_and_calls_stripe_with_amount(stripe_calls):
    b = _stay()
    row = _card_row(b)
    result = refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    assert result == refunds.RefundResult.REFUNDED
    row.refresh_from_db()
    assert row.refunded_cents == 1000
    assert stripe_calls[-1]["amount_cents"] == 1000
    assert stripe_calls[-1]["payment_intent"] == "pi_main"
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID  # грубое состояние не трогаем
    assert money_contract.due("stay", b) == 0  # вернули часть переплаты


def test_two_partial_refunds_use_two_keys(stripe_calls):
    b = _stay()
    _card_row(b)
    refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    refunds.refund_partial("stay", b, cents=500, method="card", tenant=TENANT)
    keys = [c["idempotency_key"] for c in stripe_calls]
    assert len(keys) == 2 and keys[0] != keys[1]


def test_more_than_open_is_refused_without_stripe(stripe_calls):
    b = _stay()
    _card_row(b)
    result = refunds.refund_partial("stay", b, cents=2500, method="card", tenant=TENANT)
    assert result == refunds.RefundResult.REFUSED  # переплата 20 €, не больше
    assert stripe_calls == []


def test_stripe_rejection_rolls_back_claim(monkeypatch):
    def boom(**kw):
        raise stripe.error.InvalidRequestError("nope", "amount")

    monkeypatch.setattr(connect, "refund", boom)
    b = _stay()
    row = _card_row(b)
    result = refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    assert result == refunds.RefundResult.FAILED
    row.refresh_from_db()
    assert row.refunded_cents == 0


def test_offline_refund_records_without_stripe(stripe_calls):
    b = _stay()
    _card_row(b, intent="", method="cash")
    result = refunds.refund_partial("stay", b, cents=2000, method="offline", tenant=TENANT)
    assert result == refunds.RefundResult.REFUNDED
    assert stripe_calls == []
    b.refresh_from_db()
    assert money_contract.due("stay", b) == 0


def test_overpayment_refund_brings_due_to_zero(stripe_calls):
    """Переплата: 55 € получено при цене 50 € — вернули 5 €, ждём 0, а не 5."""
    b = _stay(total=5000)
    _card_row(b)
    _card_row(b, cents=500, intent="pi_extra")
    refunds.refund_partial(
        "stay",
        b,
        cents=500,
        method="card",
        tenant=TENANT,
        row_pk=DealPayment.objects.get(deal_id=b.pk, stripe_payment_intent="pi_extra").pk,
    )
    b.refresh_from_db()
    assert money_contract.due("stay", b) == 0


def test_cancel_after_partial_refunds_only_remainder(stripe_calls):
    b = _stay()
    row = _card_row(b)
    refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    b.refresh_from_db()
    assert refunds.refund_payment("stay", b, TENANT) == refunds.RefundResult.REFUNDED
    last = stripe_calls[-1]
    assert last["amount_cents"] == 4000  # 50 € платёж − 10 € уже вернули
    assert last["idempotency_key"] != stripe_calls[0]["idempotency_key"]
    row.refresh_from_db()
    assert row.refunded_cents == row.amount_cents
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_REFUNDED


def test_refund_beyond_overpayment_is_refused(stripe_calls):
    """Ревью: вернуть больше переплаты нельзя — выручка осталась бы проведённой
    (снижение цены со сторно — отдельный шаг B2-4b)."""
    b = _stay(total=5000)
    _card_row(b)
    assert (
        refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
        == refunds.RefundResult.REFUSED
    )
    assert stripe_calls == []


def test_stripe_timeout_keeps_claim(monkeypatch):
    """Ревью: при обрыве Stripe мог вернуть деньги — захват не откатываем, иначе
    следующая попытка с другой суммой вернула бы ещё раз."""

    def boom(**kw):
        raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr(connect, "refund", boom)
    b = _stay()
    row = _card_row(b)
    result = refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    assert result == refunds.RefundResult.UNCERTAIN
    row.refresh_from_db()
    assert row.refunded_cents == 1000


def test_offline_refund_cannot_draw_on_card_money(stripe_calls):
    """Ревью: «наличными» нельзя списать деньги, пришедшие картой."""
    b = _stay()
    _card_row(b)
    assert (
        refunds.refund_partial("stay", b, cents=1000, method="offline", tenant=TENANT)
        == refunds.RefundResult.REFUSED
    )


def test_refunded_state_without_book_refund_is_not_due():
    """Ревью: «возвращено», а книга возврата не знает — ждём 0, а не всю цену."""
    b = _stay(state=StayBooking.PAYMENT_REFUNDED)
    _card_row(b)
    assert money_contract.due("stay", b) == 0


def test_legacy_deal_gets_opening_first(stripe_calls):
    b = _stay()  # оплачена до фолио: строк нет
    result = refunds.refund_partial("stay", b, cents=1000, method="card", tenant=TENANT)
    # Строка «Eröffnung» встала (возвращать можно только то, что в книге); переплаты
    # у легаси-сделки нет — возврат отклонён.
    assert result == refunds.RefundResult.REFUSED
    assert DealPayment.objects.filter(deal_id=b.pk, purpose="opening").count() == 1


def test_installment_ticket_is_refused():
    obj = SimpleNamespace(pk=uuid.uuid4(), payment_state="installment")
    assert (
        refunds.refund_partial("ticket", obj, cents=100, method="card", tenant=TENANT)
        == refunds.RefundResult.REFUSED
    )


def _post(user, b, **data):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.views import deal_refund

    request = RequestFactory().post("/x/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = TENANT
    return deal_refund(request, "stay", b.pk)


def _user(role):
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def test_owner_refunds_from_card_with_german_amount(stripe_calls):
    from apps.core.models import Membership

    b = _stay()
    row = _card_row(b)
    resp = _post(_user(Membership.ROLE_OWNER), b, amount="12,50", method="card")
    assert resp.status_code == 302
    row.refresh_from_db()
    assert row.refunded_cents == 1250


def test_staff_cannot_refund(stripe_calls):
    from apps.core.models import Membership

    b = _stay()
    row = _card_row(b)
    assert _post(_user(Membership.ROLE_STAFF), b, amount="10", method="card").status_code == 403
    row.refresh_from_db()
    assert row.refunded_cents == 0 and stripe_calls == []


def test_refund_path_is_owner_only_prefix():

    assert LG.LEGACY_OWNER_ONLY_PREFIXES and any(
        "/dashboard/erstattung/x/".startswith(p) for p in LG.LEGACY_OWNER_ONLY_PREFIXES
    )


def test_failed_rest_refund_keeps_cancel_retryable(monkeypatch):
    """error-handling: не прошёл возврат доплаты остатка — сделка не «возвращено»,
    повтор отмены доберёт остаток (основной платёж — тем же ключом)."""
    calls = []

    def refund(**kw):
        calls.append(kw["payment_intent"])
        if kw["payment_intent"] == "pi_rest" and len(calls) < 3:
            raise stripe.error.APIConnectionError("down")

    monkeypatch.setattr(connect, "refund", refund)
    b = _stay()
    _card_row(b, cents=3000)
    _card_row(b, cents=2000, intent="pi_rest")
    assert refunds.refund_payment("stay", b, TENANT) == refunds.RefundResult.FAILED
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID
    assert refunds.refund_payment("stay", b, TENANT) == refunds.RefundResult.REFUNDED
    rest = DealPayment.objects.get(deal_id=b.pk, stripe_payment_intent="pi_rest")
    assert rest.refunded_cents == 2000
