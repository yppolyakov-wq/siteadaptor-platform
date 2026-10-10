"""ТЗ «Siteadaptor 2.0» Phase 0 — быстрые исправления портала (T-8.19a).

План — docs/tz-siteadaptor-2-0-phase0-2026-10-10.md §3: истёкшее не видно сразу,
поиск с лимитом частоты, переключатель языка на портале и /entdecken/.
"""

import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import portal_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def test_expired_listing_is_not_public_before_beat_removes_it():
    now = timezone.now()
    _listing(title={"de": "Läuft"}, ends_at=now + timedelta(hours=1))
    _listing(title={"de": "Ohne Ende"}, ends_at=None)
    _listing(title={"de": "Abgelaufen"}, ends_at=now - timedelta(minutes=1))
    titles = {row.title["de"] for row in AggregatorListing.objects.public()}
    assert titles == {"Läuft", "Ohne Ende"}


@pytest.mark.urls("config.urls_public")
def test_search_is_rate_limited_per_ip(monkeypatch):
    monkeypatch.setattr(views, "SEARCH_RATE_LIMIT", 2)

    def search():
        req = RequestFactory().get("/entdecken/?q=brot", REMOTE_ADDR="10.19.0.1")
        return views.discover_index(req)

    assert search().status_code == 200
    assert search().status_code == 200
    assert search().status_code == 429


@pytest.mark.urls("config.urls_public")
def test_entdecken_offers_language_switch():
    html = views.discover_index(RequestFactory().get("/entdecken/?q=brot")).content.decode()
    assert "/sprache/?lang=ru" in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_offers_language_switch_and_route():
    from django.urls import resolve

    portal = AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "Angebote in Solingen"},
        is_active=True,
    )
    req = RequestFactory().get("/")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "/sprache/?lang=uk" in html
    assert resolve("/sprache/").url_name == "portal-set-language"  # не уходит в <facet>
