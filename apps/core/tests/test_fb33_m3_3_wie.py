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
            ("textpage", "Von einer Seite"),  # M3-3d (стык стопки)
        ]
        assert tiles[2]["hint"] == "Text einer Seite übernehmen"
        assert tiles[0]["checked"] and not tiles[1]["checked"]
        # «Nur Text» остаётся подписью в «+ Block» (решение владельца)
        assert block_catalog.menu_label("text") == "Text · Nur Text"
    thumbs = [_thumb("family", k) for k in ("text", "image_text", "textpage")]
    assert len(set(thumbs)) == 3, thumbs


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
    assert re.findall(r'<button name="value" value="([^"]+)"', form) == [
        "text",
        "image_text",
        "textpage",
    ]
    assert re.search(r'value="text" aria-pressed="true"', form)
    assert "<legend" in form and "Überschrift + Absätze" in form and "<select" not in form
    _post(b, seite="home", ref="t1", op="switch", value="image_text")
    assert _home_item(b, "t1")["key"] == "image_text"


# ───────────────────── стык стопки: M3-3a ↔ M3-3d «Von einer Seite» ─────────────────────

KEEPS_BOTH = "Beide Fassungen bleiben gespeichert — umschalten verliert nichts."


def test_text_source_tile_and_the_note_that_both_versions_are_kept():
    """M0-9: плитка «Von einer Seite» со своей схемой и плашка — там, где среди плиток есть
    смена источника текста (`block_catalog.switch_keeps_both`)."""
    b = _browser()
    html = _panel(_get(b, "?seite=home&block=t1"))
    form = re.search(r"<form[^>]*data-schema-switch.*?</form>", html, flags=re.S).group(0)
    tile = re.search(r'<button name="value" value="textpage".*?</button>', form, flags=re.S)
    assert 'data-style-thumb="family-textpage"' in tile.group(0)
    assert "Von einer Seite" in tile.group(0) and "Text einer Seite übernehmen" in tile.group(0)
    assert form.count(KEEPS_BOTH) == 1 and "data-schema-keeps-both" in form
    # туда и обратно — плашка и у «Von einer Seite»
    _post(b, seite="home", ref="t1", op="switch", value="textpage")
    assert _home_item(b, "t1")["key"] == "textpage"
    back = _panel(_get(b, "?seite=home&block=t1"))
    assert KEEPS_BOTH in back and re.search(r'value="textpage" aria-pressed="true"', back)


def test_the_note_follows_switch_keeps_both_not_a_second_list():
    with translation.override("de"):
        for key in ("text", "image_text", "textpage"):
            tiles = block_views.family_tiles(block_catalog.switch_options(key), key)
            assert [t["keeps_both"] for t in tiles] == [
                block_catalog.switch_keeps_both(key, t["value"]) for t in tiles
            ]
    html = render_to_string(
        "tenant/_bw_switch.html",
        {"selected": {"ref": "x", "view_options": [("a", "A")], "view_tiles": []}},
    )
    assert KEEPS_BOTH not in html
    # семья без смены источника — без плашки
    selected = {"key": "text", "view_options": [("text", "T"), ("image_text", "F")]}
    block_views.decorate(selected, [])
    assert selected["view_keeps_both"] is False


# ───────────────────── стык стопки: M3-3a ↔ M2b-2a виды FAQ по странице ─────────────────────


def _faq_tiles(host, value=""):
    from apps.core import site_schema

    data = {"style": value} if value else {}
    block = {"key": "faq_ref", "cblock": True, "fields": site_schema.panel_fields({"key": "faq_ref", "data": data})}  # fmt: skip
    with translation.override("de"):
        site_schema.fill_options(block, host)
        block_views.decorate(block, [], {}, host)
    field = block["fields"][0]
    assert [t["value"] for t in field["tiles"]] == [str(v) for v, _lab in field["options"]]
    assert field["thumb_src"] == "faq"
    return field["tiles"]


