"""FB-33 D4a (стопка 13): второй платёж Stripe к неотменённому заказу.

Решение владельца 2026-11-24: второй платёж Stripe к оплаченному (или возвращённому)
неотменённому заказу записывается в книгу и СРАЗУ возвращается своей строкой
(`refunds.refund_intent`), главный платёж не перезаписывается. «Касса, потом онлайн»
(главного intent нет) — не возвращаем: строка пишется, переплата видна в карточке, WARNING.
Сбой возврата — пометка «Rückerstattung offen», письмо `duplicate`; таймаут — UNCERTAIN без
письма, повтор `retry_late_refunds` (счётчик на платёж), письмо — после исчерпания повторов.
"""

import logging
from datetime import timedelta

import polib
import pytest
import stripe
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.billing import webhooks
from apps.core import folio, payment_holds, refunds
from apps.core.models import DealPayment
from apps.notifications.models import Notification
from apps.orders import payments, tasks
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.orders.tests.test_fb33_m2i71_abandoned import _order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_d4a"
OWNER = "chef@example.com"


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
        owner_email=OWNER,
    )


@pytest.fixture
def stripe_refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _pay(order, intent, *, amount=None, status="paid"):
    obj = {
        "payment_intent": intent,
        "payment_status": status,
        "metadata": {
            "kind": "order_payment",
            "tenant_schema": connection.schema_name,
            "order_id": str(order.id),
        },
    }
    if amount is not None:
        obj["amount_total"] = amount
    webhooks.handle_event("checkout.session.completed", obj, account=ACCOUNT)
    order.refresh_from_db()
    return order


def _live_paid(intent="pi_main"):
    order = _order(hours_ago=1, email="gast@example.com")
    _pay(order, intent)
    assert order.payment_state == Order.PAYMENT_PAID and order.status == Order.STATUS_CONFIRMED
    return order


def _rows(order):
    return {
        r.stripe_payment_intent: r
        for r in DealPayment.objects.filter(deal_kind="order", deal_id=order.pk)
    }


def _dup_mails(order):
    return Notification.objects.filter(
        dedupe_key__contains=f":order:{order.pk}:duplicate", type="refund_failed_owner"
    )


# ───────────── матрица второго платежа ─────────────


def test_second_payment_on_paid_order_is_booked_and_refunded(biz, stripe_refunds):
    """Оплачен картой, затем вторая сессия (SEPA) — строка в книге, возврат один раз."""
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    rows = _rows(order)
    assert set(rows) == {"pi_main", "pi_second"}
    assert rows["pi_second"].refunded_cents == rows["pi_second"].amount_cents
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_second"]
    assert order.stripe_payment_intent == "pi_main"
    assert order.payment_state == Order.PAYMENT_PAID


def test_second_payment_on_refunded_live_order_is_booked_and_refunded(biz, stripe_refunds):
    order = _live_paid()
    Order.objects.filter(pk=order.pk).update(payment_state=Order.PAYMENT_REFUNDED)
    folio.mark_refunded("order", order, intent="pi_main")
    order.refresh_from_db()
    _pay(order, "pi_second", amount=1000)
    rows = _rows(order)
    assert "pi_second" in rows and rows["pi_second"].refunded_cents == 1000
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_second"]
    assert order.stripe_payment_intent == "pi_main"


def test_processing_sepa_then_card_is_not_a_duplicate(biz, stripe_refunds):
    """SEPA «в пути», затем карта: главный — карта, это не дубль (возврата нет)."""
    order = _order(hours_ago=1, email="gast@example.com")
    payments.mark_order_processing(
        tenant_schema=connection.schema_name, order_id=str(order.id), payment_intent="pi_sepa"
    )
    _pay(order, "pi_card")
    assert order.stripe_payment_intent == "pi_card" and stripe_refunds == []


def test_processing_sepa_succeeds_after_card_is_refunded(biz, stripe_refunds):
    order = _order(hours_ago=1, email="gast@example.com")
    payments.mark_order_processing(
        tenant_schema=connection.schema_name, order_id=str(order.id), payment_intent="pi_sepa"
    )
    _pay(order, "pi_card")
    _pay(order, "pi_sepa", amount=1000)
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_sepa"]
    assert order.stripe_payment_intent == "pi_card"


