"""FB-33 M2c-1: блок «Schnellzugriff» (`quick_links`) — плитки-входы отдельным блоком.

С M2c-4 баннер плиток не рисует вовсе (ключ `site_defaults.hero_widget` снят — замки в
`test_fb33_m2c4_no_hero_widget.py`); плитки — только этот блок.
"""

import re

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import block_catalog, hero_tiles, site_schema
from apps.core import quick_links_migration as qlm
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
    assert set(hero_tiles.QUICK_LINK_SETS) == set(qlm.LEGACY_WIDGETS) - {"stays", "services"}
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


def test_block_with_no_tiles_left_draws_no_empty_region(monkeypatch):
    """Ревью M2c-1 M3: все плитки набора скрыты (модули выключены) — без пустого landmark."""
    monkeypatch.setattr(siteui, "render_to_string", lambda *a, **kw: "  \n ")
    html = _block_html({"set": "retreat"})
    assert "data-block-quick-links" not in html


def test_block_works_on_other_pages_too():
    """Блок можно поставить на любую страницу (M5 — на 404)."""
    keys = [k for g in site_schema.add_groups("text") for k, _lab in g["options"]]
    assert "quick_links" in keys


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
