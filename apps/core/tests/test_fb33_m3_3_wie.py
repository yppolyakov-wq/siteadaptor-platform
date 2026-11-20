"""FB-33 M3-3abc: вкладка «Wie anordnen» окна блока (`docs/fb33-editor-model-2026-11-19.md`
§«План M3», подсрезы M3-3a «виды картинками», M3-3b «Platz», M3-3c «как выглядит список»;
макеты M0-1, M0-3, M0-8, M0-9).

Плитки строятся из прежних пунктов (`fill_options`, `switch_options`, `width_choices`) —
имена полей и операции прежние, правка идёт тем же писателем."""

import re

import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.core import block_catalog, block_views
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_1b_window_cancel import _drafts, _home_item, _post
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "team", "enabled": True},
        {"key": "gallery", "enabled": True, "style": "strip"},
        {"key": "faq", "enabled": True},
        {"key": "categories", "enabled": True},
        {"key": "products", "enabled": True},
        {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Hallo", "body": "Welt"}},
        {"key": "list", "id": "l1", "enabled": True, "data": {"source": "products"}},
    ],
    "page_blocks": {
        "info": [
            {"key": "team_ref", "id": "tr1", "enabled": True},
            {"key": "gallery_ref", "id": "gr1", "enabled": True},
        ]
    },
}


def _browser(cfg=None):
    tenant = _tenant()
    tenant.site_config = cfg or CFG
    tenant.save()
    return Browser(tenant)


def _get(b, query):
    with translation.override("de"):
        return b.get(query)


def _thumb(src, key):
    html = render_to_string("tenant/_style_thumb.html", {"key": key, "src": src})
    return re.search(r'data-style-thumb="([^"]+)"', html).group(1)


# ─────────────────────────────── M3-3a: виды картинками ───────────────────────────────


@pytest.mark.parametrize("base", sorted(block_views.TILE_SECTIONS))
def test_every_section_view_has_its_own_thumb(base):
    views = ["", *siteconfig.SECTION_STYLES[base]]
    thumbs = [_thumb(base, v) for v in views]
    assert len(set(thumbs)) == len(views), dict(zip(views, thumbs, strict=True))
    assert all(t.startswith(f"{base}-") for t in thumbs)


def test_family_views_have_their_own_thumbs_and_tile_labels():
    with translation.override("de"):
        tiles = block_views.family_tiles(block_catalog.switch_options("text"), "text")
        assert [(t["value"], t["label"]) for t in tiles] == [
            ("text", "Text"),
            ("image_text", "Foto + Text"),
        ]
        assert tiles[0]["checked"] and not tiles[1]["checked"]
        # «Nur Text» остаётся подписью в «+ Block» (решение владельца)
        assert block_catalog.menu_label("text") == "Text · Nur Text"
    assert _thumb("family", "text") != _thumb("family", "image_text")


@pytest.mark.parametrize(
    "query, name",
    [
        ("?seite=home&block=team", "team"),
        ("?seite=home&block=gallery", "gallery"),
        ("?seite=home&block=faq", "faq"),
        ("?seite=text&block=tr1", "team_ref"),
        ("?seite=text&block=gr1", "gallery_ref"),
    ],
)
def test_section_view_is_a_radio_group_of_tiles(query, name):
    html = _panel(_get(_browser(), query))
    tiles = html[html.index('data-schema-view-tiles="style"') :]
    tiles = tiles[: tiles.index("</fieldset>")]
    assert "<legend" in tiles and "Darstellung" in tiles
    radios = re.findall(r'<input type="radio" name="f_style" value="([^"]*)"', tiles)
    base = name.removesuffix("_ref")
    assert radios == ["", *siteconfig.SECTION_STYLES[base]]
    assert tiles.count("min-h-[44px]") == len(radios)
    assert 'name="f_style"' not in html.replace(tiles, "")  # больше нет второго выбора
    assert "<select" not in tiles
    # форма полей прежняя: без скриптов — «Übernehmen»
    form = html[html.rindex("<form", 0, html.index("data-schema-view-tiles")) :]
    assert "data-schema-fields" in form[:200] and 'value="update"' in form


def test_saved_section_view_is_the_checked_tile():
    html = _panel(_get(_browser(), "?seite=home&block=gallery"))
    assert re.search(r'name="f_style" value="strip" class="sr-only" checked', html)


def test_section_view_tile_writes_the_same_field():
    b = _browser()
    b.get("?seite=home&block=team")
    _post(b, seite="home", ref="team", op="update", panel_present="1", f_style="circles")
    assert _home_item(b, "team")["style"] == "circles"
    _post(b, seite="home", ref="team", op="update", panel_present="1", f_style="")
    assert "style" not in _home_item(b, "team")


def test_ref_block_without_own_view_says_standard():
    """Ссылочный блок без своего вида — честно «Standard» (решение владельца), не «как на
    главной»."""
    html = _panel(_get(_browser(), "?seite=text&block=tr1"))
    first = re.search(
        r'value="" class="sr-only"[^>]*>.*?<span class="font-semibold">([^<]+)', html, flags=re.S
    )
    assert first.group(1) == "Standard"


def test_family_switch_is_tiles_with_the_same_operation():
    b = _browser()
    html = _panel(_get(b, "?seite=home&block=t1"))
    form = re.search(r"<form[^>]*data-schema-switch.*?</form>", html, flags=re.S).group(0)
    assert '<input type="hidden" name="op" value="switch">' in form
    assert re.findall(r'<button name="value" value="([^"]+)"', form) == ["text", "image_text"]
    assert re.search(r'value="text" aria-pressed="true"', form)
    assert "<legend" in form and "Überschrift + Absätze" in form and "<select" not in form
    _post(b, seite="home", ref="t1", op="switch", value="image_text")
    assert _home_item(b, "t1")["key"] == "image_text"


def test_regale_says_where_the_product_look_is_changed():
    """M0-3: «Regale» без своих карточек — ссылка на ★-строку товаров (в каталоге «Regale»
    доступны только при подкатегориях — проверяем построитель и разметку напрямую)."""
    blocks = [{"ref": "categories", "key": "categories", "cblock": False, "main": False},
              {"ref": "main", "key": "main", "cblock": False, "main": True}]  # fmt: skip
    regale = {"key": "categories", "catview": {"value": "regale", "tiles": []}}
    assert block_views.regale_link(blocks, regale) == "main"
    assert block_views.regale_link(blocks, {**regale, "catview": {"value": "auto"}}) is None
    block_views.decorate(regale, blocks)
    with translation.override("de"):
        html = render_to_string(
            "tenant/_bw_views.html",
            {"selected": {**regale, "ref": "categories"}, "code": "catalog"},
        )
    assert "data-schema-regale-hint" in html and "Regale hat keine eigenen Karten" in html
    assert "block=main&amp;tab=wie" in html
    other = _panel(_get(_browser(), "?seite=catalog&block=categories"))
    assert "data-schema-regale-hint" not in other


def test_regale_on_the_home_page_points_to_the_products_block():
    b = _browser()
    b.get("?seite=home&block=categories")
    _post(b, seite="home", ref="categories", op="update", panel_present="1", f_style="regale")
    html = _panel(_get(b, "?seite=home&block=categories"))
    assert "data-schema-regale-hint" in html and "block=products&amp;tab=wie" in html
    assert _drafts(b)["home"]
