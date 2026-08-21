"""ERP-5: возврат поставщику (Rücksendung) — движение, счётчик, сторно расхода.

Замки написаны по плану `docs/erp57-plan-2026-08-21.md §ERP-5`:
зеркало приёмки — складской путь один, деньги идемпотентны по накопленному
qty_returned, кламп по qty_returnable и по остатку счётчика.
"""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.finance.expenses import ExpenseEntry
from apps.inventory import purchasing, services
from apps.inventory.models import Bestellung, StockMovement
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _received_line(*, qty=8, cost="2.00", stock=0):
    po = purchasing.create_po(
        supplier=purchasing.Lieferant.objects.create(name="Großhandel Müller")
    )
    product = ProductFactory(cost_price=Decimal(cost), stock_quantity=stock)
    line = purchasing.add_po_line(po, product=product, qty=qty)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(line)
    line.refresh_from_db()
    return po, product, line


def test_return_books_movement_counter_and_credit():
    po, product, line = _received_line(qty=8, cost="2.00")
    took = purchasing.return_po_line(line, qty=3)
    assert took == 3
    product.refresh_from_db()
    line.refresh_from_db()
    assert product.stock_quantity == 5  # 8 принято − 3 возвращено
    assert line.qty_returned == 3 and line.qty_returnable == 5
    mv = StockMovement.objects.filter(product=product, kind="return_supplier")
    assert mv.count() == 1 and mv.first().delta == -3
    assert mv.first().source == "purchase"
    # Сторно-расход: отрицательная сумма, свой идемпотентный ключ.
    credit = ExpenseEntry.objects.get(source_ref=f"{line.pk}:ret:3")
    assert credit.amount == Decimal("-6.00")
    assert credit.category == ExpenseEntry.CATEGORY_GOODS
    assert credit.supplier_id == po.supplier_id
    # Запись приёмки цела — сторно складывается, а не затирает.
    assert ExpenseEntry.objects.get(source_ref=f"{line.pk}:8").amount == Decimal("16.00")


def test_return_capped_by_returnable_and_accumulates():
    _, product, line = _received_line(qty=5, cost="1.00")
    assert purchasing.return_po_line(line, qty=99) == 5  # кламп по принятому
    line.refresh_from_db()
    assert line.qty_returned == 5 and line.qty_returnable == 0
    assert purchasing.return_po_line(line, qty=1) == 0  # возвращать больше нечего
    # Два разных возврата → две сторно-записи с разными ключами.
    _, product2, line2 = _received_line(qty=6, cost="1.00")
    assert purchasing.return_po_line(line2, qty=2) == 2
    assert purchasing.return_po_line(line2, qty=1) == 1
    refs = set(
        ExpenseEntry.objects.filter(source_ref__startswith=f"{line2.pk}:ret:").values_list(
            "source_ref", flat=True
        )
    )
    assert refs == {f"{line2.pk}:ret:2", f"{line2.pk}:ret:3"}


def test_return_clamps_at_zero_stock():
    # Принятое уже продано: счётчик 8 − 6 = 2, возврат 5 честно даст 2.
    _, product, line = _received_line(qty=8, cost="2.00")
    services.apply_manual_movement(
        product=product, kind=StockMovement.KIND_SALE, delta=-6, source="manual"
    )
    took = purchasing.return_po_line(line, qty=5)
    assert took == 2
    product.refresh_from_db()
    line.refresh_from_db()
    assert product.stock_quantity == 0 and line.qty_returned == 2
    credit = ExpenseEntry.objects.get(source_ref=f"{line.pk}:ret:2")
    assert credit.amount == Decimal("-4.00")  # деньги по ФАКТИЧЕСКИ возвращённому


def test_return_keeps_ledger_reconciled():
    _, product, line = _received_line(qty=8, stock=0)
    purchasing.return_po_line(line, qty=3)
    rows = [r for r in services.reconciliation_rows() if r["product"].pk == product.pk]
    assert rows == [] or all(r["diff"] == 0 for r in rows)


def test_return_consumes_fefo_lot():
    tenant = TenantFactory.build(business_type="bakery", site_config={"lots_enabled": True})
    po = purchasing.create_po()
    product = ProductFactory(cost_price=Decimal("2.00"), stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=4)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(line, tenant=tenant, lot_code="CH-1")
    line.refresh_from_db()
    took = purchasing.return_po_line(line, qty=3, tenant=tenant)
    assert took == 3
    lot = product.lots.get()
    assert lot.qty_remaining == 1  # партия следует за остатком


def test_cabinet_return_action():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.inventory.views_purchasing import purchasing_view

    _, product, line = _received_line(qty=5, cost="1.50")

    class _User:
        is_authenticated = True
        is_active = True
        username = "chef"

    req = RequestFactory().post(
        "/dashboard/purchasing/",
        {"action": "return_line", "po": line.bestellung.pk, "line": line.pk, "qty": "2"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(business_type="bakery")
    resp = purchasing_view(req)
    assert resp.status_code == 302
    line.refresh_from_db()
    assert line.qty_returned == 2
