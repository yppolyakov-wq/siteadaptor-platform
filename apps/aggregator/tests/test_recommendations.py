"""P2.7+: рекомендации «Endet bald» в выдаче агрегатора."""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import recommendations, views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "Laden",
        "city": "Hilden",
        "title": {"de": "Eintrag"},
        "detail_url": "https://x.siteadaptor.de/x/",
        "is_active": True,
    }
    defaults.update(kw)
    defaults.setdefault("source_ref", str(uuid.uuid4()))
    return AggregatorListing.objects.create(**defaults)


def test_ending_soon_picks_urgent_and_orders():
    now = timezone.now()
    promo_soon = _listing(
        listing_kind=AggregatorListing.KIND_PROMOTION,
        promo_uuid=uuid.uuid4(),
        ends_at=now + timedelta(days=2),
        title={"de": "Bald vorbei"},
    )
    event_sooner = _listing(
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at=now + timedelta(hours=12),
        title={"de": "Heute Abend"},
    )
    # вне окна / без даты — не должны попасть
    _listing(
        listing_kind=AggregatorListing.KIND_PROMOTION,
        promo_uuid=uuid.uuid4(),
        ends_at=now + timedelta(days=10),
        title={"de": "Noch lange"},
    )
    _listing(listing_kind=AggregatorListing.KIND_STAY, title={"de": "Zimmer"})

    items = recommendations.ending_soon(days=3)
    titles = [it.title_text for it in items]
    assert titles == ["Heute Abend", "Bald vorbei"]  # по срочности
    assert promo_soon in items and event_sooner in items


def test_discover_index_shows_ending_soon_rail():
    _listing(
        listing_kind=AggregatorListing.KIND_PROMOTION,
        promo_uuid=uuid.uuid4(),
        ends_at=timezone.now() + timedelta(days=1),
        title={"de": "Letzte Chance"},
    )
    body = views.discover_index(RequestFactory().get("/entdecken/")).content.decode()
    assert "Ending soon" in body
    assert "Letzte Chance" in body