def test_repeat_of_same_intent_does_nothing(biz, stripe_refunds):
    order = _live_paid()
    _pay(order, "pi_main")
    assert stripe_refunds == [] and len(_rows(order)) == 1


def test_second_payment_on_legacy_order_without_rows(biz, stripe_refunds):
    """Легаси без строк книги: второй платёж — строка opening с главным + своя строка."""
    order = _order(hours_ago=1, email="gast@example.com")
    Order.objects.filter(pk=order.pk).update(
        payment_state=Order.PAYMENT_PAID, stripe_payment_intent="pi_legacy", status="confirmed"
    )
    order.refresh_from_db()
    _pay(order, "pi_second", amount=1000)
    rows = _rows(order)
    assert rows["pi_legacy"].purpose == DealPayment.PURPOSE_OPENING
    assert rows["pi_legacy"].refunded_cents == 0
    assert rows["pi_second"].refunded_cents == 1000
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_second"]


def test_replay_of_main_intent_legacy_without_rows_not_refunded(biz, stripe_refunds):
    """10.1 H1: легаси с главным X без строк, повтор вебхука X — не дубль."""
    order = _order(hours_ago=1, email="gast@example.com")
    Order.objects.filter(pk=order.pk).update(
        payment_state=Order.PAYMENT_PAID, stripe_payment_intent="pi_legacy", status="confirmed"
    )
    order.refresh_from_db()
    _pay(order, "pi_legacy")
    assert stripe_refunds == []
    assert not DealPayment.objects.filter(deal_kind="order", deal_id=order.pk).exists()


def test_cash_then_online_is_kept_with_warning(biz, stripe_refunds, caplog):
    """§9 №4: «bezahlt» вручную (главного intent нет), затем онлайн — не возвращаем."""
    order = _order(hours_ago=1, email="gast@example.com")
    Order.objects.filter(pk=order.pk).update(payment_state=Order.PAYMENT_PAID)
    order.refresh_from_db()
    with caplog.at_level(logging.WARNING):
        _pay(order, "pi_online")
    assert stripe_refunds == []
    assert "pi_online" in _rows(order)


