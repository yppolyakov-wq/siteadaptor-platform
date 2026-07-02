"""E-7 (платёжный микс DACH), E7-1: `Order.payment_method` проставляется в обоих
checkout-флоу; настройки Vorkasse (тумблер + реквизиты) сохраняются и нормализуются.
План — docs/e7-payments-plan-2026-07-02.md."""

import uuid
from decimal import Decimal

import pytest
import stripe
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views, views
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pub_req(data=None, tenant=None, session=None):
    request = RequestFactory().post("/warenkorb/bestellen/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.8"
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


def _configure(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_x"


def _prepay_tenant():
    return TenantFactory.build(
        orders_prepay=True, payments_enabled=True, stripe_connect_id="acct_1"
    )


def test_checkout_default_sets_on_site():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req({"name": "Kunde"}, session={"cart": {str(product.pk): 1}})
    public_views.checkout(request)
    assert Order.objects.get().payment_method == Order.METHOD_ON_SITE


def test_checkout_prepay_sets_stripe(monkeypatch, settings):
    _configure(settings)
    product = ProductFactory(base_price=Decimal("10.00"))
    monkeypatch.setattr(
        public_views.order_payments, "order_checkout_url", lambda o, t, **kw: "https://stripe/x"
    )
    request = _pub_req(
        {"name": "Kunde"}, tenant=_prepay_tenant(), session={"cart": {str(product.pk): 1}}
    )
    resp = public_views.checkout(request)
    assert resp.url == "https://stripe/x"
    assert Order.objects.get().payment_method == Order.METHOD_STRIPE


def test_checkout_stripe_error_falls_back_to_on_site(monkeypatch, settings):
    """Stripe временно недоступен → заказ остаётся, способ — оплата при получении."""
    _configure(settings)
    product = ProductFactory(base_price=Decimal("10.00"))

    def _boom(*a, **kw):
        raise stripe.error.StripeError("down")

    monkeypatch.setattr(public_views.order_payments, "order_checkout_url", _boom)
    request = _pub_req(
        {"name": "Kunde"}, tenant=_prepay_tenant(), session={"cart": {str(product.pk): 1}}
    )
    resp = public_views.checkout(request)
    order = Order.objects.get()
    assert resp.url.endswith(f"/bestellung/{order.reference_code}/")
    assert order.payment_method == Order.METHOD_ON_SITE


def test_vorkasse_settings_save_and_normalize():
    tenant = TenantFactory()
    request = _cab_req(
        {
            "form": "vorkasse",
            "vorkasse_enabled": "on",
            "bank_holder": "  Bäckerei Sonne GmbH ",
            "bank_iban": "de89 3704 0044 0532 0130 00",
            "bank_bic": "cobadeffxxx",
        }
    )
    request.tenant = tenant
    views.order_settings(request)
    tenant.refresh_from_db()
    assert tenant.vorkasse_enabled is True
    assert tenant.bank_holder == "Bäckerei Sonne GmbH"
    assert tenant.bank_iban == "DE89370400440532013000"  # без пробелов, верхний регистр
    assert tenant.bank_bic == "COBADEFFXXX"


def test_vorkasse_settings_do_not_clobber_prepay():
    tenant = TenantFactory(orders_prepay=True)
    request = _cab_req({"form": "vorkasse", "vorkasse_enabled": "on", "bank_iban": "DE1"})
    request.tenant = tenant
    views.order_settings(request)
    tenant.refresh_from_db()
    assert tenant.orders_prepay is True  # соседняя форма не сброшена
    assert tenant.vorkasse_enabled is True
