"""FB-33 стопка 16 T3: «🌐 Übersetzen» во вкладке «Texte» окна блока (+ пачки ревью T2, T1a).

Кнопка — тот же партиал, что во «Felder» (`_bw_formfields_ai.html`), вставка — в
`_bw_tr_note.html` (её берут все части «Texte»), только при ИИ (`tr`) и языках перевода; у
плашек («Was») — нет. Клиент один (`_i18n_translate_js.html`): заполняет только пустые поля
выбранного языка, переведённое — в черновик тихим `change`. Замки §4 плана «T3»:

- №19 кнопка в `fields`, `hometext`, `faq` — при ИИ и языке перевода; нет без ИИ, при одном
  языке и у плашек;
- №22 (a11y №4) id пометки ИИ «Texte» — `bwtr-ai-note[-<ns>]`, у «Felder» прежний;
- поле перевода с кнопкой несёт `data-i18n-of` на поле той же формы;
- a11y №8 имя кнопки «Übersetzen (Sprache: Русский)», видимое — начало имени, язык с `lang`;
- a11y №3 одна живая область: кнопка пишет в `data-form-status` блока языков (`data-status`);
- a11y №5 видимая пометка «Automatisch übersetzt – bitte prüfen» у поля, заполненного ИИ;
- a11y №10 служебный текст «Ohne Übersetzung:» (`t.empty_ui`) — без `lang` бизнеса;
- «Ihre Seite zeigt zuerst …» рисует блок языков (T2), эндоним — с `lang` (ревью T2 LOW);
- все ссылки `aria-*` окна — на существующие id; «Felder» бизнеса с de — байт-в-байт как до T2;
- ревью T1a A1: подпись поля перевода называет поле (`field`) и без цитаты.
"""

import difflib
import re
from collections import Counter
from pathlib import Path

