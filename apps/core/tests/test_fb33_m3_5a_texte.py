"""FB-33 M3-5a: вкладка «Texte» окна блока — простые поля; без скриптов вкладки не теряют
набранное (решение владельца M3-2 п.3, план — scratchpad m35a-plan / §«План M3» доки FB-33).

Замки L1–L8: вкладки без формы — ссылки байт-в-байт; кнопка вкладки применяет форму (черновик и
снимок окна те же, что у «Übernehmen»); отказ или сообщение — без перехода; Enter в поле не
переключает вкладку; лимиты ввода в панели и Студии (сохранённое не режется); XSS; `zu_tab` и
`op_default` только из белых списков; две формы во вкладке — ссылки. Плюс отложенное из M2i-5:
фокус «Felder» после кнопок вопроса и живая область сброшенного перевода.
"""

import copy
import re
from pathlib import Path

import pytest
from django.http import QueryDict
from django.utils import translation

from apps.core import aufbau_draft, block_window, page_title
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG, _capture, _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

TOKEN = "openT5a"
TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "tenant"


def _shop(cfg=None, locales=None):
    tenant = _tenant()
    tenant.site_config = copy.deepcopy(cfg if cfg is not None else CFG)
    if locales:
        tenant.enabled_locales = list(locales)
    tenant.save()
    return tenant


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _row(b, ref, code="home"):
    draft = _drafts(b).get(code) or {}
    rows = draft.get("items") or []
    return next((r for r in rows if r.get("id") == ref), None)


def _nav(panel):
    """Вкладки окна вместе с невидимой кнопкой «по умолчанию» перед ними."""
    at = panel.index("data-window-tabs")
    start = panel.rindex("</h2>", 0, at)
    return panel[start : panel.index("</nav>", at)]


def _texte_post(b, ref="t1", **fields):
    data = {
        "seite": "home",
        "ref": ref,
        "panel_present": "1",
        "op_default": "update",
        "tab": "texte",
        "wopen": TOKEN,
    }
    data.update({f"f_{k}": v for k, v in fields.items()})
    return data


# --- L1 / L8: вкладки без одной формы — ссылки байт-в-байт -----------------------------------


def test_tabs_without_a_single_form_stay_links():
    b = Browser(_shop())
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        for tab in ("", *block_window.TAB_KEYS):
            query = f"?seite={code}&block={ref}{extra}" + (f"&tab={tab}" if tab else "")
            html, view, selected = _capture(b, query)
            window = block_window.tabs(selected, view, tab)
            panel = _panel(html)
            if block_window.apply_form(window) is None:
                assert "zu_tab" not in panel and "data-window-default" not in panel, query
                if "data-window-tabs" in panel:
                    assert (
                        "<button" not in panel[panel.index("data-window-tabs") :].split("</nav>")[0]
                    ), query


def test_text_tab_turns_other_tabs_into_buttons_of_its_form():
    b = Browser(_shop())
    panel = _panel(b.get("?seite=home&block=t1&tab=texte"))
    nav = _nav(panel)
    # открытая — ссылка с aria-current, прочие — кнопки формы вкладки
    assert re.search(r'<a href="[^"]*tab=texte[^"]*"[^>]*aria-current="page"', nav)
    wie = re.search(
        r'<button type="submit" form="bw-form-fields" name="zu_tab" value="wie"[^>]*>', nav
    )
    assert wie and "formnovalidate" in wie.group(0)
    assert 'aria-describedby="bw-nav-apply"' in wie.group(0)
    assert 'id="bw-nav-apply"' in nav and 'class="sr-only"' in nav
    assert '<form method="post" id="bw-form-fields"' in panel
    assert '<input type="hidden" name="op_default" value="update">' in panel
    # на «Wie anordnen» (две формы) — снова ссылки
    wie_panel = _panel(b.get("?seite=home&block=t1&tab=wie"))
    assert "zu_tab" not in wie_panel


