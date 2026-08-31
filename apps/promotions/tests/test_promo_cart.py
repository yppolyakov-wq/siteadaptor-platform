"""SF-4b (вариант A владельца): корзина продаёт по промо-цене ценового слоя.

До SF-4b quick-add/корзина продавали акционный товар по ПОЛНОЙ цене — путь к
скидке был только через страницу акции (/p/<uuid>/kaufen/). Теперь витрина
(карточка/деталь/quick-add/корзина) и деньги (create_order) берут одну функцию
promo_line_price: «показано = списано». Лимит кампании клеймится на чекауте
(conditional UPDATE в той же atomic, что склад), маркер {"promo": id} в
OrderItem.modifiers питает возврат при отмене и deal_counts без правок.
"""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Product, ProductVariant
from apps.orders import editing
from apps.orders import public_views as orders_public
from apps.orders import services as order_services
from apps.orders.state_machine import OrderSM
from apps.promotions import public_views as promo_public
from apps.promotions.models import Promotion
from apps.promotions.services import OutOfStock as PromoSoldOut
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, schema=None, **kw):
    return TenantFactory(
        schema_name=schema or slug, slug=slug, name="PC", disabled_modules=[], **kw
    )


def _req(method="get", path="/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _saft(price="2.49", stock=30):
    return Product.objects.create(name={"de": "Saft"}, base_price=price, stock_quantity=stock)


def _promo(product, new="1.99", limit=None, **kw):
    return Promotion.objects.create(
        title={"de": "SaftDeal"},
        status="active",
        product=product,
        price_override=Decimal(new),
        compare_at_price=product.base_price,
        available_quantity=limit,
        **kw,
    )


def test_price_parity_card_detail_quickadd_cart_order():
    """Главный паритет-замок: одна цена на всех поверхностях и в заказе."""
    tenant = _tenant("pc1")
    product = _saft()
    _promo(product)

    # карточка каталога: промо крупно + зачёркнутая база (data-price-edit на базе)
    listing = promo_public.product_list(_req(path="/sortiment/", tenant=tenant)).content.decode()
    assert "1,99" in listing and "2,49" in listing
    assert 'data-price="2,49"' in listing  # канва-правка пишет БАЗУ (de-локаль), не промо
    # деталь: buy-box с промо-ценой
    detail = promo_public.product_detail(
        _req(path=f"/sortiment/p/{product.slug}/", tenant=tenant), pslug=product.slug
    ).content.decode()
    assert detail.count("1,99") >= 2  # buy-box + rose-баннер
    # quick-add модалка
    quick = orders_public.quick_add_form(
        _req(path=f"/warenkorb/quick/{product.pk}/", tenant=tenant), pk=product.pk
    ).content.decode()
    assert "1,99" in quick
    # корзина: промо-цена строки + зачёркнутая база + чип
    request = _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "2"}, tenant)
    orders_public.cart_add(request)
    # cart_view нужен ТОТ ЖЕ session-объект
    cart_req = _req(path="/warenkorb/", tenant=tenant)
    cart_req.session = request.session
    body = orders_public.cart_view(cart_req).content.decode()
    assert "1,99" in body and "3,98" in body  # unit и line_total по промо
    assert "line-through" in body and "Aktion" in body
    # заказ: create_order списывает ту же цену + маркер
    order = order_services.create_order(items=[(product, 2)], name="Kunde")
    item = order.items.get()
    assert item.unit_price == Decimal("1.99")
    assert order.total == Decimal("3.98")
    assert any(m.get("promo") for m in item.modifiers)


def test_limit_claim_race_and_rollback():
    """Лимит клеймится атомарно: исчерпан → промо-OutOfStock, склад не тронут."""
    product = _saft(stock=30)
    promo = _promo(product, limit=2)

    order = order_services.create_order(items=[(product, 2)], name="A")
    promo.refresh_from_db()
    product.refresh_from_db()
    assert promo.available_quantity == 0
    assert product.stock_quantity == 28

    with pytest.raises(PromoSoldOut):
        order_services.create_order(items=[(product, 1)], name="B")
    product.refresh_from_db()
    assert product.stock_quantity == 28  # atomic откатил и склад

    # отмена возвращает лимит по маркеру (штатный путь PL)
    OrderSM().apply(order, "cancelled")
    promo.refresh_from_db()
    product.refresh_from_db()
    assert promo.available_quantity == 2
    assert product.stock_quantity == 30


