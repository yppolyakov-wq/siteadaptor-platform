"""FB-33 M2i-7.1: автоотмена брошенных онлайн-заказов без e-mail.

После M2i-7 заказ корзины уходит на онлайн-оплату и без адреса. Если гость оплату бросил,
заказ висел «new / unpaid» и держал склад и лимит акции, пока владелец не отменит руками:
напоминание об оплате шлётся только на e-mail, а писать некуда. Теперь такой заказ
(stripe · unpaid · new · без e-mail клиента · без платежа) через `ORDERS_ABANDONED_HOURS`
(24) отменяет beat — штатным переходом FSM, под блокировкой строки с повторной проверкой.
Сессия Stripe такого заказа закрывается раньше срока; оплата, всё же пришедшая к уже
отменённому заказу, возвращается — один раз.
"""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.billing import webhooks
from apps.catalog.models import Product
from apps.core import payment_holds
from apps.core.models import DealPayment
from apps.loyalty.models import Voucher
from apps.orders import payments, public_views, services, tasks
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_m2i71"
PHONE = "+49 151 7654321"
NAME = "Geheimkunde"


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def biz():
    """Тенант текущей схемы с connected account — вебхук принимает только его события."""
    return TenantFactory(
        schema_name=connection.schema_name, stripe_connect_id=ACCOUNT, orders_prepay=True
    )


@pytest.fixture
def refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _product(stock=30, price="10.00"):
    return Product.objects.create(
        name={"de": f"Ware {uuid.uuid4().hex[:6]}"}, base_price=price, stock_quantity=stock
    )


def _order(*, hours_ago=25, email="", method=Order.METHOD_STRIPE, product=None, **kw):
    """Заказ корзины; `hours_ago` — возраст (created_at правим в БД, поле auto_now_add)."""
    update = {k: kw.pop(k) for k in ("payment_state", "stripe_payment_intent") if k in kw}
    order = services.create_order(
        items=[(product or _product(), 1)],
        name=NAME,
        email=email,
        payment_method=method,
        **kw,
    )
    update["created_at"] = timezone.now() - timedelta(hours=hours_ago)
    Order.objects.filter(pk=order.pk).update(**update)
    order.refresh_from_db()
    return order


def _session(order, *, intent=None, status="paid"):
    return {
        "payment_intent": intent or f"pi_{uuid.uuid4().hex[:8]}",
        "payment_status": status,
        "metadata": {
            "kind": "order_payment",
            "tenant_schema": connection.schema_name,
            "order_id": str(order.id),
        },
    }


def _hook(order, **kw):
    webhooks.handle_event("checkout.session.completed", _session(order, **kw), account=ACCOUNT)
    order.refresh_from_db()
    return order


# --- 1. отмена по сроку: склад, лимит акции, промокод ------------------------------


def test_abandoned_order_is_cancelled_and_releases_stock_and_promo_limit():
    product = _product(stock=30, price="2.49")
    promo = Promotion.objects.create(
        title={"de": "Sommer-Deal"},
        status="active",
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=product.base_price,
        available_quantity=10,
    )
    order = _order(hours_ago=24.02, product=product)  # 24 ч + 1 мин
    product.refresh_from_db()
    promo.refresh_from_db()
    assert (product.stock_quantity, promo.available_quantity) == (29, 9)

    assert tasks.expire_abandoned_online() == 1

    order.refresh_from_db()
    product.refresh_from_db()
    promo.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED
    assert order.payment_state == Order.PAYMENT_UNPAID  # денег не было — нечего возвращать
    assert product.stock_quantity == 30  # склад
    assert promo.available_quantity == 10  # лимит акции


def test_abandoned_order_gives_the_voucher_back():
    voucher = Voucher.objects.create(code="MINUS10", label="−10 %", discount_percent=10, max_uses=1)
    order = _order(voucher_code="MINUS10")
    voucher.refresh_from_db()
    assert order.voucher_code == "MINUS10" and voucher.used_count == 1

    assert tasks.expire_abandoned_online() == 1

    voucher.refresh_from_db()
    assert voucher.used_count == 0  # промокод снова действует