def test_apply_form_counts_parts_not_forms():
    def win(active, *tabs):
        return [{"key": k, "parts": list(p), "active": k == active} for k, p in tabs]

    texte = ("texte", ["fields"])
    assert block_window.apply_form(win("texte", ("wie", ["platz"]), texte))["form"] == (
        "bw-form-fields"
    )
    # две применяющие части — ссылки; вкладка не из {texte, felder, karte} — ссылки
    two = win("texte", ("wie", ["platz"]), ("texte", ["fields", "usp"]))
    assert block_window.apply_form(two) is None
    assert block_window.apply_form(win("wie", ("wie", ["listview", "platz"]), texte)) is None
    assert block_window.apply_form(win("was", ("was", ["fields"]), texte)) is None
    # «Karte»: вторая форма «zurücksetzen» — не часть, применяет одна card_pick
    karte = block_window.apply_form(win("karte", ("karte", ["card_pick"]), texte))
    assert karte == {
        "part": "card_pick",
        "form": "bw-form-card_pick",
        "name": "op",
        "value": "update",
    }
    felder = block_window.apply_form(win("felder", ("felder", ["formfields", "formlink"]), texte))
    assert (felder["name"], felder["value"]) == ("f_commit_new", "1")
    faq = block_window.apply_form(win("texte", ("wie", ["platz"]), ("texte", ["faq"])))
    assert (faq["form"], faq["value"]) == ("bw-form-faq", "faq_update")
    # одна вкладка — вкладок нет вовсе
    assert block_window.apply_form(win("texte", texte)) is None


# --- L2 / L5: кнопка вкладки применяет форму — тот же черновик, что «Übernehmen» --------------


def test_tab_button_keeps_typed_text_and_opens_the_tab():
    b = Browser(_shop())
    resp, msgs = b.post(**_texte_post(b, title="Neu", body="Welt"), zu_tab="wie")
    assert resp.status_code == 302 and msgs == []
    loc = resp["Location"]
    assert "tab=wie" in loc and "tab=texte" not in loc and loc.endswith("#schema-tab-wie")
    assert f"wopen={TOKEN}" in loc
    assert _row(b, "t1")["data"]["title"] == "Neu"
    # снимок окна (Abbrechen) — как у обычной правки из окна
    assert "t1" in (_drafts(b)["home"].get(aufbau_draft.WINDOW_KEY) or {})


def test_tab_button_draft_equals_apply_button_draft():
    one, two = Browser(_shop()), Browser(_shop())
    one.post(**_texte_post(one, title="Neu"), zu_tab="wie")
    data = _texte_post(two, title="Neu")
    data.pop("op_default")
    two.post(**data, op="update")
    first, second = _drafts(one)["home"], _drafts(two)["home"]
    for draft in (first, second):
        draft.pop("ts", None)
    assert first == second


# --- L3: отказ или сообщение — без перехода -----------------------------------------------------


def test_refused_edit_stays_on_the_tab():
    b = Browser(_shop())
    data = _texte_post(b, ref="bt1", label="Los", url="javascript:alert(1)")
    resp, msgs = b.post(**data, zu_tab="wie")
    loc = resp["Location"]
    assert msgs and "tab=texte" in loc and "tab=wie" not in loc and loc.endswith("#schema-panel")
    assert _row(b, "bt1") is None or _row(b, "bt1")["data"]["url"] == "/x"


def test_cut_text_note_stays_on_the_tab():
    b = Browser(_shop())
    resp, msgs = b.post(**_texte_post(b, ref="bt1", label="L" * 300, url="/x"), zu_tab="wie")
    assert msgs == [siteconfig.cap_note()]
    assert "tab=texte" in resp["Location"] and "#schema-tab-wie" not in resp["Location"]
    assert _row(b, "bt1")["data"]["label"] == "L" * 200


# --- L4: Enter в поле применяет, а не переключает --------------------------------------------


def test_default_button_comes_before_the_tab_buttons():
    b = Browser(_shop())
    panel = _panel(b.get("?seite=home&block=t1&tab=texte"))
    default = panel.index("data-window-default")
    first_tab_button = panel.index('name="zu_tab"')
    assert default < first_tab_button < panel.index('id="bw-form-fields"')
    tag = panel[panel.rindex("<button", 0, default) : panel.index(">", default) + 1]
    assert 'form="bw-form-fields" name="op" value="update"' in tag
    assert 'tabindex="-1"' in tag and 'aria-hidden="true"' in tag and 'type="submit"' in tag


# --- L6: лимиты на вводе — панель и Студия; сохранённое не режется -----------------------------


