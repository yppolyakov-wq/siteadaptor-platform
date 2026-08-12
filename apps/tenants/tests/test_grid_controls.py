"""DS-5/5b: сеточные контролы Studio — колонки до 6, Anzahl категорий, симметрия
(balance), горизонтальная лента (scroll), инфо/высота плитки категорий, прайс с
мини-фото. План docs/ds5-grid-controls-plan-2026-08-12.md."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _home(tenant):
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def test_layout_cols_up_to_six():
    lay = siteconfig.normalize_layout({"cols": 6})
    assert lay["cols"] == 6
    assert siteconfig.normalize_layout({"cols": 9})["cols"] == 6  # кламп сверху
    assert "lg:grid-cols-6" in siteconfig.grid_class_string({"cols": 6})


def test_balance_and_scroll_presence_minimal():
    assert "balance" not in siteconfig.normalize_layout({})
    assert "scroll" not in siteconfig.normalize_layout({"scroll": False})
    lay = siteconfig.normalize_layout({"balance": True, "cols": 5})
    assert lay["balance"] is True
    classes = siteconfig.grid_class_string(lay)
    assert "sf-balance-grid" in classes and "sf-bal-5" in classes
    scroll = siteconfig.grid_class_string({"scroll": True, "balance": True})
    assert "sf-scroll-grid" in scroll and "sf-balance-grid" not in scroll  # scroll wins


def test_default_grid_classes_unchanged():
    # Характеризация: без новых ключей — прежняя grid-строка байт-в-байт.
    assert (
        siteconfig.grid_class_string({"preset": "cols3"})
        == "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6"
    )


def test_categories_row_extras_normalize():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "categories",
                    "enabled": True,
                    "img_h": 555,
                    "tile_info": ["price", "junk", "count"],
                    "limit": 99,
                }
            ]
        }
    )
    row = next(s for s in cfg["sections"] if s["key"] == "categories")
    assert row["img_h"] == 480  # кламп сверху
    assert row["tile_info"] == ["price", "count"]  # whitelist
    assert row["limit"] == 30  # потолок Anzahl
    # presence-minimal: без значений ключей нет, limit материализован дефолтом
    bare = siteconfig.normalize({"sections": [{"key": "categories", "enabled": True}]})
    brow = next(s for s in bare["sections"] if s["key"] == "categories")
    assert "img_h" not in brow and "tile_info" not in brow
    assert brow["limit"] == 30  # дефолт = максимум (раньше выводились ВСЕ — без регрессии)


def _seed_categories(n=6):
    for i in range(n):
        cat = Category.objects.create(
            name={"de": f"Richtung {i}"},
            slug=f"gc-r{i}",
            sort_order=i,
            # img_h применяется только к фото-плиткам — даём фото каждой категории
            images=[{"id": f"img{i}", "url": f"/media/cat{i}.jpg", "is_primary": True}],
        )
        Product.objects.create(
            name={"de": f"Produkt {i}"}, base_price=f"{10 + i}.00", category=cat, is_active=True
        )


def test_categories_limit_and_tile_info_render():
    _seed_categories(6)
    tenant = TenantFactory.build(
        site_config={
            "sections": [
                {
                    "key": "categories",
                    "enabled": True,
                    "limit": 4,
                    "img_h": 120,
                    "tile_info": ["price", "count"],
                },
                # products выключаем: карточки печатают имена категорий (шум для
                # ассерта «Richtung 4 не видна»).
                {"key": "products", "enabled": False},
                {"key": "promotions", "enabled": False},
            ]
        }
    )
    html = _home(tenant)
    assert "Richtung 3" in html and "Richtung 4" not in html  # Anzahl уважен
    assert "height: 120px;" in html  # высота фото из Studio
    assert "10,00 €" in html or "10.00 €" in html  # ab-цена
    assert "1 Produkt" in html  # счётчик товаров


def test_products_scroll_mode_renders_strip():
    _seed_categories(2)
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "layout": {"scroll": True}}]}
    )
    html = _home(tenant)
    assert "sf-scroll-grid" in html


def test_preisliste_foto_variant():
    _seed_categories(1)
    # секция главной: стиль с фото валиден и рендерит прайс
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "style": "preisliste_foto"}]}
    )
    assert next(s for s in cfg["sections"] if s["key"] == "products")["style"] == "preisliste_foto"
    tenant = TenantFactory.build(site_config=cfg)
    assert "data-price-list" in _home(tenant)
    # страничный пресет каталога принимает второй вариант
    page = siteconfig.normalize({"catalog_layout": {"preset": "preisliste_foto"}})
    assert page["catalog_layout"]["preset"] == "preisliste_foto"
