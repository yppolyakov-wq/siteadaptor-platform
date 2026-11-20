"""FB-33 M2i-5b C3: ввод переводов во вкладке «Felder» окна блока формы (без скриптов).

Языки бизнеса (без основного) — группами полей в DOM, видна группа выбранного языка; выбор —
серверными кнопками `f_sprache` (aria-pressed), язык помнится после «Übernehmen». Имена полей:
`f_label_<поле>_<язык>`, `f_q_<id>_label_<язык>`, `f_q_<id>_o<h>_<язык>`, `f_et_<h>_<язык>`;
`h` — от текста варианта ТЕКУЩЕГО черновика. Перевод языка, которого не было в форме, не
трогается; переименованный вариант теряет перевод с сообщением. У бизнеса с одним языком
вкладка прежняя (замок `test_fb33_m2i5b_before`).
"""

import copy
import re

import pytest
from django.utils import translation

from apps.core import form_spec
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i5_before import CUSTOM
from apps.core.tests.test_fb33_m2i5_draft import _drafts, _edit, _saved, _tenant
from apps.core.tests.test_fb33_m2i5_window_ui import _clean

pytestmark = pytest.mark.django_db
H_GARTEN = form_spec.text_hash("Garten")
H_HOCHZEIT = form_spec.text_hash("Hochzeit")
XSS = "<script>alert(1)</script>"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(cfg=None, locales=("de", "ru", "en")):
    tenant = _tenant(cfg)
    tenant.enabled_locales = list(locales)
    tenant.save(update_fields=["enabled_locales"])
    return Browser(tenant)


def _part(b, query=""):
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder" + query)
    start = html.index("data-form-felder")
    return html, html[start : html.index("</form>", start)]


def test_language_buttons_and_groups_in_dom():
    _html, part = _part(_browser())
    buttons = re.findall(
        r'<button id="schema-tab-lang-\w+" name="f_sprache" value="(\w+)"[^>]*aria-pressed="(\w+)"',
        part,
    )
    assert buttons == [("ru", "true"), ("en", "false")]
    assert 'role="group" aria-labelledby="ff-lang-title"' in part
    # все языки в DOM: выбранный виден, другой — hidden (значение уходит с формой)
    assert re.search(r'<div data-i18n-loc="ru">\s*<label for="ff-label-phone-ru"', part)
    assert re.search(r'<div data-i18n-loc="en" hidden>\s*<label for="ff-label-phone-en"', part)
    assert 'name="f_label_phone_ru"' in part and 'lang="ru"' in part
    assert f'name="f_et_{H_HOCHZEIT}_ru"' in part and "„Hochzeit“ – Übersetzung (Русский)" in part
    assert f'name="f_q_q2_o{H_GARTEN}_ru"' in part and 'name="f_q_q2_label_ru"' in part
    # ревью п.4: имя — только у полей выбранного языка (en — без name, disabled)
    assert '_en"' not in "".join(re.findall(r'name="[^"]*"', part))
    assert re.search(r'id="ff-label-phone-en" disabled', part)
    assert 'name="f_label_title_ru"' not in part  # закреплённые поля подписи не правят
    # Enter в поле — по-прежнему «Übernehmen», а не кнопка языка
    first = re.search(r"<button[^>]*>[^<]*</button>", part).group(0)
    assert 'name="f_commit_new"' in first


def test_language_button_switches_and_is_remembered():
    b = _browser()
    resp, _msgs = _edit(b, sprache="en", label_phone_ru="Мобильный")
    assert "sprache=en" in resp["Location"]
    _html, part = _part(b, "&sprache=en")
    assert re.findall(r'value="(\w+)"[^>]*aria-pressed="true"', part) == ["en"]
    assert re.search(r'<div data-i18n-loc="ru" hidden>', part)
    assert '<input type="hidden" name="sprache" value="en">' in part
    # «Übernehmen» со скрытым `sprache` — язык остаётся
    data = {"sprache": "en"}
    resp, _msgs = b.post(seite="anfrage", ref="form", op="update", panel_present="1", **data)
    assert "sprache=en" in resp["Location"]
    resp, _msgs = b.post(seite="anfrage", ref="form", op="update", panel_present="1", sprache="pl")
    assert "sprache=pl" in resp["Location"]  # язык платформы помнится; чужой — нет:
    resp, _msgs = b.post(seite="anfrage", ref="form", op="update", panel_present="1", sprache="x")
    assert "sprache" not in resp["Location"]