def test_panel_inputs_carry_the_input_caps_and_hints():
    b = Browser(_shop())
    with translation.override("de"):
        bt = _panel(b.get("?seite=home&block=bt1&tab=texte"))
        t1 = _panel(b.get("?seite=home&block=t1&tab=texte"))
        title = _panel(b.get("?seite=promos&block=__title"))
        nxt = _panel(b.get("?seite=confirmation&block=next"))
    caps = siteconfig.CBLOCK_INPUT_CAPS
    assert f'name="f_label" value="Los" maxlength="{caps["button"]["label"]}"' in bt
    assert (
        f'name="f_url" value="/x" maxlength="{caps["button"]["url"]}" '
        'aria-describedby="schema-f-url-max"' in bt
    )
    assert re.search(
        r'<p id="schema-f-url-max"[^>]*>z\. B\. /kontakt oder https://… Höchstens 500 Zeichen\.</p>',
        bt,
    )
    assert 'id="schema-f-label-max"' in bt and "Höchstens 200 Zeichen." in bt
    assert 'maxlength="200" aria-describedby="schema-f-title-max"' in t1
    # длинный текст — только потолок, без подсказки
    assert 'rows="5" maxlength="20000" class="ui-input w-full">' in t1
    assert f'maxlength="{page_title.TITLE_MAX}"' in title
    assert f'maxlength="{page_title.INTRO_MAX}"' in title
    # подсказка самого поля (контракт закреплённых блоков M3-6) — связана с полем
    assert 'aria-describedby="schema-f-text-hint schema-f-text-max"' in nxt
    assert '<p id="schema-f-text-hint" class="mt-1 text-xs text-gray-700">Leer lassen' in nxt


def test_image_caption_is_capped_in_panel():
    cfg = copy.deepcopy(CFG)
    cfg["sections"].append({"key": "image", "id": "im1", "enabled": True, "data": {}})
    b = Browser(_shop(cfg))
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=im1&tab=texte"))
    assert 'name="f_caption" value="" maxlength="200"' in panel
    _resp, msgs = b.post(**_texte_post(b, ref="im1", caption="C" * 300), op="update")
    assert _row(b, "im1")["data"]["caption"] == "C" * 200 and msgs == [siteconfig.cap_note()]


def test_saved_long_text_is_not_cut():
    long = "L" * 300
    cfg = copy.deepcopy(CFG)
    cfg["sections"][4]["data"]["label"] = long
    # нормализация не режет — витрина прежняя
    assert siteconfig.normalize(cfg)["sections"][4]["data"]["label"] == long
    b = Browser(_shop(cfg))
    _resp, msgs = b.post(**_texte_post(b, ref="bt1", label=long, url="/neu"), op="update")
    row = _row(b, "bt1")
    assert row["data"]["url"] == "/neu" and row["data"]["label"] == long and msgs == []


def test_studio_caps_and_maxlength():
    from apps.core import views

    post = QueryDict(mutable=True)
    post.update({"cb_b1_label": "L" * 300, "cb_b1_url": "/" + "u" * 600})
    notes = []
    data = views._read_cblock_data(post, "b1", "button", notes)
    assert len(data["label"]) == 200 and len(data["url"]) == 500 and notes
    post = QueryDict(mutable=True)
    post.update({"cb_b2_caption": "C" * 300, "cb_b2_url": "/i.jpg"})
    notes = []
    data = views._read_cblock_data(post, "b2", "image", notes)
    assert len(data["caption"]) == 200 and data["url"] == "/i.jpg" and notes
    row = (TEMPLATES / "_cb_row.html").read_text()
    caps = siteconfig.CBLOCK_INPUT_CAPS
    assert f'_label" value="{{{{ b.data.label }}}}" maxlength="{caps["button"]["label"]}"' in row
    assert f'_url" value="{{{{ b.data.url }}}}" maxlength="{caps["button"]["url"]}"' in row
    assert (
        f'_caption" value="{{{{ b.data.caption }}}}" maxlength="{caps["image"]["caption"]}"' in row
    )


# --- L7: XSS и белые списки --------------------------------------------------------------------