def test_phone_alone_does_not_keep_the_order():
    """Развилка владельца: напоминание уходит только по e-mail — телефон заказ не держит."""
    order = _order(phone=PHONE)
    assert tasks.expire_abandoned_online() == 1
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


def test_deadline_comes_from_the_setting(settings):
    settings.ORDERS_ABANDONED_HOURS = 2
    order = _order(hours_ago=3)
    assert tasks.expire_abandoned_online() == 1
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


def test_default_deadline_is_24_hours():
    assert dj_settings.ORDERS_ABANDONED_HOURS == 24


# --- 2. чужие заказы не трогаются ---------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"email": "kim@test.de"},  # есть адрес — действует напоминание об оплате
        {"method": Order.METHOD_VORKASSE},
        {"method": Order.METHOD_INVOICE},
        {"method": Order.METHOD_ON_SITE},
        {"payment_state": Order.PAYMENT_PAID},
        {"stripe_payment_intent": "pi_inflight"},  # платёж уже привязан
    ],
    ids=["email", "vorkasse", "invoice", "on_site", "paid", "intent"],
)
def test_other_orders_are_left_alone(kw):
    order = _order(**kw)
    assert tasks.expire_abandoned_online() == 0
    order.refresh_from_db()
    assert order.status == Order.STATUS_NEW


def test_confirmed_order_is_left_alone():
    order = _order()
    OrderSM().apply(order, Order.STATUS_CONFIRMED)
    assert tasks.expire_abandoned_online() == 0
    order.refresh_from_db()
    assert order.status == Order.STATUS_CONFIRMED


def test_running_payment_hold_is_left_alone():
    """Срок оплаты заказа ещё не вышел (его ставит способ или «деньги в пути») — ждём."""
    order = _order()
    Order.objects.filter(pk=order.pk).update(payment_due_at=timezone.now() + timedelta(days=3))
    assert tasks.expire_abandoned_online() == 0
    order.refresh_from_db()
    assert order.status == Order.STATUS_NEW


# --- 3. до срока — нет ---------------------------------------------------------------


def test_order_before_the_deadline_stays():
    order = _order(hours_ago=23.9)
    assert tasks.expire_abandoned_online() == 0
    order.refresh_from_db()
    assert order.status == Order.STATUS_NEW


# --- 4. оплата между выборкой и блокировкой -----------------------------------------


def test_payment_between_select_and_lock_wins(biz, monkeypatch):
    """Заказ попал в выборку, но до блокировки пришёл вебхук — повторная проверка под
    локом отмену не делает, склад не возвращается."""
    product = _product(stock=5)
    order = _order(product=product)
    stale = list(tasks._abandoned_pks(timezone.now()))
    assert stale == [order.pk]
    _hook(order)
    assert order.payment_state == Order.PAYMENT_PAID
    monkeypatch.setattr(tasks, "_abandoned_pks", lambda now, **kw: stale)

    assert tasks.expire_abandoned_online() == 0

    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.STATUS_CONFIRMED
    assert product.stock_quantity == 4


def test_cancel_and_webhook_lock_the_order_row(biz):
    """И отмена, и вебхук оплаты берут строку заказа под FOR UPDATE — иначе оплата
    «в последнюю минуту» затиралась бы отменой по устаревшему снимку."""
    order = _order()
    with CaptureQueriesContext(connection) as ctx:
        _hook(order)
    assert any("FOR UPDATE" in q["sql"] and "orders_order" in q["sql"] for q in ctx)
    other = _order()
    with CaptureQueriesContext(connection) as ctx:
        tasks.expire_abandoned_online()
    assert any("FOR UPDATE" in q["sql"] and "orders_order" in q["sql"] for q in ctx)
    other.refresh_from_db()
    assert other.status == Order.STATUS_CANCELLED


# --- 5. повтор ----------------------------------------------------------------------


