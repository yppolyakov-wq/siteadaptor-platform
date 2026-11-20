"""FB-33 M3-4: вкладка «Karte» окна блока (`docs/fb33-editor-model-2026-11-19.md` §«План M3»,
срез M3-4; макет M0-2). Поле «Kartenform» переезжает из «Wie … aussehen» в свою вкладку:
только подходящие виду формы (плитки и строки — по геометрии), «как в Design» при пустом
значении, свой сброс, плашка «у N карточек своя форма» из той же выборки."""

import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.core import block_card, block_views, block_window, card_forms, list_panel
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_1b_window_cancel import _home_item, _post
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "products", "enabled": True},
        {"key": "promotions", "enabled": True},
        {"key": "list", "id": "l1", "enabled": True, "data": {"source": "products"}},
        {"key": "list", "id": "a1", "enabled": True, "data": {"source": "promotions"}},
        {"key": "list", "id": "c1", "enabled": True, "data": {"source": "categories"}},
    ],
}

#: C1: плашка «своя форма у N карточек» и журнал выборки — коммитом C2
_C2 = pytest.mark.xfail(reason="FB-33 M3-4 C2: плашка своих форм", strict=True)

CARD_SOURCES = [s for s, spec in siteconfig.LIST_SOURCES.items() if spec["card"]]


def _browser(cfg=None):
    tenant = _tenant()
    tenant.site_config = cfg or CFG
    tenant.save()
    return Browser(tenant)


def _get(b, query):
    with translation.override("de"):
        return _panel(b.get(query))


def _tab(html, key="karte"):
    at = html.find(f'data-window-tab="{key}"')
    if at < 0:
        return ""
    return html[at : html.index("</section>", at)]