def test_cash_then_online_warns(biz, stripe_refunds, caplog):
    order = _order(hours_ago=1, email="gast@example.com")
    Order.objects.filter(pk=order.pk).update(payment_state=Order.PAYMENT_PAID)
    order.refresh_from_db()
    with caplog.at_level(logging.WARNING):
        _pay(order, "pi_online")
    assert any("manual" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_extra_row_amount_is_stripe_amount(biz, stripe_refunds):
    """10.1 M5: сумма строки — `amount_total` вебхука, а не расчёт сделки."""
    order = _live_paid()
    _pay(order, "pi_second", amount=777)
    assert _rows(order)["pi_second"].amount_cents == 777


def test_extra_decided_under_lock(biz, stripe_refunds):
    """№9: признак «второй платёж» — из строки под блокировкой (FOR UPDATE до книги)."""
    order = _live_paid()
    with CaptureQueriesContext(connection) as ctx:
        _pay(order, "pi_second", amount=1000)
    sqls = [q["sql"] for q in ctx.captured_queries]
    lock = next(i for i, s in enumerate(sqls) if "orders_order" in s and "FOR UPDATE" in s)
    book = next(i for i, s in enumerate(sqls) if "core_dealpayment" in s and "pi_second" in s)
    assert lock < book
    assert stripe_refunds


# ───────────── отмена после дубля, сбои ─────────────


def test_cancel_after_duplicate_no_double_refund(biz, stripe_refunds):
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    assert [c["payment_intent"] for c in stripe_refunds] == ["pi_second"]
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    refunds.refund_payment("order", order, biz)
    second = [c for c in stripe_refunds if c["payment_intent"] == "pi_second"]
    assert len(second) == 1
    assert stripe_refunds[0]["payment_intent"] == "pi_second"  # вернули сразу, до отмены


def test_other_rows_refund_shared(biz, stripe_refunds):
    """№1: `_refund_other_card_rows` и `refund_intent` — один ключ, одна запись."""
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    key_webhook = stripe_refunds[0]["idempotency_key"]
    DealPayment.objects.filter(stripe_payment_intent="pi_second").update(refunded_cents=0)
    order.refresh_from_db()
    refunds._refund_other_card_rows("order", order, ACCOUNT, "pi_main")
    assert stripe_refunds[1]["idempotency_key"] == key_webhook
    assert _rows(order)["pi_second"].refunded_cents == 1000


def test_duplicate_refund_failure_marks_and_mails(biz, monkeypatch):
    def card_error(**kw):
        raise stripe.error.CardError("declined", None, "card_declined")

    monkeypatch.setattr("apps.billing.connect.refund", card_error)
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    assert payments.refund_open(order) is True
    mails = list(_dup_mails(order))
    assert len(mails) == 1
    assert order.reference_code in mails[0].subject
    assert "html" not in (mails[0].payload or {})


def test_duplicate_refund_timeout_is_uncertain_without_mail_then_retried(biz, monkeypatch):
    calls = []
    state = {"down": True}

    def refund(**kw):
        calls.append(kw)
        if state["down"]:
            raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    assert payments.refund_open(order) is True and not _dup_mails(order).exists()
    state["down"] = False
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    assert len(calls) == 2 and calls[0]["idempotency_key"] == calls[1]["idempotency_key"]
    assert _rows(order)["pi_second"].refunded_cents == 1000
    order.refresh_from_db()
    assert payments.refund_open(order) is False


def test_retry_extra_exhausted_mails_owner(biz, monkeypatch):
    def refund(**kw):
        raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    now = timezone.now()
    for step in range(1, 40):
        tasks.retry_late_refunds(now + timedelta(minutes=15 * step))
    assert _dup_mails(order).count() == 1


def test_retry_counters_per_intent(biz, monkeypatch):
    """10.2 M4: счётчик повтора — на (сделка, платёж), не общий с главным возвратом."""
    from django.core.cache import cache

    monkeypatch.setattr(
        "apps.billing.connect.refund",
        lambda **kw: (_ for _ in ()).throw(stripe.error.APIConnectionError("x")),
    )
    order = _live_paid()
    _pay(order, "pi_second", amount=1000)
    _pay(order, "pi_third", amount=1000)
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    schema = connection.schema_name
    assert cache.get(f"extra-refund-retry:{schema}:order:{order.pk}:pi_second")
    assert cache.get(f"extra-refund-retry:{schema}:order:{order.pk}:pi_third")
    assert cache.get(f"order-refund-retry:{schema}:{order.pk}") is None


def test_retry_extra_bounded(biz, monkeypatch):
    monkeypatch.setattr(payment_holds, "EXTRA_RETRY_BATCH", 2)
    calls = []

    def refund(**kw):
        calls.append(kw["payment_intent"])
        raise stripe.error.APIConnectionError("x")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    orders = [_live_paid(f"pi_m{i}") for i in range(3)]
    for i, order in enumerate(orders):
        _pay(order, f"pi_x{i}", amount=1000)
    calls.clear()
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    assert len(calls) == 2


def test_retry_extra_ignores_partial_refund_rows_of_main(biz, stripe_refunds):
    """10.1 M4: главная строка, открытая после частичного возврата владельцем, — не повтор."""
    _live_paid()
    DealPayment.objects.filter(stripe_payment_intent="pi_main").update(refunded_cents=100)
    stripe_refunds.clear()
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    assert stripe_refunds == []


# ───────────── refund_intent ─────────────


def test_refund_intent_without_row_is_noop(biz, stripe_refunds, caplog):
    order = _live_paid()
    with caplog.at_level(logging.ERROR):
        result = refunds.refund_intent("order", order, "pi_ghost", biz)
    assert result == refunds.RefundResult.NONE and stripe_refunds == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_refund_intent_without_row_does_not_touch_main_row(biz, stripe_refunds):
    order = _live_paid()
    refunds.refund_intent("order", order, "pi_ghost", biz)
    assert _rows(order)["pi_main"].refunded_cents == 0


def test_refund_intent_refuses_main_intent(biz, stripe_refunds, caplog):
    order = _live_paid()
    with caplog.at_level(logging.ERROR):
        result = refunds.refund_intent("order", order, "pi_main", biz)
    assert result == refunds.RefundResult.NONE and stripe_refunds == []


def test_refund_intent_idempotency_in_progress_is_uncertain(biz, monkeypatch):
    order = _live_paid()
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)
    _pay(order, "pi_second", amount=1000)
    DealPayment.objects.filter(stripe_payment_intent="pi_second").update(refunded_cents=0)

    def busy(**kw):
        raise stripe.error.IdempotencyError("in progress")

    monkeypatch.setattr("apps.billing.connect.refund", busy)
    order.refresh_from_db()
    result = refunds.refund_intent("order", order, "pi_second", biz)
    assert result == refunds.RefundResult.UNCERTAIN
    assert not _dup_mails(order).exists()


