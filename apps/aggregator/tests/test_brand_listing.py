"""T-8.10d D-1a: марка товара в каталоге города — снимок, индекс, фильтр ?marke=.

План — docs/t8-10d-search-subscriptions-plan-2026-10-19.md §2. Замки написаны ДО кода."""

import inspect
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import portal_views, search, search_index, tasks
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.catalog.models import Product
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/demo/drill.webp", "is_primary": True}]


def _tenant():
    return TenantFactory(
        schema_name="public", slug="werk", name="Werkzeug Schmitz", city="Solingen"
    )


def _product(name="Akkuschrauber", brand="Bosch", **kw):
    kw.setdefault("base_price", Decimal("89.00"))
    kw.setdefault("images", PHOTO)
    return Product.objects.create(name={"de": name}, brand=brand, **kw)


def _row(product):
    return AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))


def _promo(product, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    kw.setdefault("title", {"de": "Werkzeug-Woche"})
    kw.setdefault("discount_percent", 20)
    return Promotion.objects.create(product=product, **kw)


def test_product_listing_carries_brand():
    _tenant()
    p = _product(brand="  Bosch   Professional ")
    tasks.sync_product_listing("public", p.pk)
    assert _row(p).brand == "Bosch Professional"


def test_promo_brand_from_target_product():
    _tenant()
    promo = _promo(_product())
    tasks.sync_listing("public", str(promo.id))
    assert AggregatorListing.objects.get(promo_uuid=promo.id).brand == "Bosch"


@pytest.mark.parametrize("kw", [{"discount_style": "mystery"}, {"is_surprise": True}])
def test_mystery_and_surprise_hide_brand(kw):
    _tenant()
    promo = _promo(_product(), **kw)
    tasks.sync_listing("public", str(promo.id))
    assert AggregatorListing.objects.get(promo_uuid=promo.id).brand == ""


def test_every_builder_writes_brand():
    # Марка — через _neutral_v2v4: вид, забывший поле, никогда его не обновит.
    assert tasks._neutral_v2v4()["brand"] == ""
    src = inspect.getsource(tasks)
    assert src.count("**_neutral_v2v4(),") == src.count("_upsert_listing(\n")


def test_brand_in_search_vector_and_trigram():
    _tenant()
    p = _product("Akkuschrauber 18 V", brand="Makita")
    other = _product("Akkuschrauber Basic", brand="")
    for x in (p, other):
        tasks.sync_product_listing("public", x.pk)
    base = AggregatorListing.objects.public()
    assert [x.pk for x in search.execute(base, "Makita", surface="test").qs] == [_row(p).pk]
    assert "makita" in _row(p).search_text
    search_index.refresh(AggregatorListing.objects.filter(pk=_row(p).pk))
    assert [x.pk for x in search.execute(base, "makita", surface="test").qs] == [_row(p).pk]


def test_brand_change_reindexes():
    _tenant()
    p = _product(brand="")
    tasks.sync_product_listing("public", p.pk)
    row = _row(p)
    row.brand = "Fiskars"
    row.save(update_fields=["brand"])
    base = AggregatorListing.objects.public()
    assert [x.pk for x in search.execute(base, "Fiskars", surface="test").qs] == [row.pk]


def test_marke_filter_iexact():
    _tenant()
    bosch = _product("Bohrer A", brand="Bosch")
    makita = _product("Bohrer B", brand="Makita")
    for x in (bosch, makita):
        tasks.sync_product_listing("public", x.pk)
    f = search.parse_filters(RequestFactory().get("/", {"marke": "bosch"}), city="Solingen")
    assert f.brand == "bosch" and f.active and ("marke", "bosch") in search.carry("", f)
    out = search.apply_filters(AggregatorListing.objects.public(), f)
    assert [x.pk for x in out] == [_row(bosch).pk]


@pytest.mark.parametrize("raw", ["Bo\x00sch​", "x" * 500, "  "])
def test_marke_garbage_cleaned_or_ignored(raw):
    f = search.parse_filters(RequestFactory().get("/", {"marke": raw}), city="Solingen")
    assert "\x00" not in f.brand and "​" not in f.brand
    assert len(f.brand) <= search.BRAND_MAX


def test_marke_is_a_feed_param():
    from apps.aggregator import portal_home_blocks

    assert "marke" in search.FILTER_PARAMS
    assert set(search.FILTER_PARAMS) <= set(portal_home_blocks.FEED_PARAMS)


def test_default_kind_rule():
    from apps.aggregator import portal_home_blocks as home

    empty = search.SearchFilters()
    assert home.default_kind("", "", empty) == ""
    assert home.default_kind("", "brot", empty) == "alle"
    assert home.default_kind("", "", search.SearchFilters(brand="Bosch")) == "alle"
    assert home.default_kind("", "", search.SearchFilters(size="M")) == "alle"
    assert home.default_kind("angebote", "brot", empty) == "angebote"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_bare_marke_returns_products(isolated_ratelimit):
    _tenant()
    p = _product("Heckenschere", brand="Gardena")
    tasks.sync_product_listing("public", p.pk)
    portal = AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "S"},
        is_active=True,
    )
    req = RequestFactory().get("/", {"marke": "gardena"}, REMOTE_ADDR="10.6.7.1")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Heckenschere" in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_offer_page_shows_brand_with_link():
    from apps.aggregator import views

    _tenant()
    p = _product("Gartenschere", brand="Fiskars")
    tasks.sync_product_listing("public", p.pk)
    req = RequestFactory().get("/", REMOTE_ADDR="10.6.7.2")
    html = views.offer_page(req, _row(p).pk).content.decode()
    assert "data-offer-brand" in html and "marke=Fiskars" in html
