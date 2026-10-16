"""T-8.26 п.5c: размеры/цвета вариантов в снимке каталога города + фильтр «Größe»
(план docs/t8-26-5-query-intent-plan-2026-10-16.md Р-8; миграция aggregator/0027)."""

from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, search, search_index, tasks
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.catalog.models import Product, ProductVariant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/demo/jacke.webp", "is_primary": True}]


def _tenant():
    return TenantFactory(schema_name="public", slug="walder", name="Walder Faden", city="Solingen")


def _product(name="Damenjacke", **kw):
    kw.setdefault("base_price", Decimal("89.00"))
    kw.setdefault("images", PHOTO)
    return Product.objects.create(name={"de": name}, **kw)


def _row(product):
    return AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))


def test_product_snapshot_carries_variant_sizes_and_colors():
    _tenant()
    p = _product()
    ProductVariant.objects.create(
        product=p, label="M · Blau", size="M", color="Blau", stock_quantity=2
    )
    ProductVariant.objects.create(
        product=p, label="L · Blau", size="L", color="Blau", stock_quantity=0
    )
    ProductVariant.objects.create(
        product=p, label="XL · Rot", size="xl", color="Rot", is_active=False
    )
    assert tasks.sync_product_listing("public", p.pk) == "upserted"
    row = _row(p)
    assert set(row.variant_terms) == {"M", "L", "Blau"}  # активные; размер UPPER; без дублей
    assert "XL" not in row.variant_terms


def test_variant_terms_are_searchable_and_survive_refresh():
    _tenant()
    p = _product("Sommerkleid")
    ProductVariant.objects.create(product=p, label="38", size="38", color="Koralle")
    tasks.sync_product_listing("public", p.pk)
    base = AggregatorListing.objects.public()
    assert [x.pk for x in search.execute(base, "Koralle", surface="test").qs] == [_row(p).pk]
    search_index.refresh(AggregatorListing.objects.filter(pk=_row(p).pk))
    assert [x.pk for x in search.execute(base, "Koralle", surface="test").qs] == [_row(p).pk]


def test_size_filter_only_matching_products():
    _tenant()
    m = _product("Damenjacke M")
    ProductVariant.objects.create(product=m, label="M", size="M")
    s = _product("Damenjacke S")
    ProductVariant.objects.create(product=s, label="S", size="S")
    plain = _product("Damenjacke ohne Größen")
    for p in (m, s, plain):
        tasks.sync_product_listing("public", p.pk)
    base = AggregatorListing.objects.public()
    out = search.execute(base, "Damenjacke", search.SearchFilters(size="M"), surface="test")
    assert [x.title["de"] for x in out.qs] == ["Damenjacke M"]
    # «größe m» в тексте — тот же фильтр через намерение
    q_eff, eff, chips, _ = search.resolve_intent(
        "Damenjacke Größe M", search.SearchFilters(), city="Solingen"
    )
    assert q_eff == "Damenjacke" and eff.size == "M" and [c.key for c in chips] == ["groesse"]
    assert "noch nicht" not in chips[0].label


def test_size_param_parsed_and_carried():
    req = RequestFactory().get("/", {"groesse": "m"})
    f = search.parse_filters(req, city="Solingen")
    assert f.size == "M" and ("groesse", "M") in search.carry("", f)
    assert (
        search.parse_filters(RequestFactory().get("/", {"groesse": "<x>"}), city="Solingen").size
        == ""
    )


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_damenjacke_groesse_m_end_to_end(isolated_ratelimit):
    _tenant()
    m = _product("Damenjacke Alpin")
    ProductVariant.objects.create(product=m, label="M", size="M")
    s = _product("Damenjacke Nord")
    ProductVariant.objects.create(product=s, label="S", size="S")
    for p in (m, s):
        tasks.sync_product_listing("public", p.pk)
    portal = AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "S"},
        is_active=True,
    )
    req = RequestFactory().get("/", {"q": "Damenjacke Größe M"}, REMOTE_ADDR="10.6.6.6")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Damenjacke Alpin" in html and "Damenjacke Nord" not in html
    assert 'data-intent-chip="groesse"' in html
