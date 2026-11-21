"""FB-33 стопка 2 (M3-4 → M3-5a → M3-5b): стыки срезов.

- «Karte» (M3-4) — применяющая часть M3-5a: без скриптов прочие вкладки — кнопки формы
  `bw-form-card_pick`; вторая форма вкладки («zurücksetzen») правило «одна часть» не ломает.
- FAQ (M3-5b) во «Texte» — одна применяющая часть: кнопки вкладок применяют вопросы (и новый
  вопрос), Enter — «Übernehmen» формы (`faq_add`); плашки во «Was» — вкладки-ссылки с подсказкой.
- Фокус на вопросе FAQ после ↑/↓/Entfernen/нового вопроса — якорь вопроса (как «Felder» M3-5a).
- «anzeigen» плашки своих форм при открытии — «ausblenden».
"""

import re

import pytest
from django.http import QueryDict
from django.utils import translation

from apps.core import block_window, faq_content, window_parts
from apps.core.tests import test_fb33_m35b_faq_draft as faq_t
from apps.core.tests import test_fb33_m35b_tiles_window as tiles_t
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_1b_window_cancel import _home_item
from apps.core.tests.test_fb33_m3_4_karte import _browser, _products
from apps.core.tests.test_fb33_m3_window_before import _panel

pytestmark = pytest.mark.django_db


def _nav(panel):
    at = panel.index("data-window-tabs")
    start = panel.rindex("</h2>", 0, at)
    return panel[start : panel.index("</nav>", at)]


def _tabs_value(panel, form):
    m = re.search(rf'<input type="hidden" form="{form}" name="bw_tabs" value="([^"]*)">', panel)
    return m.group(1) if m else ""


# --- a) «Karte» — кнопки вкладок без скриптов --------------------------------------------------


def test_karte_tab_turns_other_tabs_into_buttons_of_its_form():
    b = _browser()
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=l1&tab=karte"))
    nav = _nav(panel)
    assert re.search(
        r'<button type="submit" form="bw-form-card_pick" name="zu_tab" value="wie"', nav
    )
    default = re.search(r"<button[^>]*data-window-default[^>]*>", nav).group(0)
    assert 'form="bw-form-card_pick" name="op" value="update"' in default
    assert 'id="bw-form-card_pick"' in panel
    assert "karte" in _tabs_value(panel, "bw-form-card_pick").split()


def test_karte_reset_form_keeps_one_applying_part():
    b = _browser()
    b.get("?seite=home&block=l1")
    b.post(seite="home", ref="l1", op="update", panel_present="1", f_card="deal")
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=l1&tab=karte"))
    assert "data-schema-card-reset-form" in panel  # своя форма — есть «zurücksetzen»
    assert 'form="bw-form-card_pick" name="zu_tab"' in panel
    # кнопки вкладок — только формы «Karte», не формы сброса
    assert re.findall(r'form="([^"]+)" name="zu_tab"', panel) == ["bw-form-card_pick"] * len(
        re.findall(r'name="zu_tab"', panel)
    )


def test_karte_tab_button_applies_the_card_and_opens_the_tab():
    b = _browser()
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=l1&tab=karte"))
    tabs = _tabs_value(panel, "bw-form-card_pick")
    resp, msgs = b.post(
        seite="home",
        ref="l1",
        panel_present="1",
        tab="karte",
        bw_tabs=tabs,
        f_card="deal",
        zu_tab="wie",
    )
    assert msgs == []
    assert _home_item(b, "l1")["data"]["card"] == "deal"
    assert "tab=wie" in resp["Location"] and resp["Location"].endswith("#schema-tab-wie")


# --- b) FAQ во «Texte», плашки во «Was» ---------------------------------------------------------


def test_faq_texte_tab_buttons_apply_the_questions():
    b = Browser(faq_t._tenant())
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=faq&tab=texte"))
    nav = _nav(panel)
    assert re.search(r'<button type="submit" form="bw-form-faq" name="zu_tab" value="wie"', nav)
    default = re.search(r"<button[^>]*data-window-default[^>]*>", nav).group(0)
    # Enter — та же кнопка, что «Übernehmen» формы (принимает и новый вопрос)
    assert 'form="bw-form-faq" name="faq_add" value="1"' in default
    assert "update" in block_window.OP_DEFAULTS  # op_default формы FAQ
    tabs = _tabs_value(panel, "bw-form-faq")
    resp, msgs = faq_t._faq_post(
        b,
        op_default="update",
        tab="texte",
        bw_tabs=tabs,
        zu_tab="wie",
        faq_0_q="A neu?",
        faq_new_q="D?",
        faq_new_a="4",
    )
    # FB-33 M3-5c: правка немецкого снимает перевод вопроса — сообщение, владелец остаётся во
    # вкладке (как у прочих сообщений окна); вопросы применены
    from apps.core import block_i18n

    assert msgs == [block_i18n.dropped_note(["ru"])]
    assert not resp["Location"].endswith("#schema-tab-wie")
    items = faq_t._drafts(b)["home"]["faq"]["items"]
    assert [it["q"] for it in items] == ["A neu?", "B?", "C?", "D?"]


