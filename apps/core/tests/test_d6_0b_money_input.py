"""UX-D D6.0b: один разбор сумм во всех формах кабинета (план ux-d6-0b-money-input)."""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.core import money

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "raw, cents",
    [
        ("12,50", 1250),
        ("12.50", 1250),
        ("1.234,50", 123450),
        ("12,50 €", 1250),
        ("1 299", 129900),
        ("", 0),
        (None, 0),
        ("abc", 0),
        ("NaN", 0),
        ("inf", 0),
        ("1e999", 0),
        ("-5", 0),
        ("1,234", 0),  # тысячи или дробь — не угадываем
        ("2000000", 0),  # выше потолка формы
    ],
)
def test_lenient_cents(raw, cents):
    assert money.lenient_cents(raw) == cents


def test_lenient_cents_custom_cap_and_default():
    assert money.lenient_cents("600", max_value=Decimal("500")) == 0
    assert money.lenient_cents("x", default=-1) == -1


LEGACY_FLOAT = re.compile(r"float\(.*?\.replace\(\s*\",\"")
MODULES = (
    "apps/orders/views.py",
    "apps/stays/form_input.py",
    "apps/events/details.py",
    "apps/booking/views.py",
    "apps/jobs/views.py",
    "apps/loyalty/public_views.py",
)


@pytest.mark.parametrize("path", MODULES)
def test_no_float_money_parsing_left(path):
    text = (ROOT / path).read_text()
    assert not LEGACY_FLOAT.search(text), path


# --- вьюхи: «1.234,50» больше не превращается в 0, мусор не роняет страницу -----------


@pytest.mark.parametrize(
    "module, func",
    [
        ("apps.orders.views", "_eur_to_cents"),
        ("apps.stays.form_input", "_eur_to_cents"),
        ("apps.events.details", "_eur_to_cents"),
        ("apps.booking.views", "_eur_to_cents"),
        ("apps.jobs.views", "_parse_deposit_cents"),
    ],
)
def test_form_helpers_read_german_thousands(module, func):
    import importlib

    helper = getattr(importlib.import_module(module), func)
    assert helper("1.234,50") == 123450
    assert helper("1e999") == 0 and helper("NaN") == 0 and helper("") == 0


def test_booking_helper_keeps_clamp_to_max():
    from apps.booking import views

    assert views._eur_to_cents("500000") == views.MAX_CENTS


@pytest.mark.parametrize(
    "raw, value",
    [
        ("4,90", Decimal("4.90")),
        ("1.234,50", Decimal("1234.50")),
        ("NaN", None),
        ("inf", None),
        ("-1", None),
        ("", None),
    ],
)
def test_catalog_parse_price(raw, value):
    from apps.catalog import views

    assert views._parse_price(raw) == value


@pytest.mark.parametrize(
    "raw, value",
    [
        ("−10", Decimal("-10")),
        ("-2,50", Decimal("-2.50")),
        ("+5", Decimal("5")),
        ("NaN", None),
        ("Infinity", None),
        ("", None),
    ],
)
def test_catalog_parse_signed(raw, value):
    from apps.catalog import views

    assert views._parse_signed(raw) == value
