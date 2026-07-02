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


# --- платежи на connected account (P2.5b/c) -------------------------------


def test_connected_checkout_on_account_no_fee(monkeypatch, settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {}  # вариант B: комиссия 0
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "https://checkout/booking"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    url = connect.connected_checkout_session(
        connect_id="acct_1",
        amount_cents=500,
        product_name="Anzahlung T-1",
        metadata={"kind": "booking_deposit", "booking_id": "b1"},
        success_url="https://s",
        cancel_url="https://c",
        business_type="cafe",
    )
    assert url == "https://checkout/booking"
    assert captured["stripe_account"] == "acct_1"
    assert captured["mode"] == "payment"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 500
    assert captured["metadata"]["kind"] == "booking_deposit"
    assert "application_fee_amount" not in captured["payment_intent_data"]


def test_connected_checkout_includes_fee_when_set(monkeypatch, settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"cafe": "10"}  # вариант A
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "u"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    connect.connected_checkout_session(
        connect_id="acct_1",
        amount_cents=1000,
        product_name="x",
        metadata={},
        success_url="s",
        cancel_url="c",
        business_type="cafe",
    )
    assert captured["payment_intent_data"]["application_fee_amount"] == 100  # 10 % от 1000


def test_refund_calls_stripe_on_account(monkeypatch):
    captured = {}
    monkeypatch.setattr(stripe.Refund, "create", lambda **kw: captured.update(kw))
    connect.refund(connect_id="acct_1", payment_intent="pi_9")
    assert captured == {"payment_intent": "pi_9", "stripe_account": "acct_1"}


# --- E7-3: payment_method_types (платёжный микс DACH) ----------------------


def test_checkout_passes_payment_method_types(monkeypatch, settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {}
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "u"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    connect.connected_checkout_session(
        connect_id="acct_1",
        amount_cents=1000,
        product_name="x",
        metadata={},
        success_url="s",
        cancel_url="c",
        payment_method_types=["card", "paypal", "klarna"],
    )
    assert captured["payment_method_types"] == ["card", "paypal", "klarna"]


def test_checkout_omits_payment_method_types_when_empty(monkeypatch, settings):
    """Пустой список/None → параметр НЕ передаётся (дефолт Stripe Dashboard)."""
    settings.BILLING_APPLICATION_FEE_PERCENT = {}
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "u"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    for empty in ([], None):
        captured.clear()
        connect.connected_checkout_session(
            connect_id="acct_1",
            amount_cents=1000,
            product_name="x",
            metadata={},
            success_url="s",
            cancel_url="c",
            payment_method_types=empty,
        )
        assert "payment_method_types" not in captured
