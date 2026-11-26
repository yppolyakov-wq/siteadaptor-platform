"""FB-33 стопка 16 T2 (+T5): язык бизнеса первым во «Felder», «Deutsch (Ausgangstext)».

Правило языков окна — одна функция `i18n_input.window_langs` (порядок: язык бизнеса первым;
выбранный: `wanted`, иначе язык бизнеса, иначе первый; подпись немецкого поля и подсказка
«Ihre Seite zeigt zuerst …»). «Felder» зовёт её из `form_spec.with_locales`; «Texte»
(`block_i18n.decorate`) переключит T1b — до него строка подсказки там ещё своя.
Блок языков `_bw_langs.html`: параметр `ns` (пространство id), `first_note` с id, на который
ссылается группа кнопок; без `ns` — прежние id. Бизнес с de — вкладка как до среза.
"""

import ast
import re
from collections import Counter
from pathlib import Path

import polib
import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.core import form_spec
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i5_draft import _tenant
from apps.core.tests.test_fb33_m35c_draft import _shop

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
BASE_NOTE = "Deutsch (Ausgangstext)"
FIRST = "Ihre Seite zeigt zuerst"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(default="ru", locales=("de", "en", "ru")):
    tenant = _tenant()
    tenant.enabled_locales = list(locales)
    tenant.default_locale = default
    tenant.save(update_fields=["enabled_locales", "default_locale"])
    return Browser(tenant)


def _part(b, query=""):
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder" + query)
    start = html.index("data-form-felder")
    part = html[start : html.index("</form>", start)]
    # токен CSRF и метка открытия окна — свои у каждого запроса
    part = re.sub(r'(name="(?:csrfmiddlewaretoken|wopen)" value=")[^"]*', r"\1", part)
    return html, part


def _gettext_calls(text: str) -> list[str]:
    """Файлы `apps/` (без тестов), где строка `text` — аргумент gettext/gettext_lazy/_."""
    out = []
    for path in sorted((ROOT / "apps").rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        if text not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.startswith(text)
            ):
                out.append(str(path.relative_to(ROOT)))
    return out


def test_window_langs_owns_note_strings():
    assert _gettext_calls(BASE_NOTE) == ["apps/core/i18n_input.py"]
    # «Texte» (block_i18n) держит свою подсказку до T1b — других мест нет
    assert set(_gettext_calls(FIRST)) <= {"apps/core/i18n_input.py", "apps/core/block_i18n.py"}
    assert "apps/core/i18n_input.py" in _gettext_calls(FIRST)
    tree = ast.parse((ROOT / "apps/core/form_spec.py").read_text(encoding="utf-8"))
    func = next(n for n in tree.body if getattr(n, "name", "") == "with_locales")
    called = {getattr(n.func, "id", "") for n in ast.walk(func) if isinstance(n, ast.Call)}
    assert "window_langs" in called


def test_window_langs_rule():
    from apps.core.i18n_input import window_langs

    got = window_langs(["en", "ru"], "ru", "")
    assert got["locs"] == ["ru", "en"] and got["lang"] == "ru"
    assert got["base_note"] and got["first_note"]
    assert window_langs(["en", "ru"], "ru", "en")["lang"] == "en"
    plain = window_langs(["en", "ru"], "de", "")
    assert plain == {"locs": ["en", "ru"], "lang": "en", "base_note": "", "first_note": ""}
    # язык бизнеса вне языков перевода — прежний порядок, без подписи
    assert window_langs(["en"], "ru", "")["locs"] == ["en"]
    assert window_langs(["en"], "ru", "")["first_note"] == ""
    assert window_langs([], "ru", "x") == {
        "locs": [],
        "lang": "",
        "base_note": "",
        "first_note": "",
    }


@pytest.mark.parametrize("default", ["ru"])
def test_felder_business_language_first_and_selected(default):
    _html, part = _part(_browser(default))
    buttons = re.findall(
        r'<button id="schema-tab-lang-(\w+)" name="f_sprache" value="\w+" lang="\w+" '
        r'aria-pressed="(\w+)"[^>]*>(<span aria-hidden="true">✓ </span>)?',
        part,
    )
    assert buttons == [("ru", "true", '<span aria-hidden="true">✓ </span>'), ("en", "false", "")]
    assert re.search(r'<div data-i18n-loc="ru">\s*<label for="ff-label-phone-ru"', part)
    assert re.search(r'<div data-i18n-loc="en" hidden>', part)
    _html, part = _part(_browser(default), "&sprache=en")
    assert re.findall(r'value="(\w+)" lang="\w+" aria-pressed="true"', part) == ["en"]


