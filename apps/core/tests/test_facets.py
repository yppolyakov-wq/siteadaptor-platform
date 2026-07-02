"""UB2-1: протокол `FacetProvider` (apps/core/facets.py) + провайдеры
catalog(category/diet) / events(taxonomy) / stays(date) / booking(none).
Паритет с прежней in-view логикой — без изменения выдачи."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import facets as core_facets

pytestmark = pytest.mark.django_db


def test_provider_for_kinds():
    from apps.booking.facets import ServiceFacets
    from apps.catalog.facets import CatalogFacets
    from apps.events.facets import EventFacets
    from apps.stays.facets import StayDateFacets

    assert isinstance(core_facets.provider_for("product"), CatalogFacets)
    assert isinstance(core_facets.provider_for("event"), EventFacets)
    assert isinstance(core_facets.provider_for("stay"), StayDateFacets)
    # UB2-2: у услуг фасетов нет, но есть поиск/сортировка — свой провайдер
    assert isinstance(core_facets.provider_for("service"), ServiceFacets)
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


def test_catalog_search_i18n_all_locales():
    """UB2-2: ?q= ищет по name/description на ВСЕХ локалях реестра (не только базовой)."""
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import ProductFactory

    ProductFactory(name={"de": "Roggenbrot", "en": "Rye bread"})
    ProductFactory(name={"de": "Kuchen"}, description={"de": "Mit Sahne"})
    qs = Product.objects.filter(is_active=True)
    provider = core_facets.provider_for("product")
    assert provider.search(qs, "rye").count() == 1  # EN-локаль
    assert provider.search(qs, "rogg").count() == 1  # DE-локаль
    assert provider.search(qs, "sahne").count() == 1  # описание
    assert provider.search(qs, "").count() == 2  # пусто → no-op
    assert provider.search(qs, "zzz").count() == 0


def test_service_search_flat_and_i18n_overlay():
    """UB2-2: услуги — плоские name/description + оверлеи name_i18n/description_i18n."""
    from apps.booking.models import Service

    Service.objects.create(
        name="Ölwechsel", description="Inkl. Filter", name_i18n={"en": "Oil change"}
    )
    Service.objects.create(name="Haarschnitt")
    qs = Service.objects.all()
    provider = core_facets.provider_for("service")
    assert provider.search(qs, "oil").count() == 1  # EN-оверлей
    assert provider.search(qs, "ölwechsel").count() == 1  # базовое имя
    assert provider.search(qs, "filter").count() == 1  # описание
    assert provider.search(qs, "  ").count() == 2  # пробелы → no-op


def test_service_sort_keys_and_noop_default():
    from apps.booking.models import Service

    cheap = Service.objects.create(name="B-Werk", price_cents=1000)
    dear = Service.objects.create(name="A-Werk", price_cents=9000)
    qs = Service.objects.all()
    provider = core_facets.provider_for("service")
    assert list(provider.sort(qs, "price_desc")) == [dear, cheap]
    assert list(provider.sort(qs, "price_asc")) == [cheap, dear]
    # ""/мусор → порядок Meta ["name"] без пересортировки
    assert list(provider.sort(qs, "")) == [dear, cheap]  # A-Werk < B-Werk
    assert list(provider.sort(qs, "bogus")) == [dear, cheap]


def test_stay_search_and_price_sort():
    from apps.stays.models import StayUnit

    a = StayUnit.objects.create(name="Alpensuite", price_cents=12000, is_active=True)
    b = StayUnit.objects.create(
        name="Zimmer", description_i18n={"en": "Lake view"}, price_cents=8000, is_active=True
    )
    qs = StayUnit.objects.filter(is_active=True)
    provider = core_facets.provider_for("stay")
    assert list(provider.search(qs, "alpen")) == [a]
    assert list(provider.search(qs, "lake")) == [b]  # EN-оверлей описания
    assert list(provider.sort(qs, "price_asc")) == [b, a]


def test_event_search_and_price_sort_in_memory():
    from apps.events.models import Event

    e1 = Event.objects.create(
        title="Yoga Retreat",
        title_i18n={"en": "Mountain escape"},
        starts_at=timezone.now() + timedelta(days=3),
        status=Event.STATUS_PUBLISHED,
        price_cents=5000,
        capacity=10,
    )
    e2 = Event.objects.create(
        title="Konzert",
        description="Jazz am See",
        starts_at=timezone.now() + timedelta(days=4),
        status=Event.STATUS_PUBLISHED,
        price_cents=2000,
        capacity=10,
    )
    base = [e1, e2]
    provider = core_facets.provider_for("event")
    assert provider.search(base, "mountain") == [e1]  # EN-оверлей заголовка
    assert provider.search(base, "jazz") == [e2]  # описание
    assert provider.search(base, "") == base
    assert provider.sort(base, "price_asc") == [e2, e1]
    assert provider.sort(base, "price_desc") == [e1, e2]
    assert provider.sort(base, "") == base  # дефолт — порядок вьюхи (по дате)


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


def test_catalog_price_and_stock_facets():
    """UB2-3: цена (gte/lte, «12,50» тоже) и «только в наличии» (учёт вариантов)."""
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import ProductFactory

    cheap = ProductFactory(name={"de": "Billig"}, base_price="5.00")
    ProductFactory(name={"de": "Teuer"}, base_price="50.00", stock_quantity=0)
    qs = Product.objects.filter(is_active=True)
    provider = core_facets.provider_for("product")
    assert list(provider.apply(qs, {"preis_bis": "10"})) == [cheap]
    assert provider.apply(qs, {"preis_von": "4,50"}).count() == 2  # запятая-ввод
    assert list(provider.apply(qs, {"nur_verfuegbar": "1"})) == [cheap]  # sold-out скрыт
    present = provider.present(qs, {})
    assert present["show_price_filter"] is True  # разброс цен есть
    assert float(present["price_lo"]) == 5.0 and float(present["price_hi"]) == 50.0
    assert present["show_stock_filter"] is True  # есть распроданное


def test_catalog_origin_facet():
    """UB2-3: Bio/Regional-Herkunft — чипы только указанных значений + точный фильтр."""
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import ProductFactory

    hof = ProductFactory(name={"de": "Eier"}, origin="Hof Müller")
    ProductFactory(name={"de": "Mehl"})
    qs = Product.objects.filter(is_active=True)
    provider = core_facets.provider_for("product")
    assert provider.present(qs, {})["origin_chips"] == ["Hof Müller"]
    assert list(provider.apply(qs, {"herkunft": "Hof Müller"})) == [hof]
    assert provider.apply(qs, {"herkunft": "Anderswo"}).count() == 0


def test_catalog_rating_facet_bulk_summary():
    """UB2-3: рейтинг-фасет читает reviews bulk-summary (avg >= порога, pk__in);
    мусорный порог игнорируется; present показывает фасет лишь при отзывах."""
    from apps.catalog.models import Product
    from apps.catalog.tests.factories import ProductFactory
    from apps.reviews.models import Review

    top = ProductFactory(name={"de": "TopBrot"})
    meh = ProductFactory(name={"de": "MehBrot"})
    Review.objects.create(entity_kind="product", entity_id=top.pk, rating=5, is_published=True)
    Review.objects.create(entity_kind="product", entity_id=meh.pk, rating=3, is_published=True)
    qs = Product.objects.filter(is_active=True)
    provider = core_facets.provider_for("product")
    assert list(provider.apply(qs, {"bewertung": "4"})) == [top]
    assert provider.apply(qs, {"bewertung": "3"}).count() == 2
    assert provider.apply(qs, {"bewertung": "99"}).count() == 2  # вне порогов → no-op
    present = provider.present(qs, {})
    assert present["show_rating_filter"] is True
    assert present["rating_thresholds"] == (3, 4, 5)