def test_second_pass_does_nothing():
    product = _product(stock=5)
    _order(product=product)
    assert tasks.expire_abandoned_online() == 1
    assert tasks.expire_abandoned_online() == 0
    product.refresh_from_db()
    assert product.stock_quantity == 5  # склад вернулся ровно один раз


# --- 6–7. оплата к уже отменённому заказу -------------------------------------------


def test_payment_for_cancelled_order_is_refunded(biz, refunds, caplog):
    order = _order(phone=PHONE)
    assert tasks.expire_abandoned_online() == 1
    with caplog.at_level(logging.INFO):
        _hook(order, intent="pi_late")

    assert order.status == Order.STATUS_CANCELLED  # не воскрешаем
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert len(refunds) == 1
    assert refunds[0]["connect_id"] == ACCOUNT and refunds[0]["payment_intent"] == "pi_late"
    assert refunds[0]["idempotency_key"].startswith("refund:")
    # владелец видит в карточке: платёж и его возврат стоят в книге сделки
    row = DealPayment.objects.get(
        deal_kind="order", deal_id=order.pk, stripe_payment_intent="pi_late"
    )
    assert row.refunded_cents == row.amount_cents > 0
    # и в логе — без имени и телефона
    assert any("late payment" in r.getMessage() for r in caplog.records)
    assert NAME not in caplog.text and PHONE not in caplog.text


def test_webhook_retry_does_not_refund_twice(biz, refunds):
    order = _order()
    tasks.expire_abandoned_online()
    _hook(order, intent="pi_late")
    _hook(order, intent="pi_late")
    _hook(order, intent="pi_late")
    assert len(refunds) == 1
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert DealPayment.objects.filter(deal_kind="order", deal_id=order.pk).count() == 1


def test_second_payment_for_cancelled_order_is_refunded_too(biz, refunds):
    """Две открытые сессии Stripe, оплачены обе: второй платёж (другой intent) к уже
    отменённому и возвращённому заказу тоже уходит назад — и тоже один раз."""
    order = _order()
    tasks.expire_abandoned_online()
    _hook(order, intent="pi_one")
    _hook(order, intent="pi_two")
    _hook(order, intent="pi_two")
    _hook(order, intent="pi_one")
    assert [r["payment_intent"] for r in refunds] == ["pi_one", "pi_two"]
    assert order.status == Order.STATUS_CANCELLED
    assert order.payment_state == Order.PAYMENT_REFUNDED
    rows = DealPayment.objects.filter(deal_kind="order", deal_id=order.pk)
    assert rows.count() == 2 and all(r.refunded_cents == r.amount_cents for r in rows)


def test_failed_refund_is_not_hidden(biz, monkeypatch, caplog):
    """Stripe отказал в возврате: заказ остаётся «оплачен» (не ложное «возвращено»),
    в логе — предупреждение; владельцу пишет `refunds._rollback`."""

    def boom(**kw):
        raise RuntimeError("stripe down")

    monkeypatch.setattr("apps.billing.connect.refund", boom)
    order = _order()
    tasks.expire_abandoned_online()
    with caplog.at_level(logging.WARNING):
        _hook(order, intent="pi_late")
    assert order.status == Order.STATUS_CANCELLED
    assert order.payment_state == Order.PAYMENT_PAID
    assert "refund failed" in caplog.text


def test_late_payment_for_live_order_is_kept(biz, refunds):
    """Обычная оплата (заказ не отменён) не возвращается."""
    order = _order(hours_ago=1)
    _hook(order)
    assert order.payment_state == Order.PAYMENT_PAID and order.status == Order.STATUS_CONFIRMED
    assert refunds == []


# --- 8. срок сессии Stripe ----------------------------------------------------------


