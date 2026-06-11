"""P2.2a: OpenGraph + canonical на страницах агрегатора + перелинковка сети.

Паттерн прежний: вьюхи напрямую через RequestFactory, портал — руками в
request.portal, ROOT_URLCONF под нужный urlconf для reverse в шаблонах.
"""

import uuid

import pytest
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Hilden",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _portal(**kw):
    defaults = {
        "host": "muenchen.siteadaptor.de",
        "kind": "city",
        "city": "München",
        "title": {"de": "Angebote München"},
        "tagline": {"de": "Lokale Deals"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


# --- городская страница основного домена --------------------------------------


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_has_canonical_and_og():
    _listing(city="Hilden")
    req = RequestFactory().get("/entdecken/Hilden/", HTTP_HOST="siteadaptor.de")
    body = views.city_listing(req, "Hilden").content.decode()
    assert '<link rel="canonical" href="http://siteadaptor.de/entdecken/Hilden/">' in body
    assert 'property="og:title"' in body
    assert 'property="og:url"' in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_links_other_cities():
    _listing(city="Hilden")
    _listing(city="Köln")
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert "/entdecken/K%C3%B6ln/" in body or "Köln" in body
    assert "Hilden</a>" not in body.split("Offers in other cities")[-1]  # сам город — не в блоке


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_links_city_portal_when_exists():
    _portal(city="Hilden", host="hilden.siteadaptor.de", title={"de": "Angebote Hilden"})
    _listing(city="Hilden")
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert "://hilden.siteadaptor.de/" in body
    assert "All offers in one place" in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_no_portal_block_without_portal():
    _listing(city="Hilden")
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert "All offers in one place" not in body


# --- портал --------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_home_has_og_tags():
    p = _portal(logo_url="https://cdn.example.com/logo.png")
    req = RequestFactory().get("/", HTTP_HOST=p.host)
    req.portal = p
    body = portal_views.portal_home(req).content.decode()
    assert '<meta property="og:title" content="Angebote München">' in body
    assert '<meta property="og:description" content="Lokale Deals">' in body
    assert f'<meta property="og:url" content="http://{p.host}/">' in body
    assert '<meta property="og:image" content="https://cdn.example.com/logo.png">' in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_home_links_other_portals():
    p = _portal()
    _portal(host="koeln.siteadaptor.de", city="Köln", title={"de": "Angebote Köln"})
    _portal(host="aus.siteadaptor.de", city="Weg", title={"de": "Weg"}, is_active=False)
    req = RequestFactory().get("/", HTTP_HOST=p.host)
    req.portal = p
    body = portal_views.portal_home(req).content.decode()
    assert "More local portals" in body
    assert "://koeln.siteadaptor.de/" in body
    assert "aus.siteadaptor.de" not in body  # неактивные — мимо
    # себя не линкуем: свой хост встречается только в head (canonical/og:url)
    assert body.split("More local portals")[-1].count(p.host) == 0


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_home_no_block_when_single_portal():
    p = _portal()
    req = RequestFactory().get("/", HTTP_HOST=p.host)
    req.portal = p
    body = portal_views.portal_home(req).content.decode()
    assert "More local portals" not in body
