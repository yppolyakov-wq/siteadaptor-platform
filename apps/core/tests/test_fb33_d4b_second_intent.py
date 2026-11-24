"""FB-33 D4b (стопка 13): второй платёж Stripe к записи, номеру, билету.

Как у заказа (D4a): платёж, которого нет в книге, к сделке с уже записанным главным
платежом (оплачена, возвращена, отменена с «nicht erstatten») — строкой книги на сумму
`amount_total` и назад ОДНОЙ строкой (`refund_intent`); главный платёж не перезаписывается
и не возвращается. Решение владельца 2026-11-24: дубль депозита у неотменённой сделки —
тоже назад сразу. Строка сделки — под `select_for_update(of=self)` (без связанных строк),
Stripe — после блокировки. Сбой и «не ответил» — письмо `duplicate` (повтора нет).
"""

import pytest
import stripe
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core import refunds
from apps.core.models import DealPayment
from apps.core.tests.test_ka_h4_refunds import _booking, _stay, _ticket, _urlconf  # noqa: F401
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_d4b"
_RED = pytest.mark.xfail(strict=True, reason="FB-33 D4b: до правки")
KINDS = ("booking", "stay", "ticket")
TABLE = {"booking": "booking_booking", "stay": "stays_staybooking", "ticket": "events_ticket"}


@pytest.fixture(autouse=True)
def biz():
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        payments_enabled=True,
        owner_email="chef@example.com",
    )


@pytest.fixture
def stripe_refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _make(kind):
    obj = {"booking": _booking, "stay": _stay, "ticket": _ticket}[kind]()
    model = type(obj)
    upd = {}
    if kind == "booking":
        upd = {"price_cents": 5000, "deposit_cents": 0}
    elif kind == "stay":
        upd = {"deposit_cents": 0}
    if upd:
        model.objects.filter(pk=obj.pk).update(**upd)
    obj.refresh_from_db()
    return obj


def _pay(kind, obj, intent, amount=None):
    from apps.booking.payments import mark_deposit_paid
    from apps.events.payments import mark_ticket_paid
    from apps.stays.payments import mark_stay_paid

    schema = connection.schema_name
    kw = {} if amount is None else {"amount_cents": amount}
    if kind == "booking":
        mark_deposit_paid(tenant_schema=schema, booking_id=str(obj.pk), payment_intent=intent, **kw)
    elif kind == "stay":
        mark_stay_paid(tenant_schema=schema, booking_id=str(obj.pk), payment_intent=intent, **kw)
    else:
        mark_ticket_paid(tenant_schema=schema, ticket_id=str(obj.pk), payment_intent=intent, **kw)
    obj.refresh_from_db()
    return obj


def _rows(kind, obj):
    return {
        r.stripe_payment_intent: r
        for r in DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk)
    }


def _cancel(kind, obj, *, refund=True):
    model = type(obj)
    model.objects.filter(pk=obj.pk).update(status="cancelled")
    obj.refresh_from_db()
    if refund:
        refunds.refund_payment(kind, obj, TenantFactory.build(stripe_connect_id=ACCOUNT))
    obj.refresh_from_db()


def _dup_mails(kind, obj):
    return Notification.objects.filter(
        dedupe_key__contains=f":{kind}:{obj.pk}:duplicate", type="refund_failed_owner"
    )


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_duplicate_deposit_on_active_deal(kind, stripe_refunds):
    obj = _pay(kind, _make(kind), "pi_main")
    paid_state = obj.payment_state
    _pay(kind, obj, "pi_second")
    rows = _rows(kind, obj)
    assert rows["pi_second"].refunded_cents == rows["pi_second"].amount_cents > 0
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_second"]
    assert obj.stripe_payment_intent == "pi_main" and obj.payment_state == paid_state


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_late_second_payment_on_refunded_cancelled_refunded_once(kind, stripe_refunds):
    obj = _pay(kind, _make(kind), "pi_main")
    _cancel(kind, obj)
    assert obj.payment_state == type(obj).PAYMENT_REFUNDED
    stripe_refunds.clear()
    _pay(kind, obj, "pi_late")
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_late"]
    late = _rows(kind, obj)["pi_late"]
    assert late.refunded_cents == late.amount_cents > 0
    assert obj.stripe_payment_intent == "pi_main"


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_row_amount_is_stripe_amount(kind, stripe_refunds):
    """10.1 M5: сумма строки — `amount_total` вебхука, а не расчёт сделки."""
    obj = _pay(kind, _make(kind), "pi_main")
    _pay(kind, obj, "pi_second", amount=777)
    assert _rows(kind, obj)["pi_second"].amount_cents == 777


