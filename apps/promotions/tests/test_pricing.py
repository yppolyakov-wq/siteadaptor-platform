"""Тесты вычисляемой цены/скидки акции."""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.promotions.tests.factories import PromotionFactory


@pytest.mark.django_db
def test_percent_discount_from_compare_at_price():
    p = PromotionFactory(compare_at_price=Decimal("10.00"), discount_percent=20)
    assert p.old_price == Decimal("10.00")
    assert p.new_price == Decimal("8.00")
    assert p.has_discount
    assert p.discount_amount == Decimal("2.00")
    assert p.discount_percent_display == 20


@pytest.mark.django_db
def test_new_price_override_computes_percent():
    p = PromotionFactory(compare_at_price=Decimal("20.00"), price_override=Decimal("15.00"))
    assert p.new_price == Decimal("15.00")
    assert p.discount_amount == Decimal("5.00")
    assert p.discount_percent_display == 25


@pytest.mark.django_db
def test_old_price_falls_back_to_product():
    prod = ProductFactory(base_price="12.00")
    p = PromotionFactory(product=prod, compare_at_price=None, discount_percent=50)
    assert p.old_price == Decimal("12.00")
    assert p.new_price == Decimal("6.00")
    assert p.currency == prod.currency


@pytest.mark.django_db
def test_no_discount_when_no_prices():
    p = PromotionFactory(product=None, compare_at_price=None, discount_percent=None)
    assert p.old_price is None
    assert not p.has_discount
    assert p.discount_percent_display is None


@pytest.mark.django_db
def test_primary_image_falls_back_to_product():
    prod = ProductFactory(images=[{"id": "1", "url": "/x.jpg", "is_primary": True}])
    p = PromotionFactory(product=prod, images=[])
    assert p.primary_image["url"] == "/x.jpg"

    p2 = PromotionFactory(images=[{"id": "2", "url": "/own.jpg", "is_primary": True}])
    assert p2.primary_image["url"] == "/own.jpg"