def test_concurrent_cancel_and_duplicate_refund_main_state_kept(biz, monkeypatch):
    """10.1 H2: отмена возвращает главный, а возврат второго «в полёте» у вебхука —
    `IdempotencyError` не откатывает «возвращено» главного."""
    calls = []

    def refund(**kw):
        calls.append(kw["payment_intent"])
        if kw["payment_intent"] == "pi_second":
            raise stripe.error.IdempotencyError("in progress")

    order = _live_paid()
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_second",
        source="webhook",
    )
    monkeypatch.setattr("apps.billing.connect.refund", refund)
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    result = refunds.refund_payment("order", order, biz)
    order.refresh_from_db()
    assert order.payment_state == Order.PAYMENT_REFUNDED
    assert result == refunds.RefundResult.UNCERTAIN


def test_cancel_other_rows_timeout_is_uncertain(biz, monkeypatch):
    def refund(**kw):
        if kw["payment_intent"] == "pi_second":
            raise stripe.error.APIConnectionError("timeout")

    order = _live_paid()
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_second",
        source="webhook",
    )
    monkeypatch.setattr("apps.billing.connect.refund", refund)
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    assert refunds.refund_payment("order", order, biz) == refunds.RefundResult.UNCERTAIN
    order.refresh_from_db()
    assert order.payment_state == Order.PAYMENT_REFUNDED


def test_cancel_other_rows_refusal_still_rolls_back(biz, monkeypatch):
    """Явный отказ Stripe по второй строке — как раньше: откат и письмо."""

    def refund(**kw):
        if kw["payment_intent"] == "pi_second":
            raise stripe.error.CardError("declined", None, "card_declined")

    order = _live_paid()
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_second",
        source="webhook",
    )
    monkeypatch.setattr("apps.billing.connect.refund", refund)
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    assert refunds.refund_payment("order", order, biz) == refunds.RefundResult.FAILED


def test_extra_rows_one_source(biz, stripe_refunds, monkeypatch):
    """10.2 M3: «прочие stripe-строки с остатком» — один отбор в книге (`folio`)."""
    order = _live_paid()
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=1000,
        stripe_payment_intent="pi_second",
        source="webhook",
    )
    assert payments.refund_open(order) is True
    monkeypatch.setattr(folio, "open_card_rows", lambda *a, **kw: DealPayment.objects.none())
    assert payments.refund_open(order) is False
    assert refunds._refund_other_card_rows("order", order, ACCOUNT, "pi_main")[0] == 0
    assert payment_holds.is_new_payment("order", order, "pi_new") is True
    monkeypatch.setattr(folio, "has_payment", lambda *a, **kw: True)
    assert payment_holds.is_new_payment("order", order, "pi_new") is False


# ───────────── тексты ─────────────

_MSGIDS = (
    "Doppelte Zahlung nicht erstattet: %(code)s",
    "Zu %(code)s ist eine zweite Zahlung eingegangen. Die automatische Rückerstattung ist "
    "fehlgeschlagen — bitte in Stripe prüfen und erstatten.",
)


@pytest.mark.parametrize("lang", ["de", "en", "ru", "tr", "uk"])
def test_d4a_msgids_in_all_po(lang):
    po = polib.pofile(f"locale/{lang}/LC_MESSAGES/django.po")
    found = {(e.msgctxt, e.msgid): e for e in po}
    for msgid in _MSGIDS:
        entry = found.get((None, msgid))
        assert entry is not None and (entry.msgstr or lang == "de"), msgid
