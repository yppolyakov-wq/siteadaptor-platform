"""Тесты ProductProcessor: валидация и create_or_update."""

from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.imports.processors.product import ProductProcessor


@pytest.mark.django_db
def test_validate_requires_name_de_and_price():
    proc = ProductProcessor()
    errors = proc.validate({"name_de": "", "base_price": ""})
    assert any("name_de" in e for e in errors)
    assert any("base_price" in e for e in errors)


@pytest.mark.django_db
def test_validate_rejects_bad_price():
    proc = ProductProcessor()
    errors = proc.validate({"name_de": "Brot", "base_price": "abc"})
    assert any("base_price" in e for e in errors)


@pytest.mark.django_db
def test_validate_rejects_negative_price():
    proc = ProductProcessor()
    errors = proc.validate({"name_de": "Brot", "base_price": "-1"})
    assert any("base_price" in e for e in errors)


@pytest.mark.django_db
def test_validate_passes_valid_row():
    proc = ProductProcessor()
    assert proc.validate({"name_de": "Brot", "base_price": "2.50"}) == []


@pytest.mark.django_db
def test_create_builds_i18n_name_and_price():
    proc = ProductProcessor()
    obj = proc.create_or_update(
        {
            "name_de": "Brot",
            "name_en": "Bread",
            "base_price": "2,50",
            "sku": "BR-1",
        },
        update_existing=False,
    )
    assert isinstance(obj, Product)
    assert obj.name == {"de": "Brot", "en": "Bread"}
    assert obj.base_price == Decimal("2.50")
    assert obj.sku == "BR-1"


@pytest.mark.django_db
def test_update_existing_updates_by_sku():
    proc = ProductProcessor()
    first = proc.create_or_update(
        {"name_de": "Alt", "base_price": "1.00", "sku": "SKU-X"},
        update_existing=False,
    )
    second = proc.create_or_update(
        {"name_de": "Neu", "base_price": "3.00", "sku": "SKU-X"},
        update_existing=True,
    )
    assert second.pk == first.pk
    assert second.name["de"] == "Neu"
    assert second.base_price == Decimal("3.00")
    assert Product.objects.filter(sku="SKU-X").count() == 1
