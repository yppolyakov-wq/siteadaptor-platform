"""MEN-5: наборы меню (Combo) отдельными карточками агрегатора.

Решения владельца 2026-08-13: каждый набор = своя карточка; цена = базовая
сборка «ab X €/Gast»; минимальный заказ виден в карточке; блюда состава
попадают в поиск (`?q=Rinderfilet`).
"""

from decimal import Decimal

import pytest

from apps.aggregator import tasks, views
from apps.aggregator.models import AggregatorListing
from apps.catalog.models import Category, Combo, ComboGroup, ComboOption
from apps.catalog.tests.factories import ProductFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    return TenantFactory(
        schema_name="public",
        slug="gruene",
        name="Grüne Tafel",
        city="Düsseldorf",
        business_type="catering",
        **kw,
    )


def _wedding_menu(**kw):
    cat = Category.objects.create(name={"de": "Hochzeit"}, slug="men5-hochzeit")
    combo = Combo.objects.create(
        name="Hochzeitsmenü Klassik",
        description="Drei Gänge, fest zusammengestellt.",
        price=Decimal("45.00"),
        category=cat,
        price_per_person=True,
        min_persons=20,
        event_types=["Hochzeit"],
        **kw,
    )
    fixed = ComboGroup.objects.create(combo=combo, label="Menü", included=True)
    ComboOption.objects.create(
        group=fixed,
        product=ProductFactory(name={"de": "Rinderfilet mit Rotweinjus"}, course="hauptgang"),
    )
    choice = ComboGroup.objects.create(combo=combo, label="Dessert", min_select=1, max_select=1)
    ComboOption.objects.create(
        group=choice,
        product=ProductFactory(name={"de": "Panna Cotta"}, course="dessert", diets=["vegetarisch"]),
        price_delta=Decimal("0"),
    )
    ComboOption.objects.create(
        group=choice,
        product=ProductFactory(name={"de": "Sorbet"}, course="dessert", diets=["vegan"]),
        price_delta=Decimal("2.50"),
    )
    return cat, combo


def test_sync_menu_listing_upsert_and_remove():
    _tenant()
    _cat, combo = _wedding_menu()

    assert tasks.sync_menu_listing("public", str(combo.id)) == "upserted"
    listing = AggregatorListing.objects.get(
        listing_kind=AggregatorListing.KIND_MENU, source_ref=str(combo.id)
    )
    assert listing.title_text == "Hochzeitsmenü Klassik"
    assert listing.business_name == "Grüne Tafel" and listing.city == "Düsseldorf"
    # решение №3: базовая сборка + минимум заказа в самой карточке
    assert listing.new_price == Decimal("45.00")  # дешёвый десерт = +0
    assert listing.price_per_person is True and listing.min_persons == 20
    assert listing.event_types == ["Hochzeit"]
    assert listing.detail_url.endswith(f"/kombi/{combo.id}/")
    # диеты — объединение по составу («Vegan möglich»); блюда — наружу
    assert listing.diets == ["vegan", "vegetarisch"]
    assert "Rinderfilet mit Rotweinjus" in listing.dish_names

    combo.is_active = False
    combo.save(update_fields=["is_active"])
    assert tasks.sync_menu_listing("public", str(combo.id)) == "removed"
    assert not AggregatorListing.objects.filter(source_ref=str(combo.id)).exists()


def test_free_pool_listing_prices_cheapest_dish():
    """Свободная сборка: «ab» = базовая цена + самое дешёвое блюдо пула
    (пустая сборка не продаётся — MEN-4 требует минимум одно блюдо)."""
    _tenant()
    cat = Category.objects.create(name={"de": "Hochzeit"}, slug="men5-frei")
    ProductFactory(name={"de": "Suppe"}, category=cat, course="suppe", base_price=Decimal("8.50"))
    ProductFactory(
        name={"de": "Filet"}, category=cat, course="hauptgang", base_price=Decimal("26.00")
    )
    combo = Combo.objects.create(
        name="Freie Auswahl", price=Decimal("0.00"), free_pool=True, category=cat
    )
    tasks.sync_menu_listing("public", str(combo.id))
    listing = AggregatorListing.objects.get(source_ref=str(combo.id))
    assert listing.new_price == Decimal("8.50")
    assert set(listing.dish_names) == {"Suppe", "Filet"}


def test_search_finds_menu_by_dish_name():
    """Решение №4 «блюда отдаём»: ?q=<блюдо> находит карточку набора."""
    _tenant()
    _cat, combo = _wedding_menu()
    tasks.sync_menu_listing("public", str(combo.id))
    found = views.listings_for(q="Rinderfilet")
    assert [x.source_ref for x in found] == [str(combo.id)]
    assert not views.listings_for(q="Wiener Schnitzel").exists()


def test_menu_filters_guests_diet_event_type_and_price():
    _tenant()
    _cat, combo = _wedding_menu()
    tasks.sync_menu_listing("public", str(combo.id))
    ref = str(combo.id)

    # гости: набор с min_persons=20 подходит для 50 гостей и НЕ подходит для 10
    assert [x.source_ref for x in views.listings_for(guests="50")] == [ref]
    assert not views.listings_for(guests="10").exists()
    assert views.listings_for(guests="abc").exists()  # мусор не роняет выдачу

    assert views.listings_for(diet="vegan").exists()
    assert not views.listings_for(diet="halal").exists()
    assert views.listings_for(event_type="Hochzeit").exists()
    assert not views.listings_for(event_type="Messe").exists()

    # цена с человека: 45 € попадает в 40–50, но не в 10–20
    assert views.listings_for(price_from="40", price_to="50").exists()
    assert not views.listings_for(price_from="10", price_to="20").exists()
    assert views.listings_for(price_from="45,00").exists()  # немецкая запятая


def test_menu_listing_published_regardless_of_disabled_modules():
    """Гейт публикации — САМ активный набор: catalog у нас core-модуль (выключить
    нельзя), поэтому «отключить витрину меню» через модули невозможно; владелец
    убирает карточку, деактивируя набор (проверено в upsert/remove-замке)."""
    _tenant(disabled_modules=["catalog", "orders"])
    _cat, combo = _wedding_menu()
    assert tasks.sync_menu_listing("public", str(combo.id)) == "upserted"


def test_reconcile_syncs_and_prunes_menu_listings():
    _tenant()
    _cat, combo = _wedding_menu()
    AggregatorListing.objects.create(  # осиротевший листинг мёртвого набора
        tenant_schema="public",
        listing_kind=AggregatorListing.KIND_MENU,
        source_ref="00000000-0000-0000-0000-000000000000",
        title={"de": "Alt"},
        detail_url="https://example.de/",
    )
    tasks.reconcile_schema("public")
    refs = set(
        AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_MENU).values_list(
            "source_ref", flat=True
        )
    )
    assert refs == {str(combo.id)}
