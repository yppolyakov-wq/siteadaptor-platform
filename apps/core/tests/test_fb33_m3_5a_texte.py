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
        "bw_tabs": "wie texte",  # вкладки окна — их рисует сервер рядом с кнопками
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
    # (ревью a11y) прочие — кнопки, поэтому у открытой aria-current="true", а не "page"
    assert re.search(r'<a href="[^"]*tab=texte[^"]*"[^>]*aria-current="true"', nav)
    assert '<p id="bw-nav-apply" hidden>' in nav
    assert '<input type="hidden" form="bw-form-fields" name="bw_tabs" value="wie texte">' in nav
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
    # FB-33 стопка 14 E3: на «Wie» применяет вид списка («Platz» — своя форма, не часть).
    # Стопка 15 S14-E3-wie (осознанная переписка): и вид блока (`fields` со стилем); обе части
    # на «Wie» — ссылки
    wie = block_window.apply_form(win("wie", ("wie", ["listview", "platz"]), texte))
    assert (wie["form"], wie["name"], wie["value"]) == ("bw-form-listview", "op", "update")
    style = block_window.apply_form(win("wie", ("wie", ["fields", "platz"]), texte))
    assert style["form"] == "bw-form-fields"
    assert block_window.apply_form(win("wie", ("wie", ["listview", "fields"]), texte)) is None
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
    assert (faq["form"], faq["name"], faq["value"]) == ("bw-form-faq", "faq_add", "1")
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
        title = _panel(b.get("?seite=promos&block=__page"))
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
    # длинный текст — без maxlength (браузер молча обрезал бы вставку), потолок — на сервере
    assert 'rows="5" class="ui-input w-full">' in t1
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
    assert block_window.goto_tab(QueryDict("zu_tab=felder&bw_tabs=texte+felder")) == "felder"
    assert block_window.goto_tab(QueryDict("zu_tab=x")) == ""


# --- Переводы текстов блока: с M3-5c — в самом окне (кнопки языка), подсказки со ссылкой нет -----


def test_multilang_texts_are_translated_in_the_window():
    b = Browser(_shop(locales=("de", "ru")))
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=t1&tab=texte"))
    assert 'name="f_tr_title_ru"' in panel and 'name="f_sprache" value="ru"' in panel
    assert "data-schema-translate" not in panel
    assert "Hier steht der Text der Hauptsprache." not in panel
    one = _panel(Browser(_shop(locales=("de",))).get("?seite=home&block=t1&tab=texte"))
    assert "data-schema-translate" not in one and "f_sprache" not in one


# --- Отложенное из M2i-5: фокус «Felder» и живая область сброшенного перевода ------------------


def _felder(locales=None):
    from apps.core.tests.test_fb33_m2i5_draft import _tenant as anfrage_tenant

    tenant = anfrage_tenant()
    if locales:
        tenant.enabled_locales = list(locales)
        tenant.save(update_fields=["enabled_locales"])
    return Browser(tenant)


#: подписи вопросов в порядке формы (как шлёт браузер) — соседа после «Entfernen» ищем по ним
LABELS = {"q_q1_label": "Budget", "q_q2_label": "Raum", "q_q4_label": "Vegan?"}


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
    resp, msgs = _felder_post(b, do="del:q2", **LABELS)
    # (ревью a11y) фокус — на соседний вопрос, результат — сообщением
    assert resp["Location"].endswith("#schema-tab-q-q4") and msgs == ["Frage entfernt."]
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


def test_felder_live_region_also_without_languages(_tenant_urls):
    """Ревью a11y п.8: живая область — вне блока языков (и у одноязычного), с точными текстами
    результатов кнопок вопроса и началом сообщения о сброшенном переводе."""
    for locales in (("de", "ru"), ("de",)):
        b = _felder(locales)
        with translation.override("de"):
            html = b.get("?seite=anfrage&block=form&tab=felder")
        status = re.search(
            r'<p role="status"[^>]*data-form-status data-said="([^"]*)" data-prefix="([^"]*)"></p>',
            html,
        )
        assert status, locales
        said = status.group(1).split("|")
        assert "Frage entfernt." in said and "Nach oben verschoben." in said
        assert status.group(2).startswith(
            "Übersetzungen entfernt, weil die Option geändert oder gelöscht wurde:"
        )
        assert html.index("data-form-status") < html.index('data-form-question="q1"')


def test_felder_neighbour_after_remove_and_messages(_tenant_urls):
    b = _felder()
    resp, _m = _felder_post(b, do="del:q4", **LABELS)  # последний — предыдущий
    assert resp["Location"].endswith("#schema-tab-q-q2")
    b = _felder()
    resp, msgs = _felder_post(b, do="up:q2", **LABELS)
    assert resp["Location"].endswith("#schema-tab-q-q2") and msgs == ["Nach oben verschoben."]
    assert block_window.felder_anchor(QueryDict("f_do=del:q1"), {"custom": []}) == (
        "schema-tab-questions"
    )
    # черновика вкладки нет (добавили и сразу убрали) — сосед по форме
    post = QueryDict("f_q_q1_label=a&f_q_n1_label=b&f_q_q2_label=c&f_do=del:n1")
    assert block_window.felder_anchor(post, None) == "schema-tab-q-q2"


