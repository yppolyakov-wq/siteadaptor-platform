"""KA-12 E3.6: окно времени у акции на товар — «показано = списано», фид без окон."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import price_layer
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _at(hour):
    today = timezone.localdate()
    return timezone.make_aware(datetime.datetime.combine(today, datetime.time(hour, 30)))


def _timed_promo(product, rules):
    promo = PromotionFactory(
        product=product, price_override=Decimal("2.00"), available_quantity=None
    )
    Promotion.objects.filter(pk=promo.pk).update(status="active", target_rules=rules)
    promo.refresh_from_db()
    return promo


def test_promo_applies_only_inside_the_window():
    product = ProductFactory(base_price=Decimal("4.00"))
    _timed_promo(product, {"hour_from": 17})
    assert product.pk not in price_layer.product_promo_map([product.pk], now=_at(16))
    assert product.pk in price_layer.product_promo_map([product.pk], now=_at(17))


def test_untimed_promo_unchanged_and_feed_skips_timed():
    plain, timed = ProductFactory(base_price=Decimal("4")), ProductFactory(base_price=Decimal("4"))
    _timed_promo(plain, {})
    _timed_promo(timed, {"hour_from": 0, "hour_to": 24})
    got = price_layer.product_promo_map([plain.pk, timed.pk], timeless_only=True)
    assert plain.pk in got and timed.pk not in got


def test_create_order_charges_full_price_outside_window(monkeypatch):
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("4.00"), stock_quantity=None)
    _timed_promo(product, {"hour_from": 17})
    ten = _at(10)
    monkeypatch.setattr(price_layer.timezone, "now", lambda: ten)
    order = create_order(items=[(product, 1)], name="K")
    assert order.items.get().unit_price == Decimal("4.00")