def test_faq_tab_button_moves_when_no_translation_is_dropped():
    """FB-33 M3-5c (ревью M3): без сохранённого перевода правка вопроса — без сообщения, кнопка
    вкладки переходит, как до среза."""
    from apps.tenants.models import Tenant

    tenant = faq_t._tenant()
    cfg = dict(tenant.site_config)
    cfg.pop("i18n", None)
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    b = Browser(Tenant.objects.get(pk=tenant.pk))
    data = {"op_default": "update", "tab": "texte", "zu_tab": "wie", "bw_tabs": "wie texte"}
    resp, msgs = faq_t._faq_post(b, **data, faq_0_q="A neu?", faq_new_q="D?", faq_new_a="4")
    assert msgs == []
    assert resp["Location"].endswith("#schema-tab-wie") and "tab=wie" in resp["Location"]
    items = faq_t._drafts(b)["home"]["faq"]["items"]
    assert [it["q"] for it in items] == ["A neu?", "B?", "C?", "D?"]


def test_faq_tab_button_without_op_takes_the_form_default():
    """Форма без op (её op — скрытое поле; шлёт кнопка вкладки): `op_default=update`."""
    b = Browser(faq_t._tenant())
    data = {"op_default": "update", "zu_tab": "wie", "bw_tabs": "wie texte", "faq_0_q": "A2?"}
    resp, msgs = faq_t._faq_post(b, **data, op="")
    from apps.core import block_i18n  # FB-33 M3-5c: снятый перевод вопроса — сообщением

    assert msgs == [block_i18n.dropped_note(["ru"])]
    assert faq_t._drafts(b)["home"]["faq"]["items"][0]["q"] == "A2?"


def test_tiles_in_was_stay_links_with_the_apply_first_hint():
    b = Browser(tiles_t._tenant())
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=quicklinks"))
    assert 'id="bw-form-tiles"' in panel and "zu_tab" not in panel
    assert "data-window-tabs" in panel  # Was · Wie anordnen
    # вкладки-ссылки, а во «Was» форма с «Übernehmen» — подсказка применить до перехода
    assert "data-window-hint" in panel and "Erst „Übernehmen“" in panel


# --- c) фокус на вопросе FAQ --------------------------------------------------------------------


def test_faq_buttons_bring_focus_back_to_the_question():
    b = Browser(faq_t._tenant())
    resp, _m = faq_t._faq_post(b, faq_move="0:down")
    assert resp["Location"].endswith("#schema-tab-faq-1")
    with translation.override("de"):
        html = b.get("?seite=home&block=faq")
    assert re.search(r'<summary id="schema-tab-faq-1"[^>]*autofocus', html)
    assert '<h3 id="schema-tab-faq-list" tabindex="-1"' in html
    resp, _m = faq_t._faq_post(b, faq_remove="2")
    assert resp["Location"].endswith("#schema-tab-faq-1")  # последний — предыдущий
    resp, _m = faq_t._faq_post(b, faq_remove="0")
    assert resp["Location"].endswith("#schema-tab-faq-0")  # на его место встал следующий
    resp, _m = faq_t._faq_post(b, faq_add="1", faq_new_q="Neu?", faq_new_a="x")
    assert resp["Location"].endswith("#schema-tab-faq-1")
    resp, _m = faq_t._faq_post(b, faq_add="1")  # «Übernehmen» без нового — прежний якорь
    assert "#schema-tab-faq" not in resp["Location"]


def test_faq_anchor_rules():
    post = QueryDict("faq_present=1&faq_remove=0")
    assert window_parts.faq_anchor(post, 0) == window_parts.FAQ_LIST_ANCHOR
    assert window_parts.faq_anchor(QueryDict("faq_remove=0"), 3) == ""
    assert window_parts.faq_anchor(QueryDict("faq_present=1&faq_move=0:up"), 3, None) == ""
    assert window_parts.faq_anchor(QueryDict("faq_present=1&faq_add=1&faq_new_q=+"), 3) == ""
    assert faq_content.MAX_ITEMS >= 3


def test_faq_stale_form_keeps_the_panel_anchor():
    b = Browser(faq_t._tenant())
    resp, msgs = faq_t._faq_post(b, faq_move="0:down", faq_rev="alt")
    assert msgs and "#schema-tab-faq" not in resp["Location"]


# --- d) «anzeigen» / «ausblenden» ---------------------------------------------------------------


def test_own_forms_summary_says_hide_when_open():
    b = _browser()
    _products(n_own=2)
    with translation.override("de"):
        panel = _panel(b.get("?seite=home&block=l1&tab=karte"))
    summary = re.search(
        r"<summary.*?</summary>", panel[panel.index("data-schema-card-own") :], re.S
    )
    text = summary.group(0)
    assert (
        '<span class="font-semibold underline underline-offset-2 group-open:hidden">anzeigen'
        in text
    )
    assert 'group-open:inline">ausblenden</span>' in text and 'class="hidden ' in text
