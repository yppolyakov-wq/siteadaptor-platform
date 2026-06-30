"""Track B5b: sitemap/robots агрегатора + ItemList JSON-LD на городской странице."""

import uuid

import pytest
from django.test import RequestFactory, override_settings

from apps.aggregator import views
from apps.aggregator.models import AggregatorListing

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


@override_settings(ROOT_URLCONF="config.urls_public")
def test_sitemap_has_index_cities_and_types():
    _listing(city="Hilden", business_type="bakery")
    _listing(city="Köln", business_type="butcher")
    _listing(city="Hilden", business_type="bakery", is_active=False)  # неактивные — мимо
    resp = views.sitemap_xml(RequestFactory().get("/sitemap.xml"))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    body = resp.content.decode()
    assert body.startswith("<?xml")
    assert "/entdecken/Hilden/" in body
    assert "/entdecken/Hilden/bakery/" in body
    # index + 2 города + 2 (город,тип) = 5
    assert body.count("<url>") == 5


@override_settings(ROOT_URLCONF="config.urls_public")
def test_sitemap_excludes_inactive():
    _listing(city="Hilden", is_active=True)
    _listing(city="GhostCity", is_active=False)
    body = views.sitemap_xml(RequestFactory().get("/sitemap.xml")).content.decode()
    assert "GhostCity" not in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_robots_points_to_sitemap():
    body = views.robots_txt(RequestFactory().get("/robots.txt")).content.decode()
    assert "User-agent: *" in body
    assert "Sitemap:" in body
    assert "sitemap.xml" in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_emits_itemlist_jsonld():
    _listing(city="Hilden", title={"de": "AktivesAngebot"})
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert 'type="application/ld+json"' in body
    assert '"@type":"ItemList"' in body
    assert "AktivesAngebot" in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_sort_by_name_orders_az():
    """A8: ?sort=name сортирует выдачу по business_name A–Z; select отражает выбор."""
    _listing(city="Hilden", business_name="Zeta Bäckerei", tenant_schema="tz", title={"de": "Z"})
    _listing(city="Hilden", business_name="Alpha Bistro", tenant_schema="ta", title={"de": "A"})
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?sort=name"), "Hilden"
    ).content.decode()
    assert body.index("Alpha Bistro") < body.index("Zeta Bäckerei")  # A–Z
    assert 'value="name" selected' in body  # дропдаун отражает выбор


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_default_sort_is_newest():
    """A8: дефолт — neueste (выбран в select), невалидный sort игнорируется."""
    _listing(city="Hilden", business_name="Eins")
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?sort=bogus"), "Hilden"
    ).content.decode()
    assert 'value="neueste" selected' in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_rating_facet_filters_by_min_stars():
    """A8: ?rating=4 оставляет только бизнесы с avg_rating ≥ 4 (BusinessRating)."""
    from apps.aggregator.models import BusinessRating

    _listing(city="Hilden", business_name="Top Bäckerei", tenant_schema="good", title={"de": "G"})
    _listing(city="Hilden", business_name="Mittel Bistro", tenant_schema="meh", title={"de": "M"})
    BusinessRating.objects.create(tenant_schema="good", avg_rating="4.50", review_count=10)
    BusinessRating.objects.create(tenant_schema="meh", avg_rating="3.00", review_count=4)
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?rating=4"), "Hilden"
    ).content.decode()
    assert "Top Bäckerei" in body and "Mittel Bistro" not in body
    assert 'value="4" selected' in body  # дропдаун отражает выбранный порог


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_invalid_rating_ignored():
    """A8: невалидный/слишком низкий rating не фильтрует (показываем всех)."""
    _listing(city="Hilden", business_name="Eins", tenant_schema="t1")
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?rating=2"), "Hilden"
    ).content.decode()
    assert "Eins" in body
    assert 'value=""' in body  # «Any rating» — порог не выбран


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_open_now_facet_filters_by_hours():
    """A8: ?offen=1 оставляет только бизнесы, открытые сейчас (opening_hours_structured).

    «Открыт» — окно на весь день (00:00–23:59 → live-статус open); «закрыт» — часы
    не заданы (open_status=None → не открыт). Детерминированно при любом времени дня.
    """
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="open_t", slug="op", name="Open", business_type="bakery")
    TenantFactory(schema_name="closed_t", slug="cl", name="Closed", business_type="bakery")
    Tenant.objects.filter(schema_name="open_t").update(
        opening_hours_structured={str(d): ["00:00", "23:59"] for d in range(7)}
    )
    Tenant.objects.filter(schema_name="closed_t").update(opening_hours_structured={})
    _listing(
        city="Hilden", business_name="Offen Bäckerei", tenant_schema="open_t", title={"de": "O"}
    )
    _listing(city="Hilden", business_name="Zu Bistro", tenant_schema="closed_t", title={"de": "Z"})
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?offen=1"), "Hilden"
    ).content.decode()
    assert "Offen Bäckerei" in body and "Zu Bistro" not in body
    assert "checked" in body  # чекбокс «Open now» активен


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_card_shows_open_status_badge():
    """A8: карточка города показывает live-бейдж «Geöffnet» (богатая карточка бизнеса);
    бизнес без заданных часов остаётся без бейджа (не зашумляет)."""
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="open_b", slug="ob", name="OpenB", business_type="bakery")
    TenantFactory(schema_name="nohours_b", slug="nb", name="NoHoursB", business_type="bakery")
    Tenant.objects.filter(schema_name="open_b").update(
        opening_hours_structured={str(d): ["00:00", "23:59"] for d in range(7)}
    )
    Tenant.objects.filter(schema_name="nohours_b").update(opening_hours_structured={})
    _listing(city="Hilden", business_name="Offen", tenant_schema="open_b", title={"de": "O"})
    _listing(
        city="Hilden", business_name="OhneZeiten", tenant_schema="nohours_b", title={"de": "K"}
    )
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert "Offen" in body and "OhneZeiten" in body  # оба в выдаче
    # Открытый бизнес: бейдж «Geöffnet · until 23:59» (open_until только у карточки, не у
    # чекбокса фасета). Бизнес без часов — без ложного «Geschlossen» (часы не заданы).
    assert "until 23:59" in body
    assert "Closed" not in body
