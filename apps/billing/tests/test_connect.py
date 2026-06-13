"""P2.5: application fee по типу бизнеса + Connect-онбординг (OAuth) и статус."""

from decimal import Decimal

import pytest
import stripe

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


# --- Connect onboarding (Standard, OAuth) ---------------------------------


def test_is_connect_configured(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = ""
    settings.STRIPE_CONNECT_CLIENT_ID = ""
    assert connect.is_connect_configured() is False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_x"
    assert connect.is_connect_configured() is True


def test_oauth_authorize_url(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    url = connect.oauth_authorize_url(state="s1", redirect_uri="https://app/cb")
    assert url.startswith("https://connect.stripe.com/oauth/authorize?")
    assert "client_id=ca_test" in url
    assert "state=s1" in url
    assert "redirect_uri=https%3A%2F%2Fapp%2Fcb" in url
    assert "scope=read_write" in url


def test_complete_oauth_returns_account_id(monkeypatch):
    monkeypatch.setattr(stripe.OAuth, "token", lambda **kw: {"stripe_user_id": "acct_123"})
    assert connect.complete_oauth("code_abc") == "acct_123"


@pytest.mark.django_db
def test_set_connect_status_updates_tenant():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(stripe_connect_id="acct_1", payments_enabled=False)
    assert connect.set_connect_status("acct_1", True) is True
    t.refresh_from_db()
    assert t.payments_enabled is True


@pytest.mark.django_db
def test_set_connect_status_unknown_account_is_noop():
    assert connect.set_connect_status("acct_missing", True) is False
    assert connect.set_connect_status("", True) is False
