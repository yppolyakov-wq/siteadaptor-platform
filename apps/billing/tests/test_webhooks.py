import uuid

import pytest
import stripe
from django.core.cache import cache
from django.test import RequestFactory

from apps.aggregator.models import AggregatorListing
from apps.billing import webhooks
from apps.billing.state_machine import ACTIVE, PAST_DUE, TRIAL
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _listing(promo_uuid, schema="shop1"):
    return AggregatorListing.objects.create(
        tenant_schema=schema,
        tenant_slug="x",
        business_name="X",
        promo_uuid=promo_uuid,
        title={"de": "Brot"},
        detail_url="https://x.siteadaptor.de/p/1/",
        is_active=True,
    )


def test_resolve_tenant_by_customer_id():
    tenant = TenantFactory(stripe_customer_id="cus_a")
    assert webhooks._tenant_from_object({"customer": "cus_a"}) == tenant


def test_resolve_tenant_by_metadata():
    tenant = TenantFactory(stripe_customer_id="")
    assert webhooks._tenant_from_object({"metadata": {"tenant_id": str(tenant.id)}}) == tenant


def test_resolve_tenant_by_client_reference_id():
    tenant = TenantFactory(stripe_customer_id="")
    assert webhooks._tenant_from_object({"client_reference_id": str(tenant.id)}) == tenant


def test_checkout_completed_activates():
    tenant = TenantFactory(subscription_status=TRIAL, stripe_customer_id="cus_x")
    webhooks.handle_event("checkout.session.completed", {"customer": "cus_x"})
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE


def test_payment_failed_marks_past_due():
    tenant = TenantFactory(subscription_status=ACTIVE, stripe_customer_id="cus_x")
    webhooks.handle_event("invoice.payment_failed", {"customer": "cus_x"})
    tenant.refresh_from_db()
    assert tenant.subscription_status == PAST_DUE


def test_subscription_deleted_marks_past_due():
    tenant = TenantFactory(subscription_status=ACTIVE, stripe_customer_id="cus_x")
    webhooks.handle_event(
        "customer.subscription.deleted", {"customer": "cus_x", "status": "canceled"}
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == PAST_DUE


def test_subscription_updated_active_sets_ends_at():
    tenant = TenantFactory(subscription_status=PAST_DUE, stripe_customer_id="cus_x")
    webhooks.handle_event(
        "customer.subscription.updated",
        {"customer": "cus_x", "status": "active", "current_period_end": 1893456000},
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE
    assert tenant.subscription_ends_at is not None


def test_unknown_tenant_is_noop():
    # не должно падать — просто лог + выход
    webhooks.handle_event("invoice.payment_failed", {"customer": "cus_missing"})


# --- P2.4b: featured (разовый платёж) -------------------------------------


def test_featured_checkout_sets_featured_until():
    promo_uuid = uuid.uuid4()
    listing = _listing(promo_uuid)
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "metadata": {
                "kind": "featured",
                "tenant_schema": "shop1",
                "promo_uuid": str(promo_uuid),
                "days": "7",
            }
        },
    )
    listing.refresh_from_db()
    assert listing.is_featured_now


def test_featured_checkout_does_not_touch_subscription():
    """Разовый featured-платёж не активирует подписку (статус не трогаем)."""
    tenant = TenantFactory(subscription_status=TRIAL, stripe_customer_id="cus_x")
    promo_uuid = uuid.uuid4()
    _listing(promo_uuid)
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "customer": "cus_x",
            "metadata": {
                "kind": "featured",
                "tenant_schema": "shop1",
                "promo_uuid": str(promo_uuid),
                "days": "7",
            },
        },
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == TRIAL  # подписка не активирована


def test_featured_checkout_missing_listing_is_noop():
    # листинга нет (акция завершилась) — не падаем
    webhooks.handle_event(
        "checkout.session.completed",
        {
            "metadata": {
                "kind": "featured",
                "tenant_schema": "gone",
                "promo_uuid": str(uuid.uuid4()),
                "days": "7",
            }
        },
    )
    assert not AggregatorListing.objects.filter(featured_until__isnull=False).exists()


def test_subscription_checkout_without_kind_still_activates():
    """Регрессия: подписочный checkout (без metadata.kind) активирует как раньше."""
    tenant = TenantFactory(subscription_status=TRIAL, stripe_customer_id="cus_sub")
    webhooks.handle_event(
        "checkout.session.completed",
        {"customer": "cus_sub", "metadata": {"tenant_id": str(tenant.id)}},
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE


def test_webhook_view_verifies_dispatches_and_dedupes(monkeypatch):
    tenant = TenantFactory(subscription_status=TRIAL, stripe_customer_id="cus_x")
    event = {
        "id": "evt_dedup_unit",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_x"}},
    }
    cache.delete("stripe_evt:evt_dedup_unit")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda payload, sig, secret: event)

    rf = RequestFactory()
    request = rf.post(
        "/stripe/webhook/", data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="x"
    )
    resp = webhooks.stripe_webhook(request)
    assert resp.status_code == 200
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE

    # повтор того же event.id — идемпотентный no-op (200), статус не меняется
    resp2 = webhooks.stripe_webhook(
        rf.post(
            "/stripe/webhook/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="x",
        )
    )
    assert resp2.status_code == 200
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE
