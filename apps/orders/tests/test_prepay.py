"""P2.5c: онлайн-предоплата Click&Collect — Stripe-редирект, оплата (вебхук), refund."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory

from apps.billing import webhooks
from apps.catalog.tests.factories import ProductFactory
from apps.orders import payments as orders_payments
from apps.orders import public_views, services, views
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pub_req(data=None, tenant=None, session=None):
    request = RequestFactory().post("/warenkorb/bestellen/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _cab_req(data=None):
    request = RequestFactory().post("/dashboard/orders/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _order():
    return services.create_order(
        items=[(ProductFactory(base_price=Decimal("10.00")), 1)],
        name="Kunde",
        email=f"k-{uuid.uuid4().hex[:8]}@test.de",
    )


def _configure(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_x"


# --- витрина -----------------------------------------------------------------------


def test_checkout_prepay_redirects_to_stripe(monkeypatch, settings):
    _configure(settings)
    product = ProductFactory(base_price=Decimal("10.00"))
    tenant = TenantFactory.build(
        orders_prepay=True, payments_enabled=True, stripe_connect_id="acct_1"
    )
    monkeypatch.setattr(
        public_views.order_payments, "order_checkout_url", lambda o, t, **kw: "https://stripe/order"
    )
    request = _pub_req({"name": "Kunde"}, tenant=tenant, session={"cart": {str(product.pk): 2}})
    resp = public_views.checkout(request)
    assert resp.status_code == 302
    assert resp.url == "https://stripe/order"
    order = Order.objects.get()
    assert order.total == Decimal("20.00")
    assert order.payment_state == "unpaid"  # оплата подтвердится вебхуком


def test_checkout_without_prepay_is_normal(monkeypatch):
    product = ProductFactory(base_price=Decimal("10.00"))
    tenant = TenantFactory.build(orders_prepay=False)
    called = {"stripe": False}
    monkeypatch.setattr(
        public_views.order_payments,
        "order_checkout_url",
        lambda o, t, **kw: called.__setitem__("stripe", True) or "x",
    )
    request = _pub_req({"name": "Kunde"}, tenant=tenant, session={"cart": {str(product.pk): 1}})
    resp = public_views.checkout(request)
    order = Order.objects.get()
    assert resp.url.endswith(f"/bestellung/{order.reference_code}/")  # обычная бронь
    assert called["stripe"] is False


# --- оплата (вебхук) ---------------------------------------------------------------


def test_mark_order_paid_auto_confirms():
    order = _order()
    result = orders_payments.mark_order_paid(
        tenant_schema=connection.schema_name, order_id=str(order.id), payment_intent="pi_1"
    )
    assert result is True
    order.refresh_from_db()
    assert order.payment_state == "paid"
    assert order.stripe_payment_intent == "pi_1"
    assert order.status == "confirmed"  # авто-подтверждение по оплате


def test_webhook_order_payment_marks_paid():
    order = _order()
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "payment_intent": "pi_2",
            "metadata": {
                "kind": "order_payment",
                "tenant_schema": connection.schema_name,
                "order_id": str(order.id),
            },
        },
    )
    order.refresh_from_db()
    assert order.payment_state == "paid"
    assert order.status == "confirmed"


# --- кабинет -----------------------------------------------------------------------


def test_cancel_paid_order_refunds(monkeypatch):
    order = _order()
    OrderSM().apply(order, "confirmed")
    order.payment_state = "paid"
    order.stripe_payment_intent = "pi_x"
    order.save(update_fields=["payment_state", "stripe_payment_intent"])
    captured = {}
    monkeypatch.setattr(views.connect, "refund", lambda **kw: captured.update(kw))
    request = _cab_req({"action": "cancelled"})
    request.tenant = TenantFactory.build(stripe_connect_id="acct_1")
    views.order_action(request, pk=order.pk)
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert order.payment_state == "refunded"
    assert captured == {"connect_id": "acct_1", "payment_intent": "pi_x"}


def test_order_settings_toggle():
    tenant = TenantFactory()
    request = _cab_req({"orders_prepay": "on"})
    request.tenant = tenant
    views.order_settings(request)
    tenant.refresh_from_db()
    assert tenant.orders_prepay is True
