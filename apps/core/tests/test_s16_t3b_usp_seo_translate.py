"""FB-33 стопка 16 T3b (T3.1): «🌐 Übersetzen» у полосы доверия (USP) и у SEO страницы.

T3 подключил кнопку во «Texte» вставкой `_bw_tr_note.html` при `tr`
(`i18n_translate_ctx` формы части). У форм USP (`_schema_usp.html`, ns «usp») и SEO
(`_bw_seo.html`, ns «seo») `tr` не задан — кнопки не было, хотя поля перевода готовы
(`data-i18n-of`, `field`). Замки:

- кнопка есть у USP и SEO при ИИ и языке перевода; нет без ИИ и при одном языке;
- id пометки ИИ и живой области — по ns (`bwtr-ai-note-<ns>`, `bwtr-status-<ns>`), без
  дублей в окне и при обоих блоках языков в одном документе;
- `data-i18n-of` каждого поля перевода указывает на поле той же формы (имя или id —
  клиент берёт `form.elements[of]`, а он находит и по id);
- без скриптов блок кнопки скрыт; одна живая область на событие (кнопка → `data-form-status`).
"""

import re
from collections import Counter

import pytest
from django.utils import translation

from apps.core.tests import test_fb33_m2i5c_translate as m2i5c
from apps.core.tests import test_s16_t1a_usp_i18n as t1a
from apps.core.tests import test_s16_t1b_seo_i18n as t1b
from apps.core.tests.test_fb33_m3_window_before import _panel

pytestmark = pytest.mark.django_db
BTN = re.compile(r"<button[^>]*data-i18n-translate[ >].*?</button>", re.S)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _usp_tenant(locales=("de", "ru", "en")):
    return t1a._browser(locales=locales).tenant


def _seo_tenant(locales=("de", "ru", "en")):
    return t1b._shop(seo=t1b.DE, locales=locales)


#: форма → (тенант, адрес окна, id формы, ns)
PARTS = {
    "usp": (_usp_tenant, "?seite=home&block=usp_bar&tab=texte", "bw-form-usp", "usp"),
    "seo": (_seo_tenant, "?seite=text&block=__page&tab=texte", "bw-form-seo", "seo"),
}


def _form(html, fid):
    m = re.search(rf'<form[^>]*id="{fid}".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def _window(part, **kw):
    make, query, fid, _ns = PARTS[part]
    with translation.override("de"):
        panel = _panel(m2i5c._ScreenBrowser(make(**kw)).get(query))
    return panel, _form(panel, fid)


def _btn(form):
    m = BTN.search(form)
    return m.group(0) if m else ""


def _name(html):
    html = re.sub(r'<span aria-hidden="true">.*?</span>', "", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


@pytest.mark.parametrize("part", sorted(PARTS))
def test_ai_button_with_translations_only(monkeypatch, part):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _window(part)
    assert form, part
    btn = _btn(form)
    assert btn and 'data-loc="ru"' in btn and 'type="button"' in btn, form[:400]
    assert form.count("data-i18n-translate ") == 1
    box = m2i5c.BOX.search(form).group(0)
    assert box.startswith("<div data-i18n-translate-box hidden>"), "без скриптов не видна"
    assert _name(btn) == "Übersetzen (Sprache: Русский)"
    # без ИИ и при одном языке — кнопки нет
    m2i5c._ai(monkeypatch, on=False)
    assert "data-i18n-translate" not in _window(part)[1]
    m2i5c._ai(monkeypatch)
    one = _window(part, locales=("de",))[1]
    assert one and "data-i18n-translate" not in one, "один язык"


@pytest.mark.parametrize("part", sorted(PARTS))
def test_note_and_status_ids_by_ns(monkeypatch, part):
    m2i5c._ai(monkeypatch)
    ns = PARTS[part][3]
    panel, form = _window(part)
    btn = _btn(form)
    assert f'data-note="bwtr-ai-note-{ns}"' in btn and f'id="bwtr-ai-note-{ns}"' in form
    assert f'data-status="bwtr-status-{ns}"' in btn
    target = re.search(rf'<p[^>]*\bid="bwtr-status-{ns}"[^>]*>', form).group(0)
    assert "data-form-status" in target and 'role="status"' in target
    own = re.search(r"<span[^>]*data-i18n-translate-status[^>]*>", form).group(0)
    assert "role=" not in own and "aria-live" not in own
    ids = Counter(re.findall(r'\bid="([^"]+)"', panel))
    assert [i for i, n in ids.items() if n > 1] == [], part


def test_ids_unique_with_usp_and_seo_lang_blocks(monkeypatch):
    m2i5c._ai(monkeypatch)
    doc = _window("usp")[1] + _window("seo")[1]
    assert doc.count("data-i18n-translate ") == 2
    ids = Counter(re.findall(r'\bid="([^"]+)"', doc))
    assert [i for i, n in ids.items() if n > 1] == [], ids
    for btn in BTN.findall(doc):
        for attr in ("data-status", "data-note"):
            ref = re.search(rf'{attr}="([^"]+)"', btn).group(1)
            assert ids[ref] == 1, (attr, ref)


@pytest.mark.parametrize("part", sorted(PARTS))
def test_translation_inputs_point_to_form_fields(monkeypatch, part):
    m2i5c._ai(monkeypatch)
    _panel_html, form = _window(part)
    controls = re.findall(r"<(?:input|textarea|select)\b[^>]*>", form)
    # ревью T3b LOW (T6): источник «Übersetzen» — имя поля формы (`f_…`) у всех видов, не id
    known = set()
    for el in controls:
        m = re.search(r'\bname="([^"]+)"', el)
        if m:
            known.add(m.group(1))
    fields = re.findall(r"<(?:input|textarea)[^>]*\blang=\"(?:ru|en)\"[^>]*>", form)
    assert fields
    for el in fields:
        of = re.search(r'data-i18n-of="([^"]+)"', el)
        assert of, el
        assert of.group(1) in known, (of.group(1), el)
    m2i5c._ai(monkeypatch, on=False)
    assert "data-i18n-of" not in _window(part)[1]


def test_seo_translation_caps_sent_with_maxlength(monkeypatch):
    """Потолки SEO 70/200 — `maxlength` поля перевода: клиент шлёт его `max` серверу."""
    m2i5c._ai(monkeypatch)
    _panel_html, form = _window("seo")
    title = re.search(r'<input[^>]*id="bw-seo-title-ru"[^>]*>', form).group(0)
    desc = re.search(r'<textarea[^>]*id="bw-seo-description-ru"[^>]*>', form).group(0)
    assert 'maxlength="70"' in title and 'maxlength="200"' in desc
    assert "data-i18n-of=" in title and "data-i18n-of=" in desc
