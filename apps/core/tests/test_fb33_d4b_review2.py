"""FB-33 стопка 13, повторное ревью денег (план §10.8): соседние пути возврата не молчат.

- Поздний возврат ГЛАВНОГО платежа отменённого заказа: кэш счётчика недоступен или попытки
  исчерпаны (в том числе постоянным исключением) — одно письмо владельцу на заказ.
- Первая доля рассрочки на отменённый билет: сбой возврата не роняет вебхук, письмо.
- Повтор второго платежа не берёт строки моложе `EXTRA_RETRY_MIN_AGE` (гонка с вебхуком).
- `ExpirePass`: часы — с первого вызова Stripe; серия `unknown` — по аккаунту Connect; общий
  стоп — только по ошибкам связи.
- Флаг «письмо об исчерпании ушло» — только после постановки письма.
- LOW: пустой аккаунт `expire`, обёртки, упор выборки, `_log_id` в логах вебхука, текст
  письма «возможно, уже возвращено».
"""

import logging
import uuid
from datetime import timedelta

import pytest
import stripe
from django.db import connection
from django.utils import timezone

from apps.billing import connect, webhooks
from apps.core import payment_holds, refunds
from apps.core.models import DealPayment
from apps.notifications.models import Notification
from apps.orders import payments, tasks
from apps.orders.models import Order
from apps.orders.tests.test_fb33_m2i71_abandoned import _order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
_RED = pytest.mark.xfail(strict=True, reason="FB-33 §10.8: до правки")
ACCOUNT = "acct_s13r2"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture(autouse=True)
def biz():
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        orders_prepay=True,
        payments_enabled=True,
        owner_email="chef@example.com",
    )


def _mails(kind, pk):
    return Notification.objects.filter(
        dedupe_key__contains=f":{kind}:{pk}:", type="refund_failed_owner"
    )


def _late_paid_cancelled_order():
    """Отменённый заказ, оплаченный онлайн, возврат не прошёл («Rückerstattung offen»)."""
    order = _order(hours_ago=2)
    Order.objects.filter(pk=order.pk).update(
        status=Order.STATUS_CANCELLED,
        payment_state=Order.PAYMENT_PAID,
        stripe_payment_intent="pi_late",
    )
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_late",
        source="webhook",
    )
    order.refresh_from_db()
    return order


# ───────────── 1. главный платёж заказа ─────────────


@_RED
def test_order_main_refund_cache_down_mails_once(monkeypatch):
    from django.core.cache import cache

    order = _late_paid_cancelled_order()
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)

    def boom(*a, **kw):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "get", boom)
    now = timezone.now()
    tasks.retry_late_refunds(now)
    tasks.retry_late_refunds(now + timedelta(hours=1))
    assert _mails("order", order.pk).count() == 1


@_RED
def test_order_main_refund_crash_mails_after_exhaustion(monkeypatch):
    order = _late_paid_cancelled_order()

    def crash(*a, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(refunds, "refund_payment", crash)
    now = timezone.now()
    for step in range(40):
        tasks.retry_late_refunds(now + timedelta(minutes=15 * step))
    assert _mails("order", order.pk).count() == 1


# ───────────── 2. рассрочка билета ─────────────


@_RED
def test_installment_late_refund_crash_does_not_raise_and_mails(monkeypatch):
    from apps.events import payments as event_payments
    from apps.events.tests.test_b2_6_balance_reminder import _ticket

    ticket = _ticket("pending")

    def boom(*a, **kw):
        raise RuntimeError("stripe kaputt")

    monkeypatch.setattr(payment_holds, "settle_late_payment", boom)
    assert event_payments.create_installment_plan(
        tenant_schema=connection.schema_name, ticket_id=str(ticket.id)
    )
    assert _mails("ticket", ticket.pk).count() == 1


# ───────────── 3. свежая строка ─────────────


def _extra_row(order, intent, age):
    row = DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent=intent,
        source=payment_holds.EXTRA_SOURCE,
    )
    DealPayment.objects.filter(pk=row.pk).update(created_at=timezone.now() - age)
    return row


