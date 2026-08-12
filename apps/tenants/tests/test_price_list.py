"""DS-3a (Fokus): «прайс-лист» — вид вывода товаров (секция главной + страница
каталога). План docs/ds3-fokus-output-views-plan-2026-08-12.md. Замки: нормализация
extra-пресета (только каталог), рендер строк/групп, характеризация «без стиля —
прежняя сетка», гейт PDF-чипа."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _render_home(tenant):
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def _render_catalog(tenant, query=""):
    request = RequestFactory().get(f"/sortiment/{query}")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.product_list(request).content.decode()


def _seed_products():
    cat = Category.objects.create(name={"de": "Buffets"}, slug="pl-buffets", sort_order=1)
    cat2 = Category.objects.create(name={"de": "Getränke"}, slug="pl-drinks", sort_order=2)
    Product.objects.create(
        name={"de": "Buffet Vegetarisch"},
        description={"de": "Drei Gänge mit Salaten"},
        base_price="24.00",
        category=cat,
        is_active=True,
    )
    Product.objects.create(
        name={"de": "Saftpaket"}, base_price="9.00", category=cat2, is_active=True
    )
    Product.objects.create(name={"de": "Ohne Kategorie"}, base_price="3.00", is_active=True)


def test_normalize_catalog_accepts_preisliste_only_there():
    cfg = siteconfig.normalize({"catalog_layout": {"preset": "preisliste"}})
    assert cfg["catalog_layout"]["preset"] == "preisliste"
    # мусор по-прежнему падает в дефолт
    assert (
        siteconfig.normalize({"catalog_layout": {"preset": "junk"}})["catalog_layout"]["preset"]
        == "cols3"
    )
    # у соседних страниц extra-вид НЕ валиден (пикеры его и не предлагают)
    assert (
        siteconfig.normalize({"stay_index_layout": {"preset": "preisliste"}})["stay_index_layout"][
            "preset"
        ]
        != "preisliste"
    )
    # LAYOUT_PRESETS не раздут — «preisliste» живёт только в PAGE_EXTRA_PRESETS
    assert "preisliste" not in siteconfig.LAYOUT_PRESETS
    assert siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"] == ("preisliste",)


def test_products_section_style_survives_normalize():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    row = next(s for s in cfg["sections"] if s["key"] == "products")
    assert row["style"] == "preisliste"
    junk = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "style": "junk"}]}
    )
    assert next(s for s in junk["sections"] if s["key"] == "products").get("style", "") == ""


def test_home_section_price_list_renders_groups_and_rows():
    _seed_products()
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    html = _render_home(tenant)
    assert "data-price-list" in html
    assert "Buffets" in html and "Getränke" in html
    assert "Buffet Vegetarisch" in html and "Drei Gänge" in html
    assert "Weitere" in html  # безкатегорийные — в конце, своей группой
    assert "Ganze Speisekarte" in html
    # карточная сетка секции НЕ рендерится
    assert 'data-grid="products"' not in html


def test_home_section_default_grid_unchanged():
    # Характеризация: без стиля — прежняя карточная сетка (байт-семантика вида).
    _seed_products()
    tenant = TenantFactory.build(site_config={"sections": [{"key": "products", "enabled": True}]})
    html = _render_home(tenant)
    assert 'data-grid="products"' in html
    assert "data-price-list" not in html


def test_catalog_page_preisliste_groups_and_facets_alive():
    _seed_products()
    tenant = TenantFactory.build(site_config={"catalog_layout": {"preset": "preisliste"}})
    html = _render_catalog(tenant)
    assert "data-price-list" in html
    assert 'data-grid="catalog"' not in html
    assert "Buffet Vegetarisch" in html
    # поиск (?q=) продолжает фильтровать выдачу — провайдер UB не тронут
    filtered = _render_catalog(tenant, "?q=Saftpaket")
    assert "Saftpaket" in filtered and "Buffet Vegetarisch" not in filtered


def test_catalog_page_default_grid_unchanged():
    _seed_products()
    tenant = TenantFactory.build()
    html = _render_catalog(tenant)
    assert 'data-grid="catalog"' in html
    assert "data-price-list" not in html