def _karte_form(html):
    m = re.search(r'<form[^>]*id="bw-form-card_pick".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def _fieldset(html, shape):
    m = re.search(rf'data-schema-card-shape="{shape}">.*?</fieldset>', html, flags=re.S)
    return m.group(0) if m else ""


def _radios(html):
    return re.findall(r'<input type="radio" name="f_card" value="([^"]*)"', html)


def _list_cfg(source, style="", **extra):
    data = {"source": source, **({"style": style} if style else {}), **extra}
    return {"sections": [{"key": "hero"}, {"key": "list", "id": "x1", "enabled": True,
                         "data": data}]}  # fmt: skip


# ─────────────────────────────── реестр окна ───────────────────────────────


def test_karte_part_is_registered_in_the_window():
    assert block_window.PART_TAB["card_pick"] == "karte"
    assert block_window.PANEL_KEYS["card_pick"] == "card_pick"
    assert "card_pick" in block_window.PART_ORDER
    assert block_window.tabs({"card_pick": {"groups": [1]}}, {})[0]["key"] == "karte"


def test_one_predicate_decides_storage_panel_and_tab(monkeypatch):
    """Правка architect: запись (`siteconfig`), поле панели и вкладка «Karte» спрашивают
    один `card_forms.card_applies` — отключили его, и форма не хранится, вкладки нет."""
    data = {"source": "products", "card": "deal"}
    assert siteconfig._clean_list_block(data)["card"] == "deal"
    monkeypatch.setattr(card_forms, "card_applies", lambda kind, style: False)
    assert "card" not in siteconfig._clean_list_block(data)
    html = _get(_browser(), "?seite=home&block=l1")
    assert not _tab(html) and 'name="f_card"' not in html


# ──────────────────── матрица «источник × вид → вкладка и формы» ────────────────────


def _matrix():
    for source in [*siteconfig.LIST_SOURCES]:
        for style in ["", *siteconfig.list_styles(source)]:
            yield source, style


@pytest.mark.parametrize("source, style", list(_matrix()))
def test_karte_tab_only_where_the_card_applies_and_only_fitting_forms(source, style):
    kind = siteconfig.LIST_SOURCES[source]["card"]
    html = _get(_browser(_list_cfg(source, style)), "?seite=home&block=x1")
    karte = _tab(html)
    if not card_forms.card_applies(kind, style):
        assert not karte, (source, style)
        assert 'name="f_card"' not in html
        return
    want = {k for k, _lab, _h in card_forms.forms_for_view(style, kind)} | {""}
    assert set(_radios(karte)) == want, (source, style)
    assert len(_radios(karte)) == len(want)  # каждая форма — один раз
    for shape in (card_forms.SHAPE_TILE, card_forms.SHAPE_ROW):
        values = [v for v in _radios(_fieldset(karte, shape)) if v]
        assert all(card_forms.shape_of(v) == shape for v in values), (source, style, shape)
    # карточка — ровно в одной форме окна (и в её сбросе)
    assert _radios(html) == _radios(_karte_form(html))
    assert "data-schema-listview" not in karte


def test_grid_and_slider_offer_both_groups_with_the_mockup_headings():
    html = _get(_browser(), "?seite=home&block=l1&tab=karte")
    karte = _tab(html)
    assert "<legend" in _fieldset(karte, "tile") and "Wie eine Kachel aussieht" in karte
    assert "Wie eine Zeile aussieht" in _fieldset(karte, "row")
    assert _radios(_fieldset(karte, "row")) == ["compact", "deal"]
    assert 'data-window-tab="karte" tabindex="-1"' in html
    assert "data-schema-card-off" not in karte  # у сетки отказанных форм нет


def test_view_with_rows_only_says_which_tiles_do_not_fit(monkeypatch):
    """Решение владельца 1: «passen nicht zu …» — только у вида, где разрешены одни строки
    (сейчас таких нет — подменённый реестр)."""
    shapes = {**card_forms.VIEW_SHAPES, "": frozenset({card_forms.SHAPE_ROW})}
    monkeypatch.setattr(card_forms, "VIEW_SHAPES", shapes)
    karte = _tab(_get(_browser(), "?seite=home&block=l1&tab=karte"))
    assert not _fieldset(karte, "tile")
    assert _radios(_fieldset(karte, "row")) == ["", "compact", "deal"]
    off = re.search(r"data-schema-card-off>([^<]+)<", karte).group(1)
    assert off == (
        "Kacheln (Standard, Text auf Foto …) passen nicht zu „Raster“ und werden hier "
        "nicht angeboten."
    )


def test_wie_tab_disappears_when_the_card_was_its_only_field():
    """Матрица замков: если во «Wie … aussehen» было только поле карточки, вкладка «Wie»
    у блока пропадает — «Karte» остаётся."""
    field = {"name": "card", "label": "Kartenform", "value": "", "options": [("", "x"),
             ("deal", "Deal")]}  # fmt: skip
    selected = {
        "ref": "x1",
        "list_data": {"source": "products"},
        "groups": [{"key": "wie", "title": "Wie", "fields": [field]}],
    }
    block_card.decorate(selected, {})
    found = block_window.parts(selected, {})
    assert "listview" not in found and found == ["list", "card_pick"]
    assert [t["key"] for t in block_window.tabs(selected, {})] == ["was", "karte"]


# ─────────────────────────────── наследование ───────────────────────────────


def _first_tile(karte):
    m = re.search(
        r'name="f_card" value=""[^>]*>(.*?)<span class="font-semibold">([^<]+)', karte, re.S
    )
    return m.group(1), m.group(2)


def test_empty_is_standard_when_the_design_is_standard():
    karte = _tab(_get(_browser(), "?seite=home&block=l1&tab=karte"))
    _thumb, label = _first_tile(karte)
    assert label == "Standard"
    assert re.search(r'name="f_card" value="" class="sr-only" checked', karte)
    line = re.search(r"data-schema-card-inherit>([^<]+)<", karte).group(1)
    assert line == "Wie im Design: Standard"
    link = re.search(r'<a href="([^"]+)"[^>]*data-schema-card-inherit-link', karte).group(1)
    assert link.endswith("?tab=karten#dd-product_card_form")
    assert "data-schema-card-reset" not in karte  # своей формы нет — сбрасывать нечего


def test_empty_names_the_design_form_with_its_picture():
    cfg = {**CFG, "site_defaults": {"card_style": "overlay"}}
    karte = _tab(_get(_browser(cfg), "?seite=home&block=l1&tab=karte"))
    thumb, label = _first_tile(karte)
    assert label == "Wie im Design (Text auf Foto)"
    overlay = re.search(r'value="overlay"[^>]*>(.*?)<span class="font-semibold">', karte, re.S)
    assert thumb.strip() == overlay.group(1).strip()  # картинка — та же, что у формы X
    assert "Wie im Design: Text auf Foto" in karte


def test_promotion_of_one_type_inherits_from_the_type():
    cfg = {**CFG, "promo_groups": {"Woche": {"card": "coupon"}}}
    cfg["sections"] = [*CFG["sections"], {"key": "list", "id": "a2", "enabled": True,
                       "data": {"source": "promotions", "type": "Woche"}}]  # fmt: skip
    b = _browser(cfg)
    karte = _tab(_get(b, "?seite=home&block=a2&tab=karte"))
    assert re.search(r"data-schema-card-inherit>Wie bei diesem Aktionstyp: [^<]+<", karte)
    assert "Wie bei diesem Aktionstyp (" in _first_tile(karte)[1]
    assert "/typen/" in re.search(r'<a href="([^"]+)"[^>]*data-schema-card-inherit', karte)[1]
    # без типа — Design акций
    karte = _tab(_get(b, "?seite=home&block=a1&tab=karte"))
    assert "#dd-promo_card_form" in karte and "Wie im Design: " in karte


def test_builtin_list_inherits_from_the_design_only():
    cfg = {**CFG, "site_defaults": {"promo_card": "coupon"}}
    karte = _tab(_get(_browser(cfg), "?seite=home&block=promotions&tab=karte"))
    assert re.search(r"data-schema-card-inherit>Wie im Design: [^<]+<", karte)
    assert "Wie bei diesem Aktionstyp" not in karte


# ─────────────────────────────── запись и сброс ───────────────────────────────


def test_karte_writes_card_and_wie_form_leaves_it_alone():
    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_card="deal")
    assert _home_item(b, "l1")["data"]["card"] == "deal"
    html = _get(b, "?seite=home&block=l1")
    look = re.search(r"<form[^>]*data-schema-listview.*?</form>", html, flags=re.S).group(0)
    assert 'name="f_card"' not in look
    sent = dict(re.findall(r'name="(f_[a-z]+)" value="([^"]*)"[^>]*checked', look))
    _post(b, seite="home", ref="l1", op="update", panel_present="1", **sent, f_cols="2")
    data = _home_item(b, "l1")["data"]
    assert data["card"] == "deal" and data["cols"] == 2