def _live_order():
    order = _order(hours_ago=1, email="gast@example.com")
    Order.objects.filter(pk=order.pk).update(
        status=Order.STATUS_CONFIRMED,
        payment_state=Order.PAYMENT_PAID,
        stripe_payment_intent="pi_main",
    )
    order.refresh_from_db()
    return order


@_RED
def test_retry_skips_rows_younger_than_min_age(monkeypatch):
    from django.core.cache import cache

    order = _live_order()
    _extra_row(order, "pi_now", timedelta(seconds=10))
    called = []
    monkeypatch.setattr(refunds, "refund_intent", lambda *a, **kw: called.append(a))
    payment_holds.retry_extra_refunds(timezone.now(), kinds=("order",))
    key = payment_holds._extra_retry_key(connection.schema_name, "order", order.pk, "pi_now")
    assert called == [] and cache.get(key) is None


# ───────────── 4. ExpirePass ─────────────


class _Svc:
    def __init__(self):
        self.calls = []
        self.errors = {}

    def client(self, connect_id):
        svc = self

        class _Sessions:
            @staticmethod
            def expire(session_id, params=None, options=None):
                svc.calls.append((connect_id, session_id))
                exc = svc.errors.get(connect_id)
                if exc is not None:
                    raise exc
                return {"id": session_id, "status": "expired"}

            @staticmethod
            def retrieve(session_id, params=None, options=None):
                return {"id": session_id, "status": "open"}

        class _V1:
            class checkout:  # noqa: N801
                sessions = _Sessions

        class _C:
            v1 = _V1

        return _C


@pytest.fixture
def svc(monkeypatch):
    s = _Svc()
    monkeypatch.setattr(connect, "_session_client", s.client)
    return s


def _remembered(n, acct):
    pks = []
    for i in range(n):
        order = _order(hours_ago=1)
        payments._remember_session(order, f"cs_{acct}_{i}", acct)
        pks.append(order.pk)
    return pks


@_RED
def test_expire_clock_starts_at_first_stripe_call(svc, monkeypatch):
    clock = iter([0.0])
    monkeypatch.setattr(payments, "_monotonic", lambda: next(clock, 10_000.0))
    run = payments.ExpirePass()  # проход начат в 0, до первого вызова Stripe прошло 10 000 с
    pks = _remembered(1, ACCOUNT)
    payments.expire_open_sessions(pks, connect_id=ACCOUNT, run=run)
    assert len(svc.calls) == 1


@_RED
def test_unknown_streak_per_account_other_account_closed(svc):
    run = payments.ExpirePass()
    bad = _remembered(payments.EXPIRE_UNKNOWN_STOP + 2, "acct_bad")
    good = _remembered(1, "acct_good")
    svc.errors["acct_bad"] = stripe.error.PermissionError("no access")
    payments.expire_open_sessions(bad, connect_id="acct_bad", run=run)
    payments.expire_open_sessions(good, connect_id="acct_good", run=run)
    assert len([c for c in svc.calls if c[0] == "acct_bad"]) == payments.EXPIRE_UNKNOWN_STOP
    assert ("acct_good", "cs_acct_good_0") in svc.calls


def test_offline_streak_stops_the_whole_pass(svc):
    run = payments.ExpirePass()
    bad = _remembered(payments.EXPIRE_UNKNOWN_STOP + 1, "acct_off")
    good = _remembered(1, "acct_good2")
    svc.errors["acct_off"] = stripe.error.APIConnectionError("timeout")
    payments.expire_open_sessions(bad, connect_id="acct_off", run=run)
    payments.expire_open_sessions(good, connect_id="acct_good2", run=run)
    assert not [c for c in svc.calls if c[0] == "acct_good2"]


# ───────────── 5. флаг «письмо ушло» ─────────────


