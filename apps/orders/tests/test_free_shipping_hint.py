"""M4-D (план m4-boutique-plan-2026-07-30): подсказка «ещё X € до бесплатной
доставки» в корзине — только при включённой доставке и недостигнутом пороге."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.orders.public_views import cart_view
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _cart_body(tenant, price="30.00", qty=1):
    p = Product.objects.create(name={"de": "Kleid"}, base_price=Decimal(price))
    request = RequestFactory().get("/warenkorb/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session["cart"] = {f"{p.pk}::": qty}
    request.tenant = tenant
    return cart_view(request).content.decode()


def _tenant(**kw):
    return TenantFactory.build(business_type="clothing", **kw)


def test_hint_shows_gap_when_below_threshold():
    t = _tenant(delivery_enabled=True, delivery_fee_cents=490, delivery_free_cents=8000)
    body = _cart_body(t, price="30.00")
    assert 'id="free-shipping-hint"' in body
    assert "50.00" in body  # 80 − 30 = 50 € до бесплатной доставки


def test_hint_hidden_when_threshold_reached():
    t = _tenant(delivery_enabled=True, delivery_fee_cents=490, delivery_free_cents=8000)
    body = _cart_body(t, price="90.00")
    assert 'id="free-shipping-hint"' not in body


def test_hint_absent_without_delivery():
    t = _tenant(delivery_enabled=False)
    body = _cart_body(t, price="30.00")
    assert 'id="free-shipping-hint"' not in body
