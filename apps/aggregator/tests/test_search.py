"""P2.7: текстовый поиск + фильтры в выдаче агрегатора (discover_index)."""

import uuid

import pytest
from django.test import RequestFactory

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
        "business_name": "Bäckerei Müller",
        "business_type": "bakery",
        "city": "Hilden",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brötchen -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def test_listings_for_q_matches_name_title_city():
    _listing(business_name="Bäckerei Müller", title={"de": "Brötchen"}, city="Hilden")
    _listing(business_name="Metzgerei Schmidt", title={"de": "Grillpaket"}, city="Köln")
    assert views.listings_for(q="müller").count() == 1  # по названию
    assert views.listings_for(q="grillpaket").count() == 1  # по title (JSON icontains)
    assert views.listings_for(q="hilden").count() == 1  # по городу
    assert views.listings_for(q="zzz").count() == 0


def test_discover_search_filters_results():
    _listing(business_name="Bäckerei Müller", title={"de": "Brötchen"})
    _listing(business_name="Metzgerei Schmidt", title={"de": "Grillpaket"}, city="Köln")
    body = views.discover_index(RequestFactory().get("/entdecken/?q=Müller")).content.decode()
    assert "Bäckerei Müller" in body
    assert "Metzgerei Schmidt" not in body


def test_discover_filter_by_type():
    _listing(business_name="Bäckerei Müller", business_type="bakery")
    _listing(business_name="Metzgerei Schmidt", business_type="butcher", city="Köln")
    body = views.discover_index(RequestFactory().get("/entdecken/?type=butcher")).content.decode()
    assert "Metzgerei Schmidt" in body
    assert "Bäckerei Müller" not in body


def test_discover_no_query_shows_city_index():
    _listing(city="Hilden")
    body = views.discover_index(RequestFactory().get("/entdecken/")).content.decode()
    assert "/entdecken/Hilden/" in body  # чип города (индекс, не результаты поиска)
