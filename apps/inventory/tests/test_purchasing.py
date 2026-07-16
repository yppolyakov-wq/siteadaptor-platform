"""Склад-2 E3.1: закупочные заказы (Lieferant/Bestellung) + приёмка через складской путь."""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory import purchasing
from apps.inventory.models import Bestellung, Lot, StockMovement
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_create_po_draft_with_reference():
    supplier = purchasing.Lieferant.objects.create(name="Großhandel Müller")
    po = purchasing.create_po(supplier=supplier, actor="chef", note="Wocheneinkauf")
    assert po.status == Bestellung.STATUS_DRAFT
    assert po.reference.startswith("BE-") and len(po.reference) == 9
    assert po.supplier_id == supplier.pk


def test_add_line_snapshots_cost_price():
    po = purchasing.create_po()
    product = ProductFactory(cost_price=Decimal("2.50"), stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=10)
    assert line.qty == 10 and line.unit_cost == Decimal("2.50")  # EK из T5 cost_price
    assert line.line_total == Decimal("25.00")
    # явный unit_cost переопределяет
    line2 = purchasing.add_po_line(po, product=product, qty=4, unit_cost=Decimal("3.00"))
    assert line2.unit_cost == Decimal("3.00")


def test_set_status_stamps_timestamps():
    po = purchasing.create_po()
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    po.refresh_from_db()
    assert po.status == "ordered" and po.ordered_at is not None
    purchasing.set_po_status(po, Bestellung.STATUS_RECEIVED)
    po.refresh_from_db()
    assert po.received_at is not None


def test_receive_line_books_receipt_once_and_marks_received():
    po = purchasing.create_po()
    product = ProductFactory(cost_price=Decimal("2.00"), stock_quantity=5)
    line = purchasing.add_po_line(po, product=product, qty=8)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    took = purchasing.receive_po_line(line)  # всё оставшееся (8)
    assert took == 8
    product.refresh_from_db()
    line.refresh_from_db()
    assert product.stock_quantity == 13  # 5 + 8 (счётчик двинут ОДИН раз)
    assert line.qty_received == 8 and line.is_fully_received
    mv = StockMovement.objects.filter(product=product, kind="receipt", source="purchase")
    assert mv.count() == 1 and mv.first().delta == 8  # провенанс purchase
    po.refresh_from_db()
    assert po.status == Bestellung.STATUS_RECEIVED  # авто-закрытие при полной приёмке


def test_partial_receipts_accumulate():
    po = purchasing.create_po()
    product = ProductFactory(stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=10)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    assert purchasing.receive_po_line(line, qty=4) == 4
    assert purchasing.receive_po_line(line, qty=3) == 3
    line.refresh_from_db()
    product.refresh_from_db()
    assert line.qty_received == 7 and not line.is_fully_received
    assert product.stock_quantity == 7  # два прихода: +4, +3
    po.refresh_from_db()
    assert po.status == Bestellung.STATUS_ORDERED  # ещё не полностью
    # приём сверх остатка клампится по qty_open
    assert purchasing.receive_po_line(line, qty=99) == 3
    line.refresh_from_db()
    assert line.qty_received == 10 and line.is_fully_received


def test_receive_creates_lot_when_lots_enabled():
    tenant = TenantFactory.build(business_type="bakery", site_config={"lots_enabled": True})
    po = purchasing.create_po()
    product = ProductFactory(stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=6)
    took = purchasing.receive_po_line(line, tenant=tenant, mhd=None, lot_code="CH-P1")
    assert took == 6
    lot = Lot.objects.get(product=product)
    assert lot.lot_code == "CH-P1" and lot.qty_remaining == 6  # Charge заведена (E1-путь)
    product.refresh_from_db()
    assert product.stock_quantity == 6


def test_update_cost_writes_back_cost_price():
    po = purchasing.create_po()
    product = ProductFactory(cost_price=Decimal("1.00"), stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=3, unit_cost=Decimal("1.80"))
    purchasing.receive_po_line(line, update_cost=True)
    product.refresh_from_db()
    assert product.cost_price == Decimal("1.80")  # EK обновлён из строки (форк вкл)


def test_draft_from_suggestions_builds_lines():
    p1 = ProductFactory(stock_quantity=0, cost_price=Decimal("1.00"))
    p2 = ProductFactory(stock_quantity=2)
    sugg = [
        {"product": p1, "variant": None, "suggest": 12},
        {"product": p2, "variant": None, "suggest": 0},  # без Sollbestand → пропуск
    ]
    po = purchasing.draft_from_suggestions(sugg)
    lines = list(po.positions.all())
    assert len(lines) == 1 and lines[0].product_id == p1.pk and lines[0].qty == 12
