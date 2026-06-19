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


# --- T2c быстрый заказ (модалка-конфигуратор) --------------------------------------


def test_quick_add_modal_renders_form_with_options():
    product = ProductFactory(base_price=Decimal("9.00"))
    g = _group(product, "Größe", min_select=1, max_select=1)
    _opt(g, "Klein", "0")
    body = public_views.quick_add_form(_req(method="get"), pk=product.pk).content.decode()
    assert "/warenkorb/add/" in body  # форма постит в cart_add
    assert "Größe" in body and 'name="mod"' in body


def test_quick_add_404_when_orders_inactive():
    from django.http import Http404

    product = ProductFactory()
    req = _req(method="get")
    req.tenant = TenantFactory.build(disabled_modules=["orders"])
    with pytest.raises(Http404):
        public_views.quick_add_form(req, pk=product.pk)


# --- A4 комбо-наборы (витрина/корзина/заказ) ---------------------------------------


def _combo_with_drink():
    from apps.catalog.models import Combo, ComboGroup, ComboOption

    combo = Combo.objects.create(name="Menü 1", price=Decimal("9.90"))
    g = ComboGroup.objects.create(combo=combo, label="Getränk", min_select=1, max_select=1)
    cola = ComboOption.objects.create(
        group=g, product=ProductFactory(), price_delta=Decimal("1.00")
    )
    return combo, cola


def test_combo_detail_renders_options():
    combo, _ = _combo_with_drink()
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert "Getränk" in body


def test_combo_add_and_checkout_creates_combo_line():
    combo, cola = _combo_with_drink()
    add = _req(data={"combo": str(combo.pk), "opt": [str(cola.pk)], "qty": "1"})
    public_views.combo_add(add)
    cc = add.session["combo_cart"]
    assert cc  # комбо добавлено в сессию

    public_views.checkout(_req(data={"name": "Kunde"}, session={"combo_cart": cc}))
    order = Order.objects.get()
    item = order.items.get()
    assert item.product_id is None and item.combo_id == combo.pk
    assert item.unit_price == Decimal("10.90")  # 9,90 + 1,00 (Groß/Cola)
    assert order.total == Decimal("10.90")
    assert len(item.modifiers) == 1  # снимок состава


def test_combo_add_missing_required_choice_blocks():
    combo, _ = _combo_with_drink()  # группа min_select=1
    add = _req(data={"combo": str(combo.pk), "qty": "1"})  # без выбора напитка
    public_views.combo_add(add)
    assert add.session.get("combo_cart", {}) == {}  # не добавлено


# --- A4 промокод на чекауте --------------------------------------------------------


def test_checkout_applies_voucher_discount_and_redeems():
    from apps.promotions.models import Voucher

    voucher = Voucher.objects.create(code="MINUS10", label="−10 %", discount_percent=10, max_uses=1)
    product = ProductFactory(base_price=Decimal("20.00"))
    add = _req(data={"product": str(product.pk), "qty": "1"})
    public_views.cart_add(add)
    cart = add.session["cart"]
    public_views.checkout(_req(data={"name": "K"}, session={"cart": cart, "promo_code": "MINUS10"}))
    order = Order.objects.get()
    assert order.discount_cents == 200 and order.voucher_code == "MINUS10"
    assert order.total == Decimal("18.00")  # 20,00 − 10 %
    voucher.refresh_from_db()
    assert voucher.used_count == 1  # погашен


def test_checkout_ignores_invalid_voucher():
    product = ProductFactory(base_price=Decimal("10.00"))
    add = _req(data={"product": str(product.pk), "qty": "1"})
    public_views.cart_add(add)
    public_views.checkout(
        _req(data={"name": "K"}, session={"cart": add.session["cart"], "promo_code": "NOPE"})
    )
    order = Order.objects.get()
    assert order.discount_cents == 0 and order.total == Decimal("10.00")


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


def test_checkout_persists_table_number_from_session():
    """T2a: номер стола из сессии (?tisch=) попадает в заказ."""
    product = ProductFactory(base_price=Decimal("8.00"))
    add = _req(data={"product": str(product.pk), "qty": "1"})
    public_views.cart_add(add)
    public_views.checkout(
        _req(data={"name": "Kunde"}, session={"cart": add.session["cart"], "table": "7"})
    )
    assert Order.objects.get().table_number == "7"


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
