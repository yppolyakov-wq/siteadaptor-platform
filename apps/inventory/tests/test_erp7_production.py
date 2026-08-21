"""ERP-7: акт производства v1 — сырьё −, готовое + одной операцией.

Замки по плану `docs/erp57-plan-2026-08-21.md §ERP-7`: fail-closed при
нехватке любой строки сырья (откат ВСЕГО акта), реконсиляция чиста, EK
готового из стоимости сырья, партии: FEFO у сырья + Charge у готового,
расход НЕ пишется (двойной учёт с закупкой).
"""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.finance.expenses import ExpenseEntry
from apps.inventory import services
from apps.inventory.models import Lot, StockMovement
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_produce_moves_both_sides_and_sets_cost():
    flour = ProductFactory(stock_quantity=10, cost_price=Decimal("1.50"))
    butter = ProductFactory(stock_quantity=5, cost_price=Decimal("4.00"))
    bread = ProductFactory(stock_quantity=0, cost_price=None)
    result = services.produce(
        output_product=bread, qty=20, inputs=[(flour, None, 4), (butter, None, 2)]
    )
    flour.refresh_from_db()
    butter.refresh_from_db()
    bread.refresh_from_db()
    assert flour.stock_quantity == 6 and butter.stock_quantity == 3
    assert bread.stock_quantity == 20
    # EK готового = (4×1,50 + 2×4,00) / 20 = 0,70.
    assert result["unit_cost"] == Decimal("0.70")
    assert bread.cost_price == Decimal("0.70")
    assert result["code"].startswith("PR-")
    # Все движения — kind production с общим PR-кодом.
    moves = StockMovement.objects.filter(kind="production")
    assert moves.count() == 3
    assert {m.note for m in moves} == {result["code"]}
    assert {m.source for m in moves} == {"production"}
    # Расход НЕ пишется — сырьё уже оплачено закупкой.
    assert not ExpenseEntry.objects.exists()


def test_produce_shortfall_aborts_whole_act():
    flour = ProductFactory(stock_quantity=10, cost_price=Decimal("1.00"))
    salt = ProductFactory(stock_quantity=1, cost_price=Decimal("0.50"))
    bread = ProductFactory(stock_quantity=0)
    with pytest.raises(services.ProductionError):
        services.produce(output_product=bread, qty=5, inputs=[(flour, None, 4), (salt, None, 3)])
    flour.refresh_from_db()
    salt.refresh_from_db()
    bread.refresh_from_db()
    # Атомарность: мука НЕ списана, готовое НЕ оприходовано.
    assert flour.stock_quantity == 10 and salt.stock_quantity == 1
    assert bread.stock_quantity == 0
    assert not StockMovement.objects.filter(kind="production").exists()


def test_produce_keeps_ledger_reconciled():
    # Фабричный стартовый остаток сам по себе вне леджера — сверяем, что акт
    # НЕ МЕНЯЕТ расхождение (движение = дельте счётчика у обеих сторон).
    flour = ProductFactory(stock_quantity=8, cost_price=Decimal("1.00"))
    bread = ProductFactory(stock_quantity=0, cost_price=Decimal("0.10"))
    before = {r["value"]: r["diff"] for r in services.reconciliation_rows()}
    services.produce(output_product=bread, qty=4, inputs=[(flour, None, 2)])
    after = {r["value"]: r["diff"] for r in services.reconciliation_rows()}
    assert before == after


def test_produce_cost_unknown_keeps_existing_ek():
    flour = ProductFactory(stock_quantity=10, cost_price=None)  # EK сырья неизвестен
    bread = ProductFactory(stock_quantity=0, cost_price=Decimal("0.99"))
    result = services.produce(output_product=bread, qty=5, inputs=[(flour, None, 2)])
    bread.refresh_from_db()
    assert result["unit_cost"] is None and bread.cost_price == Decimal("0.99")


def test_produce_with_lots_fefo_and_output_charge():
    tenant = TenantFactory.build(business_type="bakery", site_config={"lots_enabled": True})
    flour = ProductFactory(stock_quantity=0, cost_price=Decimal("1.00"))
    bread = ProductFactory(stock_quantity=0, cost_price=None)
    services.receive_lot(product=flour, qty=6, lot_code="MEHL-1")
    from datetime import date

    services.produce(
        output_product=bread,
        qty=8,
        inputs=[(flour, None, 4)],
        tenant=tenant,
        mhd=date(2026, 8, 25),
        lot_code="BROT-1",
    )
    assert Lot.objects.get(lot_code="MEHL-1").qty_remaining == 2  # FEFO у сырья
    out_lot = Lot.objects.get(lot_code="BROT-1")
    assert out_lot.qty_remaining == 8 and out_lot.mhd == date(2026, 8, 25)


def test_produce_rejects_output_in_inputs():
    p = ProductFactory(stock_quantity=5)
    with pytest.raises(ValueError):
        services.produce(output_product=p, qty=1, inputs=[(p, None, 1)])


def test_cabinet_production_action():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.inventory.views import stock as stock_view

    flour = ProductFactory(stock_quantity=9, cost_price=Decimal("2.00"))
    bread = ProductFactory(stock_quantity=0)

    class _User:
        is_authenticated = True
        is_active = True
        username = "chef"

    req = RequestFactory().post(
        "/dashboard/stock/",
        {
            "action": "production",
            "prod_output": f"p{bread.pk}",
            "prod_qty": "10",
            "prod_in_1": f"p{flour.pk}",
            "prod_in_qty_1": "3",
            "prod_set_cost": "on",
        },
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(business_type="bakery")
    resp = stock_view(req)
    assert resp.status_code == 302
    flour.refresh_from_db()
    bread.refresh_from_db()
    assert flour.stock_quantity == 6 and bread.stock_quantity == 10
    assert bread.cost_price == Decimal("0.60")  # 3×2,00 / 10
