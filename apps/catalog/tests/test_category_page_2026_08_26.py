"""Фидбэк 2026-08-26 по странице `/sortiment/catering/`.

Три вещи, которых на ней не было: фото у подкатегорий (текстовые карточки при
любом шаблоне, кроме «kopfbild»), виды отображения у наборов меню и собственные
C-блоки страницы (галерея/отзывы/команда были возможны только на ВЕСЬ каталог).
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, params=None, site_config=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Pranasy X", address="Hauptstr. 1")
    if site_config is not None:
        request.tenant.site_config = site_config
    return request


def _tree(page_style="sets", with_photo=True):
    parent = CategoryFactory(slug="catering", name={"de": "Catering"}, page_style=page_style)
    kid = CategoryFactory(
        slug="suppen",
        name={"de": "Suppen"},
        parent=parent,
        sort_order=1,
        images=[{"url": "/static/demo/photos/borscht-soup.webp"}] if with_photo else [],
    )
    ProductFactory(name={"de": "Borschtsch"}, category=kid)
    return parent, kid


# --- фото у подкатегорий ---------------------------------------------------


def test_subcategories_with_photos_render_as_tiles_on_any_page_style():
    """Фото были только у шаблона «kopfbild» — у «sets» шесть Gänge шли текстом."""
    _tree(page_style="sets")
    body = public_views.product_list(_req("/sortiment/catering/"), slug="catering").content.decode()
    assert "borscht-soup.webp" in body  # плитка с фото
    assert "/sortiment/suppen/" in body


def test_subcategories_without_photos_keep_the_text_grid():
    """Нет фото ни у одной подкатегории → прежняя текстовая сетка (fail-soft)."""
    _tree(page_style="sets", with_photo=False)
    body = public_views.product_list(_req("/sortiment/catering/"), slug="catering").content.decode()
    assert "Suppen" in body and "/sortiment/suppen/" in body
    assert "min-h-[4rem]" in body  # текстовая карточка, не плитка


# --- C-блоки СТРАНИЦЫ КАТЕГОРИИ -------------------------------------------


def test_category_host_is_accepted_and_garbage_is_not():
    assert siteconfig.is_page_block_host("catalog")
    assert siteconfig.is_page_block_host("catalog:catering")
    assert not siteconfig.is_page_block_host("catalog:")
    assert not siteconfig.is_page_block_host("catalog:Groß Buchstaben")
    assert not siteconfig.is_page_block_host("promo:catering")
    assert not siteconfig.is_page_block_host(None)
    assert siteconfig.category_host("catering") == "catalog:catering"
    assert siteconfig.category_host("") == ""


def test_normalize_keeps_category_blocks_and_drops_unknown_hosts():
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "catalog:catering": [{"key": "gallery_ref", "id": "pb-1", "enabled": True}],
                "catalog:UNGÜLTIG": [{"key": "gallery_ref", "id": "pb-2", "enabled": True}],
            }
        }
    )
    assert "catalog:catering" in cfg["page_blocks"]
    assert "catalog:UNGÜLTIG" not in cfg["page_blocks"]


def test_category_blocks_render_only_on_that_category():
    """Блоки «catalog:<slug>» видны на своей странице и больше нигде."""
    _tree()
    CategoryFactory(slug="shop", name={"de": "Shop"})
    cfg = {
        "gallery": [{"url": "/static/demo/photos/vegan-buffet.webp", "caption": "Buffet"}],
        "page_blocks": {
            "catalog:catering": [{"key": "gallery_ref", "id": "pb-kit-1", "enabled": True}]
        },
    }
    own = public_views.product_list(
        _req("/sortiment/catering/", site_config=cfg), slug="catering"
    ).content.decode()
    assert 'data-pb-host="catalog:catering"' in own

    other = public_views.product_list(
        _req("/sortiment/shop/", site_config=cfg), slug="shop"
    ).content.decode()
    assert "data-pb-host" not in other
    root = public_views.product_list(_req("/sortiment/", site_config=cfg)).content.decode()
    assert 'data-pb-host="catalog:catering"' not in root
