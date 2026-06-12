"""Track D / D2a: Click & Collect — сервис заказа, OrderSM, корзина-сессия,
оформление с витрины, гейтинг модуля orders."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.core.fsm import IllegalTransition
from apps.orders import public_views, services
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/warenkorb/", data=None, tenant=None, session=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    # уникальный IP — изоляция rate-limit от общего Redis
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


# --- сервис ---------------------------------------------------------------------


def test_create_order_snapshots_and_total():
    p1 = ProductFactory(base_price=Decimal("4.50"), name={"de": "Brötchen"})
    p2 = ProductFactory(base_price=Decimal("12.00"), name={"de": "Brot"})
    order = services.create_order(
        items=[(p1, 4), (p2, 1)], name="Kunde K", email="k@test.de", phone="+49 1"
    )
    assert order.reference_code.startswith("O-")
    assert order.total == Decimal("30.00")
    assert order.status == "new" and order.payment_state == "unpaid"
    items = list(order.items.all())
    assert [(i.title_snapshot, i.qty, i.unit_price) for i in items] == [
        ("Brötchen", 4, Decimal("4.50")),
        ("Brot", 1, Decimal("12.00")),
    ]
    customer = Customer.objects.get(email="k@test.de")
    assert customer.created_source == Customer.SOURCE_ORDER


def test_create_order_reuses_customer_by_email():
    existing = Customer.objects.create(name="Alt", email="k2@test.de")
    order = services.create_order(items=[(ProductFactory(), 1)], name="Neu", email="K2@test.de")
    assert order.customer == existing
    assert Customer.objects.filter(email__iexact="k2@test.de").count() == 1


def test_create_order_rejects_empty_and_bad_qty():
    with pytest.raises(services.EmptyOrder):
        services.create_order(items=[], name="X")
    with pytest.raises(ValueError):
        services.create_order(items=[(ProductFactory(), 0)], name="X")


# --- FSM -------------------------------------------------------------------------


def test_order_sm_happy_path_and_illegal():
    order = services.create_order(items=[(ProductFactory(), 1)], name="K")
    sm = OrderSM()
    for dst in ("confirmed", "ready", "picked_up"):
        order = sm.apply(order, dst)
    assert order.status == "picked_up"

    other = services.create_order(items=[(ProductFactory(), 1)], name="K2")
    with pytest.raises(IllegalTransition):
        sm.apply(other, "picked_up")  # new → picked_up запрещён
    assert sm.apply(other, "cancelled").status == "cancelled"


# --- корзина и оформление ---------------------------------------------------------


def test_cart_add_view_and_checkout_flow():
    tenant = TenantFactory.build()
    product = ProductFactory(base_price=Decimal("3.00"))

    response = public_views.cart_add(
        _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "2"}, tenant)
    )
    assert response.status_code == 302

    # корзина в сессии — переносим её в следующий запрос вручную (RequestFactory)
    cart = {str(product.pk): 2}
    body = public_views.cart_view(_req(tenant=tenant, session={"cart": cart})).content.decode()
    assert "6,00" in body or "6.00" in body  # total в DE-локали

    request = _req(
        "post",
        "/warenkorb/bestellen/",
        {"name": "Karla", "email": "karla@test.de"},
        tenant,
        session={"cart": cart},
    )
    response = public_views.checkout(request)
    assert response.status_code == 302
    order = Order.objects.get(customer__email="karla@test.de")
    assert response.url.endswith(f"/bestellung/{order.reference_code}/")
    assert request.session["cart"] == {}  # корзина очищена

    body = public_views.order_confirmation(
        _req(tenant=tenant), code=order.reference_code
    ).content.decode()
    assert order.reference_code in body


def test_checkout_honeypot_and_empty_cart():
    tenant = TenantFactory.build()
    request = _req("post", "/warenkorb/bestellen/", {"name": "Bot", "website": "spam"}, tenant)
    assert public_views.checkout(request).status_code == 302
    assert Order.objects.count() == 0

    request = _req("post", "/warenkorb/bestellen/", {"name": "Echt"}, tenant)
    assert public_views.checkout(request).status_code == 302  # назад в корзину с ошибкой
    assert Order.objects.count() == 0


def test_orders_module_gated_on_storefront():
    tenant = TenantFactory.build(disabled_modules=["orders"])
    with pytest.raises(Http404):
        public_views.cart_view(_req(tenant=tenant))
    with pytest.raises(Http404):
        public_views.checkout(_req("post", "/warenkorb/bestellen/", {"name": "X"}, tenant))


def test_product_page_hides_order_button_when_disabled():
    from apps.promotions.public_views import product_detail

    product = ProductFactory()
    on = product_detail(_req(path=f"/sortiment/{product.pk}/"), pk=product.pk).content.decode()
    assert "Order for pickup" in on or "warenkorb/add" in on

    tenant_off = TenantFactory.build(disabled_modules=["orders"])
    off = product_detail(
        _req(path=f"/sortiment/{product.pk}/", tenant=tenant_off), pk=product.pk
    ).content.decode()
    assert "warenkorb/add" not in off
