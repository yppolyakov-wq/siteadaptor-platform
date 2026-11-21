"""FB-33 M2i-7.1, находки ревью (security + silent-failure).

1. Два поздних платежа к отменённому заказу подряд, до возврата первого, — возвращаются оба.
2. Оплата «в пути» (SEPA/Klarna): заказ без e-mail не отменяется, пока платёж обрабатывается;
   не прошёл — снова подлежит отмене.
3. Сбой возврата не роняет вебхук, виден в карточке и повторяется задачей (ограниченно).
4. «Ядовитые» заказы не закрывают очередь; итог прохода — в логе.
5. За минуты до отмены новая ссылка оплаты не выдаётся.
7. В карточке — строка «Automatisch storniert».
"""

import logging
import uuid
from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone

from apps.billing import webhooks
from apps.core import payment_holds
from apps.core.models import DealPayment
from apps.notifications.models import Notification
from apps.orders import public_views, tasks, views
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.orders.tests.test_fb33_m2i71_abandoned import ACCOUNT, NAME, PHONE, _order, _session
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

xfail = pytest.mark.xfail(strict=True, reason="FB-33 M2i-7.1 (ревью): поведения ещё нет")


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def biz():
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        orders_prepay=True,
        payments_enabled=True,
    )


@pytest.fixture
def refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _event(order, event="checkout.session.completed", **kw):
    webhooks.handle_event(event, _session(order, **kw), account=ACCOUNT)
    order.refresh_from_db()
    return order


def _card(order):
    from apps.orders.tests.test_kitchen import _req as _cab_req

    return views.order_detail(_cab_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)


def _pay_request(order, biz):
    request = RequestFactory().get(f"/bestellung/{order.reference_code}/bezahlen/")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = biz
    return request


# --- 1. два поздних платежа до возврата первого --------------------------------------


@xfail
def test_two_late_payments_before_the_first_refund_are_both_refunded(biz, refunds, monkeypatch):
    order = _order()
    tasks.expire_abandoned_online()
    # вебхук A записал оплату, но его возврат ещё не захватил заказ
    real = payment_holds.settle_late_payment
    monkeypatch.setattr(payment_holds, "settle_late_payment", lambda *a, **k: None)
    _event(order, intent="pi_a")
    assert order.payment_state == Order.PAYMENT_PAID and refunds == []
    monkeypatch.setattr(payment_holds, "settle_late_payment", real)

    _event(order, intent="pi_b")  # второй платёж приходит раньше возврата A

    assert sorted(r["payment_intent"] for r in refunds) == ["pi_a", "pi_b"]
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert order.stripe_payment_intent == "pi_a"  # вторым intent не перезаписан
    rows = DealPayment.objects.filter(deal_kind="order", deal_id=order.pk)
    assert rows.count() == 2 and all(r.refunded_cents == r.amount_cents for r in rows)

    # отложенный возврат A и повторы обоих вебхуков ничего не дублируют
    real("order", order, newly_paid=True)
    _event(order, intent="pi_a")
    _event(order, intent="pi_b")
    _event(order, intent="pi_b")
    assert len(refunds) == 2
    assert order.payment_state == Order.PAYMENT_REFUNDED


# --- 2. оплата «в пути» ---------------------------------------------------------------


@xfail
def test_processing_payment_keeps_the_order(biz):
    order = _order()
    _event(order, intent="pi_sepa", status="unpaid")  # Checkout завершён, деньги в пути
    assert order.payment_state == Order.PAYMENT_UNPAID
    assert order.stripe_payment_intent == "pi_sepa"
    assert not DealPayment.objects.filter(deal_kind="order", deal_id=order.pk).exists()

    assert tasks.expire_abandoned_online() == 0
    order.refresh_from_db()
    assert order.status == Order.STATUS_NEW


def test_processing_payment_that_succeeds_is_booked_as_new_money(biz, refunds):
    order = _order()
    _event(order, intent="pi_sepa", status="unpaid")
    _event(order, "checkout.session.async_payment_succeeded", intent="pi_sepa")
    assert order.payment_state == Order.PAYMENT_PAID
    assert order.status == Order.STATUS_CONFIRMED
    row = DealPayment.objects.get(deal_kind="order", deal_id=order.pk)
    assert row.stripe_payment_intent == "pi_sepa" and row.refunded_cents == 0
    assert refunds == []


def test_processing_payment_that_fails_makes_the_order_expirable_again(biz):
    order = _order()
    _event(order, intent="pi_sepa", status="unpaid")
    _event(order, "checkout.session.async_payment_failed", intent="pi_sepa", status="unpaid")
    assert order.stripe_payment_intent == "" and order.payment_state == Order.PAYMENT_UNPAID
    assert tasks.expire_abandoned_online() == 1
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