@_RED
def test_stay_kept_payment_untouched(stripe_refunds):
    """Номер отменён с «nicht erstatten» (главный у бизнеса), поздний второй → назад
    только второй, главный оплачен."""
    obj = _pay("stay", _make("stay"), "pi_main")
    _cancel("stay", obj, refund=False)
    state = obj.payment_state
    _pay("stay", obj, "pi_late")
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_late"]
    rows = _rows("stay", obj)
    assert rows["pi_main"].refunded_cents == 0
    assert obj.payment_state == state


@_RED
def test_ticket_repeat_webhook_not_resurrected(stripe_refunds, monkeypatch):
    obj = _pay("ticket", _make("ticket"), "pi_main")
    _cancel("ticket", obj)
    assert obj.payment_state == "refunded"
    stripe_refunds.clear()
    from apps.core import payment_holds

    seen = []
    real = payment_holds.settle_late_payment
    monkeypatch.setattr(
        payment_holds,
        "settle_late_payment",
        lambda kind, o, *, newly_paid: (
            seen.append(newly_paid) or real(kind, o, newly_paid=newly_paid)
        ),
    )
    monkeypatch.setattr(
        "apps.events.payments.settle_late_payment",
        payment_holds.settle_late_payment,
        raising=False,
    )
    _pay("ticket", obj, "pi_main")
    assert True not in seen  # refunded повтором не «оплачен заново»
    assert obj.payment_state == "refunded"
    assert stripe_refunds == []  # повтор вебхука не «оплатил» и не вернул ещё раз


@pytest.mark.parametrize("kind", KINDS)
def test_repeat_second_webhook_single_refund(kind, stripe_refunds):
    obj = _pay(kind, _make(kind), "pi_main")
    _pay(kind, obj, "pi_second")
    _pay(kind, obj, "pi_second")
    assert [c["payment_intent"] for c in stripe_refunds].count("pi_second") <= 1


@pytest.mark.parametrize("kind", KINDS)
def test_replay_of_main_intent_legacy_without_rows_not_refunded(kind, stripe_refunds):
    """10.1 H1: легаси с главным X без строк книги, повтор X — не дубль."""
    obj = _make(kind)
    model = type(obj)
    model.objects.filter(pk=obj.pk).update(
        payment_state=model.PAYMENT_PAID, stripe_payment_intent="pi_legacy"
    )
    obj.refresh_from_db()
    _pay(kind, obj, "pi_legacy")
    assert stripe_refunds == []


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_mark_paid_locks_row(kind, stripe_refunds):
    """№9 / 10.1 H3: строка сделки под FOR UPDATE OF самой сделки (без ресурса/события)."""
    obj = _make(kind)
    with CaptureQueriesContext(connection) as ctx:
        _pay(kind, obj, "pi_main")
    locks = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
    first = locks[0] if locks else ""
    assert TABLE[kind] in first
    assert " OF " in first


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_refund_timeout_notifies_owner(kind, monkeypatch):
    """10.2 H4: у записи/номера/билета повтора нет — «Stripe не ответил» = письмо."""
    obj = _pay(kind, _make(kind), "pi_main")

    def down(**kw):
        raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr("apps.billing.connect.refund", down)
    _pay(kind, obj, "pi_second")
    _pay(kind, obj, "pi_second")
    assert _dup_mails(kind, obj).count() == 1


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_duplicate_deposit_refund_failure_mails_owner_once(kind, monkeypatch):
    obj = _pay(kind, _make(kind), "pi_main")

    def declined(**kw):
        raise stripe.error.CardError("declined", None, "card_declined")

    monkeypatch.setattr("apps.billing.connect.refund", declined)
    _pay(kind, obj, "pi_second")
    assert _dup_mails(kind, obj).count() == 1


def test_balance_payment_not_refunded(stripe_refunds, monkeypatch):
    """`deal_balance` — законная вторая строка своим путём, вебхук депозита её не трогает."""
    from types import SimpleNamespace

    from apps.core import balance_pay
    from apps.promotions import notifications

    monkeypatch.setattr(
        notifications, "_tenant", lambda s: SimpleNamespace(stripe_connect_id=ACCOUNT)
    )
    obj = _make("stay")
    type(obj).objects.filter(pk=obj.pk).update(deposit_cents=3000)
    obj.refresh_from_db()
    _pay("stay", obj, "pi_main")
    balance_pay.mark_balance_paid(
        tenant_schema=connection.schema_name,
        deal_kind="stay",
        deal_id=str(obj.pk),
        payment_intent="pi_rest",
        amount_cents=5000,
        account=ACCOUNT,
    )
    _pay("stay", obj, "pi_main")  # повтор вебхука депозита
    assert stripe_refunds == []