def _checkout_kwargs(order, biz, monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return "https://stripe.test/pay"

    monkeypatch.setattr("apps.billing.connect.connected_checkout_session", fake)
    payments.order_checkout_url(order, biz, success_url="https://s/ok", cancel_url="https://s/no")
    return seen


def test_checkout_session_of_order_without_email_expires_before_the_cancel(biz, monkeypatch):
    order = _order(hours_ago=2)
    seen = _checkout_kwargs(order, biz, monkeypatch)
    deadline = order.created_at + timedelta(hours=24)
    assert seen["expires_at"] == int((deadline - payment_holds.SESSION_MARGIN).timestamp())


def test_checkout_session_never_outlives_stripe_maximum(biz, monkeypatch, settings):
    """Срок длиннее суток: Stripe держит сессию не дольше 24 ч."""
    settings.ORDERS_ABANDONED_HOURS = 72
    order = _order(hours_ago=0)
    seen = _checkout_kwargs(order, biz, monkeypatch)
    top = timezone.now() + payment_holds.ONLINE_HOLD - payment_holds.SESSION_MARGIN
    assert seen["expires_at"] <= int(top.timestamp()) + 1


def test_checkout_session_too_close_to_the_cancel_has_no_own_expiry(biz, monkeypatch):
    """Stripe не принимает срок ближе 30 минут — сессия без срока, поздняя оплата вернётся."""
    order = _order(hours_ago=23.5)
    assert _checkout_kwargs(order, biz, monkeypatch).get("expires_at") is None


def test_checkout_session_of_order_with_email_has_no_expiry(biz, monkeypatch):
    order = _order(hours_ago=2, email="kim@test.de")
    assert _checkout_kwargs(order, biz, monkeypatch).get("expires_at") is None


# --- 9. «Jetzt bezahlen» по отменённому ---------------------------------------------


def test_order_pay_for_cancelled_order_goes_back_to_confirmation(biz, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no Stripe session for a cancelled order")

    monkeypatch.setattr("apps.orders.payments.order_checkout_url", boom)
    order = _order()
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    request = RequestFactory().get(f"/bestellung/{order.reference_code}/bezahlen/")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    biz.orders_enabled = True
    request.tenant = biz
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)
    resp = public_views.order_pay(request, order.reference_code)
    assert resp.status_code == 302
    assert resp.url.endswith(f"/bestellung/{order.reference_code}/")


# --- 10. беда одного заказа / одной схемы -------------------------------------------


def test_one_failing_order_does_not_stop_the_pass(monkeypatch, caplog):
    bad = _order(phone=PHONE)
    good = _order()
    real = OrderSM.apply

    def apply(self, instance, *a, **kw):
        if instance.pk == bad.pk:
            raise RuntimeError("kaputt")
        return real(self, instance, *a, **kw)

    monkeypatch.setattr(OrderSM, "apply", apply)
    with caplog.at_level(logging.ERROR):
        assert tasks.expire_abandoned_online() == 1
    bad.refresh_from_db()
    good.refresh_from_db()
    assert (bad.status, good.status) == (Order.STATUS_NEW, Order.STATUS_CANCELLED)
    assert str(bad.pk) in caplog.text  # не молча
    assert NAME not in caplog.text and PHONE not in caplog.text  # и без PII


def test_one_failing_schema_does_not_stop_the_pass(monkeypatch, caplog):
    order = _order()
    schema = connection.schema_name
    monkeypatch.setattr(tasks, "_iter_tenant_schemas", lambda: [schema, schema])
    real = tasks.expire_abandoned_online
    calls = []

    def flaky(now=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("схема сломана")
        return real(now)

    monkeypatch.setattr(tasks, "expire_abandoned_online", flaky)
    with caplog.at_level(logging.ERROR):
        result = tasks.expire_abandoned_online_orders()
    assert result["expired"] == 1
    assert len(calls) == 2
    assert "expire_abandoned_online_orders" in caplog.text
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


# --- 11. beat ------------------------------------------------------------------------


def test_beat_runs_the_task_every_15_minutes():
    entries = [
        e
        for e in dj_settings.CELERY_BEAT_SCHEDULE.values()
        if e["task"] == "apps.orders.tasks.expire_abandoned_online_orders"
    ]
    assert len(entries) == 1
    assert entries[0]["schedule"] == 900.0
    assert tasks.expire_abandoned_online_orders.name == entries[0]["task"]
