"""KA-12 PR-4: «Gratis-Artikel ab Bestellwert» — подарок строкой 0 € в корзине и заказе."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders import services as order_services
from apps.promotions import gifts, price_layer
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db

D = Decimal


def _setup(limit=None, stock=None):
    goods = Product.objects.create(name={"de": "Kaffee"}, base_price=D("12.00"))
    present = Product.objects.create(
        name={"de": "Tasse"}, base_price=D("6.00"), stock_quantity=stock
    )
    promo = Promotion.objects.create(
        title={"de": "Tasse gratis ab 30 €"},
        product=present,
        status="active",
        starts_at=timezone.now(),
        available_quantity=limit,
        metadata={"gift_min_order": "30.00"},
    )
    return goods, present, promo


def test_gift_does_not_change_product_price():
    _goods, present, _promo = _setup()
    assert present.pk not in price_layer.product_promo_map([present.pk])


def test_pick_reached_and_progress():
    _goods, _present, promo = _setup()
    gift, nxt, missing = gifts.pick(D("24.00"))
    assert gift is None and nxt == promo and missing == D("6.00")
    gift, nxt, _ = gifts.pick(D("36.00"))
    assert gift == promo and nxt is None


def test_order_gets_free_line_and_claims_limit_and_stock():
    goods, present, promo = _setup(limit=2, stock=5)
    order = order_services.create_order(items=[(goods, 3)], name="K")
    assert order.total == D("36.00")
    free = order.items.get(product=present)
    assert free.unit_price == D("0.00") and free.promotion_id == promo.pk
    promo.refresh_from_db()
    present.refresh_from_db()
    assert promo.available_quantity == 1 and present.stock_quantity == 4


def test_below_threshold_or_exhausted_no_gift_but_order_ok():
    goods, present, promo = _setup(limit=0)
    order = order_services.create_order(items=[(goods, 3)], name="K")
    assert not order.items.filter(product=present).exists()
    order = order_services.create_order(items=[(goods, 1)], name="K")
    assert order.items.count() == 1


def test_staff_cannot_multiply_gift_line():
    from apps.orders import editing

    goods, present, _promo = _setup(stock=5)
    order = order_services.create_order(items=[(goods, 3)], name="K")
    free = order.items.get(product=present)
    with pytest.raises(editing.OrderLocked):
        editing.set_item_qty(order, free.pk, 4)
