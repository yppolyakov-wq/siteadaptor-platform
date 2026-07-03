"""P2.4b: самообслуживание featured-продвижения — планы, Checkout, применение."""

import uuid
from datetime import timedelta

import pytest
import stripe
from django.utils import timezone

from apps.aggregator.models import AggregatorListing
from apps.billing import featured, services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


# --- планы / конфиг -------------------------------------------------------


def test_default_plans():
    plans = featured.get_plans()
    assert [p.days for p in plans] == [7, 14, 30]
    assert featured.get_plan(7).amount_cents == 900
    assert featured.get_plan(14).amount_cents == 1500
    assert featured.get_plan(30).amount_cents == 2500
    assert featured.get_plan(99) is None  # поддельный ?days=


def test_amount_eur_formatting():
    assert featured.FeaturedPlan(7, 900).amount_eur == "9 €"
    assert featured.FeaturedPlan(30, 2500).amount_eur == "25 €"
    assert featured.FeaturedPlan(7, 950).amount_eur == "9,50 €"


def test_env_override_prices(settings):
    settings.BILLING_FEATURED_PRICES = {"30": "1999"}
    plans = featured.get_plans()
    assert [(p.days, p.amount_cents) for p in plans] == [(30, 1999)]


def test_is_enabled_requires_stripe_key(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = ""
    assert featured.is_enabled() is False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    assert featured.is_enabled() is True


# --- Checkout-сессия (mode=payment) ---------------------------------------


def test_create_featured_checkout_builds_payment_session(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="cus_1", schema_name="shop1")
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "https://checkout/featured"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    promo_id = str(uuid.uuid4())
    url = services.create_featured_checkout_session(
        tenant,
        promo_uuid=promo_id,
        days=14,
        title="Brot -20%",
        success_url="https://s",
        cancel_url="https://c",
    )
    assert url == "https://checkout/featured"
    assert captured["mode"] == "payment"
    assert captured["customer"] == "cus_1"
    assert captured["client_reference_id"] == str(tenant.id)
    meta = captured["metadata"]
    assert meta["kind"] == "featured"
    assert meta["promo_uuid"] == promo_id
    assert meta["tenant_schema"] == "shop1"
    assert meta["days"] == "14"
    price_data = captured["line_items"][0]["price_data"]
    assert price_data["unit_amount"] == 1500
    assert price_data["currency"] == "eur"


def test_create_featured_checkout_rejects_unknown_plan(monkeypatch):
    tenant = TenantFactory(stripe_customer_id="cus_1")
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: {"url": "x"})
    with pytest.raises(ValueError):
        services.create_featured_checkout_session(
            tenant,
            promo_uuid=str(uuid.uuid4()),
            days=99,
            title="X",
            success_url="https://s",
            cancel_url="https://c",
        )


# --- применение покупки к листингу ----------------------------------------


def test_apply_featured_sets_until_from_now():
    listing = _listing()
    before = timezone.now()
    ok = services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema, promo_uuid=str(listing.promo_uuid), days=7
    )
    assert ok is True
    listing.refresh_from_db()
    delta = listing.featured_until - before
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_apply_featured_extends_from_existing_future():
    until = timezone.now() + timedelta(days=5)
    listing = _listing(featured_until=until)
    services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema, promo_uuid=str(listing.promo_uuid), days=7
    )
    listing.refresh_from_db()
    # продлено от будущей даты (≈12 дней), а не сброшено к now+7
    assert listing.featured_until > until + timedelta(days=6)


def test_apply_featured_ignores_expired_base():
    past = timezone.now() - timedelta(days=2)
    listing = _listing(featured_until=past)
    before = timezone.now()
    services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema, promo_uuid=str(listing.promo_uuid), days=7
    )
    listing.refresh_from_db()
    # истёкший срок — считаем от now, не от прошлого
    assert listing.featured_until > before + timedelta(days=6)


def test_apply_featured_same_payment_ref_is_idempotent():
    # реплей того же платежа (напр. потеря Redis-дедупа) не продлевает срок повторно
    listing = _listing()
    ok1 = services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema,
        promo_uuid=str(listing.promo_uuid),
        days=7,
        payment_ref="pi_123",
    )
    assert ok1 is True
    listing.refresh_from_db()
    until_after_first = listing.featured_until
    ok2 = services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema,
        promo_uuid=str(listing.promo_uuid),
        days=7,
        payment_ref="pi_123",
    )
    assert ok2 is False  # тот же платёж — no-op
    listing.refresh_from_db()
    assert listing.featured_until == until_after_first  # срок не сдвинулся


def test_apply_featured_different_payment_ref_extends():
    # новый платёж (другой payment_intent) — легитимно продлевает
    listing = _listing()
    services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema,
        promo_uuid=str(listing.promo_uuid),
        days=7,
        payment_ref="pi_a",
    )
    listing.refresh_from_db()
    first = listing.featured_until
    ok = services.apply_featured_purchase(
        tenant_schema=listing.tenant_schema,
        promo_uuid=str(listing.promo_uuid),
        days=7,
        payment_ref="pi_b",
    )
    assert ok is True
    listing.refresh_from_db()
    assert listing.featured_until > first  # второй платёж продлил


def test_apply_featured_missing_listing_is_noop():
    ok = services.apply_featured_purchase(
        tenant_schema="nope", promo_uuid=str(uuid.uuid4()), days=7
    )
    assert ok is False


def test_apply_featured_rejects_nonpositive_days():
    listing = _listing()
    assert (
        services.apply_featured_purchase(
            tenant_schema=listing.tenant_schema, promo_uuid=str(listing.promo_uuid), days=0
        )
        is False
    )


# --- D2.4: generic-адресация (listing_kind, source_ref) --------------------


def test_apply_featured_by_kind_and_source_ref():
    listing = _listing(
        promo_uuid=None,
        listing_kind=AggregatorListing.KIND_STAY,
        source_ref="unit-1",
    )
    ok = services.apply_featured_purchase(
        tenant_schema="t1",
        listing_kind=AggregatorListing.KIND_STAY,
        source_ref="unit-1",
        days=7,
    )
    assert ok is True
    listing.refresh_from_db()
    assert listing.featured_until is not None


def test_apply_featured_without_any_key_is_noop():
    _listing()
    assert services.apply_featured_purchase(tenant_schema="t1", days=7) is False


def test_checkout_requires_some_listing_key(monkeypatch):
    monkeypatch.setattr(services, "ensure_stripe_customer", lambda t: "cus_x")
    tenant = TenantFactory.build(schema_name="t1")
    with pytest.raises(ValueError):
        services.create_featured_checkout_session(
            tenant, days=7, title="X", success_url="s", cancel_url="c"
        )


def test_checkout_metadata_carries_kind_and_ref(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    monkeypatch.setattr(services, "ensure_stripe_customer", lambda t: "cus_x")
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "https://stripe.test/session"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    tenant = TenantFactory.build(schema_name="t1")
    url = services.create_featured_checkout_session(
        tenant,
        listing_kind=AggregatorListing.KIND_EVENT,
        source_ref="ev-9",
        days=7,
        title="Konzert",
        success_url="s",
        cancel_url="c",
    )
    assert url == "https://stripe.test/session"
    assert captured["metadata"]["listing_kind"] == AggregatorListing.KIND_EVENT
    assert captured["metadata"]["source_ref"] == "ev-9"
    assert captured["metadata"]["kind"] == "featured"
