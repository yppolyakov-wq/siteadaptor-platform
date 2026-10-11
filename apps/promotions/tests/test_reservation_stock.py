"""T-8.23f: резерв по акции и склад товара (решение владельца S2, 2026-10-11)."""

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import StockMovement
from apps.promotions import services
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _promo(stock, limit=None):
    product = ProductFactory(base_price="4.50", stock_quantity=stock)
    promo = PromotionFactory(
        status="active", product=product, price_override="3", available_quantity=limit
    )
    return promo, product


def test_reserve_holds_stock_and_cancel_returns_it_once():
    promo, product = _promo(stock=3, limit=10)
    r = services.reserve(promo, name="Anna", email="a@test.de", quantity=2)
    product.refresh_from_db()
    assert product.stock_quantity == 1
    assert StockMovement.objects.get(source="reservation", kind="sale").delta == -2

    services.cancel(r)
    services.release_product_stock(r)  # повтор — без двойного возврата
    product.refresh_from_db()
    assert product.stock_quantity == 3
    assert StockMovement.objects.filter(source="reservation", kind="return").count() == 1
    promo.refresh_from_db()
    assert promo.available_quantity == 10


def test_not_enough_stock_refuses_and_rolls_back_promo_limit():
    promo, product = _promo(stock=1, limit=10)
    with pytest.raises(services.OutOfStock):
        services.reserve(promo, name="Ben", email="b@test.de", quantity=2)
    product.refresh_from_db()
    promo.refresh_from_db()
    assert product.stock_quantity == 1
    assert promo.available_quantity == 10  # лимит акции не съеден
    assert not promo.reservations.exists()


def test_fulfill_does_not_touch_stock_again():
    promo, product = _promo(stock=5)
    r = services.reserve(promo, name="Cem", email="c@test.de", quantity=1)
    services.fulfill(r)
    product.refresh_from_db()
    assert product.stock_quantity == 4
    assert StockMovement.objects.filter(source="reservation").count() == 1


def test_product_without_stock_tracking_is_untouched():
    promo, product = _promo(stock=None, limit=2)
    services.reserve(promo, name="Dana", email="d@test.de")
    product.refresh_from_db()
    assert product.stock_quantity is None
    assert not StockMovement.objects.filter(source="reservation").exists()
    assert Promotion.objects.get(pk=promo.pk).available_quantity == 1
