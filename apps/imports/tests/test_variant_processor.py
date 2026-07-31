"""A1: ProductVariantProcessor — массовый импорт вариантов товара (R1)."""

from decimal import Decimal

import pytest

from apps.catalog.models import Product, ProductVariant
from apps.imports.processors.product import ProductVariantProcessor

pytestmark = pytest.mark.django_db


def _product(sku="BR-1", name="Tee"):
    return Product.objects.create(name={"de": name}, base_price=Decimal("3.00"), sku=sku)


def test_validate_requires_parent_and_label():
    proc = ProductVariantProcessor()
    errors = proc.validate({"product_sku": "", "label": ""})
    assert any("product_sku" in e for e in errors)
    assert any("label" in e for e in errors)


def test_validate_parent_must_exist():
    proc = ProductVariantProcessor()
    errors = proc.validate({"product_sku": "NOPE", "label": "100 g"})
    assert any("parent product not found" in e for e in errors)


def test_validate_passes_with_existing_parent():
    _product(sku="BR-1")
    proc = ProductVariantProcessor()
    assert proc.validate({"product_sku": "BR-1", "label": "100 g"}) == []


def test_create_variant_inherits_price_when_blank():
    _product(sku="BR-1")
    proc = ProductVariantProcessor()
    variant = proc.create_or_update(
        {"product_sku": "BR-1", "label": "100 g", "stock_quantity": "7"},
        update_existing=False,
    )
    assert isinstance(variant, ProductVariant)
    assert variant.price is None  # пусто → наследует base_price
    assert variant.stock_quantity == 7


def test_create_variant_with_price_and_gtin():
    _product(sku="BR-1")
    proc = ProductVariantProcessor()
    variant = proc.create_or_update(
        {"product_sku": "BR-1", "label": "250 g", "price": "5,50", "gtin": "4006381333931"},
        update_existing=False,
    )
    assert variant.price == Decimal("5.50")
    assert variant.gtin == "4006381333931"


def test_reimport_same_label_upserts_not_duplicates():
    _product(sku="BR-1")
    proc = ProductVariantProcessor()
    proc.create_or_update(
        {"product_sku": "BR-1", "label": "100 g", "price": "4.00"}, update_existing=False
    )
    again = proc.create_or_update(
        {"product_sku": "BR-1", "label": "100 g", "price": "4.50"}, update_existing=False
    )
    assert again.price == Decimal("4.50")
    assert ProductVariant.objects.filter(label="100 g").count() == 1


def test_axes_only_row_is_valid_and_label_generated():
    """M4-A: файл может нести только оси — label соберётся моделью."""
    _product(sku="MO-1")
    proc = ProductVariantProcessor()
    assert proc.validate({"product_sku": "MO-1", "size": "M", "color": "Blau"}) == []
    variant = proc.create_or_update(
        {"product_sku": "MO-1", "size": "M", "color": "Blau"}, update_existing=False
    )
    assert (variant.size, variant.color) == ("M", "Blau")
    assert variant.label == "M · Blau"


def test_reimport_by_axes_upserts_not_duplicates():
    """Ловушка 4 плана: повторный импорт тех же осей не плодит варианты."""
    _product(sku="MO-1")
    proc = ProductVariantProcessor()
    proc.create_or_update(
        {"product_sku": "MO-1", "size": "M", "color": "Blau", "price": "39.00"},
        update_existing=False,
    )
    again = proc.create_or_update(
        {"product_sku": "MO-1", "size": "M", "color": "Blau", "price": "29.00"},
        update_existing=False,
    )
    assert again.price == Decimal("29.00")
    assert ProductVariant.objects.filter(product__sku="MO-1").count() == 1


def test_axes_import_upgrades_existing_label_only_variant():
    """Вариант заведён до осей — импорт с осями дополняет его, а не дублирует."""
    product = _product(sku="MO-1")
    ProductVariant.objects.create(product=product, label="M · Blau", price=Decimal("39.00"))
    proc = ProductVariantProcessor()
    variant = proc.create_or_update(
        {"product_sku": "MO-1", "size": "M", "color": "Blau", "stock_quantity": "4"},
        update_existing=False,
    )
    assert ProductVariant.objects.filter(product=product).count() == 1
    assert (variant.size, variant.color, variant.stock_quantity) == ("M", "Blau", 4)


def test_explicit_label_wins_over_generated():
    _product(sku="MO-1")
    proc = ProductVariantProcessor()
    variant = proc.create_or_update(
        {"product_sku": "MO-1", "label": "Sondergröße", "size": "XXL", "color": "Rot"},
        update_existing=False,
    )
    assert variant.label == "Sondergröße"
    assert variant.size == "XXL"


def test_parent_found_by_name_when_no_sku():
    _product(sku="", name="Honig")
    proc = ProductVariantProcessor()
    variant = proc.create_or_update(
        {"product_name_de": "Honig", "label": "500 g"}, update_existing=False
    )
    assert variant.product.name["de"] == "Honig"
