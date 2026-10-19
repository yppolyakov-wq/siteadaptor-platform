"""T-8.10d D-1b: фильтр ?unternehmen=<slug> в поиске каталога города."""

from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import portal_views, search, tasks
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.catalog.models import Product
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/demo/x.webp", "is_primary": True}]


def _listing(slug, title, **kw):
    return AggregatorListing.objects.create(
        tenant_schema=f"s_{slug}",
        tenant_slug=slug,
        business_name=slug.title(),
        listing_kind=kw.pop("kind", "product"),
        source_ref=title,
        title={"de": title},
        city="Solingen",
        is_active=True,
        **kw,
    )


def test_unternehmen_filter_scopes_to_business():
    a = _listing("baeckerei-a", "Roggenbrot A")
    _listing("baeckerei-b", "Roggenbrot B")
    f = search.parse_filters(RequestFactory().get("/", {"unternehmen": "baeckerei-a"}), city="")
    assert f.business == "baeckerei-a" and f.active
    assert ("unternehmen", "baeckerei-a") in search.carry("", f)
    out = search.apply_filters(AggregatorListing.objects.public(), f)
    assert [x.pk for x in out] == [a.pk]


@pytest.mark.parametrize("raw", ["../x", "Bäckerei", "a" * 101, "x y", "<b>"])
def test_unternehmen_bad_slug_ignored(raw):
    f = search.parse_filters(RequestFactory().get("/", {"unternehmen": raw}), city="")
    assert f.business == ""


def test_unternehmen_is_feed_param_and_default_kind_all():
    assert "unternehmen" in search.FILTER_PARAMS
    assert set(search.FILTER_PARAMS) <= set(home.FEED_PARAMS)
    assert home.default_kind("", "", search.SearchFilters(business="x")) == "alle"


def test_portal_kind_rule_unchanged_for_old_combinations():
    empty = search.SearchFilters()
    assert home.default_kind("", "", empty) == ""
    for f in (
        search.SearchFilters(kats=("obst-gemuese",)),
        search.SearchFilters(tags=("vegan",)),
        search.SearchFilters(size="M"),
    ):
        assert home.default_kind("", "", f) == "alle"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_root_with_unternehmen_shows_business_products(isolated_ratelimit):
    TenantFactory(schema_name="public", slug="krume", name="Backhaus Krume", city="Solingen")
    p = Product.objects.create(name={"de": "Dinkelbrot"}, base_price=Decimal("4.20"), images=PHOTO)
    tasks.sync_product_listing("public", p.pk)
    _listing("andere", "Dinkelbrot Fremd")
    portal = AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "S"},
        is_active=True,
    )
    req = RequestFactory().get("/", {"unternehmen": "krume"}, REMOTE_ADDR="10.6.8.1")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Dinkelbrot" in html and "Dinkelbrot Fremd" not in html