import polib
import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.core.tests import test_fb33_m2i5c_translate as m2i5c
from apps.core.tests.test_fb33_m3_window_before import _panel

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
BTN = re.compile(r"<button[^>]*data-i18n-translate[ >].*?</button>", re.S)
NOTE = "Automatisch übersetzt – bitte prüfen"
#: «Felder» бизнеса с de, ИИ выключен — эталон снят на `5169ae7` (до T2) тем же `m2i5c._part`
#: в чистой тест-БД со свежими `.mo` (ревью T3 D1: файл с читаемым диффом, не хеш)
FELDER_DE_GOLDEN = Path(__file__).parent / "golden_fb33s16t3" / "felder_de_before_t2.html"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _form(html, fid):
    m = re.search(rf'<form[^>]*id="{fid}".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def _get(tenant, query):
    with translation.override("de"):
        return _panel(m2i5c._ScreenBrowser(tenant).get(query))


def _fields_tenant(locales=("de", "ru", "en"), default="de"):
    from apps.core.tests import test_fb33_m35c_draft as c5

    return c5._shop(c5._with_ru(), locales=locales, default=default)


def _hometext_tenant(locales=("de", "ru")):
    from apps.core.tests import test_s15_m5e1b_home_window as h

    tenant = h._shop()
    tenant.enabled_locales = list(locales)
    tenant.save()
    return tenant


def _faq_tenant(locales=("de", "ru")):
    from apps.core.tests.test_fb33_m35b_faq_draft import _tenant

    tenant = _tenant()
    tenant.enabled_locales = list(locales)
    tenant.save()
    return tenant


#: часть «Texte» → (тенант, адрес окна, id формы)
PARTS = {
    "fields": (_fields_tenant, "?seite=home&block=t1&tab=texte", "bw-form-fields"),
    "hometext": (_hometext_tenant, "?seite=home&block=about&tab=texte", "bw-form-hometext"),
    "faq": (_faq_tenant, "?seite=home&block=faq&tab=texte", "bw-form-faq"),
}


def _texte(part, **kw):
    make, query, fid = PARTS[part]
    panel = _get(make(**kw), query)
    return panel, _form(panel, fid)


def _btn(form):
    m = BTN.search(form)
    return m.group(0) if m else ""


def _name(html):
    """Доступное имя: без `aria-hidden`, текст без тегов, пробелы схлопнуты."""
    html = re.sub(r'<span aria-hidden="true">.*?</span>', "", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


# --- №19: кнопка в «Texte» ----------------------------------------------------------------


@pytest.mark.parametrize("part", sorted(PARTS))
def test_texte_ai_button_only_with_tr_and_langs(monkeypatch, part):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte(part)
    btn = _btn(form)
    assert btn and 'data-loc="ru"' in btn and 'type="button"' in btn, form[:400]
    assert form.count("data-i18n-translate ") == 1
    box = m2i5c.BOX.search(form).group(0)
    assert box.startswith("<div data-i18n-translate-box hidden>"), "без скриптов не видна"
    # внутри блока языков: после подсказки «Leeres Feld…»
    assert form.index("bwtr-lang-hint") < form.index("data-i18n-translate-box")
    m2i5c._ai(monkeypatch, on=False)
    assert "data-i18n-translate" not in _texte(part)[1]
    m2i5c._ai(monkeypatch)
    assert "data-i18n-translate" not in _texte(part, locales=("de",))[1], "один язык"


def test_tiles_have_no_ai_button(monkeypatch):
    from apps.core import hero_tiles
    from apps.core.tests.test_fb33_m35b_tiles_window import _tenant as tiles_tenant

    m2i5c._ai(monkeypatch)
    keys = hero_tiles.tile_keys("aktionsmarkt")
    tenant = tiles_tenant({"set": "aktionsmarkt", "labels": {keys[0]: "Meine Deals"}})
    tenant.enabled_locales = ["de", "ru"]
    tenant.save()
    form = _form(_get(tenant, "?seite=home&block=quicklinks"), "bw-form-tiles")
    assert 'data-i18n-loc="ru"' in form, "у плашки есть поле перевода"
    assert "data-i18n-translate" not in form and "data-i18n-of" not in form


# --- №22 (a11y №4): id пометки ИИ ---------------------------------------------------------


def test_texte_note_id_differs_from_felder(monkeypatch):
    m2i5c._ai(monkeypatch)
    panel, form = _texte("fields")
    assert 'data-note="bwtr-ai-note"' in _btn(form) and 'id="bwtr-ai-note"' in form
    ids = Counter(re.findall(r'\bid="([^"]+)"', panel))
    assert [i for i, n in ids.items() if n > 1] == []
    # «Felder» — прежний id (замок M2i-5c)
    _html, felder = m2i5c._part(m2i5c._b())
    assert 'data-note="i18n-ai-note"' in felder and 'id="i18n-ai-note"' in felder
    # блок языков со своим пространством id — свои id пометки и живой области
    with translation.override("de"):
        doc = render_to_string(
            "tenant/_bw_tr_note.html",
            {
                "tr": {"url": "/t/", "result": "/r/", "screen": "s", "base": "de"},
                "ns": "usp",
                "locales": [{"code": "ru", "label": "Русский", "shown": True}],
            },
        )
    assert 'id="bwtr-ai-note-usp"' in doc and 'data-status="bwtr-status-usp"' in doc
    assert 'id="bwtr-status-usp"' in doc


# --- источник текста ----------------------------------------------------------------------


@pytest.mark.parametrize("part", sorted(PARTS))
def test_texte_translation_inputs_have_source(monkeypatch, part):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte(part)
    names = set(re.findall(r'\bname="([^"]+)"', form))
    fields = re.findall(r"<(?:input|textarea)[^>]*\blang=\"ru\"[^>]*>", form)
    assert fields
    for el in fields:
        of = re.search(r'data-i18n-of="([^"]+)"', el)
        assert of, el
        assert of.group(1) in names, (of.group(1), el)
    # без ИИ — прежний вид (эталоны)
    m2i5c._ai(monkeypatch, on=False)
    assert "data-i18n-of" not in _texte(part)[1]


# --- a11y №8: имя кнопки ------------------------------------------------------------------


def test_translate_button_name_has_language(monkeypatch):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte("fields")
    btn = _btn(form)
    assert _name(btn) == "Übersetzen (Sprache: Русский)"
    assert '<span lang="ru">Русский</span>' in btn
    assert re.search(r'<span class="sr-only">[^<]*\(Sprache: <span lang="ru">', btn)
    # «Felder» — так же (тот же партиал)
    _html, felder = m2i5c._part(m2i5c._b())
    assert _name(_btn(felder)) == "Übersetzen (Sprache: Русский)"
    for loc in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{loc}/LC_MESSAGES/django.po"))
        entry = next(e for e in po if e.msgid == "(Sprache: %(lang)s)" and not e.msgctxt)
        assert entry.msgstr and "fuzzy" not in entry.flags, loc


# --- a11y №3: одна живая область ----------------------------------------------------------


def test_one_live_region_per_translate_event(monkeypatch):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte("fields")
    status = re.search(r'data-status="([^"]+)"', _btn(form)).group(1)
    target = re.search(rf'<p[^>]*\bid="{status}"[^>]*>', form).group(0)
    assert "data-form-status" in target and 'role="status"' in target
    own = re.search(r"<span[^>]*data-i18n-translate-status[^>]*>", form).group(0)
    assert "role=" not in own and "aria-live" not in own
    assert form.count('role="status"') == 1
    # «Felder» — прежняя своя живая область кнопки (замок M2i-5c)
    _html, felder = m2i5c._part(m2i5c._b())
    assert "data-status=" not in _btn(felder)


# --- a11y №5: видимая пометка ИИ ----------------------------------------------------------


def test_ai_note_visible_and_described(monkeypatch):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte("fields")
    marks = re.findall(r"<p[^>]*data-ai-mark[^>]*>.*?</p>", form, flags=re.S)
    assert len(marks) == len(re.findall(r"<div data-i18n-loc=", form)), "у каждого поля"
    for mk in marks:
        assert "sr-only" not in mk and NOTE in mk
        assert re.search(r'<span aria-hidden="true">[^<]+</span>', mk), "значок"
        # видна только у поля с пометкой клиента (data-ai-filled — после поля, в той же группе)
        assert "hidden" in mk and "[[data-ai-filled]~&]:flex" in mk
    # цель aria-describedby поля (data-note кнопки) — в той же форме
    note = re.search(r'data-note="([^"]+)"', _btn(form)).group(1)
    assert f'id="{note}"' in form
    m2i5c._ai(monkeypatch, on=False)
    assert "data-ai-mark" not in _texte("fields")[1]


# --- a11y №10: служебный текст «Ohne Übersetzung» -----------------------------------------


def _tr(ctx=None, **t):
    base = {
        "loc": "ru",
        "label": "Русский",
        "id": "x-ru",
        "name": "f_tr_x_ru",
        "shown": True,
        "value": "",
        "empty": "Hallo",
        "empty_lang": "de",
        "hint": "h",
    }
    with translation.override("de"):
        return render_to_string("tenant/_bw_tr.html", {**(ctx or {}), "t": {**base, **t}})


def test_empty_ui_text_has_no_business_lang():
    plain = _tr()
    assert '<span lang="de" class="break-words">Hallo</span>' in plain
    ui = _tr(empty="Standardtext der Seite", empty_ui=True)
    src = re.search(r'<p id="x-ru-src"[^>]*>.*?</p>', ui, flags=re.S).group(0)
    assert "Standardtext der Seite" in src and "lang=" not in src


# --- «Ihre Seite zeigt zuerst …» (T2 → T3, ревью T2 LOW) ----------------------------------


def test_first_note_moved_to_langs_block():
    panel, form = _texte("fields", default="ru")
    assert "data-tr-first" not in panel
    assert form.count("data-langs-first") == 1
    note = re.search(r"<p[^>]*data-langs-first[^>]*>(.*?)</p>", form, flags=re.S).group(1)
    assert note == 'Ihre Seite zeigt zuerst <span lang="ru">Русский</span>.'
    with translation.override("de"):
        doc = render_to_string(
            "tenant/_bw_tr_note.html", {"fl": {"first_note": "Ihre Seite zeigt zuerst X."}}
        )
    assert "zeigt zuerst" not in doc


def test_felder_first_note_endonym_has_lang():
    from apps.core.tests.test_s16_t2_felder_langs import _browser, _part

    _html, part = _part(_browser())
    note = re.search(r"<p[^>]*data-langs-first[^>]*>(.*?)</p>", part, flags=re.S).group(1)
    assert note == 'Ihre Seite zeigt zuerst <span lang="ru">Русский</span>.'


# --- ссылки aria-* окна и прежняя «Felder» ------------------------------------------------


def _refs_ok(doc):
    ids = set(re.findall(r'\bid="([^"]+)"', doc))
    bad = []
    for ref in re.findall(r'aria-(?:labelledby|describedby)="([^"]*)"', doc):
        bad += [i for i in ref.split() if i not in ids]
    return bad


def test_window_aria_refs_point_to_existing_ids(monkeypatch):
    from apps.core.tests import test_s16_t1a_usp_i18n as t1a
    from apps.core.tests.test_s16_t2_felder_langs import _browser

    m2i5c._ai(monkeypatch)
    for part in PARTS:
        panel, _form_html = _texte(part)
        assert _refs_ok(panel) == [], part
    panel, _f = _texte("fields", default="ru")
    assert _refs_ok(panel) == []
    with translation.override("de"):
        felder = _panel(
            m2i5c._ScreenBrowser(_browser().tenant).get("?seite=anfrage&block=form&tab=felder")
        )
    assert _refs_ok(felder) == []
    # блок языков со своим пространством (USP): ни одной ссылки на id «Texte» без ns
    b = t1a._browser()
    with translation.override("de"):
        panel = _panel(m2i5c._ScreenBrowser(b.tenant).get("?seite=home&block=usp_bar&tab=texte"))
    usp = _form(panel, "bw-form-usp")
    assert usp and _refs_ok(panel) == []
    for old in ("bwtr-lang-title", "bwtr-lang-hint", "ff-lang-title", "ff-lang-hint"):
        assert old not in usp, old


def test_felder_de_unchanged_since_before_t2(monkeypatch):
    m2i5c._ai(monkeypatch, on=False)
    _html, part = m2i5c._part(m2i5c._b())
    want = FELDER_DE_GOLDEN.read_text(encoding="utf-8")
    diff = difflib.unified_diff(
        want.splitlines(), part.splitlines(), "5169ae7", "HEAD", lineterm="", n=1
    )
    assert part == want, "\n".join(list(diff)[:60])


# --- ревью T1a A1: подпись поля перевода называет поле ------------------------------------


def test_usp_translation_labels_differ_for_empty_item():
    def tr(f):
        return {
            "loc": "en",
            "label": "English",
            "id": f"bw-usp-0-{f}-en",
            "shown": True,
            "name": f"f_tr_usp_0_{f}_en",
            "value": "",
            "empty": "",
            "empty_lang": "de",
            "hint": "usp-lang-hint",
            "of": f"f_usp_0_{f}",
        }

    with translation.override("de"):
        doc = render_to_string(
            "tenant/_schema_usp_fields.html",
            {
                "i": 0,
                "icon": "check",
                "label": "",
                "text": "",
                "usp": {"icons": []},
                "tr_label": [tr("label")],
                "tr_text": [tr("text")],
            },
        )
    labels = re.findall(r'<label for="bw-usp-0-\w+-en"[^>]*>(.*?)</label>', doc, flags=re.S)
    assert len(labels) == 2 and labels[0] != labels[1], labels
    assert _name(labels[0]) == "Titel – Übersetzung (English)"
    assert _name(labels[1]) == "Text – Übersetzung (English)"


# --- ревью T3 A1/A2: язык в подписи поля перевода -----------------------------------------


def _label(doc):
    return re.search(r"<label[^>]*>(.*?)</label>", doc, flags=re.S).group(1)


@pytest.mark.parametrize("biz", ["ru", "tr"])
def test_label_ui_what_has_no_business_lang(biz):
    """Строка интерфейса («Überschrift», «Frage 1») — без `lang` языка бизнеса."""
    label = _label(_tr({"what": "Frage 1"}, empty_lang=biz, loc="en", label="English"))
    assert "„Frage 1“" in label
    assert f'lang="{biz}"' not in label, label


def test_label_content_what_keeps_business_lang():
    """Текст бизнеса (пункт USP: `field` + `what`) — с `lang` языка бизнеса."""
    label = _label(_tr({"what": "Бесплатно", "field": "Titel"}, empty_lang="ru", loc="en"))
    assert '<span lang="ru">„Бесплатно“</span>' in label, label


@pytest.mark.parametrize("ctx", [{}, {"what": "Frage 1"}, {"what": "X", "field": "Titel"}])
def test_label_endonym_has_own_lang(ctx):
    label = _label(_tr(ctx))
    assert '<span lang="ru">Русский</span>' in label, label
    assert _name(label).endswith("Übersetzung (Русский)")


def test_label_endonym_escaped():
    label = _label(_tr(label="<b>x</b>", loc='ru"x'))
    assert "<b>" not in label and "&lt;b&gt;" in label and 'lang="ru&quot;x"' in label


# --- ревью T3 A3: пометка ИИ читается один раз --------------------------------------------


def test_visible_ai_mark_hidden_from_reader(monkeypatch):
    """Видимая копия — `aria-hidden`; для чтения — sr-only `data-note` по `aria-describedby`."""
    m2i5c._ai(monkeypatch)
    _panel_html, form = _texte("fields")
    marks = re.findall(r"<p[^>]*data-ai-mark[^>]*>", form)
    assert marks
    for mk in marks:
        assert 'aria-hidden="true"' in mk and "id=" not in mk, mk
    note = re.search(r'data-note="([^"]+)"', _btn(form)).group(1)
    assert re.search(rf'<span class="sr-only" id="{note}">{NOTE}</span>', form)


# --- ревью T3 A6: id живой области при двух блоках языков ---------------------------------


def test_status_ids_unique_with_two_lang_blocks():
    tr = {"url": "/t/", "result": "/r/", "screen": "s", "base": "de"}
    locs = [{"code": "ru", "label": "Русский", "shown": True}]
    with translation.override("de"):
        doc = "".join(
            render_to_string("tenant/_bw_tr_note.html", {"tr": tr, "ns": ns, "locales": locs})
            for ns in ("", "usp", "seo")
        )
    ids = Counter(re.findall(r'\bid="([^"]+)"', doc))
    assert [i for i, n in ids.items() if n > 1] == [], ids
    assert doc.count('role="status"') == 3
    for btn in BTN.findall(doc):
        for attr in ("data-status", "data-note"):
            ref = re.search(rf'{attr}="([^"]+)"', btn).group(1)
            assert ids[ref] == 1, (attr, ref)
