"""Склад-2 E1: партии (Lot) + FEFO-расход + MHD-обзор + реконсиляция Σlot↔счётчик."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import Lot
from apps.inventory.services import (
    consume_fefo,
    expiring_lots,
    has_lots,
    lot_balance,
    receive_lot,
)

pytestmark = pytest.mark.django_db


def _product(stock=0):
    return ProductFactory(base_price=Decimal("5.00"), stock_quantity=stock)


def _date(days):
    return timezone.localdate() + timedelta(days=days)


def test_receive_lot_moves_counter_ledger_and_creates_lot():
    product = _product(0)
    lot, mv = receive_lot(product=product, qty=12, mhd=_date(10), lot_code="CH-1")
    product.refresh_from_db()
    assert product.stock_quantity == 12  # счётчик двинулся
    assert mv is not None and mv.kind == "receipt" and mv.delta == 12  # леджер
    assert lot.qty_remaining == 12 and lot.qty_received == 12
    assert lot_balance(product) == 12  # Σ партий == счётчик (реконсиляция)


def test_consume_fefo_picks_earliest_mhd_first():
    product = _product(0)
    # Три партии: дальний срок, ближний, без даты.
    receive_lot(product=product, qty=5, mhd=_date(30), lot_code="far")
    receive_lot(product=product, qty=5, mhd=_date(3), lot_code="near")
    receive_lot(product=product, qty=5, mhd=None, lot_code="nodate")
    # Расход 7 → сначала near(5), потом far(2); nodate не тронут.
    taken = consume_fefo(product, qty=7)
    assert taken == 7
    by = {lot.lot_code: lot.qty_remaining for lot in Lot.objects.filter(product=product)}
    assert by["near"] == 0  # ближайший MHD выбран первым
    assert by["far"] == 3  # затем дальний
    assert by["nodate"] == 5  # партия без даты — в хвосте FEFO, не тронута
    assert lot_balance(product) == 8


def test_consume_fefo_capped_at_available_lot_qty():
    product = _product(0)
    receive_lot(product=product, qty=4, mhd=_date(5))
    # Просят больше, чем в партиях → списываем сколько есть (недостачу докрывает счётчик).
    taken = consume_fefo(product, qty=10)
    assert taken == 4 and lot_balance(product) == 0


def test_has_lots_only_when_remaining_positive():
    product = _product(0)
    assert has_lots(product) is False
    receive_lot(product=product, qty=2, mhd=_date(1))
    assert has_lots(product) is True
    consume_fefo(product, qty=2)
    assert has_lots(product) is False  # остаток исчерпан


def test_variant_lots_isolated_from_product_level():
    from apps.catalog.models import ProductVariant

    product = _product(0)
    variant = ProductVariant.objects.create(product=product, label="L", sku="v-l", stock_quantity=0)
    receive_lot(product=product, variant=variant, qty=6, mhd=_date(2))
    receive_lot(product=product, variant=None, qty=3, mhd=_date(2))
    assert lot_balance(product, variant) == 6  # партии варианта отдельно
    assert lot_balance(product, None) == 3  # партии товар-уровня отдельно
    consume_fefo(product, variant, qty=4)
    assert lot_balance(product, variant) == 2 and lot_balance(product, None) == 3


def test_expiring_and_expired_lots():
    product = _product(0)
    receive_lot(product=product, qty=1, mhd=_date(-1), lot_code="expired")
    receive_lot(product=product, qty=1, mhd=_date(2), lot_code="soon")
    receive_lot(product=product, qty=1, mhd=_date(60), lot_code="ok")
    receive_lot(product=product, qty=1, mhd=None, lot_code="nodate")
    # within 7 дней, включая просроченные → expired + soon (по MHD, ближайший первым).
    codes = [lot.lot_code for lot in expiring_lots(within_days=7, include_expired=True)]
    assert codes == ["expired", "soon"]
    # без просроченных → только soon.
    codes2 = [lot.lot_code for lot in expiring_lots(within_days=7, include_expired=False)]
    assert codes2 == ["soon"]
    exp = Lot.objects.get(lot_code="expired")
    assert exp.is_expired is True and exp.days_left() == -1
    assert Lot.objects.get(lot_code="nodate").is_expired is False
