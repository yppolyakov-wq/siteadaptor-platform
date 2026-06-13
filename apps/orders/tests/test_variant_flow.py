"""R1 Push 2: варианты на витрине/в корзине — create_order, cart, checkout."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views, services
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", path="/warenkorb/", data=None, session=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.8"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _variant(product, label, price=None):
    return ProductVariant.objects.create(product=product, label=label, price=price)


# --- create_order -----------------------------------------------------------------


def test_create_order_variant_snapshot():
    product = ProductFactory(base_price=Decimal("9.90"), name={"de": "Tee"})
    v = _variant(product, "250 g", Decimal("19.00"))
    order = services.create_order(items=[(product, v, 2)], name="K", email="k@test.de")
    item = order.items.get()
    assert item.variant_id == v.pk
    assert item.variant_label == "250 g"
    assert item.unit_price == Decimal("19.00")
    assert "250 g" in item.title_snapshot
    assert order.total == Decimal("38.00")


def test_create_order_backward_compatible_two_tuple():
    product = ProductFactory(base_price=Decimal("5.00"))
    order = services.create_order(items=[(product, 3)], name="K")
    item = order.items.get()
    assert item.variant_id is None
    assert item.variant_label == ""
    assert item.unit_price == Decimal("5.00")
    assert order.total == Decimal("15.00")


# --- корзина / оформление ---------------------------------------------------------


def test_cart_add_requires_variant_for_variant_product():
    product = ProductFactory()
    _variant(product, "M")
    req = _req(data={"product": str(product.pk)})  # без выбора варианта
    resp = public_views.cart_add(req)
    assert resp.status_code == 302
    assert req.session.get("cart", {}) == {}  # ничего не добавлено


def test_cart_add_with_variant_then_checkout():
    product = ProductFactory(base_price=Decimal("9.90"))
    v = _variant(product, "250 g", Decimal("19.00"))
    add = _req(data={"product": str(product.pk), "variant": str(v.pk), "qty": "2"})
    public_views.cart_add(add)
    cart = add.session["cart"]
    assert cart == {f"{product.pk}:{v.pk}": 2}

    body = public_views.cart_view(_req(method="get", session={"cart": cart})).content.decode()
    assert "250 g" in body  # вариант показан в корзине

    public_views.checkout(_req(data={"name": "Kunde"}, session={"cart": cart}))
    item = Order.objects.get().items.get()
    assert item.variant_id == v.pk
    assert item.unit_price == Decimal("19.00")


def test_cart_items_drops_inactive_variant():
    product = ProductFactory()
    v = _variant(product, "M", Decimal("5.00"))
    req = _req(method="get", session={"cart": {f"{product.pk}:{v.pk}": 1}})
    v.is_active = False
    v.save(update_fields=["is_active"])
    assert public_views._cart_items(req) == []