def test_resets_touch_only_their_own_fields():
    """Замок architect: сброс «Wie» (VIEW_RESET_FIELDS/BUILTIN_RESET_FIELDS) не трогает
    карточку, сброс «Karte» — только её."""
    assert "card" not in block_views.VIEW_RESET_FIELDS
    assert "card" not in block_views.BUILTIN_RESET_FIELDS
    assert block_card.CARD_RESET_FIELDS == ("card",)
    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1",
          f_card="deal", f_cols="2", f_limit="5")  # fmt: skip
    html = _get(b, "?seite=home&block=l1")
    reset = re.search(r"<form[^>]*data-schema-card-reset-form.*?</form>", html, flags=re.S)[0]
    sent = dict(re.findall(r'name="(f_[a-z]+)" value="([^"]*)"', reset))
    assert sent == {"f_card": ""}
    assert "Eigene Einstellung für diesen Block: Deal-Kachel" in _tab(html)
    assert not re.search(r'<button[^>]*value="update"', reset)  # грабля M3-3: не прячется
    _post(b, seite="home", ref="l1", op="update", panel_present="1", **sent)
    data = _home_item(b, "l1")["data"]
    assert "card" not in data and data["cols"] == 2 and data["limit"] == 5
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_card="compact")
    view_reset = {f"f_{k}": "" for k in block_views.VIEW_RESET_FIELDS}
    _post(b, seite="home", ref="l1", op="update", panel_present="1", **view_reset)
    data = _home_item(b, "l1")["data"]
    assert data["card"] == "compact" and "cols" not in data


def test_builtin_list_card_from_karte_and_its_reset():
    b = _browser()
    b.get("?seite=home&block=products")
    _post(b, seite="home", ref="products", op="update", panel_present="1", f_card="lookbook")
    assert _home_item(b, "products")["data"]["card"] == "lookbook"
    karte = _tab(_get(b, "?seite=home&block=products&tab=karte"))
    assert re.search(r'value="lookbook" class="sr-only" checked', karte)
    _post(b, seite="home", ref="products", op="update", panel_present="1",
          **{f"f_{k}": "" for k in block_views.BUILTIN_RESET_FIELDS})  # fmt: skip
    assert _home_item(b, "products")["data"]["card"] == "lookbook"
    _post(b, seite="home", ref="products", op="update", panel_present="1", f_card="")
    assert "card" not in ((_home_item(b, "products") or {}).get("data") or {})


def test_cancel_brings_the_card_back():
    b = _browser()
    b.get("?seite=home&block=l1&tab=karte")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_card="deal", tab="karte")
    assert _home_item(b, "l1")["data"]["card"] == "deal"
    _post(b, seite="home", ref="l1", op="revert")
    assert "card" not in ((_home_item(b, "l1") or {}).get("data") or {})


def test_view_switch_to_a_price_list_drops_the_tab_and_cancel_restores():
    """Решение владельца 6 (как M1c): у блока «Liste» несовместимая форма выбрасывается,
    «Abbrechen» вернёт; у встроенного списка остаётся и не действует (асимметрия)."""
    b = _browser()
    b.get("?seite=home&block=l1")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_card="deal")
    _post(b, seite="home", ref="l1", op="update", panel_present="1", f_style="preisliste")
    assert "card" not in _home_item(b, "l1")["data"]
    assert not _tab(_get(b, "?seite=home&block=l1"))
    _post(b, seite="home", ref="l1", op="revert")
    assert "card" not in ((_home_item(b, "l1") or {}).get("data") or {})
    b.get("?seite=home&block=products")
    _post(b, seite="home", ref="products", op="update", panel_present="1", f_card="deal")
    _post(b, seite="home", ref="products", op="update", panel_present="1", f_style="preisliste")
    item = _home_item(b, "products")
    assert item["style"] == "preisliste" and item["data"]["card"] == "deal"
    assert not _tab(_get(b, "?seite=home&block=products"))


