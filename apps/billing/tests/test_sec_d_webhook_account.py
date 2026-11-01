"""SEC-D1/SEC-D2 (аудит безопасности 2026-11-01): вебхук Stripe верит только своему источнику.

Один эндпоинт получает события и платформенного аккаунта (подписка, featured), и
connected-аккаунтов бизнесов (оплаты сделок). Раньше `event.account` сверялся только у
`deal_balance` — владелец с подключённым Stripe мог создать Checkout у СЕБЯ с чужой
metadata и активировать подписку, отметить чужой заказ оплаченным или получить featured
на 10 лет. Второй замок: пустой `STRIPE_WEBHOOK_SECRET` принимал любую подпись
(HMAC с пустым ключом) — теперь 503.
"""

import uuid

import pytest
from django.test import RequestFactory

from apps.aggregator.models import AggregatorListing
from apps.billing import webhooks
from apps.billing.state_machine import ACTIVE, TRIAL
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _order_event(schema, order_id="11111111-1111-1111-1111-111111111111"):
    return {
        "payment_intent": "pi_x",
        "payment_status": "paid",
        "metadata": {"kind": "order_payment", "tenant_schema": schema, "order_id": order_id},
    }


@pytest.fixture
def paid_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.orders.payments.mark_order_paid", lambda **kw: calls.append(kw) or True
    )
    return calls


def test_connect_kind_without_account_is_dropped(paid_calls):
    TenantFactory(schema_name="biz_a", stripe_connect_id="acct_a")
    webhooks.handle_event("checkout.session.completed", _order_event("biz_a"), account="")
    assert paid_calls == []


def test_connect_kind_from_foreign_account_is_dropped(paid_calls):
    TenantFactory(schema_name="biz_a", stripe_connect_id="acct_a")
    webhooks.handle_event("checkout.session.completed", _order_event("biz_a"), account="acct_evil")
    assert paid_calls == []


def test_connect_kind_from_own_account_is_applied(paid_calls):
    TenantFactory(schema_name="biz_a", stripe_connect_id="acct_a")
    webhooks.handle_event("checkout.session.completed", _order_event("biz_a"), account="acct_a")
    assert len(paid_calls) == 1


def test_connect_kind_unknown_schema_is_dropped(paid_calls):
    webhooks.handle_event("checkout.session.completed", _order_event("nope"), account="acct_a")
    assert paid_calls == []


def test_subscription_event_from_connected_account_is_ignored():
    tenant = TenantFactory(subscription_status=TRIAL)
    webhooks.handle_event(
        "checkout.session.completed",
        {"client_reference_id": str(tenant.id), "metadata": {}},
        account="acct_attacker",
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == TRIAL


def test_past_due_from_connected_account_is_ignored():
    tenant = TenantFactory(subscription_status=ACTIVE)
    webhooks.handle_event(
        "invoice.payment_failed",
        {"metadata": {"tenant_id": str(tenant.id)}},
        account="acct_attacker",
    )
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE


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


def _featured(promo_uuid, days):
    return {
        "payment_intent": "pi_f",
        "payment_status": "paid",
        "metadata": {
            "kind": "featured",
            "tenant_schema": "shop1",
            "promo_uuid": str(promo_uuid),
            "days": str(days),
        },
    }


def test_featured_from_connected_account_is_ignored():
    promo_uuid = uuid.uuid4()
    listing = _listing(promo_uuid)
    webhooks.handle_event("checkout.session.completed", _featured(promo_uuid, 7), account="acct_x")
    listing.refresh_from_db()
    assert not listing.is_featured_now


def test_featured_days_outside_price_table_is_ignored():
    promo_uuid = uuid.uuid4()
    listing = _listing(promo_uuid)
    webhooks.handle_event("checkout.session.completed", _featured(promo_uuid, 3650))
    listing.refresh_from_db()
    assert not listing.is_featured_now


def test_account_updated_must_match_event_account():
    tenant = TenantFactory(stripe_connect_id="acct_9", payments_enabled=False)
    webhooks.handle_event(
        "account.updated", {"id": "acct_9", "charges_enabled": True}, account="acct_other"
    )
    tenant.refresh_from_db()
    assert tenant.payments_enabled is False
    webhooks.handle_event(
        "account.updated", {"id": "acct_9", "charges_enabled": True}, account="acct_9"
    )
    tenant.refresh_from_db()
    assert tenant.payments_enabled is True


def test_webhook_without_secret_refuses(settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    request = RequestFactory().post(
        "/stripe/webhook/", data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="x"
    )
    assert webhooks.stripe_webhook(request).status_code == 503


def test_deploy_check_requires_secret_in_live_mode(settings):
    from apps.billing import checks

    settings.STRIPE_LIVE_MODE = True
    settings.STRIPE_WEBHOOK_SECRET = ""
    assert [e.id for e in checks.stripe_webhook_secret_set(None)] == ["billing.E001"]
    settings.STRIPE_WEBHOOK_SECRET = "whsec_abc"
    assert checks.stripe_webhook_secret_set(None) == []
