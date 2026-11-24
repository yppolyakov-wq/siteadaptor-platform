"""FB-33 D4a, ревью диффа (план §10.7): повтор возврата второго платежа, `expire`, перечитка
строки перед Stripe, возвращённая сделка и удержание.

- Повтор возврата второго платежа — в ядре (`payment_holds.retry_extra_refunds`), только по
  строкам, записанным новым путём (`DealPayment.source == "extra"`): прежние двойные оплаты
  (до деплоя) задним числом не возвращаются. Свежие первыми — исчерпанные не держат окно;
  письмо об исчерпании — одно на строку; кэш счётчика недоступен — письмо, а не «ждать».
- `expire`: свой клиент Stripe (таймаут, без сетевых повторов); `unknown` — пропуск заказа,
  стоп прохода после `EXPIRE_UNKNOWN_STOP` подряд (общий счёт прохода по схемам); неоднозначный
  `InvalidRequestError` решает `Session.retrieve(...).status`.
"""

import logging
from datetime import timedelta

import pytest
import stripe
from django.utils import timezone

from apps.billing import connect
from apps.core import payment_holds, refunds
from apps.core.models import DealPayment
from apps.notifications.models import Notification
from apps.orders import payments, tasks
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.orders.tests.test_fb33_d4a_second_payment import _live_paid, _pay
from apps.orders.tests.test_fb33_m2i71_abandoned import _order

pytestmark = pytest.mark.django_db
ACCOUNT = "acct_d4a"


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def biz():
    from django.db import connection

    from apps.tenants.tests.factories import TenantFactory

    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        orders_prepay=True,
        payments_enabled=True,
        owner_email="chef@example.com",
    )


@pytest.fixture
def stripe_refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _down(**kw):
    raise stripe.error.APIConnectionError("timeout")


def _dup_mails(order):
    return Notification.objects.filter(
        dedupe_key__contains=f":order:{order.pk}:duplicate", type="refund_failed_owner"
    )


def _row(order, intent, *, source="extra", refunded=0, age=None):
    row = DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        refunded_cents=refunded,
        stripe_payment_intent=intent,
        source=source,
    )
    if age is not None:
        DealPayment.objects.filter(pk=row.pk).update(created_at=timezone.now() - age)
    return row


# ───────────── повтор возврата второго платежа ─────────────


def test_extra_row_is_marked_extra(biz, stripe_refunds):
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    row = DealPayment.objects.get(stripe_payment_intent="pi_second")
    assert row.source == "extra"


def test_retry_only_rows_of_the_new_path(biz, stripe_refunds):
    """Прежняя двойная оплата (строка до деплоя, `source="webhook"`) — не автовозврат."""
    order = _live_paid()
    _row(order, "pi_old", source="webhook")
    _row(order, "pi_new")
    stripe_refunds.clear()
    payment_holds.retry_extra_refunds(timezone.now() + timedelta(hours=1), kinds=("order",))
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_new"]


def test_retry_extra_cache_down_mails_owner(biz, monkeypatch):
    from django.core.cache import cache

    order = _live_paid()
    monkeypatch.setattr("apps.billing.connect.refund", _down)
    _pay(order, "pi_second", amount=1000)
    assert not _dup_mails(order).exists()

    def boom(*a, **kw):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "get", boom)
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    assert _dup_mails(order).count() == 1


def test_retry_extra_not_starved_by_exhausted(biz, stripe_refunds, monkeypatch):
    monkeypatch.setattr(payment_holds, "EXTRA_RETRY_BATCH", 2)
    now = timezone.now()
    stale = []
    for i in range(3):
        order = _live_paid(f"pi_m{i}")
        _row(order, f"pi_old{i}", age=timedelta(days=2))
        stale.append(order)
    fresh = _live_paid("pi_mf")
    _row(fresh, "pi_fresh", age=timedelta(minutes=5))
    monkeypatch.setattr(
        payment_holds,
        "_extra_retry_state",
        lambda schema, kind, pk, intent, now: (
            "due" if intent == "pi_fresh" else payment_holds.RETRY_EXHAUSTED
        ),
    )
    stripe_refunds.clear()
    payment_holds.retry_extra_refunds(now, kinds=("order",))
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_fresh"]


def test_retry_exhausted_notifies_once_per_row(biz, monkeypatch):
    sent = []
    monkeypatch.setattr("apps.billing.connect.refund", _down)
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    monkeypatch.setattr(
        refunds, "notify_duplicate_failed", lambda *a, **kw: sent.append(kw.get("intent"))
    )
    now = timezone.now()
    for step in range(1, 40):
        tasks.retry_late_refunds(now + timedelta(minutes=15 * step))
    assert sent == ["pi_second"]


# ───────────── expire ─────────────


class _Svc:
    def __init__(self):
        self.expired = []
        self.errors = {}
        self.status = {}

    def expire(self, session_id, params=None, options=None):
        self.expired.append(session_id)
        exc = self.errors.get(session_id)
        if exc is not None:
            raise exc
        return {"id": session_id, "status": "expired"}

    def retrieve(self, session_id, params=None, options=None):
        return {"id": session_id, "status": self.status.get(session_id, "open")}


@pytest.fixture
def svc(monkeypatch):
    s = _Svc()

    class _V1:
        class checkout:  # noqa: N801
            sessions = s

    class _Client:
        v1 = _V1

    monkeypatch.setattr(connect, "_session_client", lambda connect_id: _Client, raising=False)
    return s