def test_translations_go_to_draft_and_save():
    b = _browser()
    _edit(
        b,
        label_phone_ru="Мобильный",
        label_email_en="Mail",
        q_q2_label_ru="Зал",
        **{f"q_q2_o{H_GARTEN}_ru": "Сад", f"et_{H_HOCHZEIT}_ru": "Свадьба", "et_deadbeef_ru": "x"},
    )
    form = _drafts(b)["anfrage"]["form"]
    assert form["labels_i18n"] == {"email": {"en": "Mail"}, "phone": {"ru": "Мобильный"}}
    assert form["event_types_i18n"] == {"Hochzeit": {"ru": "Свадьба"}}
    resp, _msgs = b.post(seite="anfrage", op="save")
    entry = _saved(b.tenant)["form_fields"]["anfrage"]
    assert entry["labels_i18n"]["phone"] == {"ru": "Мобильный"}
    assert entry["custom"][1]["label_i18n"] == {"ru": "Зал"}
    assert entry["custom"][1]["options_i18n"] == {"Garten": {"ru": "Сад"}}
    assert entry["event_types_i18n"] == {"Hochzeit": {"ru": "Свадьба"}}
    _html, part = _part(b)
    assert 'name="f_label_phone_ru" value="Мобильный"' in part


def test_language_not_in_form_is_kept():
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["labels_i18n"] = {"phone": {"en": "Mobile", "ru": "Моб"}}
    b = _browser(cfg, locales=("de", "ru"))  # en у бизнеса выключен — полей en нет
    _html, part = _part(b)
    assert 'name="f_label_phone_en"' not in part
    _edit(b, label_phone_ru="")  # ru стёрли
    b.post(seite="anfrage", op="save")
    assert _saved(b.tenant)["form_fields"]["anfrage"]["labels_i18n"] == {"phone": {"en": "Mobile"}}


def test_renamed_option_drops_translation_with_note():
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["custom"][1]["options_i18n"] = {"Garten": {"ru": "Сад"}}
    cfg["form_fields"]["anfrage"]["event_types_i18n"] = {"Hochzeit": {"ru": "Свадьба"}}
    b = _browser(cfg)
    _resp, msgs = _edit(
        b, q_q2_label="Raum", q_q2_options="Saal\nTerrasse", event_types="Trauung\nFirmenfeier"
    )
    form = _drafts(b)["anfrage"]["form"]
    assert "options_i18n" not in form["custom"][1]
    assert form["event_types_i18n"] == {}
    assert any("„Garten“" in m and "„Hochzeit“" in m for m in msgs)


def test_moved_option_keeps_translation():
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["event_types_i18n"] = {"Hochzeit": {"ru": "Свадьба"}}
    b = _browser(cfg)
    _resp, msgs = _edit(b, event_types="Firmenfeier\nHochzeit")
    assert _drafts(b)["anfrage"]["form"]["event_types_i18n"] == {"Hochzeit": {"ru": "Свадьба"}}
    assert msgs == []


def test_translations_are_escaped_in_window():
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["labels_i18n"] = {"phone": {"ru": XSS}}
    cfg["form_fields"]["anfrage"]["custom"][1]["options_i18n"] = {"Garten": {"ru": XSS}}
    _html, part = _part(_browser(cfg))
    _clean(part)


