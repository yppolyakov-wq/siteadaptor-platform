"""SF-10: акция с исчерпанным лимитом снимается с витрины (решение владельца 2026-10-19).

Раньше акция с `available_quantity=0` оставалась `active`: карточки и корзина показывали
цену акции, а чекаут отказывал «Aktionslimit erreicht». Теперь «в продаже» = действует И
лимит не исчерпан (`Promotion.on_sale_q`): товар/услуга/номер возвращаются к обычной цене,
акция пропадает из списков витрины. Возврат лимита (отмена) возвращает акцию сам — без
перехода статуса. Страница самой акции остаётся (QR/флаер/лист ожидания ведут туда).
"""

from decimal import Decimal

import pytest

from apps.orders import public_views as orders_public
from apps.orders import services as order_services
from apps.orders.state_machine import OrderSM
from apps.promotions import public_views as promo_public
from apps.promotions.models import Promotion
from apps.promotions.price_layer import product_promo_map, promo_for_product
from apps.promotions.tests.test_promo_cart import _promo, _req, _saft, _tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _p(product, limit, title="Deal", status="active"):
    return Promotion.objects.create(
        title={"de": title},
        status=status,
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=product.base_price,
        available_quantity=limit,
    )


def test_on_sale_rule():
    product = _saft()
    endless = _promo(product, limit=None)
    left = _promo(product, limit=3)
    gone = _promo(product, limit=0)
    paused = _p(product, None, status="paused")
    ids = set(Promotion.objects.filter(Promotion.on_sale_q()).values_list("pk", flat=True))
    assert endless.pk in ids and left.pk in ids
    assert gone.pk not in ids and paused.pk not in ids


def test_exhausted_promo_leaves_product_price():
    product = _saft()
    _promo(product, limit=0)
    assert product_promo_map([product.pk]) == {}
    assert promo_for_product(product) is None


def test_cart_order_charges_regular_price_without_error():
    product = _saft()
    promo = _promo(product, limit=0)
    order = order_services.create_order(items=[(product, 1)], name="Kunde")
    item = order.items.get()
    assert item.unit_price == Decimal("2.49")
    assert not any(m.get("promo") for m in item.modifiers)
    promo.refresh_from_db()
    assert promo.available_quantity == 0


def test_product_detail_and_listing_show_regular_price():
    tenant = _tenant("sf10a")
    product = _saft()
    _promo(product, limit=0)
    detail = promo_public.product_detail(
        _req(path=f"/sortiment/p/{product.slug}/", tenant=tenant), pslug=product.slug
    ).content.decode()
    assert "1,99" not in detail and "2,49" in detail
    listing = promo_public.product_list(_req(path="/sortiment/", tenant=tenant)).content.decode()
    assert "1,99" not in listing


def test_returned_units_bring_promo_back():
    product = _saft()
    promo = _promo(product, limit=1)
    order = order_services.create_order(items=[(product, 1)], name="A")
    promo.refresh_from_db()
    assert promo.available_quantity == 0 and product_promo_map([product.pk]) == {}
    OrderSM().apply(order, "cancelled")
    assert product_promo_map([product.pk])[product.pk].pk == promo.pk


def test_exhausted_promo_hidden_from_aktionen_but_page_stays():
    tenant = _tenant("sf10b")
    product = _saft()
    gone = _p(product, 0, "Ausverkauft-Deal")
    _p(product, 5, "Laufender-Deal")
    listing = promo_public.promotion_list(_req(path="/aktionen/", tenant=tenant)).content.decode()
    assert "Laufender-Deal" in listing and "Ausverkauft-Deal" not in listing
    detail = promo_public.promotion_detail(_req(path=f"/p/{gone.pk}/", tenant=tenant), pk=gone.pk)
    assert detail.status_code == 200


def test_checkout_rejects_stale_promo_price(isolated_ratelimit):
    """Цена акции была в корзине, лимит кончился до «Kaufen» — заказа нет, назад в корзину
    (SF-4b: честная ошибка вместо молчаливой полной цены)."""
    from apps.orders.models import Order

    tenant = _tenant("sf10c")
    product = _saft()
    promo = _promo(product, limit=1)
    add = _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "1"}, tenant)
    orders_public.cart_add(add)
    Promotion.objects.filter(pk=promo.pk).update(available_quantity=0)
    co = _req(
        "post",
        "/warenkorb/kasse/",
        {"name": "Kunde", "website": "", "promo_seen": str(promo.pk)},
        tenant,
    )
    co.session = add.session
    resp = orders_public.checkout(co)
    assert resp.status_code == 302 and Order.objects.count() == 0
    # без поля (старая форма) — заказ по обычной цене
    co2 = _req("post", "/warenkorb/kasse/", {"name": "Kunde", "website": ""}, tenant)
    co2.session = add.session
    orders_public.checkout(co2)
    assert Order.objects.get().items.get().unit_price == Decimal("2.49")


def test_cart_form_carries_seen_promos():
    tenant = _tenant("sf10d")
    product = _saft()
    promo = _promo(product, limit=3)
    add = _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "1"}, tenant)
    orders_public.cart_add(add)
    cart_req = _req(path="/warenkorb/", tenant=tenant)
    cart_req.session = add.session
    body = orders_public.cart_view(cart_req).content.decode()
    assert f'name="promo_seen" value="{promo.pk}"' in body
