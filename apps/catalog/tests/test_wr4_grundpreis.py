"""KA-12 WR-4 (E3.8, PAngV): Grundpreis для m/m²/m³ и проверка «единица без количества»."""

from decimal import Decimal

import pytest

from apps.catalog.forms import ProductForm
from apps.catalog.pricing import grundpreis

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "unit,content,price,expected",
    [
        ("m", "2.5", "10.00", (Decimal("4.00"), "m")),
        ("m2", "1.8", "45.00", (Decimal("25.00"), "m²")),
        ("m3", "0.5", "30.00", (Decimal("60.00"), "m³")),
        ("g", "250", "2.50", (Decimal("10.00"), "kg")),
    ],
)
def test_grundpreis_units(unit, content, price, expected):
    assert grundpreis(Decimal(price), unit, Decimal(content)) == expected


def _data(**over):
    data = {"name_de": "Laminat", "base_price": "45.00", "currency": "EUR"}
    data.update(over)
    return data


def test_unit_without_amount_is_refused():
    form = ProductForm(_data(unit="m2"))
    assert not form.is_valid()
    assert "content_amount" in form.errors
    assert ProductForm(_data(unit="m2", content_amount="1.8")).is_valid()
    assert ProductForm(_data()).is_valid()  # Stück — без количества можно
