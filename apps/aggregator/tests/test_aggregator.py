import pytest

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.promotions.models import Promotion
from apps.promotions.state_machine import PromotionSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _public_tenant(**kw):
    # В тестах все приложения SHARED → акции лежат в public; делаем "public"-тенанта,
    # чтобы sync_listing нашёл и акцию (schema_context("public")), и его контакты.
    return TenantFactory(schema_name="public", **kw)


def test_active_promotion_upserts_listing():
    _public_tenant(slug="baeckerei", name="Bäckerei X", city="Hilden", business_type="bakery")
    promo = Promotion.objects.create(status="active", title={"de": "Brötchen -20%"})
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"

    listing = AggregatorListing.objects.get(tenant_schema="public", promo_uuid=promo.id)
    assert listing.city == "Hilden"
    assert listing.business_type == "bakery"
    assert listing.business_name == "Bäckerei X"
    assert listing.is_active is True
    assert listing.detail_url.endswith(f"/p/{promo.id}/")


def test_inactive_promotion_removes_listing():
    _public_tenant(slug="x", name="X")
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    tasks.sync_listing("public", str(promo.id))
    assert AggregatorListing.objects.filter(promo_uuid=promo.id).exists()

    promo.status = "ended"
    promo.save(update_fields=["status"])
    assert tasks.sync_listing("public", str(promo.id)) == "removed"
    assert not AggregatorListing.objects.filter(promo_uuid=promo.id).exists()


def test_sync_is_idempotent():
    _public_tenant(slug="x", name="X")
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    tasks.sync_listing("public", str(promo.id))
    tasks.sync_listing("public", str(promo.id))
    assert AggregatorListing.objects.filter(promo_uuid=promo.id).count() == 1


def test_missing_tenant_keeps_no_listing():
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    assert tasks.sync_listing("public", str(promo.id)) == "removed"
    assert not AggregatorListing.objects.filter(promo_uuid=promo.id).exists()


def test_promotion_sm_active_enqueues_sync(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.sync_aggregator_listing, "delay", lambda **kw: calls.append(kw))
    promo = Promotion.objects.create(status="draft", title={"de": "A"})
    PromotionSM().apply(promo, "active")
    assert calls and calls[0]["promotion_id"] == str(promo.id)
    assert calls[0]["dedupe_key"] == f"agg:{promo.id}:active"
