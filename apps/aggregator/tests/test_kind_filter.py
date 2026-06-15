"""A5/A6-2: фильтр по виду листинга + скрытие прошедших событий в выдаче."""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "Haus am See",
        "city": "Hilden",
        "title": {"de": "Eintrag"},
        "detail_url": "https://x.siteadaptor.de/x/",
        "is_active": True,
    }
    defaults.update(kw)
    # У stay/event нет promo_uuid → дадим уникальный source_ref, иначе unique-ключ
    # (schema, kind, "") столкнётся при нескольких листингах одного тенанта.
    defaults.setdefault("source_ref", str(uuid.uuid4()))
    return AggregatorListing.objects.create(**defaults)


def test_listings_for_filters_by_kind():
    _listing(listing_kind=AggregatorListing.KIND_PROMOTION, promo_uuid=uuid.uuid4())
    _listing(listing_kind=AggregatorListing.KIND_STAY)
    _listing(
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at=timezone.now() + timedelta(days=2),
    )
    assert views.listings_for(kind=AggregatorListing.KIND_STAY).count() == 1
    assert views.listings_for(kind=AggregatorListing.KIND_EVENT).count() == 1
    assert views.listings_for().count() == 3


def test_listings_for_hides_past_events():
    _listing(
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at=timezone.now() - timedelta(days=1),
        title={"de": "Vorbei"},
    )
    _listing(
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at=timezone.now() + timedelta(days=1),
        title={"de": "Kommt"},
    )
    pool = views.listings_for()
    assert pool.count() == 1
    assert pool.first().title_text == "Kommt"


def test_discover_filter_by_kind():
    _listing(listing_kind=AggregatorListing.KIND_STAY, title={"de": "Doppelzimmer am Meer"})
    _listing(
        listing_kind=AggregatorListing.KIND_PROMOTION,
        promo_uuid=uuid.uuid4(),
        title={"de": "Brötchen Angebot"},
    )
    body = views.discover_index(RequestFactory().get("/entdecken/?kind=stay")).content.decode()
    assert "Doppelzimmer am Meer" in body
    assert "Brötchen Angebot" not in body
    assert "Übernachten" in body  # бейдж вида


def test_discover_bad_kind_ignored():
    _listing(listing_kind=AggregatorListing.KIND_STAY, title={"de": "Zimmer"})
    # мусорный kind → как индекс городов (не падаем, не фильтруем по мусору)
    resp = views.discover_index(RequestFactory().get("/entdecken/?kind=zzz"))
    assert resp.status_code == 200
