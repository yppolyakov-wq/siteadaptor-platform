"""A4b: модификаторы на витрине/в корзине/заказе — валидация, цена, снимок."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ModifierGroup, ModifierOption
from apps.catalog.modifiers import options_delta, validate_selection
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views, services
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", path="/warenkorb/", data=None, session=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = TenantFactory.build()
    return request


def _group(product, name, **kw):
    return ModifierGroup.objects.create(product=product, name=name, **kw)


def _opt(group, label, delta="0"):
    return ModifierOption.objects.create(group=group, label=label, price_delta=Decimal(delta))


# --- валидация выбора --------------------------------------------------------------


def test_validate_required_group_missing():
    product = ProductFactory()
    g = _group(product, "Größe", min_select=1, max_select=1)
    _opt(g, "Klein")
    options, error = validate_selection(product, [])
    assert options == [] and error  # обязательная группа без выбора → ошибка


def test_validate_max_exceeded():
    product = ProductFactory()
    g = _group(product, "Extras", min_select=0, max_select=1)
    a, b = _opt(g, "A"), _opt(g, "B")
    options, error = validate_selection(product, [str(a.pk), str(b.pk)])
    assert error  # больше max


def test_validate_ok_collects_options_and_delta():
    product = ProductFactory()
    g = _group(product, "Extras", min_select=0, max_select=0)
    a = _opt(g, "Pommes", "2.50")
    b = _opt(g, "Käse", "1.00")
    options, error = validate_selection(product, [str(a.pk), str(b.pk)])
    assert error == ""
    assert {o.pk for o in options} == {a.pk, b.pk}
    assert options_delta(options) == Decimal("3.50")


# --- create_order: надбавка в цене + снимок ----------------------------------------


def test_create_order_with_modifier_surcharge_and_snapshot():
    product = ProductFactory(base_price=Decimal("8.00"), name={"de": "Burger"})
    g = _group(product, "Extras", min_select=0, max_select=0)
    cheese = _opt(g, "Käse", "1.50")
    order = services.create_order(items=[(product, None, 2, [cheese])], name="K", email="k@test.de")
    item = order.items.get()
    assert item.unit_price == Decimal("9.50")  # 8.00 + 1.50
    assert item.modifiers == [{"label": "Käse", "delta": "1.50"}]
    assert item.modifiers_label == "Käse"
    assert order.total == Decimal("19.00")  # 9.50 × 2


# --- корзина / оформление ----------------------------------------------------------


def test_cart_shows_upsell_suggestions():
    """T1: корзина показывает «Passt dazu» — товары не из корзины."""
    in_cart = ProductFactory(base_price=Decimal("9.00"), name={"de": "Pizza"})
    ProductFactory(base_price=Decimal("2.50"), name={"de": "Cola"}, is_featured=True)
    add = _req(data={"product": str(in_cart.pk), "qty": "1"})
    public_views.cart_add(add)
    body = public_views.cart_view(
        _req(method="get", session={"cart": add.session["cart"]})
    ).content.decode()
    assert "Cola" in body  # upsell-предложение присутствует


def test_cart_add_with_modifiers_keys_by_selection():
    product = ProductFactory(base_price=Decimal("8.00"))
    g = _group(product, "Extras", min_select=0, max_select=0)
    cheese = _opt(g, "Käse", "1.50")
    add = _req(data={"product": str(product.pk), "mod": [str(cheese.pk)], "qty": "1"})
    public_views.cart_add(add)
    cart = add.session["cart"]
    assert list(cart.keys()) == [f"{product.pk}::{cheese.pk}"]

    body = public_views.cart_view(_req(method="get", session={"cart": cart})).content.decode()
    assert "Käse" in body  # опция показана в корзине

    public_views.checkout(_req(data={"name": "Kunde"}, session={"cart": cart}))
    item = Order.objects.get().items.get()
    assert item.unit_price == Decimal("9.50")
    assert item.modifiers_label == "Käse"


def test_cart_add_required_modifier_missing_blocks():
    product = ProductFactory()
    g = _group(product, "Größe", min_select=1, max_select=1)
    _opt(g, "Klein")
    add = _req(data={"product": str(product.pk)})  # обязательная группа без выбора
    public_views.cart_add(add)
    assert add.session.get("cart", {}) == {}  # ничего не добавлено


def test_cart_distinguishes_selections():
    """Разные наборы опций — разные позиции корзины."""
    product = ProductFactory(base_price=Decimal("8.00"))
    g = _group(product, "Extras", min_select=0, max_select=0)
    a = _opt(g, "Käse", "1.50")
    b = _opt(g, "Speck", "2.00")
    add1 = _req(data={"product": str(product.pk), "mod": [str(a.pk)]})
    public_views.cart_add(add1)
    add2 = _req(
        data={"product": str(product.pk), "mod": [str(b.pk)]},
        session={"cart": add1.session["cart"]},
    )
    public_views.cart_add(add2)
    assert len(add2.session["cart"]) == 2
