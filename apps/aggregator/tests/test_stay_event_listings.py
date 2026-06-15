"""A5/A6: date-range листинги (размещение/события) в агрегаторе."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.events.models import Event
from apps.promotions.models import Promotion
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory(
        schema_name="public", slug="x", name="X", city="Hilden", business_type="hotel"
    )


# --- stays --------------------------------------------------------------------


def test_sync_stay_listing_upsert_and_remove():
    _tenant()
    unit = StayUnit.objects.create(name="Doppelzimmer", price_cents=8900, is_active=True)

    assert tasks.sync_stay_listing("public", str(unit.id)) == "upserted"
    listing = AggregatorListing.objects.get(
        listing_kind=AggregatorListing.KIND_STAY, source_ref=str(unit.id)
    )
    assert listing.title_text == "Doppelzimmer"
    assert listing.new_price == pytest.approx(89.0)
    assert listing.promo_uuid is None
    assert listing.detail_url.endswith(f"/unterkunft/{unit.id}/")
    assert listing.starts_at is None

    # деактивация → листинг удаляется
    unit.is_active = False
    unit.save(update_fields=["is_active"])
    assert tasks.sync_stay_listing("public", str(unit.id)) == "removed"
    assert not AggregatorListing.objects.filter(source_ref=str(unit.id)).exists()


def test_stay_not_listed_when_module_disabled():
    tenant = _tenant()
    tenant.disabled_modules = ["stays"]
    tenant.save(update_fields=["disabled_modules"])
    unit = StayUnit.objects.create(name="Zimmer", price_cents=5000, is_active=True)

    assert tasks.sync_stay_listing("public", str(unit.id)) == "removed"
    assert not AggregatorListing.objects.filter(source_ref=str(unit.id)).exists()


# --- events -------------------------------------------------------------------


def test_sync_event_listing_published_future():
    _tenant()
    event = Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        price_cents=4500,
        status=Event.STATUS_PUBLISHED,
    )

    assert tasks.sync_event_listing("public", str(event.id)) == "upserted"
    listing = AggregatorListing.objects.get(
        listing_kind=AggregatorListing.KIND_EVENT, source_ref=str(event.id)
    )
    assert listing.title_text == "Yoga-Retreat"
    assert listing.new_price == pytest.approx(45.0)
    assert listing.starts_at is not None
    assert listing.detail_url.endswith(f"/veranstaltung/{event.id}/")


def test_event_not_listed_when_draft_or_past():
    _tenant()
    draft = Event.objects.create(
        title="Entwurf", starts_at=timezone.now() + timedelta(days=5), status=Event.STATUS_DRAFT
    )
    past = Event.objects.create(
        title="Vorbei",
        starts_at=timezone.now() - timedelta(days=1),
        status=Event.STATUS_PUBLISHED,
    )
    assert tasks.sync_event_listing("public", str(draft.id)) == "removed"
    assert tasks.sync_event_listing("public", str(past.id)) == "removed"
    assert not AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_EVENT).exists()


# --- reconcile + общий пул ----------------------------------------------------


def test_reconcile_covers_all_kinds_and_prunes():
    _tenant()
    Promotion.objects.create(status="active", title={"de": "Angebot"})
    StayUnit.objects.create(name="Zimmer", price_cents=7000, is_active=True)
    Event.objects.create(
        title="Konzert",
        starts_at=timezone.now() + timedelta(days=3),
        status=Event.STATUS_PUBLISHED,
    )
    # устаревший листинг события (источника уже нет) — должен исчезнуть
    AggregatorListing.objects.create(
        tenant_schema="public",
        tenant_slug="x",
        business_name="X",
        listing_kind=AggregatorListing.KIND_EVENT,
        source_ref="00000000-0000-0000-0000-000000000000",
        title={"de": "Geist"},
        detail_url="https://x.siteadaptor.de/veranstaltung/x/",
    )

    n = tasks.reconcile_schema("public")

    assert n == 3  # 1 акция + 1 размещение + 1 событие
    kinds = set(
        AggregatorListing.objects.filter(tenant_schema="public").values_list(
            "listing_kind", flat=True
        )
    )
    assert kinds == {"promotion", "stay", "event"}
    assert not AggregatorListing.objects.filter(title__de="Geist").exists()


def test_listings_for_returns_all_kinds_together():
    from apps.aggregator.views import listings_for

    _tenant()
    Promotion.objects.create(status="active", title={"de": "Angebot"})
    StayUnit.objects.create(name="Zimmer", price_cents=7000, is_active=True)
    Event.objects.create(
        title="Konzert",
        starts_at=timezone.now() + timedelta(days=3),
        status=Event.STATUS_PUBLISHED,
    )
    tasks.reconcile_schema("public")

    pool = listings_for(city="Hilden")
    assert pool.count() == 3
