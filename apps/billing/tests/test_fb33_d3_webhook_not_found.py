"""FB-33 D3 (стопка 13): вебхук «деньги пришли, а записать некуда» и повтор «same».

* Любая денежная ветка вебхука, не нашедшая сделку своего бизнеса, — ERROR (kind, схема, id,
  intent, event.id; без `meta` целиком: у `pass_purchase` там e-mail) и одно письмо владельцу
  «Zahlung nicht verbucht» (`balance_pay._notify_unbooked`, ключ `unbooked:{schema}:{ref}`).
  Ответ — 200: повтор Stripe того же события ничего не найдёт; 5xx — только исключение.
* Чужой аккаунт до хелпера не доходит (SEC-D1).
* Повтор `mark_order_paid` при адресе «same» догоняет только недостающие письма клиента —
  один запрос к `Notification`, без рендера, если всё уже ушло.
"""

import logging
import uuid
from decimal import Decimal

import pytest
import stripe
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.billing import webhooks
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_d3"
OWNER = "chef@example.com"

#: kind → ключ id в metadata (все денежные ветки вебхука на connected account).
KINDS = {
    "booking_deposit": "booking_id",
    "order_payment": "order_id",
    "stay_deposit": "booking_id",
    "deal_balance": "deal_id",
    "gift_voucher": "gift_id",
    "job_deposit": "job_id",
    "pass_purchase": "plan_id",
    "event_ticket": "ticket_id",
    "event_installment": "ticket_id",
}


@pytest.fixture
def biz(monkeypatch):
    # рассрочка спрашивает мандат у Stripe — без сети
    monkeypatch.setattr("apps.billing.connect.mandate_from_payment_intent", lambda **kw: ("", ""))
    return TenantFactory(
        schema_name=connection.schema_name, stripe_connect_id=ACCOUNT, owner_email=OWNER
    )


def _obj(kind, *, intent="pi_d3_missing"):
    meta = {"kind": kind, "tenant_schema": connection.schema_name, KINDS[kind]: str(uuid.uuid4())}
    if kind == "deal_balance":
        meta["deal_kind"] = "booking"
    if kind == "pass_purchase":
        meta.update(name="Erika Muster", email="erika@example.com")
    return {
        "id": "cs_d3",
        "payment_intent": intent,
        "payment_status": "paid",
        "amount_total": 4200,
        "metadata": meta,
    }


def _unbooked():
    return Notification.objects.filter(dedupe_key__startswith="unbooked:")


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_money_not_booked_logged_error(biz, caplog, kind):
    caplog.set_level(logging.INFO)
    webhooks.handle_event("checkout.session.completed", _obj(kind), account=ACCOUNT)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("NOT booked" in r.getMessage() for r in errors), [
        r.getMessage() for r in caplog.records
    ]
    assert not [
        r for r in caplog.records if r.levelno == logging.WARNING and "not found" in r.getMessage()
    ]


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_not_booked_log_has_no_pii(biz, caplog, kind):
    caplog.set_level(logging.DEBUG)
    webhooks.handle_event("checkout.session.completed", _obj(kind), account=ACCOUNT)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "@" not in text and "Erika" not in text
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_not_booked_log_has_no_email():
    """`pass_purchase` писал `meta` целиком — с `email` и `name` покупателя."""
    TenantFactory(schema_name=connection.schema_name, stripe_connect_id=ACCOUNT)
    import logging as _logging

    records = []

    class _H(_logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _H()
    _logging.getLogger("billing").addHandler(handler)
    try:
        webhooks.handle_event("checkout.session.completed", _obj("pass_purchase"), account=ACCOUNT)
    finally:
        _logging.getLogger("billing").removeHandler(handler)
    assert records and all("erika@example.com" not in r.getMessage() for r in records)
    assert any(r.levelno == _logging.ERROR for r in records)


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_not_booked_notifies_owner_once(biz, kind):
    webhooks.handle_event("checkout.session.completed", _obj(kind), account=ACCOUNT)
    webhooks.handle_event("checkout.session.completed", _obj(kind), account=ACCOUNT)
    mails = list(_unbooked())
    assert len(mails) == 1
    assert mails[0].recipient == OWNER and "pi_d3_missing" in mails[0].dedupe_key


def test_not_booked_without_intent_uses_session_id(biz):
    """Ветка без `payment_intent` — ключ по id сессии, а не общий `unbooked:{schema}:`."""
    webhooks.handle_event(
        "checkout.session.completed", _obj("order_payment", intent=""), account=ACCOUNT
    )
    keys = list(_unbooked().values_list("dedupe_key", flat=True))
    assert keys == [f"unbooked:{connection.schema_name}:cs_d3"]


def test_foreign_account_does_not_notify(biz, caplog):
    caplog.set_level(logging.INFO)
    webhooks.handle_event("checkout.session.completed", _obj("order_payment"), account="acct_x")
    assert not _unbooked().exists()
    assert not any("NOT booked" in r.getMessage() for r in caplog.records)


def test_not_booked_log_carries_event_id(biz, caplog):
    caplog.set_level(logging.INFO)
    webhooks.handle_event(
        "checkout.session.completed", _obj("event_ticket"), account=ACCOUNT, event_id="evt_d3"
    )
    assert any("evt_d3" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)


def test_not_found_still_200_and_dedupe_kept(biz, monkeypatch, settings):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    event = {
        "id": "evt_d3_200",
        "type": "checkout.session.completed",
        "account": ACCOUNT,
        "data": {"object": _obj("order_payment")},
    }
    cache.delete("stripe_evt:evt_d3_200")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda payload, sig, secret: event)
    rf = RequestFactory()
    resp = webhooks.stripe_webhook(
        rf.post(
            "/stripe/webhook/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="x",
        )
    )
    assert resp.status_code == 200
    assert cache.get("stripe_evt:evt_d3_200") == "1"


