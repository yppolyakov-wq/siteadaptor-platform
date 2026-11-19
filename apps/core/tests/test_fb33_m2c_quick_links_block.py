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
        block = {"key": "quick_links", "id": "q", "enabled": True, "data": {"set": "shop"}}
        cfg["sections"] = [*cfg["sections"], block]
        return cfg

    monkeypatch.setattr(siteconfig, "normalize", with_block)
    html_after, _ctx = _render(style, "shop")
    assert tiles not in _squash(html_after)
    if style in ("accent", "split", "fullscreen"):
        assert "data-hero-cta" in html_after  # кнопка баннера возвращается


def _site(widget, block=None):
    return {"site_defaults": {"hero_widget": widget}, "sections": [block] if block else []}


def test_banner_hands_tiles_to_the_block_only_when_it_draws_them():
    """Ревью M2c-1 H1: пустой (только что добавленный) или скрытый блок плитки не прячет."""
    on = {"key": "quick_links", "id": "q", "enabled": True, "data": {"set": "shop"}}
    assert siteui.banner_tiles(_site("shop")) == "shop"
    assert siteui.banner_tiles(_site("shop", on)) == ""
    assert siteui.banner_tiles(_site("shop", {**on, "enabled": False})) == "shop"
    assert siteui.banner_tiles(_site("shop", {**on, "data": {}})) == "shop"
    assert siteui.banner_tiles(_site("")) == ""


@pytest.mark.parametrize("widget", ("stays", "services"))
def test_date_search_and_services_never_leave_the_banner(widget):
    """Форму дат и топ услуг блок не рисует — баннер их не прячет (до переноса M2c-2)."""
    on = {"key": "quick_links", "id": "q", "enabled": True, "data": {"set": "shop"}}
    assert siteui.banner_tiles(_site(widget, on)) == widget


def test_slider_uses_the_same_rule():
    import pathlib

    src = pathlib.Path("templates/storefront/sections/_hero_slider.html").read_text()
    assert "{% if site|banner_tiles %}" in src
    assert "{% if site.site_defaults.hero_widget" not in src


def test_block_with_no_tiles_left_draws_no_empty_region(monkeypatch):
    """Ревью M2c-1 M3: все плитки набора скрыты (модули выключены) — без пустого landmark."""
    monkeypatch.setattr(siteui, "render_to_string", lambda *a, **kw: "  \n ")
    html = _block_html({"set": "retreat"})
    assert "data-block-quick-links" not in html


def test_block_works_on_other_pages_too():
    """Блок можно поставить на любую страницу (M5 — на 404); плитки баннера главной
    он не прячет — их прячет только блок на самой главной."""
    keys = [k for g in site_schema.add_groups("text") for k, _lab in g["options"]]
    assert "quick_links" in keys
    assert siteui.banner_tiles({"site_defaults": {"hero_widget": "shop"}, "sections": []}) == "shop"


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
