"""G4 / G4a: доставка/Versand — расчёт стоимости, создание заказа с доставкой,
переход shipped (выручка + письмо), кабинет (трек-номер, настройки доставки)."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.finance.models import RevenueEntry
from apps.notifications.models import Notification
from apps.orders import public_views, services, views
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cab_req(data=None):
    request = RequestFactory().post("/dashboard/orders/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _delivery_order(email=None, shipping_cents=390):
    return services.create_order(
        items=[(ProductFactory(base_price=Decimal("10.00")), 2)],
        name="Kunde",
        email=email or f"d-{uuid.uuid4().hex[:8]}@t.de",
        fulfillment="delivery",
        shipping_address="Hauptstr. 1\n40721 Hilden",
        shipping_cents=shipping_cents,
    )


# --- расчёт стоимости -------------------------------------------------------------


def test_shipping_cost_flat_and_free_threshold():
    tenant = TenantFactory.build(
        delivery_enabled=True, delivery_fee_cents=390, delivery_free_cents=3000
    )
    assert services.shipping_cost(tenant, 2000) == 390  # под порогом
    assert services.shipping_cost(tenant, 3000) == 0  # бесплатно от 30 €
    off = TenantFactory.build(delivery_enabled=False, delivery_fee_cents=390)
    assert services.shipping_cost(off, 2000) == 0  # доставка выключена


# --- создание заказа --------------------------------------------------------------


def test_create_delivery_order_includes_shipping():
    order = _delivery_order()
    assert order.is_delivery
    assert order.shipping_cents == 390
    assert order.total == Decimal("23.90")  # 2×10 + 3.90
    assert "Hilden" in order.shipping_address


def test_pickup_order_ignores_shipping():
    order = services.create_order(
        items=[(ProductFactory(base_price=Decimal("10.00")), 1)],
        name="K",
        shipping_cents=390,  # самовывоз по умолчанию → доставка не учитывается
    )
    assert not order.is_delivery
    assert order.shipping_cents == 0
    assert order.total == Decimal("10.00")


# --- переход shipped --------------------------------------------------------------


def test_shipped_records_revenue_and_email():
    order = _delivery_order()
    sm = OrderSM()
    for dst in ("confirmed", "ready", "shipped"):
        order = sm.apply(order, dst)
    assert order.status == "shipped"
    entry = RevenueEntry.objects.get(source="order", source_ref=str(order.id))
    assert entry.amount == Decimal("23.90")  # доставка в выручке
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:shipped:customer").exists()


# --- кабинет ----------------------------------------------------------------------


def test_cabinet_shipped_action_sets_tracking():
    order = _delivery_order()
    OrderSM().apply(order, "confirmed")
    OrderSM().apply(order, "ready")
    views.order_action(_cab_req({"action": "shipped", "tracking_code": "DHL123"}), pk=order.pk)
    order.refresh_from_db()
    assert order.status == "shipped"
    assert order.tracking_code == "DHL123"
    assert order.shipped_at is not None


def test_delivery_settings_save_without_clobbering_prepay():
    tenant = TenantFactory(orders_prepay=True)
    request = _cab_req(
        {
            "form": "delivery",
            "delivery_enabled": "on",
            "delivery_fee_eur": "3,90",
            "delivery_free_eur": "30",
            "delivery_min_eur": "15",
            "delivery_area": "40721, 40724",
        }
    )
    request.tenant = tenant
    views.order_settings(request)
    tenant.refresh_from_db()
    assert tenant.delivery_enabled is True
    assert tenant.delivery_fee_cents == 390
    assert tenant.delivery_free_cents == 3000
    assert tenant.delivery_min_cents == 1500
    assert tenant.delivery_area == "40721, 40724"
    assert tenant.orders_prepay is True  # вторая форма не сбросила предоплату


# --- витрина: выбор доставки (G4b) ------------------------------------------------


def _pub_req(data=None, tenant=None, session=None):
    request = RequestFactory().post("/warenkorb/bestellen/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _delivery_tenant(**kwargs):
    kwargs.setdefault("delivery_enabled", True)
    kwargs.setdefault("delivery_fee_cents", 390)
    return TenantFactory.build(**kwargs)


_ADDR = {"street": "Hauptstr. 1", "plz": "40721", "city": "Hilden"}


def test_checkout_delivery_creates_order_with_shipping():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "K", "fulfillment": "delivery", **_ADDR},
        tenant=_delivery_tenant(),
        session={"cart": {str(product.pk): 2}},
    )
    resp = public_views.checkout(request)
    order = Order.objects.get()
    assert order.is_delivery and order.shipping_cents == 390
    assert order.total == Decimal("23.90")
    assert "Hilden" in order.shipping_address
    assert resp.url.endswith(f"/bestellung/{order.reference_code}/")


def test_checkout_delivery_requires_address():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "K", "fulfillment": "delivery"},  # без адреса
        tenant=_delivery_tenant(),
        session={"cart": {str(product.pk): 1}},
    )
    public_views.checkout(request)
    assert not Order.objects.exists()


def test_checkout_delivery_below_min_rejected():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "K", "fulfillment": "delivery", **_ADDR},
        tenant=_delivery_tenant(delivery_min_cents=5000),  # мин. 50 €
        session={"cart": {str(product.pk): 2}},  # 20 € < 50
    )
    public_views.checkout(request)
    assert not Order.objects.exists()


def test_checkout_delivery_free_over_threshold():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "K", "fulfillment": "delivery", **_ADDR},
        tenant=_delivery_tenant(delivery_free_cents=1500),  # бесплатно от 15 €
        session={"cart": {str(product.pk): 2}},  # 20 € ≥ 15
    )
    public_views.checkout(request)
    order = Order.objects.get()
    assert order.shipping_cents == 0 and order.total == Decimal("20.00")


def test_checkout_pickup_when_delivery_enabled():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "K", "fulfillment": "pickup"},
        tenant=_delivery_tenant(),
        session={"cart": {str(product.pk): 1}},
    )
    public_views.checkout(request)
    order = Order.objects.get()
    assert not order.is_delivery and order.shipping_cents == 0
    assert order.total == Decimal("10.00")


# --- рендер шаблонов (ловим ошибки разметки) --------------------------------------


def test_cart_renders_delivery_options():
    product = ProductFactory(base_price=Decimal("10.00"))
    request = RequestFactory().get("/warenkorb/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.update({"cart": {str(product.pk): 1}})
    request.tenant = _delivery_tenant(delivery_free_cents=3000, delivery_min_cents=1500)
    body = public_views.cart_view(request).content.decode()
    assert "Delivery" in body  # опция доставки отрисована


def test_order_confirmation_renders_delivery():
    order = _delivery_order()
    request = RequestFactory().get(f"/bestellung/{order.reference_code}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _delivery_tenant()
    body = public_views.order_confirmation(request, code=order.reference_code).content.decode()
    assert order.reference_code in body and "Hilden" in body