def _old_part(monkeypatch, b):
    """Рендер, как до среза: `with_locales` без языка бизнеса."""
    real = form_spec.with_locales

    def old(fs, locales, wanted="", default_locale=""):
        return real(fs, locales, wanted)

    with monkeypatch.context() as m:
        m.setattr(form_spec, "with_locales", old)
        return _part(b)[1]


def test_felder_unchanged_for_german_business(monkeypatch):
    b = _browser("de")
    _html, part = _part(b)
    assert part == _old_part(monkeypatch, b)
    assert BASE_NOTE not in part and FIRST not in part
    assert re.findall(r'name="f_sprache" value="(\w+)"', part) == ["en", "ru"]
    assert 'aria-labelledby="ff-lang-title" aria-describedby="ff-lang-hint"' in part
    # язык бизнеса вне включённых языков — тоже прежняя вкладка
    b = _browser("ru", locales=("de", "en"))
    assert _part(b)[1] == _old_part(monkeypatch, b)


def test_felder_base_note_on_custom_label_and_question():
    _html, part = _part(_browser())
    assert re.search(
        r'>Eigene Beschriftung <span class="font-normal text-gray-700">– Deutsch \(Ausgangstext\)'
        r"</span></label>",
        part,
    )
    assert re.search(r">Frage 1 <span[^>]*>– Deutsch \(Ausgangstext\)</span></label>", part)
    # подсказка — внутри блока языков: после кнопок, до первого поля формы
    start = part.index("data-form-langs")
    note = part.index("Ihre Seite zeigt zuerst Русский.")
    assert part.index('name="f_sprache"', start) < note < part.index("data-form-field=", start)


def test_first_note_described_by_group():
    _html, part = _part(_browser())
    m = re.search(r'<p id="([^"]+)"[^>]*>Ihre Seite zeigt zuerst Русский\.</p>', part)
    assert m, "у подсказки свой id"
    group = re.search(r'role="group" aria-labelledby="[^"]+" aria-describedby="([^"]+)"', part)
    assert group.group(1).split() == ["ff-lang-hint", m.group(1)]


LOCALES = [{"code": "ru", "label": "Русский", "shown": True}, {"code": "en", "label": "English"}]


def _langs(**kw):
    with translation.override("de"):
        return render_to_string("tenant/_bw_langs.html", {"locales": LOCALES, **kw})


def test_langs_block_ids_namespaced():
    doc = _langs(ns="usp", first_note="Ihre Seite zeigt zuerst Русский.") + _langs(
        ns="seo", first_note="Ihre Seite zeigt zuerst Русский."
    )
    ids = Counter(re.findall(r'\bid="([^"]+)"', doc))
    assert [i for i, n in ids.items() if n > 1] == []
    assert "schema-tab-lang-usp-ru" in ids and "schema-tab-lang-seo-ru" in ids
    for ref in re.findall(r'aria-(?:labelledby|describedby)="([^"]+)"', doc):
        assert all(i in ids for i in ref.split())
    # без ns — прежние id и прежний вид (Felder и Texte байт-в-байт)
    plain = _langs()
    assert re.findall(r'\bid="([^"]+)"', plain) == [
        "ff-lang-title",
        "schema-tab-lang-ru",
        "schema-tab-lang-en",
        "ff-lang-hint",
    ]
    assert 'aria-describedby="ff-lang-hint"' in plain
    texte = _langs(title_id="bwtr-lang-title", hint_id="bwtr-lang-hint")
    assert re.findall(r'\bid="([^"]+)"', texte)[0] == "bwtr-lang-title"


def test_no_german_button_in_lang_block():
    _html, part = _part(_browser())
    assert "de" not in re.findall(r'name="f_sprache" value="(\w+)"', part)
    from apps.core.tests.test_fb33_m35c_window import _form

    _html, form = _form(Browser(_shop(locales=("de", "en", "ru"), default="ru")))
    assert re.findall(r'name="f_sprache" value="(\w+)"', form) == ["ru", "en"]


def test_ausgangstext_msgid_in_all_po():
    for loc in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{loc}/LC_MESSAGES/django.po"))
        entry = next(e for e in po if e.msgid == BASE_NOTE and not e.msgctxt)
        assert entry.msgstr and "fuzzy" not in entry.flags, loc


def test_first_note_not_a_second_live_region():
    _html, part = _part(_browser())
    _html, plain = _part(_browser("de"))
    assert part.count('role="status"') == plain.count('role="status"')
    note = re.search(r"<p[^>]*>Ihre Seite zeigt zuerst", part).group(0)
    assert "role=" not in note and "aria-live" not in note