def test_texts_are_escaped_in_the_tab():
    evil = '"><script>alert(1)</script>'
    cfg = copy.deepcopy(CFG)
    cfg["sections"][4]["data"] = {"label": evil, "url": "/x"}
    panel = _panel(Browser(_shop(cfg)).get("?seite=home&block=bt1&tab=texte"))
    assert "<script>alert" not in panel and "&lt;script&gt;" in panel


def test_unknown_tab_and_operation_are_ignored():
    b = Browser(_shop())
    resp, _msgs = b.post(**_texte_post(b, title="Neu"), zu_tab="<x>")
    assert "schema-tab-" not in resp["Location"] and "tab=texte" in resp["Location"]
    # op_default не из белого списка — правка полей, не удаление
    data = {**_texte_post(b, title="Zwei"), "op_default": "delete"}
    resp, _msgs = b.post(**data, zu_tab="wie")
    assert _row(b, "t1")["data"]["title"] == "Zwei" and resp["Location"].endswith("#schema-tab-wie")
    assert block_window.default_op(QueryDict("op_default=faq_update")) == "faq_update"
    assert block_window.default_op(QueryDict("op_default=save")) == "update"
    assert block_window.goto_tab(QueryDict("zu_tab=felder")) == "felder"
    assert block_window.goto_tab(QueryDict("zu_tab=x")) == ""


# --- Переводы текстов блока — в Студии (M3-5c), здесь подсказка и ссылка -------------------------


def test_multilang_hint_links_to_the_page_editor():
    b = Browser(_shop(locales=("de", "ru")))
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=t1&tab=texte"))
    assert "Hier steht der Text der Hauptsprache." in panel
    link = re.search(r'<a href="([^"]*)"[^>]*data-schema-translate>([^<]*)</a>', panel)
    assert link and link.group(1).startswith("/") and "Übersetzungen auf der Seite" in link.group(2)
    one = _panel(Browser(_shop(locales=("de",))).get("?seite=home&block=t1&tab=texte"))
    assert "data-schema-translate" not in one


# --- Отложенное из M2i-5: фокус «Felder» и живая область сброшенного перевода ------------------


def _felder(locales=None):
    from apps.core.tests.test_fb33_m2i5_draft import _tenant as anfrage_tenant

    tenant = anfrage_tenant()
    if locales:
        tenant.enabled_locales = list(locales)
        tenant.save(update_fields=["enabled_locales"])
    return Browser(tenant)


def _felder_post(b, **fields):
    data = {"seite": "anfrage", "ref": "form", "op": "update", "panel_present": "1"}
    data.update({"wopen": TOKEN, "tab": "felder"})
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


@pytest.fixture
def _tenant_urls(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_felder_question_buttons_bring_focus_back(_tenant_urls):
    b = _felder()
    resp, _m = _felder_post(b, do="down:q1")
    assert resp["Location"].endswith("#schema-tab-q-q1")
    resp, _m = _felder_post(b, do="del:q2")
    assert resp["Location"].endswith("#schema-tab-questions")
    resp, _m = _felder_post(b, do="add", new_label="Neu", new_type="text")
    assert re.search(r"#schema-tab-q-n[0-9]+$", resp["Location"])
    # без текста новой вопроса — сообщение, якорь прежний
    resp, msgs = _felder_post(b, do="add", new_label="")
    assert msgs and resp["Location"].endswith("#schema-panel")
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder")
    assert re.search(r'id="schema-tab-q-q1" tabindex="-1"', html)
    assert '<fieldset id="schema-tab-q-q1" tabindex="-1"' in html  # языки — fieldset/legend
    with translation.override("de"):
        one = _felder(("de",)).get("?seite=anfrage&block=form&tab=felder")
    assert '<div role="group" aria-label="Frage 1" id="schema-tab-q-q1" tabindex="-1"' in one
    assert 'id="schema-tab-questions" tabindex="-1"' in html


def test_dropped_translation_has_a_live_region_in_the_language_block(_tenant_urls):
    b = _felder(("de", "ru"))
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder")
    langs = html[html.index("data-form-langs") : html.index("</div>", html.index("ff-lang-hint"))]
    status = re.search(
        r'<p role="status"[^>]*data-form-langs-status data-prefix="([^"]*)"></p>', langs
    )
    assert status and status.group(1).startswith(
        "Übersetzungen entfernt, weil die Option geändert oder gelöscht wurde:"
    )
