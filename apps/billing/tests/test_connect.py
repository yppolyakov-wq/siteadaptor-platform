"""P2.5: конфиг application fee по типу бизнеса (дефолт 0, настройка существует)."""

from decimal import Decimal

from apps.billing import connect


def test_default_fee_is_zero_for_any_type(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {}
    assert connect.application_fee_percent("bakery") == Decimal(0)
    assert connect.application_fee_percent("hotel") == Decimal(0)
    assert connect.application_fee_percent("") == Decimal(0)


def test_per_business_type_override(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"hotel": "3", "tour_operator": "5.5"}
    assert connect.application_fee_percent("hotel") == Decimal("3")
    assert connect.application_fee_percent("tour_operator") == Decimal("5.5")
    assert connect.application_fee_percent("bakery") == Decimal(0)  # не задан → 0


def test_wildcard_default_applies_to_all(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"": "2"}
    assert connect.application_fee_percent("bakery") == Decimal("2")
    assert connect.application_fee_percent("hotel") == Decimal("2")


def test_specific_type_overrides_wildcard(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"": "2", "hotel": "5"}
    assert connect.application_fee_percent("hotel") == Decimal("5")
    assert connect.application_fee_percent("cafe") == Decimal("2")


def test_negative_clamped_to_zero(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"hotel": "-1"}
    assert connect.application_fee_percent("hotel") == Decimal(0)


def test_fee_cents_zero_when_percent_zero(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {}
    assert connect.application_fee_cents(10000, "bakery") == 0


def test_fee_cents_computed_and_floored(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"hotel": "3"}
    assert connect.application_fee_cents(10000, "hotel") == 300  # 3 % от 100,00 €
    # округление вниз: 3 % от 1,01 € = 3,03 ct → 3
    assert connect.application_fee_cents(101, "hotel") == 3


def test_fee_cents_zero_for_nonpositive_amount(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"hotel": "3"}
    assert connect.application_fee_cents(0, "hotel") == 0
