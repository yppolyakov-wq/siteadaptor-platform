"""T-8.13b: свои категории → категории каталога города (связь, не копия).

План — docs/t8-13b-category-mapping-plan-2026-10-10.md §2.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.catalog import city, views
from apps.catalog.forms import CategoryForm
from apps.catalog.models import Category, Product
from apps.core import city_categories as cc
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _cat(name, parent=None, **kw):
    return Category.objects.create(
        name={"de": name}, slug=name.lower().replace(" ", "-")[:90], parent=parent, **kw
    )


@pytest.mark.parametrize(
    ("name", "want"),
    [
        ("Damenjacken", "damenmode"),
        ("Brötchen & Brot", "brot-backwaren"),
        ("Kinderschuhe", "schuhe"),
        ("Schweinefleisch", "fleisch-wurst"),
        ("Sonstiges", ""),
        ("Neuheiten", ""),
    ],
)
def test_name_hint(name, want):
    assert cc.suggest_for_name(name) == want


def test_name_hints_point_to_known_categories():
    assert all(cc.category(key) for _prefix, key in cc.NAME_HINTS)


def test_resolver_own_beats_parent_and_child_inherits():
    root = _cat("Herbst", city_category="damenmode")
    child = _cat("Jacken", parent=root)
    assert city.resolve(child) == "damenmode"
    child.city_category = "herrenmode"
    assert city.resolve(child) == "herrenmode"
    child.city_category = "zzz"  # мусор → дальше по цепочке
    assert city.resolve(child) == "damenmode"


def test_resolver_falls_back_to_name_then_empty():
    assert city.resolve(_cat("Taschen")) == "taschen"
    assert city.resolve(_cat("Unsere Herbstkollektion")) == ""
    assert city.auto_for(_cat("Kleines", parent=_cat("Schmuck"))) == "schmuck"


def test_promotion_on_product_takes_its_category_own_wins():
    TenantFactory(schema_name="public", slug="map-sync", business_type="clothing")
    cat = _cat("Herbst", city_category="schuhe")
    product = Product.objects.create(name={"de": "Stiefel"}, base_price="80.00", category=cat)
    promo = Promotion.objects.create(status="active", title={"de": "Stiefel"}, product=product)
    tasks.sync_listing("public", str(promo.pk))
    assert AggregatorListing.objects.get().city_category == "schuhe"  # не «Damenmode»
    promo.city_category = "taschen"
    promo.save()
    tasks.sync_listing("public", str(promo.pk))
    assert AggregatorListing.objects.get().city_category == "taschen"


def test_category_form_saves_and_clears_choice():
    cat = _cat("Herbst")
    data = {"name_de": "Herbst", "slug": "herbst", "sort_order": 0, "is_active": "on"}
    form = CategoryForm({**data, "city_category": "kindermode"}, instance=cat)
    assert form.is_valid(), form.errors
    assert form.save().city_category == "kindermode"
    form = CategoryForm({**data, "city_category": ""}, instance=cat)
    assert form.is_valid(), form.errors
    assert form.save().city_category == ""
    bad = CategoryForm({**data, "city_category": "zzz"}, instance=cat)
    assert not bad.is_valid() and "city_category" in bad.errors


def _req(data=None):
    user = get_user_model().objects.create_user(username="map", password="pw12345678")
    req = RequestFactory().post("/catalog/categories/", data) if data else RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = TenantFactory(schema_name="public", slug="map-view")
    return req


def test_list_shows_mapping_rows_with_auto_hint():
    _cat("Damenjacken")
    html = views.category_list(_req()).content.decode()
    assert "data-city-map" in html and "Automatisch: Damenmode" in html


def test_bulk_mapping_writes_only_sent_rows_and_ignores_garbage():
    a, b = _cat("Alpha"), _cat("Beta", city_category="schuhe")
    with mock.patch("apps.aggregator.tasks.reconcile_aggregator_schema.delay"):
        resp = views.category_list(
            _req(
                {
                    "action": "city_map",
                    "map_id": [str(a.pk), "not-a-uuid"],
                    f"map_{a.pk}": "geschenke",
                    f"map_{b.pk}": "taschen",  # строки нет в map_id → не трогаем
                }
            )
        )
    assert resp.status_code == 302
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.city_category, b.city_category) == ("geschenke", "schuhe")
