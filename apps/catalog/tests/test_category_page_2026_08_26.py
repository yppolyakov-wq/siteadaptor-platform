"""Фидбэк 2026-08-26 по странице `/sortiment/catering/`.

Три вещи, которых на ней не было: фото у подкатегорий (текстовые карточки при
любом шаблоне, кроме «kopfbild»), виды отображения у наборов меню и собственные
C-блоки страницы (галерея/отзывы/команда были возможны только на ВЕСЬ каталог).
"""

import json
import re

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
    assert siteconfig.is_page_block_host("catalog:Sommer_2026")  # SlugField допускает
    assert not siteconfig.is_page_block_host("catalog:")
    assert not siteconfig.is_page_block_host("catalog:zwei woerter")
    assert not siteconfig.is_page_block_host("catalog:" + "x" * 61)
    assert not siteconfig.is_page_block_host("promo:catering")
    assert not siteconfig.is_page_block_host(None)
    assert siteconfig.category_host("catering") == "catalog:catering"
    assert siteconfig.category_host("") == ""


def test_normalize_keeps_category_blocks_and_drops_unknown_hosts():
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "catalog:catering": [{"key": "gallery_ref", "id": "pb-1", "enabled": True}],
                "catalog:kein slug": [{"key": "gallery_ref", "id": "pb-2", "enabled": True}],
            }
        }
    )
    assert "catalog:catering" in cfg["page_blocks"]
    assert "catalog:kein slug" not in cfg["page_blocks"]


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


# --- Studio: страница категории достижима, «+» кладёт блок в её хост ---------


def _builder_req(tenant, data=None):
    import uuid

    from django.contrib.auth import get_user_model

    factory = RequestFactory()
    request = (
        factory.post("/dashboard/site/home/", data)
        if data is not None
        else factory.get("/dashboard/site/home/")
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    ident = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{ident}", email=f"o-{ident}@t.de", password="pw12345678"
    )
    return request


def test_studio_lists_category_pages_and_inserts_into_their_host():
    """Без записи в preview_pages Studio не могла открыть страницу категории —
    панель показывала бы настройки главной, а «+» слал бы блок не в тот хост."""
    from apps.core import views as core_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(slug="cbcat", name="X")
    CategoryFactory(slug="catering", name={"de": "Catering"})
    body = core_views.home_builder_view(_builder_req(tenant)).content.decode()
    # страница категории — в переключателе превью, с группой каталога
    assert "/sortiment/catering/" in body
    groups = json.loads(re.search(r"var PAGE_GROUPS = (\{.*?\});", body, re.S).group(1))
    assert groups["/sortiment/catering/"] == "catalog"

    core_views.home_builder_view(
        _builder_req(
            tenant,
            {"action": "add_block", "block_type": "gallery_ref", "page_key": "catalog:catering"},
        )
    )
    tenant.refresh_from_db()
    blocks = siteconfig.normalize(tenant.site_config)["page_blocks"]
    assert [b["key"] for b in blocks["catalog:catering"]] == ["gallery_ref"]
    assert "catalog" not in blocks  # общий хост каталога не тронут