def test_failed_event_of_another_payment_does_not_touch_the_order(biz):
    order = _order(stripe_payment_intent="pi_mine")
    _event(order, "checkout.session.async_payment_failed", intent="pi_other", status="unpaid")
    assert order.stripe_payment_intent == "pi_mine"


@xfail
def test_processing_payment_closes_pay_link_and_reminder(biz, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no second Stripe session while the payment is processing")

    monkeypatch.setattr("apps.orders.payments.order_checkout_url", boom)
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)
    order = _order(hours_ago=30, email="kim@test.de")
    _event(order, intent="pi_sepa", status="unpaid")
    resp = public_views.order_pay(_pay_request(order, biz), order.reference_code)
    assert resp.status_code == 302 and resp.url.endswith(f"/bestellung/{order.reference_code}/")
    assert tasks.send_due_payment_reminders() == 0
    assert not Notification.objects.filter(type="order_payment_reminder").exists()


def test_processing_payment_of_cancelled_order_is_refunded_when_it_arrives(biz, refunds):
    order = _order()
    tasks.expire_abandoned_online()
    _event(order, intent="pi_sepa", status="unpaid")
    _event(order, "checkout.session.async_payment_succeeded", intent="pi_sepa")
    assert order.status == Order.STATUS_CANCELLED
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert [r["payment_intent"] for r in refunds] == ["pi_sepa"]


def test_payment_holds_still_do_not_expire_orders():
    """Неизменность: общий снос удержаний (Vorkasse/счёт у брони, номера, билета)
    заказов не касается — автоотмена заказа живёт только в `orders.tasks`."""
    assert "order" not in payment_holds.HOLD_KINDS
    assert "order_payment" not in payment_holds._PROCESSING_KINDS
    vorkasse = _order(method=Order.METHOD_VORKASSE)
    Order.objects.filter(pk=vorkasse.pk).update(payment_due_at=timezone.now() - timedelta(days=1))
    tenant = TenantFactory.build()
    assert payment_holds.expire_overdue(tenant) == 0
    assert tasks.expire_abandoned_online() == 0
    vorkasse.refresh_from_db()
    assert vorkasse.status == Order.STATUS_NEW


# --- 3. сбой возврата ----------------------------------------------------------------


@xfail
def test_crash_in_late_refund_does_not_fail_the_webhook(biz, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(payment_holds, "settle_late_payment", boom)
    order = _order(phone=PHONE)
    tasks.expire_abandoned_online()
    with caplog.at_level(logging.ERROR):
        _event(order, intent="pi_late")  # не падает: Stripe не должен получить 500
    assert order.payment_state == Order.PAYMENT_PAID
    assert str(order.pk) in caplog.text
    assert NAME not in caplog.text and PHONE not in caplog.text


@xfail
def test_open_refund_is_flagged_on_the_card(biz, monkeypatch):
    def boom(**kw):
        raise RuntimeError("stripe down")

    monkeypatch.setattr("apps.billing.connect.refund", boom)
    order = _order()
    tasks.expire_abandoned_online()
    _event(order, intent="pi_late")
    body = _card(order).content.decode()
    assert "data-refund-open" in body
    assert "Rückerstattung offen — bitte in Stripe prüfen" in body


def test_refunded_or_live_order_has_no_open_refund_flag(biz, refunds):
    done = _order()
    tasks.expire_abandoned_online()
    _event(done, intent="pi_late")
    assert done.payment_state == Order.PAYMENT_REFUNDED
    assert "data-refund-open" not in _card(done).content.decode()
    live = _order(hours_ago=1)
    _event(live, intent="pi_live")
    assert "data-refund-open" not in _card(live).content.decode()


@xfail
def test_failed_late_refund_is_retried_by_the_task(biz, monkeypatch):
    state = {"fail": True}
    calls = []

    def refund(**kw):
        calls.append(kw)
        if state["fail"]:
            raise RuntimeError("stripe down")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    order = _order()
    tasks.expire_abandoned_online()
    _event(order, intent="pi_late")
    assert order.payment_state == Order.PAYMENT_PAID and len(calls) == 1

    state["fail"] = False
    later = timezone.now() + timedelta(hours=1)
    assert tasks.retry_late_refunds(later) == 1
    order.refresh_from_db()
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert len(calls) == 2
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]  # тот же возврат
    assert tasks.retry_late_refunds(later + timedelta(hours=1)) == 0
    assert len(calls) == 2


