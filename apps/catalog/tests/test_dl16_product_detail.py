"""DL-16.6 — деталь товара: D1 мобильная лента галереи, D2 раскладка «Tabs», D3 полоса
доверия, D4 лента похожих (> ряда) + «Zuletzt angesehen» (localStorage → фрагмент)."""

from __future__ import annotations

import re
import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.catalog.slugs import RESERVED_SLUGS
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/sortiment/", tenant=None, params=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build(name="Hofladen", address="Feldweg 1")
    return request


def _detail(product, tenant=None, config=None):
    req = _req(f"/sortiment/{product.pk}/", tenant)
    if config is not None:
        req.tenant.site_config = config
    return public_views.product_detail(req, pk=product.pk).content.decode()


CARD_WRAP = '<div class="w-44 sm:w-56 shrink-0 flex [&>*]:w-full">'


# --- D2: раскладка ------------------------------------------------------------
def test_product_detail_layout_presence_minimal():
    assert "layout" not in siteconfig.normalize({})["product_detail"]
    cfg = siteconfig.normalize({"product_detail": {"layout": "tabs", "hidden": ["info"]}})
    assert cfg["product_detail"]["layout"] == "tabs"
    assert siteconfig.product_detail_layout(cfg) == "tabs"
    assert siteconfig.product_detail_hidden(cfg) == {"info"}  # hidden живёт рядом
    cfg = siteconfig.normalize({"product_detail": {"layout": "grid"}})
    assert "layout" not in cfg["product_detail"] and siteconfig.product_detail_layout(cfg) == ""


def test_default_layout_keeps_aside_description_and_no_tabs():
    p = ProductFactory(description={"de": "Frisch aus dem Ofen."}, origin="Allgäu")
    body = _detail(p)
    assert "data-pd-tabs" not in body
    assert body.count('data-edit-field="description"') == 1
    # описание и Kennzeichnung — в правой колонке (до buy-box), как раньше
    assert body.index('data-edit-field="description"') < body.index("/warenkorb/add/")
    assert body.index("Allgäu") < body.index("/warenkorb/add/")
    assert 'id="bewertungen"' in body


def test_tabs_layout_moves_sections_into_panels():
    p = ProductFactory(description={"de": "Frisch aus dem Ofen."}, origin="Allgäu")
    body = _detail(p, config={"product_detail": {"layout": "tabs"}})
    assert "data-pd-tabs" in body and "pd-tabs-on" in body  # JS переключает класс
    for key in ("description", "info", "reviews"):
        assert f'data-pd-panel="{key}"' in body, key
    assert body.count('data-edit-field="description"') == 1  # один раз — в панели
    # секции ушли из правой колонки: описание и Kennzeichnung после buy-box
    assert body.index("/warenkorb/add/") < body.index('data-edit-field="description"')
    assert body.index("/warenkorb/add/") < body.index("Allgäu")
    assert 'id="bewertungen"' in body  # якорь рейтинга жив в панели отзывов


def test_tabs_layout_respects_hidden_registry_and_empty_info():
    p = ProductFactory(description={"de": "Text."})  # без Kennzeichnung
    body = _detail(p, config={"product_detail": {"layout": "tabs", "hidden": ["reviews"]}})
    assert 'data-pd-panel="description"' in body
    assert 'data-pd-panel="info"' not in body  # нет данных — нет панели
    assert 'data-pd-panel="reviews"' not in body and 'id="bewertungen"' not in body


# --- D3: полоса доверия --------------------------------------------------------
def test_trust_strip_lists_only_facts():
    p = ProductFactory()
    tenant = TenantFactory.build(
        name="H",
        delivery_enabled=True,
        opening_hours_structured={str(d): ["00:00", "23:59"] for d in range(7)},
    )
    body = _detail(p, tenant)
    strip = body[body.index("data-trust-strip") :]
    strip = strip[: strip.index("</ul>")]
    assert "Abholung im Laden" in strip and "heute bis 23:59" in strip
    assert "Lieferung" in strip and "00:00–23:59" in strip


def test_trust_strip_absent_without_facts():
    p = ProductFactory()
    tenant = TenantFactory.build(name="H", disabled_modules=["orders"], delivery_enabled=False)
    body = _detail(p, tenant)
    assert "data-trust-strip" not in body


# --- D1: галерея ---------------------------------------------------------------
def test_gallery_mobile_strip_only_for_multiple_photos():
    two = ProductFactory(images=[{"url": "/a.jpg", "id": "1"}, {"url": "/b.jpg", "id": "2"}])
    one = ProductFactory(images=[{"url": "/a.jpg", "id": "1"}])
    body = _detail(two)
    assert "data-media-strip" in body and "data-media-thumbs" in body
    assert body.count('class="js-media-strip-item') == 2  # не голое имя — оно и в JS
    assert "js-media-zoom" in body and "js-lb-img" in body  # лайтбокс цел
    body = _detail(one)
    assert "data-media-strip" not in body and "data-media-thumbs" not in body
    assert "js-media-zoom" in body


