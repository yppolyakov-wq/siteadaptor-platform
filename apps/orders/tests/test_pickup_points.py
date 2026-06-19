"""Точки самовывоза: нормализация, выбор в корзине → снимок в заказе."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data=None, session=None, pickup_locations=None):
    request = RequestFactory().post("/warenkorb/bestellen/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.6"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = TenantFactory.build(
        business_type="restaurant", pickup_locations=pickup_locations or []
    )
    return request


def test_pickup_points_normalizes_and_skips_blank():
    t = TenantFactory.build(
        pickup_locations=[{"name": "Mitte", "address": "Hauptstr. 1"}, {"name": ""}, "junk"]
    )
    pts = t.pickup_points
    assert [p["name"] for p in pts] == ["Mitte"]


def _add_to_cart(product):
    add = _req(data={"product": str(product.pk), "qty": "1"}, session=None)
    public_views.cart_add(add)
    return add.session[public_views.CART_SESSION_KEY]


def test_checkout_requires_valid_pickup_when_multiple():
    product = ProductFactory(base_price=Decimal("8.00"))
    cart = _add_to_cart(product)
    locs = [{"name": "Mitte", "address": "A"}, {"name": "Süd", "address": "B"}]
    # без выбора → ошибка, заказа нет
    public_views.checkout(_req(data={"name": "K"}, session={"cart": cart}, pickup_locations=locs))
    assert Order.objects.count() == 0
    # с выбором → заказ со снимком точки
    public_views.checkout(
        _req(
            data={"name": "K", "pickup_location": "Süd"},
            session={"cart": cart},
            pickup_locations=locs,
        )
    )
    assert Order.objects.get().pickup_location == "Süd"


def test_single_point_auto_applied():
    product = ProductFactory(base_price=Decimal("8.00"))
    cart = _add_to_cart(product)
    public_views.checkout(
        _req(data={"name": "K"}, session={"cart": cart}, pickup_locations=[{"name": "Mitte"}])
    )
    assert Order.objects.get().pickup_location == "Mitte"
