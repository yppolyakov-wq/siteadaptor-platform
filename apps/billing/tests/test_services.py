import pytest
import stripe

from apps.billing import services
from apps.billing.plans import modules_for_tier
from apps.billing.state_machine import ACTIVE, PAST_DUE, TRIAL
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_ensure_stripe_customer_creates_and_persists(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="")
    monkeypatch.setattr(stripe.Customer, "create", lambda **kw: {"id": "cus_123"})
    assert services.ensure_stripe_customer(tenant) == "cus_123"
    tenant.refresh_from_db()
    assert tenant.stripe_customer_id == "cus_123"


def test_ensure_stripe_customer_is_idempotent(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="cus_existing")

    def _boom(**kw):
        raise AssertionError("Customer.create must not be called when id exists")

    monkeypatch.setattr(stripe.Customer, "create", _boom)
    assert services.ensure_stripe_customer(tenant) == "cus_existing"


def test_create_checkout_session_returns_url(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="cus_1")
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "https://checkout.stripe/session"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    url = services.create_checkout_session(tenant, success_url="https://s", cancel_url="https://c")
    assert url == "https://checkout.stripe/session"
    assert captured["mode"] == "subscription"
    assert captured["customer"] == "cus_1"
    assert captured["client_reference_id"] == str(tenant.id)


def test_create_billing_portal_session_returns_url(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="cus_1")
    monkeypatch.setattr(
        stripe.billing_portal.Session, "create", lambda **kw: {"url": "https://portal"}
    )
    assert (
        services.create_billing_portal_session(tenant, return_url="https://r") == "https://portal"
    )


def test_activate_subscription_sets_active_and_full_modules():
    tenant = TenantFactory(subscription_status=TRIAL, enabled_modules=["catalog"])
    services.activate_subscription(tenant)
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE
    assert tenant.enabled_modules == modules_for_tier()


def test_mark_past_due_only_from_active():
    active = TenantFactory(subscription_status=ACTIVE)
    services.mark_past_due(active)
    assert active.subscription_status == PAST_DUE

    trial = TenantFactory(subscription_status=TRIAL)
    services.mark_past_due(trial)  # не active → no-op
    assert trial.subscription_status == TRIAL