@pytest.mark.parametrize("host", ["service_detail", "event_detail", f"service:{'c' * 32}"])
def test_faq_tiles_on_a_detail_page_are_its_three_views(host):
    from apps.core import faq_views

    tiles = _faq_tiles(host)
    with translation.override("de"):
        assert [(t["value"], t["label"], t["hint"]) for t in tiles] == [
            (v.key, str(v.label), str(v.hint)) for v in faq_views.views(host)
        ]
    assert [t["label"] for t in tiles] == ["Akkordeon", "Liste", "Zwei Spalten"]
    assert [t["checked"] for t in tiles] == [True, False, False]


def test_faq_tiles_keep_a_saved_view_the_detail_page_does_not_offer():
    tiles = _faq_tiles("service_detail", "cards")
    assert [t["value"] for t in tiles] == ["", "list", "twocol", "cards"]
    assert tiles[-1]["label"] == "Karten (nicht unter den Ansichten dieser Seite)"
    assert tiles[-1]["checked"] and tiles[-1]["hint"] == ""
    assert _thumb("faq", "cards") == "faq-cards"


@pytest.mark.parametrize("host", ["", "home", "catalog", "promo_detail"])
def test_faq_tiles_elsewhere_are_all_five_views_with_hints(host):
    tiles = _faq_tiles(host)
    assert [(t["label"], t["hint"]) for t in tiles] == [
        ("Akkordeon", "Antwort beim Antippen"),
        ("Liste", "alles offen"),
        ("Zwei Spalten", "Fragen nebeneinander"),
        ("Karten", "Fragen als Kacheln"),
        ("Nummeriert", "Fragen mit Nummern"),
    ]


def test_faq_tiles_of_the_home_window_show_the_registry_hints():
    html = _panel(_get(_browser(), "?seite=home&block=faq"))
    tiles = html[html.index('data-schema-view-tiles="style"') :]
    tiles = tiles[: tiles.index("</fieldset>")]
    assert re.findall(r'<span class="font-semibold">([^<]+)</span>', tiles) == [
        "Akkordeon",
        "Liste",
        "Zwei Spalten",
        "Karten",
        "Nummeriert",
    ]
    assert "Antwort beim Antippen" in tiles and "Fragen mit Nummern" in tiles


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


# ─────────────────────────────── M3-3b: секция «Platz» ───────────────────────────────


def _platz(html):
    return html[
        html.index("data-schema-platz") : html.index(
            "schema-width-hint", html.index("data-schema-platz") + 20
        )
    ]


@pytest.mark.parametrize(
    "query, ref", [("?seite=home&block=t1", "t1"), ("?seite=home&block=products", "products")]
)
def test_width_tiles_are_exactly_the_width_choices(query, ref):
    from apps.core import site_schema

    b = _browser()
    html = _panel(_get(b, query))
    box = html[
        html.index("data-schema-width") : html.index("</form>", html.index("data-schema-width"))
    ]
    sent = re.findall(r'<button name="value" value="([^"]+)"', box)
    item = next(
        i for i in siteconfig.normalize(CFG)["sections"] if (i.get("id") or i["key"]) == ref
    )
    allowed = [v for v, _lab in site_schema.width_choices(item)]
    big = [v for v in allowed if v in block_views.BIG_WIDTHS]
    assert sent == big + [v for v in allowed if v not in block_views.BIG_WIDTHS]
    assert big == ["contained", "w23", "w12", "w13"]  # четыре крупные (решение владельца)
    with translation.override("de"):
        for text in ("Breite auf dem Computer", "ganze Breite", "zwei Drittel", "halbe Breite"):
            assert text in box
    assert box.count("data-schema-width-bar") == len(sent)
    assert re.search(r'value="contained"[^>]*aria-pressed="true"', box)


