"""U-D3: StockMovement + record_movement — идемпотентность, ручные, реконсиляция."""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import StockMovement
from apps.inventory.services import ledger_balance, record_movement

pytestmark = pytest.mark.django_db


def _product(stock=10):
    return ProductFactory(base_price=Decimal("5.00"), stock_quantity=stock)


def test_event_movement_idempotent_by_source_ref_kind():
    product = _product()
    first = record_movement(
        product=product, kind="sale", delta=-2, source="order", source_ref="item-1"
    )
    assert first is not None
    # тот же (source, source_ref, kind) — дубль → None, вторая строка не пишется
    dup = record_movement(
        product=product, kind="sale", delta=-2, source="order", source_ref="item-1"
    )
    assert dup is None
    assert StockMovement.objects.filter(source="order", source_ref="item-1").count() == 1


def test_same_ref_different_kind_are_distinct_rows():
    product = _product()
    record_movement(product=product, kind="sale", delta=-2, source="order", source_ref="item-1")
    ret = record_movement(
        product=product, kind="return", delta=2, source="order", source_ref="item-1"
    )
    assert ret is not None  # sale и return по одной позиции — разные строки
    assert StockMovement.objects.filter(source_ref="item-1").count() == 2


def test_manual_movements_are_not_deduped():
    product = _product()
    record_movement(product=product, kind="receipt", delta=5, source="manual", actor="chef")
    record_movement(product=product, kind="receipt", delta=5, source="manual", actor="chef")
    assert StockMovement.objects.filter(source="manual").count() == 2


def test_zero_delta_is_noop():
    product = _product()
    assert record_movement(product=product, kind="adjustment", delta=0, source="manual") is None
    assert StockMovement.objects.count() == 0


def test_record_does_not_touch_counter():
    product = _product(stock=10)
    record_movement(product=product, kind="sale", delta=-3, source="order", source_ref="x")
    product.refresh_from_db()
    assert product.stock_quantity == 10  # леджер append-only, счётчик не трогает


def test_ledger_balance_sums_deltas():
    product = _product()
    record_movement(product=product, kind="receipt", delta=10, source="manual")
    record_movement(product=product, kind="sale", delta=-3, source="order", source_ref="a")
    record_movement(product=product, kind="return", delta=1, source="order", source_ref="a")
    assert ledger_balance(product) == 8
    other = _product()
    assert ledger_balance(other) == 0