@xfail
def test_refund_retries_are_bounded(biz, monkeypatch):
    calls = []

    def refund(**kw):
        calls.append(kw)
        raise RuntimeError("stripe down")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    order = _order()
    tasks.expire_abandoned_online()
    _event(order, intent="pi_late")
    now = timezone.now()
    for step in range(1, 40):
        tasks.retry_late_refunds(now + timedelta(minutes=15 * step))
    assert len(calls) == 1 + tasks.REFUND_RETRY_MAX  # первая попытка + ограниченные повторы
    order.refresh_from_db()
    assert order.payment_state == Order.PAYMENT_PAID  # не ложное «возвращено»


@xfail
def test_retry_leaves_ordinary_orders_alone(biz, refunds):
    live = _order(hours_ago=1)
    _event(live, intent="pi_live")  # оплачен и подтверждён
    assert tasks.retry_late_refunds(timezone.now() + timedelta(hours=1)) == 0
    assert refunds == []
    live.refresh_from_db()
    assert live.payment_state == Order.PAYMENT_PAID


# --- 4. «ядовитые» заказы и итог прохода ---------------------------------------------


@xfail
def test_poison_orders_do_not_block_the_queue(monkeypatch, caplog):
    monkeypatch.setattr(tasks, "ABANDONED_BATCH", 2)
    bad = [_order(hours_ago=50, phone=PHONE), _order(hours_ago=49)]  # самые старые
    good = [_order(hours_ago=30), _order(hours_ago=29), _order(hours_ago=28)]
    bad_pks = {o.pk for o in bad}
    real = OrderSM.apply

    def apply(self, instance, *a, **kw):
        if instance.pk in bad_pks:
            raise RuntimeError("kaputt")
        return real(self, instance, *a, **kw)

    monkeypatch.setattr(OrderSM, "apply", apply)
    with caplog.at_level(logging.INFO):
        assert tasks.expire_abandoned_online() == 3
    for o in good:
        o.refresh_from_db()
        assert o.status == Order.STATUS_CANCELLED
    summary = [r for r in caplog.records if "abandoned-online" in r.getMessage()]
    info = [r.getMessage() for r in summary if r.levelno == logging.INFO]
    errors = [r.getMessage() for r in summary if r.levelno == logging.ERROR]
    assert any(connection.schema_name in m and "cancelled=3" in m and "failed=2" in m for m in info)
    assert any(all(str(pk) in m for pk in bad_pks) for m in errors)
    assert NAME not in caplog.text and PHONE not in caplog.text


@xfail
def test_full_pass_is_reported(monkeypatch, caplog):
    monkeypatch.setattr(tasks, "ABANDONED_BATCH", 2)
    monkeypatch.setattr(tasks, "ABANDONED_MAX_BATCHES", 1)
    for hours in (30, 29, 28):
        _order(hours_ago=hours)
    with caplog.at_level(logging.WARNING):
        assert tasks.expire_abandoned_online() == 2
    assert "batch full" in caplog.text
    assert tasks.expire_abandoned_online() == 1  # остаток — следующим проходом


# --- 5. за минуты до отмены ссылку оплаты не выдаём ----------------------------------


@xfail
def test_no_new_pay_link_shortly_before_the_cancel(biz, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no Stripe session minutes before the cancel")

    monkeypatch.setattr("apps.orders.payments.order_checkout_url", boom)
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)
    order = _order(hours_ago=23.5)
    request = _pay_request(order, biz)
    resp = public_views.order_pay(request, order.reference_code)
    assert resp.status_code == 302 and resp.url.endswith(f"/bestellung/{order.reference_code}/")
    assert len(list(get_messages(request))) == 1


def test_pay_link_is_still_given_in_time_and_to_orders_with_email(biz, monkeypatch):
    monkeypatch.setattr(
        "apps.orders.payments.order_checkout_url", lambda *a, **k: "https://stripe.test/pay"
    )
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)
    for order in (_order(hours_ago=2), _order(hours_ago=23.5, email="kim@test.de")):
        resp = public_views.order_pay(_pay_request(order, biz), order.reference_code)
        assert resp.url == "https://stripe.test/pay"


# --- 7. карточка: «Automatisch storniert» ---------------------------------------------


@xfail
def test_card_says_the_order_was_cancelled_automatically(biz):
    order = _order()
    tasks.expire_abandoned_online()
    body = _card(order).content.decode()
    assert "data-auto-cancelled" in body
    assert "Automatisch storniert: nicht bezahlt" in body


def test_manual_cancel_has_no_automatic_line(biz):
    order = _order()
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    assert "data-auto-cancelled" not in _card(order).content.decode()
