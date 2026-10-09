"""ERP-8: Mängelanzeige — рекламация поставщику (§ 377 HGB).

План — `docs/erp8-maengelanzeige-plan-2026-10-09.md`. Замки до кода: виды дефектов из
реестра, строки только из принятого, три решения (скидка · возврат · замена) применяются
ровно один раз, деньги сходятся (замена = одна оплата), статус производный.
"""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.finance.expenses import ExpenseEntry
from apps.inventory import maengel, purchasing
from apps.inventory.models import Bestellung, StockMovement

pytestmark = pytest.mark.django_db


def _received_line(*, qty=10, cost="2.00"):
    po = purchasing.create_po(
        supplier=purchasing.Lieferant.objects.create(
            name="Großhandel Müller", email="einkauf@mueller.example"
        )
    )
    product = ProductFactory(cost_price=Decimal(cost), stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=qty)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(line)
    po.refresh_from_db()
    line.refresh_from_db()
    return po, product, line


def _anzeige(po, line, *, qty=3, types=("quality",), **head):
    return maengel.create_anzeige(
        po,
        lines=[{"position": line, "qty": qty, "defect_types": list(types), "description": "x"}],
        actor="anna",
        **head,
    )


def _spent(line_pk_prefix):
    return sum(
        (e.amount for e in ExpenseEntry.objects.filter(source_ref__startswith=line_pk_prefix)),
        Decimal("0"),
    )


# ───────────────────────────── 1–2: фиксация ─────────────────────────────


def test_defect_types_are_cleaned_against_the_registry_in_registry_order():
    assert maengel.clean_defect_types(["quality", "nonsense", "packaging", "quality"]) == [
        "packaging",
        "quality",
    ]
    assert [code for code, _label in maengel.DEFECT_TYPES] == [
        "packaging",
        "wrong_item",
        "quantity",
        "quality",
        "other",
    ]


def test_create_anzeige_takes_only_lines_with_qty_and_clamps_it():
    po, _product, line = _received_line(qty=10)
    other = purchasing.add_po_line(po, product=ProductFactory(), qty=4)
    anzeige = maengel.create_anzeige(
        po,
        lines=[
            {"position": line, "qty": 99, "defect_types": ["packaging"], "description": "nass"},
            {"position": other, "qty": 0, "defect_types": ["quality"], "description": ""},
        ],
        actor="anna",
        carrier="DHL Freight",
    )
    assert anzeige.reference.startswith("MA-") and len(anzeige.reference) == 9
    rows = list(anzeige.maengel.all())
    assert len(rows) == 1
    assert rows[0].qty == 10  # кламп по позиции
    assert rows[0].defect_types == ["packaging"]
    assert anzeige.carrier == "DHL Freight" and anzeige.inspected_by == "anna"
    assert anzeige.status == maengel.STATUS_OPEN


def test_anzeige_without_any_line_is_not_created():
    po, _product, line = _received_line()
    assert maengel.create_anzeige(po, lines=[{"position": line, "qty": 0}], actor="") is None


def test_lines_of_another_order_are_ignored():
    po, _product, _line = _received_line()
    _po2, _p2, foreign = _received_line()
    assert maengel.create_anzeige(po, lines=[{"position": foreign, "qty": 2}], actor="") is None


# ───────────────────────────── 3: скидка ─────────────────────────────


def test_discount_books_a_credit_once_and_leaves_stock():
    po, product, line = _received_line(qty=10, cost="2.00")
    anzeige = _anzeige(po, line, qty=3)
    mangel = anzeige.maengel.get()
    assert maengel.resolve(mangel, maengel.DECISION_DISCOUNT, discount=Decimal("4.50"))
    assert not maengel.resolve(mangel, maengel.DECISION_DISCOUNT, discount=Decimal("4.50"))
    product.refresh_from_db()
    assert product.stock_quantity == 10  # склад не тронут
    credit = ExpenseEntry.objects.get(source_ref=f"mangel:{mangel.pk}")
    assert credit.amount == Decimal("-4.50") and credit.supplier_id == po.supplier_id
    mangel.refresh_from_db()
    assert mangel.decision == "discount" and mangel.resolved_at is not None
    assert anzeige.status == maengel.STATUS_DONE


