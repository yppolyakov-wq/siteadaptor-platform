"""FB-33 M3-5b: часть «Fragen» окна блока FAQ (макет M0-4) — вкладка «Texte».

Замки: часть — у секции FAQ главной и блока «FAQ» страниц, во вкладке «Texte», одной
формой `bw-form-faq` (первая кнопка — «Übernehmen», без `panel_present`); вид — по-прежнему
«Wie anordnen»; окно показывает вопросы черновика; тексты экранированы; подпись «Gilt für
alle Seiten…»; у детальной секции «faq» (свои вопросы объекта) части нет.
"""

import copy
import re

import pytest

from apps.core import block_window, faq_content
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m35b_faq_draft import BASE, _faq_post, _tenant

pytestmark = pytest.mark.django_db


def _tab(html, key):
    m = re.search(rf'<section id="schema-tab-{key}".*?</section>', html, flags=re.S)
    return m.group(0) if m else ""


def _form(html):
    m = re.search(r'<form[^>]*id="bw-form-faq".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def test_home_faq_window_has_questions_in_texte_and_view_in_wie():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=faq")
    texte = _tab(html, "texte")
    assert 'id="bw-form-faq"' in texte and 'data-window-part="faq"' in texte
    assert 'name="f_style"' in _tab(html, "wie") and 'id="bw-form-faq"' not in _tab(html, "wie")
    form = _form(html)
    for i, item in enumerate(BASE):
        assert f'name="faq_{i}_q" value="{item["q"]}"' in form
    assert "Gilt für alle Seiten — dieselben Fragen zeigt jeder FAQ-Block." in form
    assert 'name="op_default" value="update"' in form and 'name="faq_present"' in form
    assert "panel_present" not in form
    first = re.search(r"<button[^>]*>", form).group(0)
    # Enter — «Übernehmen» (с новым вопросом), а не «↓» вопроса 1
    assert 'name="faq_add"' in first and "data-schema-apply" in first
    assert f'name="faq_rev" value="{faq_content.revision(BASE, [0, 1, 2])}"' in form
    assert 'aria-label="Frage 1 nach unten"' in form and "Frage 1 nach oben" not in form
    assert "Frage hinzufügen" in form


def test_window_tabs_registry_places_the_part():
    assert block_window.PART_TAB["faq"] == "texte"
    selected = {"faq_items": {"items": []}, "fields": [{"name": "style"}]}
    assert [t["key"] for t in block_window.tabs(selected, {})] == ["wie", "texte"]


def test_faq_ref_block_shows_the_same_questions():
    b = Browser(_tenant())
    form = _form(b.get("?seite=text&block=f1"))
    assert 'name="faq_2_q" value="C?"' in form


def test_window_shows_the_draft_and_its_number():
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    form = _form(b.get("?seite=home&block=faq"))
    assert form.index('value="B?"') < form.index('value="A?"')
    assert f'value="{faq_content.revision(BASE, [1, 0, 2])}"' in form


def test_questions_are_escaped():
    tenant = _tenant()
    cfg = copy.deepcopy(tenant.site_config)
    cfg["faq"] = [{"q": '<script>alert("x")</script>', "a": "<b>a</b>"}]
    tenant.site_config = cfg
    tenant.save()
    form = _form(Browser(tenant).get("?seite=home&block=faq"))
    assert "<script>alert" not in form and "&lt;script&gt;" in form and "<b>a</b>" not in form


def test_full_list_has_no_add():
    tenant = _tenant()
    cfg = copy.deepcopy(tenant.site_config)
    cfg["faq"] = [{"q": f"Q{i}?", "a": ""} for i in range(faq_content.MAX_ITEMS)]
    tenant.site_config = cfg
    tenant.save()
    form = _form(Browser(tenant).get("?seite=home&block=faq"))
    assert "data-faq-new" not in form
    assert "Höchstens 12 Fragen." in form  # лимит виден, а не молча пропавший «＋»


def test_other_blocks_have_no_faq_part():
    b = Browser(_tenant())
    for query in ("?seite=home&block=t1", "?seite=home&block=usp_bar", "?seite=text&block=tp1"):
        assert 'id="bw-form-faq"' not in b.get(query), query
