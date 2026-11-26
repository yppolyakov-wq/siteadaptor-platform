"""FB-33 M3-5c C3: поля перевода во вкладке «Texte» окна блока (без скриптов).

L13 кнопки языка — общий партиал `_bw_langs.html` (aria-pressed, lang, 44 px), группы всех
языков в DOM, имя — только у выбранного языка, первая кнопка формы — невидимая «Übernehmen»
(Enter не переключает язык), id в окне не повторяются, прежней подсказки со ссылкой нет.
L14 основной язык бизнеса не de — он первой кнопкой и выбран, немецкое поле «Deutsch
(Grundtext)», подсказка «Ihre Seite zeigt zuerst …». L15 язык помнится после действия
(`sprache`, фокус на кнопке), тексты экранированы.
"""

import copy
import re
from collections import Counter

import pytest
from django.utils import translation

from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.core.tests.test_fb33_m35c_draft import WOPEN, _post, _shop, _with_ru

pytestmark = pytest.mark.django_db
XSS = "<script>alert(1)</script>"


def _form(b, query="?seite=home&block=t1&tab=texte"):
    with translation.override("de"):
        html = b.get(query)
    m = re.search(r'<form[^>]*id="bw-form-fields".*?</form>', html, flags=re.S)
    return html, (m.group(0) if m else "")


def test_language_buttons_and_fields_of_the_chosen_language():
    html, form = _form(Browser(_shop(_with_ru())))
    buttons = re.findall(
        r'<button id="schema-tab-lang-(\w+)" name="f_sprache" value="\w+" lang="\w+" '
        r'aria-pressed="(\w+)"',
        form,
    )
    assert buttons == [("ru", "true"), ("en", "false")]
    assert 'role="group" aria-labelledby="bwtr-lang-title"' in form
    assert re.search(r'<div data-i18n-loc="ru">\s*<label for="schema-f-title-ru"', form)
    assert re.search(r'<div data-i18n-loc="en" hidden>', form)
    assert 'name="f_tr_title_ru" value="Привет" lang="ru"' in form
    assert re.search(r'<textarea id="schema-f-body-ru" name="f_tr_body_ru"', form)
    assert "_en" not in "".join(re.findall(r'name="[^"]*"', form))  # имя — только у ru
    assert re.search(r'id="schema-f-title-en" disabled', form)
    assert (
        "Ohne Übersetzung:" in form and '<span lang="de" class="break-words">Hallo</span>' in form
    )
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'value="update"' in first and "sr-only" in first  # Enter — «Übernehmen»
    assert "data-schema-translate" not in form  # прежней ссылки на страницу нет
    ids = Counter(re.findall(r'\bid="([^"]+)"', _panel(html)))
    assert [i for i, n in ids.items() if n > 1] == []


def test_business_language_first_and_german_marked_as_base():
    _html, form = _form(Browser(_shop(locales=("de", "en", "ru"), default="ru")))
    assert re.findall(r'name="f_sprache" value="(\w+)"', form) == ["ru", "en"]
    assert re.findall(r'value="(\w+)" lang="\w+" aria-pressed="true"', form) == ["ru"]
    first = (
        'Ihre Seite zeigt zuerst <span lang="ru">Русский</span>.'  # стопка 16 T3: эндоним с lang
    )
    assert "Deutsch (Grundtext)" in form and first in form
    _html, plain = _form(Browser(_shop()))
    assert "Deutsch (Grundtext)" not in plain and "Ihre Seite zeigt zuerst" not in plain


def test_language_is_remembered_and_focus_goes_to_its_button():
    b = Browser(_shop())
    resp, _msgs = _post(b, title="Hallo", body="Welt", tr_title_ru="Привет", sprache="en")
    assert "sprache=en" in resp["Location"]
    assert resp["Location"].endswith("#schema-tab-lang-en")
    _html, form = _form(b, "?seite=home&block=t1&tab=texte&sprache=en&wopen=" + WOPEN)
    assert re.findall(r'value="(\w+)" lang="\w+" aria-pressed="true"', form) == ["en"]
    assert '<input type="hidden" name="sprache" value="en">' in form
    assert 'name="f_tr_title_en"' in form and 'name="f_tr_title_ru"' not in form


def test_texts_are_escaped():
    cfg = _with_ru(title=XSS)
    b = Browser(_shop(cfg))
    _html, form = _form(b)
    assert XSS not in form and "&lt;script&gt;" in form


def test_page_title_window_has_translations():
    cfg = copy.deepcopy(_with_ru())
    cfg["page_titles"] = {"promos": {"title": "Aktionen"}}
    _html, form = _form(Browser(_shop(cfg)), "?seite=promos&block=__page")
    assert 'name="f_tr_title_ru"' in form and 'name="f_tr_intro_ru"' in form
    assert 'name="f_tr_align_ru"' not in form