# --- D4: похожие ---------------------------------------------------------------
def _related(n):
    cat = CategoryFactory(slug=f"brot{n}", name={"de": "Brot"})
    p = ProductFactory(name={"de": "Haupt"}, category=cat)
    for i in range(n):
        ProductFactory(name={"de": f"Rel {i}"}, category=cat)
    return p


def test_related_strip_only_when_more_than_a_row():
    body = _detail(_related(2))
    assert "data-related-strip" not in body and "lg:grid-cols-4" in body
    body = _detail(_related(5))
    assert "data-related-strip" in body and "data-sf-slider" in body
    strip = body[body.index("data-related-strip") :]
    strip = strip[: strip.index("data-recent-strip")]
    assert strip.count(CARD_WRAP) == 5


def test_related_capped_at_eight_and_studio_preset_keeps_grid():
    p = _related(10)
    body = _detail(p)
    strip = body[body.index("data-related-strip") :]
    strip = strip[: strip.index("data-recent-strip")]
    assert strip.count(CARD_WRAP) == 8
    # scroll-режим Studio → лента движка раскладок (sf-scroll-grid), без второго слайдера
    body = _detail(p, config={"detail_related_layout": {"scroll": True}})
    assert "data-related-strip" not in body and "sf-scroll-grid" in body


# --- D4: «Zuletzt angesehen» ---------------------------------------------------
def test_recent_container_and_endpoint_reserved():
    p = ProductFactory()
    body = _detail(p)
    assert f'data-recent-strip data-current="{p.pk}" data-url="/sortiment/zuletzt/" hidden' in body
    assert "sf_seen_products" in body  # localStorage-ключ, не сессия
    assert resolve("/sortiment/zuletzt/").func is public_views.products_recent
    assert reverse("storefront-products-recent") == "/sortiment/zuletzt/"
    assert "zuletzt" in RESERVED_SLUGS


def test_recent_fragment_keeps_client_order_and_drops_garbage():
    a = ProductFactory(name={"de": "Alpha"})
    b = ProductFactory(name={"de": "Beta"})
    dead = ProductFactory(name={"de": "Tot"}, is_active=False)
    ids = ",".join([str(b.pk), "not-a-uuid", str(dead.pk), str(uuid.uuid4()), str(a.pk)])
    resp = public_views.products_recent(_req("/sortiment/zuletzt/", params={"ids": ids}))
    body = resp.content.decode()
    assert body.index("Beta") < body.index("Alpha")
    assert "Tot" not in body and body.count(CARD_WRAP) == 2
    # пусто / мусор → пустой ответ (JS не раскрывает блок)
    assert public_views.products_recent(_req("/sortiment/zuletzt/")).content == b""
    assert (
        public_views.products_recent(_req("/sortiment/zuletzt/", params={"ids": "x"})).content
        == b""
    )


def test_recent_fragment_caps_at_eight():
    ps = [ProductFactory(name={"de": f"R{i}"}) for i in range(10)]
    ids = ",".join(str(p.pk) for p in ps)
    body = public_views.products_recent(
        _req("/sortiment/zuletzt/", params={"ids": ids})
    ).content.decode()
    assert body.count(CARD_WRAP) == 8
    # CI #2326: голый substring ловил случайный CSRF-токен («…5GR8iyd…») — сверяем
    # заголовок карточки, а не любой байт страницы.
    assert ">R8</h3>" not in body and ">R9</h3>" not in body
    assert ">R0</h3>" in body


# --- Studio: селект «Aufbau» --------------------------------------------------
def test_studio_layout_select_and_save():
    from apps.core import views

    tenant = TenantFactory(
        schema_name="public", slug="dl166", name="DL166", enabled_modules=["catalog"]
    )
    from apps.core.tests.test_home_builder import _request

    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert re.search(r'<select name="pd_layout"[^>]*>\s*<option value="">', body)
    data = {"order_hero": "1", "enabled_hero": "on", "pd_present": "1", "pd_layout": "tabs"}
    for k in siteconfig.PRODUCT_DETAIL_SECTION_KEYS:
        data[f"pd_visible_{k}"] = "on"
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    assert siteconfig.product_detail_layout(siteconfig.normalize(tenant.site_config)) == "tabs"
    # повторный Save без селекта-«tabs» → ключ уходит (presence-minimal), hidden цел
    data["pd_layout"] = ""
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.product_detail_layout(cfg) == "" and "layout" not in cfg["product_detail"]