@_RED
def test_exhausted_mail_flag_set_only_after_mail(monkeypatch):
    order = _live_order()
    _extra_row(order, "pi_dup", timedelta(hours=1))
    monkeypatch.setattr(
        payment_holds, "_extra_retry_state", lambda *a, **kw: payment_holds.RETRY_EXHAUSTED
    )
    from apps.notifications import services

    real = services.notify
    state = {"fail": True}

    def flaky(**kw):
        if state["fail"]:
            raise RuntimeError("queue down")
        return real(**kw)

    monkeypatch.setattr(services, "notify", flaky)
    payment_holds.retry_extra_refunds(timezone.now(), kinds=("order",))
    assert not _mails("order", order.pk).exists()
    state["fail"] = False
    payment_holds.retry_extra_refunds(timezone.now(), kinds=("order",))
    assert _mails("order", order.pk).count() == 1


# ───────────── 6. LOW ─────────────


@_RED
def test_expire_empty_account_is_unknown_without_client(monkeypatch):
    def no_client(connect_id):
        raise AssertionError("client must not be built")

    monkeypatch.setattr(connect, "_session_client", no_client)
    assert connect.expire_session(connect_id="", session_id="cs_x") == connect.UNKNOWN


@_RED
def test_retry_extra_crash_does_not_skip_order_block(monkeypatch):
    order = _late_paid_cancelled_order()
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))

    def boom(*a, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(payment_holds, "retry_extra_refunds", boom)
    tasks.retry_late_refunds(timezone.now())
    order.refresh_from_db()
    assert calls and order.payment_state == Order.PAYMENT_REFUNDED


@_RED
def test_order_late_payment_crash_mails(monkeypatch):
    order = _order(hours_ago=1)
    Order.objects.filter(pk=order.pk).update(status=Order.STATUS_CANCELLED)

    def boom(*a, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(payment_holds, "settle_late_payment", boom)
    payments.mark_order_paid(
        tenant_schema=connection.schema_name, order_id=str(order.id), payment_intent="pi_x"
    )
    assert _mails("order", order.pk).count() == 1


@_RED
def test_scan_cap_warns(monkeypatch, caplog):
    monkeypatch.setattr(payment_holds, "EXTRA_SCAN_MAX", 1)
    for i in range(2):
        _extra_row(_live_order(), f"pi_cap{i}", timedelta(hours=1))
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)
    with caplog.at_level(logging.WARNING):
        payment_holds.retry_extra_refunds(timezone.now(), kinds=("order",))
    assert any(
        "EXTRA_SCAN_MAX" in r.getMessage() or "scan" in r.getMessage() for r in caplog.records
    )


@_RED
def test_webhook_logs_account_and_schema_without_control_chars(caplog):
    caplog.set_level(logging.INFO)
    obj = {
        "payment_intent": "pi_x",
        "payment_status": "paid",
        "metadata": {
            "kind": "order_payment",
            "tenant_schema": "biz\nFAKE",
            "order_id": str(uuid.uuid4()),
        },
    }
    webhooks.handle_event("checkout.session.completed", obj, account="acct\nFAKE")
    assert caplog.records
    assert all("\n" not in r.getMessage() for r in caplog.records)


@_RED
def test_uncertain_mail_says_possibly_refunded(monkeypatch):
    from django.utils import translation

    order = _live_order()
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_main",
        source="webhook",
    )
    _extra_row(order, "pi_two", timedelta(hours=1))

    def refund(**kw):
        if kw["payment_intent"] == "pi_two":
            raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    Order.objects.filter(pk=order.pk).update(status=Order.STATUS_CANCELLED)
    order.refresh_from_db()
    with translation.override("de"):
        refunds.refund_payment(
            "order", order, TenantFactory.build(stripe_connect_id=ACCOUNT, owner_email="o@t.de")
        )
    mail = _mails("order", order.pk).get()
    assert "Möglicherweise wurde die Zahlung bereits erstattet" in mail.payload["body"]