def test_felder_enter_default_and_add_label(_tenant_urls):
    """Ревью a11y п.9: первая submit-кнопка формы «Felder» по дереву — sr-only «Übernehmen»
    (Enter), вне Tab и без aria-hidden (FB-33 M2i-34); «+ Frage» — с именем «Frage hinzufügen»."""
    b = _felder(("de",))
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder")
    form = html[
        html.index('id="bw-form-formfields"') : html.index(
            "</form>", html.index("data-form-felder")
        )
    ]
    first = re.search(r"<button\b[^>]*>", form).group(0)
    assert 'name="f_commit_new"' in first and 'class="sr-only"' in first
    assert "aria-hidden" not in first and 'tabindex="-1"' in first
    assert re.search(r'<button name="f_do" value="add"[^>]*aria-label="Frage hinzufügen"', form)


# --- Ревью ECC M3-5a ----------------------------------------------------------------------------


def test_studio_keeps_unchanged_long_texts():
    """П.1: Студия режет только изменённое — ссылка кнопки из прошлого (> 500) не ломается."""
    from apps.core import views

    long_url = "/" + "u" * 700
    cfg = {
        "sections": [{"key": "button", "id": "b1", "data": {"label": "L" * 300, "url": long_url}}],
        "page_blocks": {"info": [{"key": "image", "id": "i1", "data": {"caption": "C" * 300}}]},
    }
    assert views._stored_cblock_data(cfg, "b1")["url"] == long_url
    assert views._stored_cblock_data(cfg, "i1")["caption"] == "C" * 300
    assert views._stored_cblock_data(cfg, "zz") == {}
    post = QueryDict(mutable=True)
    post.update({"cb_b1_label": "L" * 300, "cb_b1_url": long_url})
    notes = []
    data = views._read_cblock_data(
        post, "b1", "button", notes, views._stored_cblock_data(cfg, "b1")
    )
    assert data["url"] == long_url and data["label"] == "L" * 300 and notes == []
    post["cb_b1_label"] = "N" * 300  # изменённое — режется, с сообщением
    data = views._read_cblock_data(
        post, "b1", "button", notes, views._stored_cblock_data(cfg, "b1")
    )
    assert data["label"] == "N" * 200 and data["url"] == long_url and notes


def test_tab_missing_on_the_block_is_not_kept():
    """П.4: zu_tab из белого списка, но вкладки у блока нет — без перехода и якоря."""
    b = Browser(_shop())
    resp, _msgs = b.post(**_texte_post(b, title="Neu"), zu_tab="karte")
    loc = resp["Location"]
    assert "tab=karte" not in loc and "schema-tab-karte" not in loc and "tab=texte" in loc
    assert _row(b, "t1")["data"]["title"] == "Neu"  # правка при этом применена
    assert block_window.goto_tab(QueryDict("zu_tab=wie&bw_tabs=wie+texte")) == "wie"
    assert block_window.goto_tab(QueryDict("zu_tab=wie")) == ""


def test_only_form_operations_move_to_the_tab():
    """П.6: переход — только у правки формы (op из OP_DEFAULTS), не у прочих операций."""
    b = Browser(_shop())
    data = {**_texte_post(b), "op": "toggle"}
    resp, _msgs = b.post(**data, zu_tab="wie")
    assert "schema-tab-wie" not in resp["Location"] and "tab=wie" not in resp["Location"]


def test_every_live_applying_part_has_its_form():
    """П.5: у каждой живой применяющей части окна — форма с её `form_id` (записи card_pick/faq
    ждут части M3-4/M3-5b; пока их нет в `parts()` — пропускаются)."""
    b = Browser(_shop())
    seen = set()
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        html, view, selected = _capture(b, f"?seite={code}&block={ref}{extra}")
        panel = _panel(html)
        if view["confirm_remove"]:
            continue  # подтверждение удаления — без частей окна
        for part in block_window.parts(selected, view):
            if part in block_window.APPLY_FORM_PARTS:
                seen.add(part)
                assert f'id="{block_window.form_id(part)}"' in panel, (case, part)
    with translation.override("de"):
        felder = _felder_page()
    assert f'id="{block_window.form_id("formfields")}"' in felder
    assert {"fields", "usp"} <= seen


def _felder_page():
    from django.test import override_settings

    with override_settings(ROOT_URLCONF="config.urls_tenant"):
        return _felder().get("?seite=anfrage&block=form&tab=felder")


def test_link_tabs_with_a_form_warn_to_apply_first():
    """П.3: вкладки-ссылки, а у открытой форма с «Übernehmen» — подсказка (без JS)."""
    b = Browser(_shop())
    with translation.override("de"):
        listing = _panel(b.get("?seite=home&block=l1"))
        texte = _panel(b.get("?seite=home&block=t1&tab=texte"))
        wie = _panel(b.get("?seite=home&block=t1"))
    hint = '<p class="mt-2 text-xs text-gray-700" data-window-hint>Erst „Übernehmen“'
    assert hint in listing
    assert "data-window-hint" not in texte  # кнопки вкладок применяют сами
    assert "data-window-hint" not in wie  # «Wie» у текста — плитки и «Platz» без «Übernehmen»
    assert 'aria-current="page"' in listing
