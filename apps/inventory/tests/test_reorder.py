"""T5: inventory_value (Warenwert) + reorder_suggestions (Bestellvorschläge)."""

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.inventory import services

pytestmark = pytest.mark.django_db


def test_inventory_value_sums_tracked_entities_with_cost():
    ProductFactory(base_price=Decimal("10"), stock_quantity=4, cost_price=Decimal("6.00"))  # 24
    ProductFactory(base_price=Decimal("5"), stock_quantity=2, cost_price=Decimal("2.50"))  # 5
    ProductFactory(stock_quantity=10, cost_price=None)  # без EK → не в сумме
    ProductFactory(stock_quantity=None, cost_price=Decimal("9"))  # untracked → не в сумме
    val = services.inventory_value()
    assert val["total"] == Decimal("29.00")
    assert len(val["rows"]) == 2


def test_inventory_value_uses_variant_cost_fallback():
    p = ProductFactory(base_price=Decimal("10"), stock_quantity=None, cost_price=Decimal("6.00"))
    ProductVariant.objects.create(product=p, label="A", stock_quantity=3, cost_price=None)  # 3×6=18
    val = services.inventory_value()
    assert val["total"] == Decimal("18.00")


def test_reorder_suggestions_uses_per_item_point_and_target():
    # остаток 3 ≤ Meldebestand 10 → в списке; Vorschlag = Soll 20 − 3 = 17
    ProductFactory(stock_quantity=3, reorder_point=10, reorder_target=20)
    out = services.reorder_suggestions(global_threshold=5)
    assert len(out) == 1
    assert out[0]["counter"] == 3
    assert out[0]["point"] == 10
    assert out[0]["suggest"] == 17


def test_reorder_global_threshold_fallback():
    # без per-item point: остаток 4 ≤ глобальный 5 → попадает; остаток 9 > 5 → нет
    ProductFactory(stock_quantity=4)
    ProductFactory(stock_quantity=9)
    out = services.reorder_suggestions(global_threshold=5)
    assert len(out) == 1
    assert out[0]["counter"] == 4
    assert out[0]["suggest"] is None  # target не задан → без количества


def test_reorder_skips_untracked_and_above_point():
    ProductFactory(stock_quantity=None, reorder_point=10)  # untracked → пропуск
    ProductFactory(stock_quantity=50, reorder_point=10)  # выше порога → пропуск
    assert services.reorder_suggestions(global_threshold=5) == []


def test_reorder_sold_out_first():
    ProductFactory(stock_quantity=4, reorder_point=10)
    ProductFactory(stock_quantity=0, reorder_point=10)
    ProductFactory(stock_quantity=2, reorder_point=10)
    out = services.reorder_suggestions(global_threshold=5)
    # Ausverkauft (0) первым, затем по возрастанию остатка
    assert [r["counter"] for r in out] == [0, 2, 4]
