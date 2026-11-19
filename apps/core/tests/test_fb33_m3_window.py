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
    assert 'data-window-tab-link="wie"' in nav and 'aria-current="page"' in nav
    # без скриптов — обычная ссылка на якорь своей вкладки (фокус и скринридер — во вкладку)
    assert "&amp;tab=texte#schema-tab-texte" in nav
    assert nav.count("focus-visible:outline-2") == 2  # явный фокус у каждой вкладки
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


def _sections(panel):
    """{вкладка: (скрыта ли, html)} — по разметке окна."""
    out = {}
    for m in re.finditer(r'<section id="schema-tab-([a-z]+)"([^>]*)>(.*?)</section>', panel, re.S):
        out[m.group(1)] = ("hidden" in m.group(2), m.group(2), m.group(3))
    return out


def test_every_rendered_part_sits_in_exactly_one_tab_for_each_matrix_row():
    """Ревью M3-1: на каждой строке матрицы M3-0 каждая непустая часть нарисована ровно
    один раз и внутри своей вкладки (замок форм M3-0 их сортирует и этого не видит)."""
    tenant = _shop()
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        html, view, selected = _capture(Browser(tenant), f"?seite={code}&block={ref}{extra}")
        panel = _panel(html)
        if view.get("confirm_remove") and selected.get("cblock"):
            assert "data-window-part" not in panel, case
            continue
        sections = _sections(panel)
        for part in block_window.parts(selected, view):
            tab = block_window.tab_of(part, selected)
            marker = f'data-window-part="{part}"'
            assert panel.count(marker) == 1, (case, part)
            assert marker in sections[tab][2], (case, part, tab)


def test_tabs_are_named_by_a_heading_and_add_no_landmarks():
    b = Browser(_shop())
    for query in ("?seite=home&block=t1", "?seite=promos&block=__title"):
        sections = _sections(_panel(b.get(query)))
        for key, (hidden, attrs, body) in sections.items():
            assert "aria-label" not in attrs and "role=" not in attrs, key
            assert body.lstrip().startswith('<h3 class="sr-only">'), key
            assert ('tabindex="-1"' in attrs) is not hidden, key  # фокус — у открытой


def _post_data(form_html):
    data = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form_html))
    op = re.search(r'name="op"[^>]*value="([^"]+)"', form_html)
    if op:
        data["op"] = op.group(1)
    return data


def test_each_tab_with_a_form_remembers_itself_after_an_action():
    """Ревью M3-1: вкладка переживает действие — у каждой вкладки с формой, на каждой
    строке матрицы (и «Seite»: настройки типа страницы)."""
    tenant = _shop()
    seen = set()
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        if extra:
            continue
        b = Browser(tenant)
        for tab in block_window.TAB_KEYS:
            html = b.get(f"?seite={code}&block={ref}&tab={tab}")
            body = _sections(_panel(html)).get(tab)
            if not body or body[0]:
                continue  # такой вкладки у блока нет — открыта первая
            form = re.search(r'<form method="post".*?</form>', body[2], re.S)
            if not form:
                continue
            data = _post_data(form.group(0))
            assert data.get("tab") == tab, (case, tab)
            resp, _msgs = b.post(**data)
            assert resp.status_code == 302 and f"tab={tab}" in resp["Location"], (case, tab)
            seen.add(tab)
    assert seen >= {"was", "wie", "texte", "seite"}


def test_which_mode_and_tab_travel_together():
    """Ревью M3-1: ссылки вкладок несут открытый способ «Welche», ссылки «Welche» — вкладку."""
    b = Browser(_shop())
    html = _panel(b.get("?seite=home&block=l1&welche=regel&tab=wie"))
    assert "&amp;tab=was&amp;welche=" in html  # ссылка вкладки «Was» помнит способ
    regel = re.search(r'<a href="([^"]*welche=[a-z]+[^"]*)"[^>]*data-schema-which-mode', html)
    assert regel and "&amp;tab=wie" in regel.group(1)


def test_confirm_keeps_the_old_order_and_no_tabs():
    """Ревью M3-1: при подтверждении удаления — прежний вывод (без «Gehört zu» и вкладок)."""
    panel = _panel(Browser(_shop()).get("?seite=home&block=t1&entfernen=1"))
    assert "data-schema-confirm" in panel and "data-schema-family" not in panel
    assert "data-window-tab" not in panel


def test_block_links_drop_aria_controls_and_view_switch_marks_the_page():
    html = Browser(_shop()).get("?seite=home&block=t1")
    assert 'aria-controls="schema-panel"' not in html
    view = html[
        html.index("data-schema-view>") : html.index("</div>", html.index("data-schema-view>"))
    ]
    assert 'aria-current="page"' in view
    for lang in ("de", "en", "ru", "tr", "uk"):
        po = Path(f"locale/{lang}/LC_MESSAGES/django.po").read_text()
        assert 'msgctxt "block view"\nmsgid "Ansicht"' in po, lang