def test_row_choice_only_for_a_narrow_block_and_is_the_newline_operation():
    b = _browser()
    assert "data-schema-reihe" not in _panel(_get(b, "?seite=home&block=t1"))
    b.get("?seite=home&block=t1")
    _post(b, seite="home", ref="t1", op="width", value="w13")
    html = _panel(_get(b, "?seite=home&block=t1"))
    form = re.search(r"<form[^>]*data-schema-reihe.*?</form>", html, flags=re.S).group(0)
    assert (
        "<legend" in form and "Neben dem vorigen Block" in form and "In einer neuen Reihe" in form
    )
    # выбранный способ — нажатая кнопка без действия; второй — операция newline
    assert re.findall(r'name="op" value="([^"]+)"', form) == ["newline"]
    assert re.search(
        r'<button type="button" aria-pressed="true"[^>]*data-schema-reihe-op="beside"', form
    )
    _post(b, seite="home", ref="t1", op="newline")
    assert _home_item(b, "t1")["newline"] is True
    html = _panel(_get(b, "?seite=home&block=t1"))
    form = re.search(r"<form[^>]*data-schema-reihe.*?</form>", html, flags=re.S).group(0)
    pressed = re.search(
        r'<button type="button" aria-pressed="true"[^>]*data-schema-reihe-op="([a-z]+)"', form
    )
    assert pressed.group(1) == "newline"
    _post(b, seite="home", ref="t1", op="newline")  # «Neben dem vorigen Block» — снова рядом
    assert not _home_item(b, "t1").get("newline")


def test_row_choice_names_the_neighbours():
    b = _browser()
    b.get("?seite=home&block=t1")
    _post(b, seite="home", ref="l1", op="width", value="w12")
    _post(b, seite="home", ref="t1", op="width", value="w12")
    with translation.override("de"):
        html = _panel(b.get("?seite=home&block=l1"))
    assert "zusammen eine Reihe" in html


def test_platz_says_the_phone_stacks_everything():
    with translation.override("de"):
        html = _panel(_browser().get("?seite=home&block=t1"))
    assert "Auf dem Telefon stehen alle Blöcke untereinander, immer volle Breite." in html
    assert "<h4" in _platz(html)


# ──────────────── M3-3c: как выглядит список, наследование и сброс ────────────────


def _forms_of(html):
    return re.findall(r"<form\b.*?</form>", html, flags=re.S)


def _listview(html):
    return next(f for f in _forms_of(html) if "data-schema-listview" in f[:200])


def _was_form(html):
    return next(
        f for f in _forms_of(html) if "data-schema-list" in f[:200] and "listview" not in f[:200]
    )


@pytest.mark.parametrize("query", ["?seite=home&block=l1", "?seite=home&block=products"])
def test_list_look_is_its_own_form_in_wie_anordnen(query):
    from apps.core.tests.test_fb33_m3_window_before import _capture

    b = _browser()
    html, _view, selected = _capture(b, query)
    panel = _panel(html)
    wie = panel[panel.index('data-window-tab="wie"') :]
    wie = wie[: wie.index("</section>")]
    assert "data-schema-listview" in wie
    look = _listview(panel)
    for name in ("f_out", "f_cols", "f_rows"):
        assert f'name="{name}"' in look and f'name="{name}"' not in _was_form(panel)
    assert 'name="f_style"' in look and 'name="f_style"' not in _was_form(panel)
    assert "data-schema-view-tiles" in look
    assert not re.search(r'<select[^>]*name="f_(style|out)"', look)  # вид — плитками


def test_list_look_form_does_not_touch_the_what_fields_and_back():
    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_limit="5", f_title="Neu")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_cols="2", f_out="slider")
    data = _home_item(b, "l1")["data"]
    assert data["limit"] == 5 and data["title"] == "Neu" and data["cols"] == 2
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_limit="7")
    data = _home_item(b, "l1")["data"]
    assert data["cols"] == 2 and data["out"] == "slider" and data["limit"] == 7


def _reset_form(html):
    form = re.search(r"<form[^>]*data-schema-reset-form.*?</form>", html, flags=re.S)
    return form.group(0) if form else ""


def _line(html):
    return re.search(r"<p[^>]*data-schema-inherit>.*?</p>", html, flags=re.S).group(0)


