"""FB-33 M3-1: окно блока — части прежней панели по вкладкам (`apps/core/block_window.py`)."""

import re
from pathlib import Path

import pytest

from apps.core import block_window, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG, _capture, _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _shop():
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    return tenant


def _nonempty(d):
    return {k for k, v in d.items() if v not in (None, "", [], {}, (), False)}


def test_every_row_key_is_a_panel_part_or_a_row_label():
    """Замок architect: новый ключ строки без места в окне роняет тест (обход ключей, а не
    списка полей)."""
    tenant = _shop()
    cfg = siteconfig.normalize(tenant.site_config)
    known = set(block_window.PANEL_KEYS) | block_window.ROW_KEYS
    for _g, items in site_schema.type_groups(tenant, cfg):
        for row in items:
            for b in site_schema.blocks_for(cfg, row.code, host=row.host):
                assert _nonempty(b) <= known, (row.code, b["ref"], _nonempty(b) - known)
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        _html, _view, selected = _capture(Browser(tenant), f"?seite={code}&block={ref}{extra}")
        assert _nonempty(selected) <= known, (case, _nonempty(selected) - known)


def test_every_part_lands_in_exactly_one_tab():
    tenant = _shop()
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        _html, view, selected = _capture(Browser(tenant), f"?seite={code}&block={ref}{extra}")
        found = block_window.parts(selected, view)
        tabs = block_window.tabs(selected, view)
        placed = [p for t in tabs for p in t["parts"]]
        assert sorted(placed) == sorted(found), case
        assert len(placed) == len(set(placed)), case
        assert sum(t["active"] for t in tabs) == (1 if tabs else 0), case


def test_a_form_is_never_split_and_fields_go_by_their_role():
    texts = [{"name": "title"}, {"name": "body"}]
    assert block_window.fields_tab(texts) == "texte"
    assert block_window.fields_tab([{"name": "style"}]) == "wie"
    assert block_window.fields_tab([{"name": "page"}, {"name": "mode"}]) == "was"
    assert block_window.fields_tab([{"name": "set"}]) == "was"
    # смешанная форма — целиком в «Texte»
    assert block_window.fields_tab([{"name": "page"}, {"name": "title"}]) == "texte"


def _tabs_of(html):
    panel = _panel(html)
    return re.findall(r'data-window-tab="([a-z]+)"(?: aria-label="[^"]*")?( hidden)?', panel)


def test_text_block_opens_with_view_and_place_and_texts_on_their_own_tab():
    b = Browser(_shop())
    html = b.get("?seite=home&block=t1")
    assert _tabs_of(html) == [("wie", ""), ("texte", " hidden")]
    panel = _panel(html)
    nav = panel[panel.index("data-window-tabs") : panel.index("</nav>")]
    assert 'data-window-tab-link="wie"' in nav and 'aria-current="true"' in nav
    assert "&amp;tab=texte" in nav  # без скриптов — обычная ссылка
    # смена вида и ширина — в «Wie anordnen», тексты — в «Texte»
    wie = panel[panel.index('data-window-tab="wie"') : panel.index('data-window-tab="texte"')]
    assert "data-schema-switch" in wie and "data-schema-width" in wie
    assert "data-schema-fields" in panel[panel.index('data-window-tab="texte"') :]


def test_asked_tab_is_open_and_its_forms_remember_it():
    b = Browser(_shop())
    html = b.get("?seite=home&block=t1&tab=texte")
    assert _tabs_of(html) == [("wie", " hidden"), ("texte", "")]
    assert '<input type="hidden" name="tab" value="texte">' in _panel(html)
    resp, _msgs = b.post(seite="home", ref="t1", op="toggle", tab="texte")
    assert resp.status_code == 302 and "tab=texte" in resp["Location"]


def test_unknown_or_missing_tab_falls_back_without_a_hidden_field():
    b = Browser(_shop())
    for tab in ("zzz", "karte"):  # мусор и вкладка, которой у блока нет
        html = b.get(f"?seite=home&block=t1&tab={tab}")
        assert _tabs_of(html) == [("wie", ""), ("texte", " hidden")]
        assert 'name="tab"' not in _panel(html)
    resp, _msgs = b.post(seite="home", ref="t1", op="toggle", tab="<x>")
    assert "tab=" not in resp["Location"]


def test_one_tab_needs_no_tab_bar_and_banner_shows_choice_and_page():
    b = Browser(_shop())
    title = b.get("?seite=promos&block=__title")
    assert _tabs_of(title) == [("texte", "")] and "data-window-tabs" not in title
    hero = b.get("?seite=home&block=hero")
    assert [t for t, _h in _tabs_of(hero)] == ["was", "seite"]
    assert [t for t, _h in _tabs_of(b.get("?seite=text&block=bn1"))] == ["was", "wie"]
    assert [t for t, _h in _tabs_of(b.get("?seite=catalog&block=main"))] == ["wie", "seite"]
    assert [t for t, _h in _tabs_of(b.get("?seite=home&block=l1"))] == ["was", "wie"]
    # FB-33 M2h-5: «Was passiert jetzt» — свой текст, одна вкладка «Texte»
    assert _tabs_of(b.get("?seite=confirmation&block=next")) == [("texte", "")]
    assert _tabs_of(b.get("?seite=confirmation&block=summary")) == []


def test_pinned_and_confirm_have_no_tabs():
    b = Browser(_shop())
    assert _tabs_of(b.get("?seite=cart&block=summary")) == []
    confirm = b.get("?seite=home&block=t1&entfernen=1")
    assert _tabs_of(confirm) == [] and "data-schema-confirm" in confirm


def test_panel_anchor_stays_on_the_wrapper_not_on_a_tab():
    """architect: `id="schema-panel"` и `data-schema-panel` — на обёртке (будущий
    `<dialog>` M3-2 не подменяется `aufbau.js`)."""
    html = Browser(_shop()).get("?seite=home&block=t1")
    assert html.count('id="schema-panel"') == 1 and html.count("data-schema-panel") == 1
    tag = html[html.rindex("<aside", 0, html.index('id="schema-panel"')) :]
    assert tag[: tag.index(">")].count("data-schema-panel") == 1


def test_tab_labels_are_translated_with_a_context():
    src = Path("apps/core/block_window.py").read_text()
    assert src.count('pgettext_lazy("block window tab"') == len(block_window.TABS)
    msgids = ("Was", "Wie anordnen", "Karte", "Texte", "Seite", "Felder")
    for msgid in msgids:
        assert f'pgettext_lazy("block window tab", "{msgid}")' in src
    for lang in ("de", "en", "ru", "tr", "uk"):
        po = Path(f"locale/{lang}/LC_MESSAGES/django.po").read_text()
        for msgid in msgids:
            assert f'msgctxt "block window tab"\nmsgid "{msgid}"' in po, (lang, msgid)