def test_discount_needs_a_positive_amount():
    po, _product, line = _received_line()
    mangel = _anzeige(po, line).maengel.get()
    assert not maengel.resolve(mangel, maengel.DECISION_DISCOUNT, discount=Decimal("0"))
    mangel.refresh_from_db()
    assert mangel.resolved_at is None


# ───────────────────────────── 4: возврат ─────────────────────────────


def test_return_goes_through_erp5_and_records_the_actual_qty():
    po, product, line = _received_line(qty=10, cost="2.00")
    mangel = _anzeige(po, line, qty=3).maengel.get()
    assert maengel.resolve(mangel, maengel.DECISION_RETURN)
    assert not maengel.resolve(mangel, maengel.DECISION_RETURN)  # повтор — ничего
    product.refresh_from_db()
    line.refresh_from_db()
    mangel.refresh_from_db()
    assert product.stock_quantity == 7 and line.qty_returned == 3
    assert mangel.resolved_qty == 3
    mv = StockMovement.objects.filter(product=product, kind="return_supplier")
    assert mv.count() == 1 and mv.first().delta == -3
    assert ExpenseEntry.objects.get(source_ref=f"{line.pk}:ret:3").amount == Decimal("-6.00")


def test_return_is_clamped_by_what_is_left_in_stock():
    po, product, line = _received_line(qty=10)
    product.stock_quantity = 1
    product.save(update_fields=["stock_quantity"])
    mangel = _anzeige(po, line, qty=3).maengel.get()
    assert maengel.resolve(mangel, maengel.DECISION_RETURN)
    mangel.refresh_from_db()
    assert mangel.resolved_qty == 1  # вернулось ровно то, что было на складе


# ───────────────────────────── 5: замена ─────────────────────────────


def test_replacement_reopens_the_line_and_money_adds_up_to_one_payment():
    po, product, line = _received_line(qty=10, cost="2.00")
    assert po.status == Bestellung.STATUS_RECEIVED
    mangel = _anzeige(po, line, qty=4).maengel.get()
    assert maengel.resolve(mangel, maengel.DECISION_REPLACEMENT)
    po.refresh_from_db()
    line.refresh_from_db()
    product.refresh_from_db()
    assert line.qty_replacement == 4 and line.qty_open == 4
    assert not line.is_fully_received
    assert po.status == Bestellung.STATUS_ORDERED and po.received_at is None
    assert product.stock_quantity == 6
    # Ersatzlieferung: приёмка открытого остатка
    assert purchasing.receive_po_line(line) == 4
    po.refresh_from_db()
    product.refresh_from_db()
    assert product.stock_quantity == 10
    assert po.status == Bestellung.STATUS_RECEIVED
    assert _spent(f"{line.pk}:") == Decimal("20.00")  # 10 × 2 € — заплатили один раз
    assert not maengel.resolve(mangel, maengel.DECISION_REPLACEMENT)


def test_without_replacement_line_semantics_are_unchanged():
    _po, _product, line = _received_line(qty=10)
    assert line.qty_replacement == 0
    assert line.qty_open == 0 and line.is_fully_received


# ───────────────────────────── 6: статус ─────────────────────────────


def test_status_is_derived_from_lines_and_open_count_per_order():
    po, _product, line = _received_line(qty=10)
    second = purchasing.add_po_line(po, product=ProductFactory(cost_price=Decimal("1")), qty=5)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(second)
    anzeige = maengel.create_anzeige(
        po,
        lines=[
            {"position": line, "qty": 1, "defect_types": ["packaging"]},
            {"position": second, "qty": 2, "defect_types": ["quantity"]},
        ],
        actor="",
    )
    first, other = list(anzeige.maengel.all())
    maengel.resolve(first, maengel.DECISION_DISCOUNT, discount=Decimal("1"))
    assert anzeige.status == maengel.STATUS_OPEN
    assert maengel.open_counts([po.pk]) == {po.pk: 1}
    maengel.resolve(other, maengel.DECISION_RETURN)
    assert anzeige.status == maengel.STATUS_DONE
    assert maengel.open_counts([po.pk]) == {}


def test_mark_notified_sets_the_date_once():
    po, _product, line = _received_line()
    anzeige = _anzeige(po, line)
    assert anzeige.notified_at is None
    maengel.mark_notified(anzeige)
    first = anzeige.notified_at
    assert first is not None
    maengel.mark_notified(anzeige)
    assert anzeige.notified_at == first
