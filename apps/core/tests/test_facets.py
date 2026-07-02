"""UB2-1: протокол `FacetProvider` (apps/core/facets.py) + провайдеры
catalog(category/diet) / events(taxonomy) / stays(date) / booking(none).
Паритет с прежней in-view логикой — без изменения выдачи."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import facets as core_facets

pytestmark = pytest.mark.django_db


def test_provider_for_kinds():
    from apps.catalog.facets import CatalogFacets
    from apps.events.facets import EventFacets
    from apps.stays.facets import StayDateFacets

    assert isinstance(core_facets.provider_for("product"), CatalogFacets)
    assert isinstance(core_facets.provider_for("event"), EventFacets)
    assert isinstance(core_facets.provider_for("stay"), StayDateFacets)
    # у услуг фасетов нет; неизвестный kind тоже деградирует в no-op
    assert isinstance(core_facets.provider_for("service"), core_facets.NullFacets)
    assert isinstance(core_facets.provider_for("bogus"), core_facets.NullFacets)


def test_null_facets_noop():
    provider = core_facets.NullFacets()
    items = [1, 2]
    assert provider.apply(items, {}) is items
    assert provider.present(items, {}) == {}
    assert provider.selected({}) == {}


def test_catalog_facets_apply_category_and_diet():
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import CategoryFactory, ProductFactory

    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "VeganBrot"}, category=cat, diets=["vegan"])
    ProductFactory(name={"de": "Fleischwurst"})
    qs = Product.objects.filter(is_active=True)
    provider = core_facets.provider_for("product")
    assert provider.apply(qs, {"kategorie": "brot"}).count() == 1
    assert provider.apply(qs, {"diet": "vegan"}).count() == 1
    assert provider.apply(qs, {"diet": "zzz"}).count() == 2  # мусорная диета игнорируется
    assert provider.apply(qs, {"kategorie": "brot", "diet": "vegan"}).count() == 1


def test_catalog_facets_present_diet_chips_only_existing():
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import ProductFactory

    ProductFactory(name={"de": "VeganBrot"}, diets=["vegan"])
    qs = Product.objects.filter(is_active=True)
    chips = core_facets.provider_for("product").present(qs, {})["diet_chips"]
    codes = [c["code"] for c in chips]
    assert codes == ["vegan"]  # только реально встречающиеся диеты
    assert chips[0]["label"] and chips[0]["icon"]


def test_event_facets_parity_with_view_helpers():
    from apps.events.models import Event
    from apps.events.public_views import _event_facets

    e1 = Event.objects.create(
        title="Yoga Bern",
        city="Bern",
        starts_at=timezone.now() + timedelta(days=5),
        status=Event.STATUS_PUBLISHED,
        capacity=10,
    )
    e2 = Event.objects.create(
        title="Yoga Chur",
        city="Chur",
        starts_at=timezone.now() + timedelta(days=6),
        status=Event.STATUS_PUBLISHED,
        capacity=10,
    )
    base = [e1, e2]
    provider = core_facets.provider_for("event")
    sel = provider.selected({"city": " Bern ", "cat": ""})
    assert sel["city"] == "Bern" and sel["cat"] == ""  # strip + все 7 ключей
    assert set(sel) == {"cat", "level", "lang", "city", "dur", "month", "teacher"}
    assert provider.apply(base, {"city": "Bern"}) == [e1]
    assert provider.apply(base, {}) == base
    assert provider.present(base, {}) == _event_facets(base)  # делегирование канону


def test_stay_date_facets_selected_parses_and_clamps():
    provider = core_facets.provider_for("stay")
    sel = provider.selected({"von": "2027-01-10", "bis": "2027-01-12", "erw": "2", "kinder": "1"})
    assert sel["von"].isoformat() == "2027-01-10"
    assert sel["bis"].isoformat() == "2027-01-12"
    assert sel["adults"] == 2 and sel["children"] == 1
    junk = provider.selected({"von": "nope", "erw": "x", "kinder": "x"})
    assert junk["von"] is None and junk["bis"] is None
    assert junk["adults"] == 2 and junk["children"] == 0  # дефолты _parse_guests
    legacy = provider.selected({"gaeste": "3"})
    assert legacy["adults"] == 3 and legacy["children"] == 0  # legacy-диплинк H2