def test_session_client_has_timeout_and_no_retries(monkeypatch):
    seen = {}

    class _Fake:
        def __init__(self, api_key, **kw):
            seen.update(kw)

    monkeypatch.setattr(stripe, "StripeClient", _Fake)
    connect._session_client("acct_x")
    assert seen["stripe_account"] == "acct_x" and seen["max_network_retries"] == 0
    assert getattr(seen["http_client"], "_timeout", None) == connect.EXPIRE_TIMEOUT


def test_retrieve_decides_outcome(svc):
    ambiguous = stripe.error.InvalidRequestError("This session cannot be expired.", None)
    svc.errors = {"cs_done": ambiguous, "cs_open": ambiguous}
    svc.status = {"cs_done": "complete", "cs_open": "open"}
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_done") == connect.CLOSED
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_open") == connect.UNKNOWN


def test_unknown_on_first_order_second_closed(biz, svc):
    first, second = _order(hours_ago=30), _order(hours_ago=29)
    payments._remember_session(first, "cs_a", ACCOUNT)
    payments._remember_session(second, "cs_b", ACCOUNT)
    svc.errors["cs_a"] = stripe.error.APIConnectionError("timeout")
    tasks.expire_abandoned_online()
    assert svc.expired == ["cs_a", "cs_b"]
    assert payments.remembered_sessions(second.pk) == []


def test_unknown_streak_stops_pass_across_schemas(svc):
    run = payments.ExpirePass()
    pks = []
    for i in range(payments.EXPIRE_UNKNOWN_STOP + 2):
        order = _order(hours_ago=1)
        payments._remember_session(order, f"cs_{i}", ACCOUNT)
        svc.errors[f"cs_{i}"] = stripe.error.APIConnectionError("timeout")
        pks.append(order.pk)
    payments.expire_open_sessions(pks[:2], connect_id=ACCOUNT, run=run)
    payments.expire_open_sessions(pks[2:], connect_id=ACCOUNT, run=run)
    assert len(svc.expired) == payments.EXPIRE_UNKNOWN_STOP


# ───────────── refund_intent, возвращённая сделка, удержание ─────────────


def test_refund_intent_rereads_row_before_stripe(biz, stripe_refunds, monkeypatch):
    """Владелец вернул строку между чтением под блокировкой и вызовом Stripe — без
    второго возврата и без ложного письма."""
    order = _live_paid()
    row = _row(order, "pi_second")
    real = refunds._ledger_row

    def racing(kind, obj, intent):
        found = real(kind, obj, intent)
        DealPayment.objects.filter(pk=row.pk).update(refunded_cents=1000)
        return found

    monkeypatch.setattr(refunds, "_ledger_row", racing)
    stripe_refunds.clear()
    result = refunds.refund_intent("order", order, "pi_second", biz)
    assert result == refunds.RefundResult.ALREADY and stripe_refunds == []


def test_refunded_deal_retry_skips_partially_refunded_rows(biz, stripe_refunds):
    order = _live_paid()
    _row(order, "pi_kept", refunded=300)
    Order.objects.filter(pk=order.pk).update(
        payment_state=Order.PAYMENT_REFUNDED, status=Order.STATUS_CANCELLED
    )
    order.refresh_from_db()
    stripe_refunds.clear()
    result = refunds.refund_payment("order", order, biz)
    assert stripe_refunds == [] and result == refunds.RefundResult.ALREADY


def test_refund_on_cancel_uncertain_keeps_no_retained_revenue(biz, monkeypatch):
    from apps.core import money_contract

    order = _live_paid()
    retained = []
    monkeypatch.setattr(refunds, "refund_payment", lambda *a, **kw: refunds.RefundResult.UNCERTAIN)
    monkeypatch.setattr(money_contract, "retain_on_cancel", lambda *a, **kw: retained.append(a))
    refunds.refund_on_cancel("order", order, "cancelled", "confirmed", biz)
    assert retained == []


def test_cancel_uncertain_mail_once_not_per_minute(biz, monkeypatch):
    order = _live_paid()
    _row(order, "pi_second", source="extra")
    monkeypatch.setattr(
        "apps.billing.connect.refund",
        lambda **kw: _down() if kw["payment_intent"] == "pi_second" else None,
    )
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    refunds.refund_payment("order", order, biz)
    keys = list(
        Notification.objects.filter(type="refund_failed_owner").values_list("dedupe_key", flat=True)
    )
    assert len(keys) == 1 and keys[0].endswith(
        f":cancel:{refunds.duplicate_key('order', order.pk, 'pi_second')}"
    )


def test_extra_without_amount_warns(biz, stripe_refunds, caplog):
    order = _live_paid()
    with caplog.at_level(logging.WARNING):
        _pay(order, "pi_second")
    assert any("amount" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


@pytest.mark.parametrize("kind", ["order", "stay"])
def test_cancel_other_rows_refusal_rolls_back_by_kind(kind, biz, monkeypatch):
    """Явный отказ Stripe по второй строке — откат и письмо (заказ и номер)."""
    from apps.core.tests.test_ka_h4_refunds import _paid, _stay

    def refund(**kw):
        if kw["payment_intent"] == "pi_second":
            raise stripe.error.CardError("declined", None, "card_declined")

    obj = _live_paid() if kind == "order" else _paid(_stay(), intent="pi_main")
    DealPayment.objects.create(
        deal_kind=kind,
        deal_id=obj.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_second",
        source="extra",
    )
    monkeypatch.setattr("apps.billing.connect.refund", refund)
    type(obj).objects.filter(pk=obj.pk).update(status="cancelled")
    obj.refresh_from_db()
    assert refunds.refund_payment(kind, obj, biz) == refunds.RefundResult.FAILED
    obj.refresh_from_db()
    assert obj.payment_state == type(obj).PAYMENT_PAID
