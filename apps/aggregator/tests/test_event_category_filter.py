"""R2b: направление (category) в листинге события + фильтр агрегатора по направлению/месяцу."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.aggregator.views import _distinct_event_categories, listings_for
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    return TenantFactory(
        schema_name="public", slug="x", name="X", city="Freiburg", business_type="other", **kw
    )


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "price_cents": 4500,
        "status": Event.STATUS_PUBLISHED,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_event_sync_populates_category_and_city():
    _tenant()
    event = _event(category="yoga", city="Konstanz")
    tasks.sync_event_listing("public", str(event.id))
    listing = AggregatorListing.objects.get(source_ref=str(event.id))
    assert listing.category == "yoga"
    assert listing.city == "Konstanz"  # город события переопределяет город бизнеса


def test_event_sync_falls_back_to_business_city():
    _tenant()
    event = _event(category="meditation")  # без city
    tasks.sync_event_listing("public", str(event.id))
    listing = AggregatorListing.objects.get(source_ref=str(event.id))
    assert listing.city == "Freiburg"  # из тенанта


def test_listings_filter_by_category():
    _tenant()
    yoga = _event(title="Yoga-Tage", category="yoga")
    medi = _event(title="Meditation", category="meditation")
    tasks.sync_event_listing("public", str(yoga.id))
    tasks.sync_event_listing("public", str(medi.id))
    pool = listings_for(category="yoga")
    titles = {listing.title_text for listing in pool}
    assert titles == {"Yoga-Tage"}


def test_listings_filter_by_month():
    _tenant()
    start = timezone.now() + timedelta(days=10)
    soon = _event(title="Bald", starts_at=start, category="yoga")
    _event(title="Spaeter", starts_at=start + timedelta(days=90), category="yoga")
    tasks.reconcile_schema("public")
    pool = listings_for(month=soon.starts_at.strftime("%Y-%m"))
    titles = {listing.title_text for listing in pool}
    assert "Bald" in titles and "Spaeter" not in titles


def test_distinct_event_categories_present_only():
    _tenant()
    tasks.sync_event_listing("public", str(_event(category="yoga").id))
    cats = dict(_distinct_event_categories())
    assert "yoga" in cats and cats["yoga"] == "Yoga"
    assert "ayurveda" not in cats  # нет такого листинга
