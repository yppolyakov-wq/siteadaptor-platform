"""Тесты P2.1b: подмена urlconf на портальном хосте + portal_home.

Вьюхи — напрямую через RequestFactory с ручным request.portal (как в
test_pages.py); подмену urlconf проверяем через middleware с заглушкой
get_response. ROOT_URLCONF переопределяем на config.urls_portal, чтобы
{% url 'portal-home' %} в шаблонах резолвился.
"""

import types
import uuid

import pytest
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.test import RequestFactory, override_settings

from apps.aggregator import middleware, portal_views
from apps.aggregator.middleware import AggregatorPortalMiddleware
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_portal_cache():
    cache.delete(middleware._CACHE_KEY)
    yield
    cache.delete(middleware._CACHE_KEY)


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


def _get(portal, path="/", **params):
    req = RequestFactory().get(path, params)
    req.portal = portal
    return req


# --- middleware: подмена urlconf ---------------------------------------------


def _pass_through(request):
    captured = {}

    def get_response(req):
        captured["urlconf"] = getattr(req, "urlconf", None)
        return HttpResponse("ok")

    AggregatorPortalMiddleware(get_response)(request)
    return captured


def test_middleware_swaps_urlconf_on_portal_host():
    _portal()
    req = RequestFactory().get("/", HTTP_HOST="muenchen.siteadaptor.de")
    req.tenant = types.SimpleNamespace(schema_name="public")
    assert _pass_through(req)["urlconf"] == "config.urls_portal"


def test_middleware_keeps_urlconf_on_main_domain():
    _portal()
    req = RequestFactory().get("/", HTTP_HOST="siteadaptor.de")
    req.tenant = types.SimpleNamespace(schema_name="public")
    assert _pass_through(req)["urlconf"] is None


# --- portal_home: городской портал --------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_city_portal_shows_only_its_city_and_branding():
    p = _portal()
    _listing(city="München", title={"de": "MuenchenDeal"})
    _listing(city="Köln", title={"de": "KoelnDeal"})
    resp = portal_views.portal_home(_get(p))
    assert resp.status_code == 200
    assert b"MuenchenDeal" in resp.content
    assert b"KoelnDeal" not in resp.content
    assert "Angebote München".encode() in resp.content  # брендированный заголовок


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_city_portal_facet_filters_by_business_type():
    p = _portal()
    _listing(business_type="bakery", title={"de": "BakeryDeal"})
    _listing(business_type="butcher", title={"de": "ButcherDeal"})
    resp = portal_views.portal_home(_get(p, "/bakery/"), facet="bakery")
    assert b"BakeryDeal" in resp.content
    assert b"ButcherDeal" not in resp.content


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_city_portal_lists_type_chips():
    p = _portal()
    _listing(business_type="bakery")
    _listing(business_type="butcher")
    resp = portal_views.portal_home(_get(p))
    assert b"/bakery/" in resp.content
    assert b"/butcher/" in resp.content


def test_unknown_facet_raises_404():
    p = _portal()
    _listing(business_type="bakery")
    with pytest.raises(Http404):
        portal_views.portal_home(_get(p, "/florist/"), facet="florist")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_facet_is_case_insensitive():
    p = _portal()
    _listing(business_type="bakery", title={"de": "BakeryDeal"})
    resp = portal_views.portal_home(_get(p, "/Bakery/"), facet="Bakery")
    assert b"BakeryDeal" in resp.content


# --- portal_home: вертикальный и combo -----------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_vertical_portal_facet_is_city():
    p = _portal(
        host="baeckerei.siteadaptor.de",
        kind="vertical",
        city="",
        business_type="bakery",
        title={"de": "Bäckereien"},
    )
    _listing(city="München", business_type="bakery", title={"de": "MuenchenBrot"})
    _listing(city="Köln", business_type="bakery", title={"de": "KoelnBrot"})
    _listing(city="München", business_type="butcher", title={"de": "FleischDeal"})

    resp = portal_views.portal_home(_get(p))  # корень: вся вертикаль
    assert b"MuenchenBrot" in resp.content
    assert b"KoelnBrot" in resp.content
    assert b"FleischDeal" not in resp.content

    resp = portal_views.portal_home(_get(p, "/K%C3%B6ln/"), facet="Köln")
    assert b"KoelnBrot" in resp.content
    assert b"MuenchenBrot" not in resp.content


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_combo_portal_filters_both_axes_and_rejects_facet():
    p = _portal(
        host="baeckerei-muenchen.siteadaptor.de",
        kind="combo",
        city="München",
        business_type="bakery",
        title={"de": "Bäckereien München"},
    )
    _listing(city="München", business_type="bakery", title={"de": "ComboDeal"})
    _listing(city="München", business_type="butcher", title={"de": "FleischDeal"})
    _listing(city="Köln", business_type="bakery", title={"de": "KoelnBrot"})

    resp = portal_views.portal_home(_get(p))
    assert b"ComboDeal" in resp.content
    assert b"FleischDeal" not in resp.content
    assert b"KoelnBrot" not in resp.content

    with pytest.raises(Http404):
        portal_views.portal_home(_get(p, "/bakery/"), facet="bakery")


def test_portal_home_404_without_portal():
    with pytest.raises(Http404):
        portal_views.portal_home(_get(None))