# ─────────────────────── плашка «своя форма у N карточек» ───────────────────────


def _products(n_own=0, via_category=False, total=4):
    cat = CategoryFactory(card_style="lookbook" if via_category else "")
    for i in range(total):
        ProductFactory(category=cat, card_style="overlay" if i < n_own else "")
    return cat


def _queries(b, query):
    with CaptureQueriesContext(connection) as ctx:
        _get(b, query)
    return len(ctx.captured_queries)


def test_own_forms_cost_no_extra_queries():
    """Замок architect: 0 / 3 своих формы и «форма от категории» — одно число запросов
    (категория — `select_related` выборки блока)."""
    counts = []
    for n_own, via in ((0, False), (3, False), (0, True)):
        b = _browser()
        _products(n_own, via)
        b.get("?seite=home&block=l1&tab=karte")
        counts.append(_queries(b, "?seite=home&block=l1&tab=karte"))
        from apps.catalog.models import Category, Product

        Product.objects.all().delete()
        Category.objects.all().delete()
    assert counts[0] == counts[1] == counts[2], counts


@_C2
def test_own_forms_note_lists_the_cards_with_edit_links():
    b = _browser()
    cat = _products(n_own=3)
    karte = _tab(_get(b, "?seite=home&block=l1&tab=karte"))
    note = re.search(r'<div role="note"[^>]*data-schema-card-own>.*?</div>', karte, re.S)[0]
    assert "3 Produkte haben eine eigene Kartenform — sie gilt dort statt dieser" in note
    assert "<details>" in note and "anzeigen" in note
    links = re.findall(r'<a href="(/[^"]+/edit/)"', note)
    assert len(links) == 3 and all(link.startswith("/catalog/products/") for link in links)
    assert str(cat.pk) not in note


@_C2
def test_own_form_from_the_category_links_to_the_category():
    b = _browser()
    cat = _products(via_category=True, total=1)
    note = _tab(_get(b, "?seite=home&block=l1&tab=karte"))
    assert "1 Produkt hat eine eigene Kartenform" in note
    assert f"/catalog/categories/{cat.pk}/edit/" in note
    assert "Kartenform der Kategorie" in note


def test_no_note_without_own_forms():
    b = _browser()
    _products()
    assert "data-schema-card-own" not in _tab(_get(b, "?seite=home&block=l1&tab=karte"))


@_C2
@pytest.mark.parametrize(
    "lang, n, want",
    [
        ("ru", 1, "1 товар"),
        ("ru", 3, "3 товара"),
        ("ru", 5, "5 товаров"),
        ("uk", 1, "1 товар"),
        ("uk", 3, "3 товари"),
        ("uk", 5, "5 товарів"),
        ("en", 1, "1 product has"),
        ("en", 2, "2 products have"),
    ],
)
def test_own_forms_text_has_the_plural_forms_of_the_language(lang, n, want):
    with translation.override(lang):
        assert block_card._own_text("products", n).startswith(want)


@_C2
def test_own_forms_text_is_named_by_the_source():
    with translation.override("de"):
        assert block_card._own_text("promotions", 2).startswith("2 Aktionen haben")
        assert block_card._own_text("services", 1).startswith("1 Leistung hat")


@_C2
def test_promotion_own_form_reads_the_raw_field_only():
    class Promo:
        card_style = "coupon"

        @property
        def category(self):  # у акции категория — FK: трогать нельзя (N+1)
            raise AssertionError("category read")

    assert card_forms.own_form(Promo(), card_forms.PROMO) == "coupon"
    Promo.card_style = ""
    assert card_forms.own_form(Promo(), card_forms.PROMO) == ""
    assert list_panel.own_forms("promotions", [Promo()]) == []


@_C2
def test_failed_selection_is_logged_not_swallowed(monkeypatch, caplog):
    from apps.core import list_blocks

    def boom(*a, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(list_blocks, "resolve_for", boom)
    with caplog.at_level("WARNING", logger="apps.core.list_panel"):
        assert list_panel.result(None, {}, {"source": "products"}) is None
    assert any("selection failed" in r.getMessage() for r in caplog.records)


def test_window_lands_karte_after_wie_and_selected_keys_are_known():
    b = _browser()
    html, view, selected = _capture(b, "?seite=home&block=l1")
    assert [t["key"] for t in block_window.tabs(selected, view)] == ["was", "wie", "karte"]
    known = set(block_window.PANEL_KEYS) | block_window.ROW_KEYS
    assert {k for k, v in selected.items() if v} <= known
