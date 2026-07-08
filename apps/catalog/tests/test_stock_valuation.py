"""T5: Bestandswert/Marge на модели — stock_value, margin_pct, cost_value-фолбэк."""

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


def test_product_stock_value_and_margin():
    p = ProductFactory(base_price=Decimal("10.00"), stock_quantity=4, cost_price=Decimal("6.00"))
    assert p.stock_value == Decimal("24.00")  # 4 × 6.00
    assert p.margin_pct == 40  # (10−6)/10 = 40 %


def test_product_stock_value_none_when_untracked_or_no_cost():
    # нет остатка → нет Warenwert
    assert ProductFactory(stock_quantity=None, cost_price=Decimal("5.00")).stock_value is None
    # нет EK → нет Warenwert и нет Marge
    p = ProductFactory(stock_quantity=10, cost_price=None)
    assert p.stock_value is None
    assert p.margin_pct is None


def test_margin_none_when_price_zero():
    p = ProductFactory(base_price=Decimal("0.00"), cost_price=Decimal("1.00"))
    assert p.margin_pct is None  # деление на VK=0 не считаем


def test_negative_margin_when_sold_below_cost():
    p = ProductFactory(base_price=Decimal("5.00"), cost_price=Decimal("8.00"))
    assert p.margin_pct == -60  # (5−8)/5 = −60 %


def test_variant_cost_value_falls_back_to_product():
    p = ProductFactory(base_price=Decimal("10.00"), cost_price=Decimal("6.00"))
    # у варианта свой EK — берётся он
    own = ProductVariant.objects.create(
        product=p, label="A", price=Decimal("12.00"), stock_quantity=2, cost_price=Decimal("7.00")
    )
    assert own.cost_value == Decimal("7.00")
    assert own.stock_value == Decimal("14.00")  # 2 × 7
    assert own.margin_pct == 41  # (12−7)/12 = 41.6 → 41
    # у варианта EK не задан — фолбэк на product.cost_price
    fb = ProductVariant.objects.create(
        product=p, label="B", price=Decimal("10.00"), stock_quantity=3, cost_price=None
    )
    assert fb.cost_value == Decimal("6.00")
    assert fb.stock_value == Decimal("18.00")  # 3 × 6


def test_effective_reorder_point_overrides_global():
    p = ProductFactory(stock_quantity=5, reorder_point=None)
    assert p.effective_reorder_point(5) == 5  # фолбэк на глобальный
    p2 = ProductFactory(stock_quantity=5, reorder_point=12)
    assert p2.effective_reorder_point(5) == 12  # per-Artikel перекрывает


# --- форма (T5 поля) --------------------------------------------------------------


def test_product_form_has_t5_fields():
    from apps.catalog.forms import ProductForm

    for f in ("cost_price", "reorder_point", "reorder_target"):
        assert f in ProductForm().fields


def test_product_form_saves_cost_and_reorder():
    from apps.catalog.forms import ProductForm

    form = ProductForm(
        {
            "name_de": "Kaffee",
            "base_price": "9.90",
            "currency": "EUR",
            "cost_price": "5.50",
            "reorder_point": "8",
            "reorder_target": "24",
        }
    )
    assert form.is_valid(), form.errors
    p = form.save()
    assert p.cost_price == Decimal("5.50")
    assert p.reorder_point == 8
    assert p.reorder_target == 24


def test_product_form_rejects_negative_cost():
    from apps.catalog.forms import ProductForm

    form = ProductForm(
        {"name_de": "X", "base_price": "1.00", "currency": "EUR", "cost_price": "-3"}
    )
    assert not form.is_valid()
    assert "cost_price" in form.errors