def test_reset_button_is_not_inside_a_script_applied_form():
    """Ревью M3-3 (1): aufbau.js прячет первую `button[value=update]` формы `data-schema-list` —
    кнопка сброса живёт в своей форме ПОСЛЕ формы вида и под этот селектор не попадает."""
    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_cols="2")
    html = _panel(_get(b, "?seite=home&block=l1"))
    look = _listview(html)
    assert "data-schema-view-reset" not in look and 'form="' not in look
    reset = _reset_form(html)
    assert "data-schema-view-reset" in reset and "data-schema-" + "list" not in reset[:120]
    assert not re.search(r'<button[^>]*value="update"', reset)
    assert html.index("data-schema-listview") < html.index("data-schema-reset-form")


def test_reset_brings_the_list_back_to_its_base_view_and_keeps_the_card():
    from apps.core import list_blocks

    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1",
          f_cols="2", f_out="slider", f_rows="2", f_limit="5", f_card="deal")  # fmt: skip
    assert _home_item(b, "l1")["data"]["card"] == "deal"
    html = _panel(_get(b, "?seite=home&block=l1"))
    assert "hier geändert gilt nur für diesen Block" in _line(html)
    sent = dict(re.findall(r'name="(f_[a-z]+)" value="([^"]*)"', _reset_form(html)))
    assert sent == {f"f_{k}": "" for k in block_views.VIEW_RESET_FIELDS}
    _post(b, seite="home", ref="l1", op="update", panel_present="1", **sent)
    data = _home_item(b, "l1")["data"]
    assert not {"cols", "out", "rows", "style"} & set(data)
    assert data["limit"] == 5  # «Welche» не тронуто
    assert data["card"] == "deal"  # «Kartenform» — не сбрасывается (M3-4)
    cfg = siteconfig.normalize({**CFG})
    # «Deal» сама ужимает колонки (грабля FB-33 M1) — это ось «Karte», сравниваем без неё
    view = {k: v for k, v in data.items() if k != "card"}
    eff = list_blocks.effective_view(cfg, view)
    assert eff["layout"] == list_blocks.base_view(cfg, view)["layout"]
    assert not _reset_form(_panel(_get(b, "?seite=home&block=l1")))


def test_inheritance_line_names_the_page_the_view_comes_from():
    cfg = {**CFG, "catalog_layout": {"preset": "cols3"}}
    b = _browser(cfg)
    html = _panel(_get(b, "?seite=home&block=l1"))
    assert "Wie auf der Seite „Katalog“: Raster · 3 Spalten" in _line(html)
    # FB-33 M5b-2 W1: настройки типа — у ★-строки страницы (`page_row_ref`), вкладка «Seite»
    assert "seite=catalog&amp;block=__page&amp;tab=seite" in html
    assert not _reset_form(html)  # своего вида у блока нет
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_cols="2")
    html = _panel(_get(b, "?seite=home&block=l1"))
    line = _line(html)
    # строка перечисляет ровно то, что у блока своё
    assert "Eigene Einstellung für diesen Block: Spalten — hier geändert" in line
    assert _reset_form(html)
    # без страницы-источника (плитки категорий) — честно «Standard»
    own = {**CFG, "sections": [*CFG["sections"], {"key": "list", "id": "l2", "enabled": True,
           "data": {"source": "categories"}}]}  # fmt: skip
    b = _browser(own)
    html = _panel(_get(b, "?seite=home&block=l2"))
    assert re.search(r"data-schema-inherit>Standard: Raster · \d Spalten</p>", html)
    b.get("?seite=home&block=l2")
    _post(b, seite="home", ref="l2", op="update", panel_present="1", f_style="square")
    line = _line(_panel(_get(b, "?seite=home&block=l2")))
    assert "Eigene Einstellung für diesen Block: " in line and "Spalten," not in line
    assert "hier geändert" not in line  # не наследует — «nur für diesen Block» не нужно


def test_link_actions_have_context_for_screen_readers():
    cfg = {**CFG, "catalog_layout": {"preset": "cols3"}}
    b = _browser(cfg)
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_cols="2")
    html = _panel(_get(b, "?seite=home&block=l1"))
    link = re.search(r"<a[^>]*data-schema-inherit-link.*?</a>", html, flags=re.S).group(0)
    assert "underline-offset-2" in link and "sr-only" in link and "Katalog" in link
    reset = _reset_form(html)
    assert "underline-offset-2" in reset and "Ansicht dieses Blocks" in reset


