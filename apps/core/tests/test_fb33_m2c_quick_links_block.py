"""FB-33 M2c-1: блок «Schnellzugriff» (`quick_links`) — плитки-входы отдельным блоком.

Пока у сайта блока нет, баннер рисует плитки как раньше (M2c-0). Блок стоит на главной —
баннер плиток не рисует, а у видов, где плитки заменяли кнопку, кнопка возвращается.
"""

import re

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import block_catalog, hero_tiles, site_schema
from apps.core.tests.test_fb33_m2c_quick_links_before import _render, _squash, _tiles_html
from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_block_keeps_only_a_known_link_set():
    clean = siteconfig._clean_cblock_data
    assert clean("quick_links", {"set": "friseur", "x": 1}) == {"set": "friseur"}
    assert clean("quick_links", {"set": "stays"}) == {}  # форма дат — не ссылки
    assert clean("quick_links", {"set": "evil"}) == {}


def test_every_link_set_has_a_label_and_the_block_a_family():
    assert set(hero_tiles.QUICK_LINK_LABELS) == set(hero_tiles.QUICK_LINK_SETS)
    assert set(hero_tiles.QUICK_LINK_SETS) == set(siteconfig.HERO_WIDGETS) - {"stays", "services"}
    assert block_catalog.family_of("quick_links").key == "quick_links"
    assert not block_catalog.library_entry("quick_links").studio  # ставится в «Seitenaufbau»


def _block_html(data):
    tenant_req = RequestFactory().get("/")
    from apps.tenants.tests.factories import TenantFactory

    tenant_req.tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    tpl = Template("{% load siteui %}{% render_block b %}")
    ctx = {"request": tenant_req, "site": siteconfig.normalize({}), "modules": {}}
    return tpl.render(Context({**ctx, "b": {"key": "quick_links", "id": "q1", "data": data}}))


def test_block_draws_the_same_tiles_as_the_banner_did():
    _html, ctx = _render("plain", "shop")
    html = _block_html({"set": "shop"})
    assert "data-block-quick-links" in html and 'aria-label="Schnellzugriff"' in html
    assert _tiles_html("shop", ctx) in _squash(html)


def test_empty_block_draws_nothing():
    assert "data-block-quick-links" not in _block_html({})


@pytest.mark.parametrize("style", ("plain", "accent", "split", "fullscreen"))
def test_with_the_block_on_home_the_banner_stops_drawing_tiles(style, monkeypatch):
    html_before, ctx = _render(style, "shop")
    tiles = _tiles_html("shop", ctx)
    assert tiles in _squash(html_before)
    real = siteconfig.normalize

    def with_block(raw):
        cfg = real(raw)
        cfg["sections"] = [*cfg["sections"], {"key": "quick_links", "id": "q", "enabled": True}]
        return cfg

    monkeypatch.setattr(siteconfig, "normalize", with_block)
    html_after, _ctx = _render(style, "shop")
    assert tiles not in _squash(html_after)
    if style in ("accent", "split", "fullscreen"):
        assert "data-hero-cta" in html_after  # кнопка баннера возвращается


def test_hidden_block_keeps_the_old_banner_tiles():
    site = {"sections": [{"key": "quick_links", "id": "q", "enabled": False}]}
    assert not siteui.has_home_block(site, "quick_links")
    site["sections"][0]["enabled"] = True
    assert siteui.has_home_block(site, "quick_links")


def test_panel_offers_the_link_sets():
    block = {"key": "quick_links", "fields": site_schema.panel_fields({"key": "quick_links"})}
    site_schema.fill_options(block, "")
    values = [v for v, _lab in block["fields"][0]["options"]]
    assert values == ["", *hero_tiles.QUICK_LINK_SETS]


def test_studio_save_keeps_the_chosen_set():
    saved = [{"key": "quick_links", "id": "q1", "data": {"set": "friseur"}}]
    posted = [{"key": "quick_links", "id": "q1", "data": {}}]
    assert site_schema.merge_structure(saved, posted)[0]["data"] == {"set": "friseur"}


def test_add_menu_offers_the_block_on_home():
    keys = [k for g in site_schema.add_groups("home") for k, _lab in g["options"]]
    assert "quick_links" in keys
    assert re.search("quick_links", str(site_schema.add_groups("home")[0]))