def test_main_text_is_visible_and_described():
    """Ревью a11y п.9: что покажет сайт без перевода — видимым текстом со своим `lang`
    (своя немецкая подпись — de, подпись по умолчанию — на языке перевода), связан с полем
    `aria-describedby` вместе с подсказкой; placeholder не нужен."""
    _html, part = _part(_browser())
    phone = re.search(r'<input[^>]*name="f_label_phone_ru"[^>]*>', part).group(0)
    assert 'aria-describedby="ff-label-phone-ru-src ff-lang-hint"' in phone
    assert "placeholder" not in phone
    assert re.search(
        r'<p id="ff-label-phone-ru-src"[^>]*>Ohne Übersetzung: <span lang="de">Handy</span>', part
    )
    with translation.override("ru"):
        email = translation.gettext("Email")
    assert re.search(
        rf'<p id="ff-label-email-ru-src"[^>]*>Ohne Übersetzung: <span lang="ru">{email}</span>',
        part,
    )
    assert 'id="ff-lang-hint"' in part


def test_question_is_a_group_and_translation_labels_name_the_text():
    """Ревью a11y п.7: вопрос — fieldset с legend «Frage N», подпись перевода называет текст."""
    _html, part = _part(_browser())
    box = part[part.index('data-form-question="q2"') - 80 :]
    assert re.match(r'.*<fieldset[^>]*data-form-question="q2"', box, re.S)
    assert '<legend class="sr-only">Frage 2</legend>' in box
    assert "„Raum“ – Übersetzung (Русский)" in box


def test_option_translations_are_folded_open_when_filled():
    """Ревью п.10: переводы вариантов — в <details>, открыт, если у выбранного языка что-то
    заполнено."""
    _html, part = _part(_browser())
    assert re.search(
        r"<details data-form-qo-tr>\s*<summary[^>]*>Optionen übersetzen \(Русский\) – 2", part
    )
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"]["custom"][1]["options_i18n"] = {"Garten": {"ru": "Сад"}}
    _html, part = _part(_browser(cfg))
    assert "<details open data-form-qo-tr>" in part
    assert '<details class="mt-2" data-form-et-tr>' in part  # у события пусто — свёрнуто


def test_language_button_keeps_unsaved_input_and_focus_anchor():
    """Ревью п.8: кнопка языка сначала применяет набранное, затем меняет язык; адрес ведёт к
    нажатой кнопке (`#schema-tab-lang-…`: фокус по id и в окне, и без JS)."""
    b = _browser()
    resp, _msgs = _edit(b, sprache="en", label_phone_ru="Мобильный")
    assert resp["Location"].endswith("#schema-tab-lang-en")
    assert _drafts(b)["anfrage"]["form"]["labels_i18n"]["phone"] == {"ru": "Мобильный"}
    _html, part = _part(b, "&sprache=en")
    assert 'id="schema-tab-lang-en" name="f_sprache" value="en"' in part


def test_max_form_stays_under_field_limit():
    """Ревью п.4: 10 вопросов × 20 вариантов, 12 вариантов события, 4 языка перевода —
    полей в POST меньше `DATA_UPLOAD_MAX_NUMBER_FIELDS` (1000)."""
    from django.conf import settings

    cfg = copy.deepcopy(CUSTOM)
    entry = cfg["form_fields"]["anfrage"]
    entry["custom"] = [
        {
            "id": f"q{i}",
            "type": "choice",
            "label": f"F{i}",
            "options": [f"o{i}-{k}" for k in range(20)],
        }
        for i in range(1, 11)
    ]
    entry["next_id"] = 10
    cfg["anfrage"]["event_types"] = [f"E{k}" for k in range(12)]
    _html, part = _part(_browser(cfg, locales=("de", "ru", "en", "tr", "uk")))
    names = re.findall(r'<(?:input|textarea|select|button)[^>]*\sname="([^"]+)"', part)
    limit = settings.DATA_UPLOAD_MAX_NUMBER_FIELDS or 1000
    assert len(set(names)) + 20 < limit, len(names)
    assert len(names) < 400
