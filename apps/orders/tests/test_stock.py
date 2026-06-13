"""R3: остаток с atomic-списанием — списание при заказе, отказ, возврат при отмене."""

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.orders import services
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


def test_create_order_decrements_tracked_stock():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=10)
    services.create_order(items=[(product, 3)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 7


def test_create_order_untracked_stock_unchanged():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=None)
    services.create_order(items=[(product, 3)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity is None


def test_create_order_decrements_variant_stock():
    product = ProductFactory(base_price=Decimal("5.00"))
    v = ProductVariant.objects.create(product=product, label="M", stock_quantity=2)
    services.create_order(items=[(product, v, 2)], name="K")
    v.refresh_from_db()
    assert v.stock_quantity == 0


def test_create_order_out_of_stock_rejected():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=1)
    with pytest.raises(services.OutOfStock):
        services.create_order(items=[(product, 2)], name="K")
    assert Order.objects.count() == 0  # откат — заказа нет
    product.refresh_from_db()
    assert product.stock_quantity == 1  # остаток не тронут


def test_cancel_restocks_product():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=10)
    order = services.create_order(items=[(product, 4)], name="K")
    product.refresh_from_db()
    assert product.stock_quantity == 6
    OrderSM().apply(order, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 10  # возвращено


def test_cancel_restocks_variant():
    product = ProductFactory(base_price=Decimal("5.00"))
    v = ProductVariant.objects.create(product=product, label="M", stock_quantity=5)
    order = services.create_order(items=[(product, v, 2)], name="K")
    v.refresh_from_db()
    assert v.stock_quantity == 3
    OrderSM().apply(order, "cancelled")
    v.refresh_from_db()
    assert v.stock_quantity == 5


def test_cancel_untracked_is_noop():
    product = ProductFactory(base_price=Decimal("5.00"), stock_quantity=None)
    order = services.create_order(items=[(product, 2)], name="K")
    OrderSM().apply(order, "cancelled")  # не падает, остаток без учёта
    product.refresh_from_db()
    assert product.stock_quantity is None


def test_in_stock_helpers():
    assert ProductFactory(stock_quantity=0).in_stock is False  # явный 0
    assert ProductFactory(stock_quantity=None).in_stock is True  # без учёта
    assert ProductFactory(stock_quantity=3).in_stock is True


def test_in_stock_with_variants():
    product = ProductFactory()
    ProductVariant.objects.create(product=product, label="A", stock_quantity=0)
    assert product.in_stock is False  # единственный вариант распродан
    ProductVariant.objects.create(product=product, label="B", stock_quantity=2)
    assert product.in_stock is True  # есть доступный вариант