def test_checkout_shows_friendly_message_on_limit(client):
    tenant = _tenant("pc3")
    product = _saft()
    _promo(product, limit=1)

    add = _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "2"}, tenant)
    orders_public.cart_add(add)
    co = _req("post", "/warenkorb/kasse/", {"name": "Kunde", "website": ""}, tenant)
    co.session = add.session
    resp = orders_public.checkout(co)
    assert resp.status_code == 302  # назад в корзину, заказа нет
    from apps.orders.models import Order

    assert Order.objects.count() == 0
    promo = Promotion.objects.get()
    assert promo.available_quantity == 1  # клейм откатился


def test_variant_with_own_price_not_discounted():
    """Применимость: вариант со своей ценой едет по полной (new_price — из базы)."""
    product = _saft()
    variant = ProductVariant.objects.create(
        product=product, label="XL", price=Decimal("3.49"), stock_quantity=5
    )
    _promo(product)
    order = order_services.create_order(items=[(product, variant, 1)], name="K")
    assert order.items.get().unit_price == Decimal("3.49")

    # вариант БЕЗ своей цены наследует базу → промо применимо
    v2 = ProductVariant.objects.create(product=product, label="M", stock_quantity=5)
    order2 = order_services.create_order(items=[(product, v2, 1)], name="K2")
    assert order2.items.get().unit_price == Decimal("1.99")


def test_modifier_delta_on_top_of_promo_price():
    from apps.catalog.models import ModifierGroup, ModifierOption

    product = _saft()
    group = ModifierGroup.objects.create(product=product, name="Extras")
    opt = ModifierOption.objects.create(group=group, label="Bio", price_delta=Decimal("0.50"))
    _promo(product)
    order = order_services.create_order(items=[(product, None, 1, [opt])], name="K")
    item = order.items.get()
    assert item.unit_price == Decimal("2.49")  # 1.99 промо + 0.50 опция
    labels = [m.get("label") for m in item.modifiers]
    assert "Bio" in labels and "Aktion" in labels


def test_editing_mirrors_campaign_limit():
    """SH-дыра закрыта: правка qty промо-строки двигает лимит зеркально складу."""
    product = _saft()
    promo = _promo(product, limit=10)
    order = order_services.create_order(items=[(product, 3)], name="K")
    item = order.items.get()
    promo.refresh_from_db()
    assert promo.available_quantity == 7

    editing.set_item_qty(order, item.pk, 1)  # −2 → возврат
    promo.refresh_from_db()
    assert promo.available_quantity == 9

    editing.set_item_qty(order, item.pk, 4)  # +3 → дозабор
    promo.refresh_from_db()
    assert promo.available_quantity == 6

    editing.set_item_qty(order, item.pk, 0)  # удаление → полный возврат
    promo.refresh_from_db()
    assert promo.available_quantity == 10
    # последующая отмена не задваивает (строки нет)
    OrderSM().apply(order, "cancelled")
    promo.refresh_from_db()
    assert promo.available_quantity == 10


def test_deal_counts_sees_cart_orders():
    from apps.promotions.price_layer import deal_counts

    product = _saft()
    promo = _promo(product)
    order_services.create_order(items=[(product, 1)], name="K")
    assert deal_counts(promo)["orders"] >= 1


def test_no_promo_no_changes():
    """Товар без акции: цены и снимки байт-в-байт прежние."""
    product = _saft()
    order = order_services.create_order(items=[(product, 2)], name="K")
    item = order.items.get()
    assert item.unit_price == Decimal("2.49")
    assert item.modifiers == []