# ───────────── повтор «same» ─────────────


@pytest.fixture
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _order(email, **kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services
    from apps.orders.models import Order

    return services.create_order(
        items=[(ProductFactory(base_price=Decimal("10.00")), 1)],
        name="Kunde",
        email=email,
        payment_method=Order.METHOD_STRIPE,
        **kw,
    )


def _paid(order, email, intent="pi_same"):
    from apps.orders.payments import mark_order_paid

    mark_order_paid(
        tenant_schema=connection.schema_name,
        order_id=str(order.id),
        payment_intent=intent,
        payer_email=email,
    )
    order.refresh_from_db()


def test_repeat_same_email_no_render(biz, _tenant_urlconf, monkeypatch):
    from apps.orders import notifications

    order = _order("gast@example.com")
    _paid(order, "gast@example.com")
    renders = []
    real = notifications._render
    monkeypatch.setattr(
        notifications, "_render", lambda *a, **kw: renders.append(a[0]) or real(*a, **kw)
    )
    with CaptureQueriesContext(connection) as ctx:
        _paid(order, "gast@example.com")
    assert renders == []
    note_q = [q for q in ctx.captured_queries if "notifications_notification" in q["sql"]]
    assert len(note_q) <= 1


def test_same_retry_sends_only_missing(biz, _tenant_urlconf, monkeypatch):
    from apps.orders import notifications
    from apps.orders.models import Order
    from apps.orders.state_machine import OrderSM

    order = _order("gast@example.com")
    _paid(order, "gast@example.com")
    assert order.status == Order.STATUS_CONFIRMED
    OrderSM().apply(order, Order.STATUS_READY)
    Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").delete()
    events = []
    real = notifications.enqueue_order_email
    monkeypatch.setattr(
        notifications,
        "enqueue_order_email",
        lambda o, e, *a, **kw: events.append(e) or real(o, e, *a, **kw),
    )
    _paid(order, "gast@example.com")
    assert events == ["ready"]
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").count() == 1


@pytest.mark.parametrize("flag", ["anprobe", "quote"])
def test_dedupe_key_one_builder(biz, _tenant_urlconf, flag):
    """Ключ проверки «уже ушло» = ключ `enqueue_order_email` (с подменой события)."""
    from django.utils import timezone

    from apps.orders import notifications

    order = _order("gast@example.com")
    if flag == "anprobe":
        order.reserve_expires_at = timezone.now()
    else:
        order.source_channel = "quote"
    notifications.enqueue_order_email(order, "created")
    key = notifications.customer_dedupe_key(order, "created")
    assert Notification.objects.filter(dedupe_key=key).exists()
    assert notifications.missing_customer_mails(order, ["created"]) == []
    assert key == f"order:{order.id}:{flag}_created:customer"
