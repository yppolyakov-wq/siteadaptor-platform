"""Тесты P2.1c: SEO портала — canonical, CollectionPage JSON-LD, sitemap/robots.

Паттерн test_seo.py: вьюхи напрямую через RequestFactory (HTTP_HOST = хост
портала, request.portal руками), ROOT_URLCONF=config.urls_portal для reverse.
"""

import uuid

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db

_HOST = "muenchen.siteadaptor.de"


def _portal(**kw):
    defaults = {
        "host": _HOST,
        "kind": "city",
        "city": "München",
        "title": {"de": "Angebote München"},
        "tagline": {"de": "Lokale Deals täglich"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "München",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(portal, path="/"):
    req = RequestFactory().get(path, HTTP_HOST=portal.host if portal else _HOST)
    req.portal = portal
    return req


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_home_has_canonical_and_meta_description():
    p = _portal()
    body = portal_views.portal_home(_get(p)).content.decode()
    assert f'<link rel="canonical" href="http://{_HOST}/">' in body
    assert "Lokale Deals täglich" in body  # meta description из tagline


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_meta_description_falls_back_to_intro():
    p = _portal(tagline={}, intro={"de": "Интро портала"})
    body = portal_views.portal_home(_get(p)).content.decode()
    assert "Интро портала" in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_home_emits_collectionpage_jsonld():
    p = _portal()
    _listing(title={"de": "AktivesAngebot"})
    body = portal_views.portal_home(_get(p)).content.decode()
    assert 'type="application/ld+json"' in body
    assert '"@type":"CollectionPage"' in body
    assert '"@type":"ItemList"' in body
    assert "AktivesAngebot" in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_facet_canonical_points_to_facet_url():
    p = _portal()
    _listing(business_type="bakery")
    body = portal_views.portal_home(_get(p, "/bakery/"), facet="bakery").content.decode()
    assert f'<link rel="canonical" href="http://{_HOST}/bakery/">' in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_sitemap_lists_home_and_facets():
    p = _portal()
    _listing(business_type="bakery")
    _listing(business_type="butcher")
    _listing(business_type="cafe", is_active=False)  # неактивные — мимо
    _listing(business_type="grocery", city="Köln")  # чужой город — мимо
    resp = portal_views.portal_sitemap_xml(_get(p, "/sitemap.xml"))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    body = resp.content.decode()
    assert f"http://{_HOST}/" in body
    assert f"http://{_HOST}/bakery/" in body
    assert f"http://{_HOST}/butcher/" in body
    assert "cafe" not in body
    assert "grocery" not in body
    assert body.count("<url>") == 3  # корень + 2 типа


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_combo_portal_sitemap_has_only_home():
    p = _portal(host="baeckerei-muenchen.siteadaptor.de", kind="combo", business_type="bakery")
    _listing(business_type="bakery")
    body = portal_views.portal_sitemap_xml(_get(p, "/sitemap.xml")).content.decode()
    assert body.count("<url>") == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_robots_points_to_portal_sitemap():
    p = _portal()
    body = portal_views.portal_robots_txt(_get(p, "/robots.txt")).content.decode()
    assert "User-agent: *" in body
    assert f"Sitemap: http://{_HOST}/sitemap.xml" in body


def test_sitemap_404_without_portal():
    with pytest.raises(Http404):
        portal_views.portal_sitemap_xml(_get(None, "/sitemap.xml"))


def test_portal_urlconf_routes_sitemap_and_robots():
    from django.urls import resolve

    sitemap = resolve("/sitemap.xml", urlconf="config.urls_portal")
    robots = resolve("/robots.txt", urlconf="config.urls_portal")
    assert sitemap.func is portal_views.portal_sitemap_xml
    assert robots.func is portal_views.portal_robots_txt
