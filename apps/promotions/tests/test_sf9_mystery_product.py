"""SF-9: акция-сюрприз не трогает цену товара (решение владельца 2026-10-19 «закрыть»).

Секрет mystery-акции раскрывается только на странице самой акции (/p/<uuid>/), и
продаётся она только там (/kaufen/). Страница товара, карточки, quick-add, корзина и
заказ показывают и списывают ОБЫЧНУЮ цену — «показано = списано», секрет не течёт
ни через баннер, ни через корзину. На детали товара — нейтральный баннер без цены.
"""

from decimal import Decimal

import pytest

from apps.orders import public_views as orders_public
from apps.orders import services as order_services
from apps.promotions import public_views as promo_public
from apps.promotions.models import Promotion
from apps.promotions.price_layer import attach_promos, product_promo_map, promo_for_product
from apps.promotions.tests.test_promo_cart import _req, _saft, _tenant

pytestmark = pytest.mark.django_db

SECRET = "1.37"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _mystery(product, new=SECRET, **kw):
    return Promotion.objects.create(
        title={"de": "Überraschung"},
        status="active",
        product=product,
        price_override=Decimal(new),
        compare_at_price=product.base_price,
        discount_style="mystery",
        **kw,
    )


def _no_secret(body):
    assert SECRET not in body and SECRET.replace(".", ",") not in body


def test_resolvers_ignore_mystery():
    product = _saft()
    _mystery(product)
    assert product_promo_map([product.pk]) == {}
    assert promo_for_product(product) is None
    card = attach_promos([product])[0]
    assert card.promo is None and card.promo_price is None and card.promo_badge == ""


def test_cheaper_mystery_does_not_hide_regular_promo():
    product = _saft()
    _mystery(product)
    regular = Promotion.objects.create(
        title={"de": "Normal"},
        status="active",
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=product.base_price,
    )
    assert product_promo_map([product.pk])[product.pk] == regular


def test_product_detail_shows_neutral_banner_without_price():
    tenant = _tenant("sf9a")
    product = _saft()
    promo = _mystery(product)
    body = promo_public.product_detail(
        _req(path=f"/sortiment/p/{product.slug}/", tenant=tenant), pslug=product.slug
    ).content.decode()
    _no_secret(body)
    assert "2,49" in body
    assert "data-mystery-teaser" in body and f"/p/{promo.pk}/" in body


def test_listing_quickadd_and_cart_use_regular_price():
    tenant = _tenant("sf9b")
    product = _saft()
    _mystery(product)
    listing = promo_public.product_list(_req(path="/sortiment/", tenant=tenant)).content.decode()
    _no_secret(listing)
    quick = orders_public.quick_add_form(
        _req(path=f"/warenkorb/quick/{product.pk}/", tenant=tenant), pk=product.pk
    ).content.decode()
    _no_secret(quick)
    add = _req("post", "/warenkorb/add/", {"product": str(product.pk), "qty": "1"}, tenant)
    orders_public.cart_add(add)
    cart_req = _req(path="/warenkorb/", tenant=tenant)
    cart_req.session = add.session
    _no_secret(orders_public.cart_view(cart_req).content.decode())


def test_order_from_cart_charges_regular_price_without_marker():
    product = _saft()
    promo = _mystery(product, available_quantity=5)
    order = order_services.create_order(items=[(product, 1)], name="Kunde")
    item = order.items.get()
    assert item.unit_price == Decimal("2.49")
    assert not any(m.get("promo") for m in item.modifiers)
    promo.refresh_from_db()
    assert promo.available_quantity == 5


def test_promotion_page_purchase_still_charges_mystery_price():
    from apps.promotions import services as promo_services

    product = _saft()
    promo = _mystery(product, promo_type="discount")
    order = promo_services.purchase(promo, quantity=1, name="Kunde", email="k@example.org")
    assert order.items.get().unit_price == Decimal(SECRET)


def test_promotion_detail_has_no_target_card():
    """Название и фото цели выдали бы товар — у сюрприза карточки «Gilt für» нет."""
    tenant = _tenant("sf9c")
    product = _saft()
    promo = _mystery(product, promo_type="discount")
    body = promo_public.promotion_detail(
        _req(path=f"/p/{promo.pk}/", tenant=tenant), pk=promo.pk
    ).content.decode()
    assert "data-promo-target" not in body