def test_builtin_list_reset_keeps_the_section_look():
    """«zurücksetzen» у встроенного списка — только раскладка; «Darstellung» секции остаётся
    (решение владельца)."""
    b = _browser()
    b.get("?seite=home&block=products")
    _post(b, seite="home", ref="products", op="update", panel_present="1",
          f_style="preisliste", f_limit="6")  # fmt: skip
    assert not _reset_form(_panel(_get(b, "?seite=home&block=products")))  # вид — не «своё»
    _post(b, seite="home", ref="products", op="update", panel_present="1",
          f_cols="2", f_out="slider")  # fmt: skip
    item = _home_item(b, "products")
    assert item["layout"]["cols"] == 2 and item["layout"]["scroll"]
    html = _panel(_get(b, "?seite=home&block=products"))
    sent = dict(re.findall(r'name="(f_[a-z]+)" value="([^"]*)"', _reset_form(html)))
    assert sent == {f"f_{k}": "" for k in block_views.BUILTIN_RESET_FIELDS}
    _post(b, seite="home", ref="products", op="update", panel_present="1", **sent)
    item = _home_item(b, "products")
    default = siteconfig.normalize_layout(None, siteconfig.GRID_SECTION_DEFAULTS["products"])
    assert item["layout"]["cols"] == default["cols"] and "scroll" not in item["layout"]
    assert item["style"] == "preisliste" and item["limit"] == 6
    assert not _reset_form(_panel(_get(b, "?seite=home&block=products")))


def test_update_without_changes_does_not_invent_a_draft():
    """Ревью M3-3 (4): «Übernehmen» без правок и пустые колонки у строки без своих колонок
    ничего не пишут."""
    from apps.core import site_schema

    item = {"key": "products", "enabled": True}
    assert site_schema._update_builtin(item, {"cols": "", "rows": "", "out": ""}) is False
    assert item == {"key": "products", "enabled": True}
    b = _browser()
    html = _panel(_get(b, "?seite=home&block=products"))
    sent = dict(re.findall(r'name="(f_[a-z]+)" value="([^"]*)"[^>]*checked', _listview(html)))
    _post(b, seite="home", ref="products", op="update", panel_present="1", **sent)
    from types import SimpleNamespace

    from apps.core import aufbau_draft

    assert "f_cols" in sent and "f_out" in sent  # прислано всё, что отмечено
    assert aufbau_draft.get(SimpleNamespace(session=b.session), "home") is None


def test_home_products_show_catalog_only_views_with_a_reason():
    with translation.override("de"):
        html = _listview(_panel(_browser().get("?seite=home&block=products")))
        for key in block_views.CATALOG_ONLY_PRODUCT_VIEWS:
            off = re.search(rf'data-schema-style-off="{key}">.*?</div>', html, flags=re.S)
            assert off and "Vorerst nur auf Katalogseiten." in off.group(0)
    assert 'value="schaufenster"' not in html  # не выбирается


def test_tiles_a11y_after_review():
    """Ревью a11y M3-3 (7): пояснение плитки — только внутри подписи, у недоступного вида —
    «Nicht verfügbar:» для читалки, фокус кнопок-плиток 3 px, ссылка «dort ändern» подчёркнута
    и с контекстом."""
    b = _browser()
    switch = _panel(_get(b, "?seite=home&block=t1"))
    look = _listview(_panel(_get(b, "?seite=home&block=products")))
    for html in (switch, look, _panel(_get(b, "?seite=home&block=team"))):
        assert 'aria-describedby="vt-' not in html
    assert "focus-visible:outline-[3px]" in switch.split("data-schema-switch")[1]
    assert look.count('<span class="sr-only">Nicht verfügbar: </span>') == 2
    with translation.override("de"):
        hint = render_to_string(
            "tenant/_schema_regale_hint.html", {"link": "main", "code": "catalog"}
        )
    assert "underline-offset-2" in hint and "sr-only" in hint and "Produkte" in hint
