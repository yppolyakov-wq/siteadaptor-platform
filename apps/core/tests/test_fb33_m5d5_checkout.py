"""FB-33 M5d-5 (G4 стопки 12): часть окна «Inhalt» у строк корзины и подтверждения —
«Positionen» корзины, «Bestätigung» и «Empfehlungen» страницы подтверждения.

План — `docs/fb33-stack12-plan-2026-11-23.md` §0 «M5dG4», §3, §4 «G4», правки §10 (Y8), ответы
владельца §11. Срез добавляет только записи реестра (`detail_sections.py`: `items` у `cart`,
`summary` и `recommend` у `confirmation`); ядро части — M5d-2 (`test_fb33_m5d2_core.py`).
Корзинные «Summe und Bestellbutton», «Bestellformular» и «Passt gut dazu» не трогаются.

Отступления от артборда: ссылка «Empfehlungen» — «Sortiment» (записи «Produkte» в навигации
нет, ответ владельца §11); у скрытой строки — текст ядра «Schließen Sie das Fenster; dann
„Einblenden“ unter „Ausgeblendet“.» (§11); начало фразы «Bestätigung» в плане опущено («…») —
«die Bestätigung nach dem Kauf — Nummer, Positionen, Summe, Zahlung».
"""

import re
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.core import confirmation_page, detail_sections, nav_registry, window_parts
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import CFG, _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import MODULE_OFF, _inventory, _view_ctx
from apps.core.tests.test_fb33_m5d2_core import (
    ACT_HIDE,
    ACT_SHOW,
    FIXED,
    HIDDEN,
    HINT,
    NO_RIGHT,
    ON_PAGE,
    VISIBLE,
    WOHER,
    _inhalt,
    _shop,
    _staff,
    _staff_part,
    _text,
    _warm_count,
)

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]

SHOWS_ITEMS = "die Artikel, die der Kunde in den Warenkorb gelegt hat — mit Menge und Preis"
WOHER_ITEMS = "automatisch — aus dem Warenkorb des Kunden. Nichts zu pflegen."
SHOWS_SUMMARY = "die Bestätigung nach dem Kauf — Nummer, Positionen, Summe, Zahlung"
NOTE_SUMMARY = "Gilt für Bestellung, Termin, Zimmer, Ticket und Tisch."
WOHER_SUMMARY = "automatisch — aus der Bestellung oder Buchung."
SHOWS_RECOMMEND = (
    "bis zu 4 Produkte unter der Bestätigung — empfohlene zuerst, ohne die gerade gekauften"
)
WOHER_RECOMMEND = "Produkte mit Häkchen „Empfohlen“."
ONLY_IF_RECOMMEND = "Erscheint nur, wenn es Produkte gibt."
MSGIDS = (
    SHOWS_ITEMS,
    WOHER_ITEMS,
    SHOWS_SUMMARY,
    NOTE_SUMMARY,
    WOHER_SUMMARY,
    SHOWS_RECOMMEND,
    WOHER_RECOMMEND,
    ONLY_IF_RECOMMEND,
)
ROWS = (("cart", "items"), ("confirmation", "summary"), ("confirmation", "recommend"))
#: немецкие подписи части, которых нет в окне на русском
GERMAN = ("Dieser Block zeigt", "Woher", "Auf der Seite", "automatisch", "Produkte", "Gilt für")


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _section(module, key):
    return next(s for s in detail_sections.sections_for(module) if s.key == key)


def _msgid(value) -> str:
    with translation.override(None):  # без языка ленивая строка отдаёт msgid
        return str(value)


def _dd(part: str, name: str) -> str:
    m = re.search(rf"<dd\b[^>]*data-inhalt-{name}[^>]*>(.*?)</dd>", part, re.S)
    assert m, name
    return _text(m.group(1))


# --- №2: реестр ----------------------------------------------------------------------------------------


def test_g4_sources_in_the_registry():
    """`items` корзины и `summary` подтверждения — `auto` (ссылки нет); `recommend` — `setting`
    на «Sortiment» с условием появления (раздел с presence-гейтом, A7б)."""
    items = _section("cart", "items").source
    assert items is not None and items.kind == "auto"
    assert (_msgid(items.shows), _msgid(items.woher)) == (SHOWS_ITEMS, WOHER_ITEMS)
    assert not _section("cart", "items").content_nav
    summary = _section("confirmation", "summary").source
    assert summary is not None and summary.kind == "auto"
    assert _msgid(summary.shows) == SHOWS_SUMMARY and _msgid(summary.note) == NOTE_SUMMARY
    assert _msgid(summary.woher) == WOHER_SUMMARY
    assert not _section("confirmation", "summary").content_nav
    recommend = _section("confirmation", "recommend")
    src = recommend.source
    assert recommend.content_nav == "sellable-manage"
    assert src is not None and src.kind == "setting" and not src.query and not src.sub
    assert _msgid(src.shows) == SHOWS_RECOMMEND and _msgid(src.woher) == WOHER_RECOMMEND
    assert _msgid(src.only_if) == ONLY_IF_RECOMMEND
    assert _msgid(nav_registry.entry_by_url("sellable-manage").label) == "Sortiment"
    for _module, key in ROWS:
        assert not _section(_module, key).source.object_only


def test_texts_match_the_code():
    """Число товаров и галочка в тексте «Empfehlungen» — те, что в коде: `RECOMMEND_MAX` и
    подпись поля `is_featured` формы товара («Empfohlen»)."""
    from apps.catalog.forms import ProductForm

    assert _section("confirmation", "recommend").source is not None
    assert f"bis zu {confirmation_page.RECOMMEND_MAX} Produkte" in SHOWS_RECOMMEND
    with translation.override("de"):
        label = str(ProductForm.base_fields["is_featured"].label)
    assert f"„{label}“" in WOHER_RECOMMEND


def test_cart_summary_form_untouched():
    """Корзинные «Summe und Bestellbutton», «Bestellformular» и «Passt gut dazu» — как были:
    источника и части «Inhalt» нет, окна прежние (§ 312j и «Felder»); у «Positionen» часть
    теперь есть (правка `test_cart_pinned_rows_unchanged`, план §4 «G4»)."""
    for key in ("summary", "form", "upsell"):
        s = _section("cart", key)
        assert s.source is None and not s.content_nav, key
    assert _section("cart", "items").source is not None
    tenant, _product = _shop()
    tenant.site_config = CFG
    tenant.save()
    b = Browser(tenant)
    for ref in ("summary", "form", "upsell"):
        ctx = _view_ctx(b, f"?seite=cart&block={ref}")
        selected = ctx.get("selected") or {}
        assert "content" not in selected, ref
        assert "inhalt" not in [p for t in ctx["window"] for p in t["parts"]], ref
    ctx = _view_ctx(b, "?seite=cart&block=summary")
    assert [(t["key"], t["parts"]) for t in ctx["window"]] == [
        ("texte", ["pinned"]),
        ("felder", ["noinput"]),
    ]
    assert ctx["bw_preview"] is not None
    ctx = _view_ctx(b, "?seite=cart&block=items")
    assert [t["parts"] for t in ctx["window"]] == [["inhalt"]]
    assert ctx["bw_preview"] is None


def test_g4_no_row_without_window(monkeypatch):
    """Логикой `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): у всех строк корзины и
    подтверждения окно есть."""
    from apps.core import view_perms
    from apps.core.tests.test_fb33_m5d_inventory import view_fetch
    from apps.tenants import siteconfig

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant, _product = _shop()
    mod = _inventory()
    saved = siteconfig.normalize(tenant.site_config)
    codes = {
        r.code
        for r in mod.schema_pages(tenant, saved)
        if mod.group_of(r.code, r.host or "") == "G4"
    }
    assert {"cart", "confirmation"} <= codes, codes
    lines = mod.inventory(tenant, view_fetch(tenant), codes=codes)
    assert not [ln for ln in lines if ln.get("skipped")]
    rows = {(ln["host"], ln["key"]) for ln in lines if ln.get("key")}
    assert set(ROWS) <= rows, rows
    bare = [(ln["host"], ln["ref"]) for ln in lines if ln.get("key") and not ln["window"]]
    assert not bare, bare


# --- тексты артборда -------------------------------------------------------------------------------------


def test_items_window_of_the_cart():
    """Артборд M5dG4 «Block 1: Positionen 🔒 fest» дословно; ссылки нет (авто)."""
    tenant, _product = _shop()
    part, panel, selected, _view = _inhalt(tenant, "?seite=cart&block=items")
    text = _text(part)
    assert f"Dieser Block zeigt: {SHOWS_ITEMS}." in text
    assert text.count(FIXED) == 1 and part.count("data-inhalt-fixed") == 1
    assert _dd(part, "woher") == WOHER_ITEMS
    assert part.count("<dl") == 1 and "data-inhalt-visibility" not in part and ON_PAGE not in part
    assert selected["content"]["link"] is None and selected["content"]["reason"] == ""
    assert "<a " not in part and "data-inhalt-reason" not in part
    assert HINT in part and "data-bw-preview" not in panel


def test_summary_window_of_the_confirmation():
    """Артборд M5dG4 «Block 1: Bestätigung 🔒 fest»: что показывает, для каких сделок, откуда;
    ссылки нет (авто)."""
    tenant, _product = _shop()
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=confirmation&block=summary")
    text = _text(part)
    assert f"Dieser Block zeigt: {SHOWS_SUMMARY}. {NOTE_SUMMARY}" in text
    assert text.count(FIXED) == 1
    assert _dd(part, "woher") == WOHER_SUMMARY
    assert "data-inhalt-visibility" not in part
    assert selected["content"]["link"] is None and "<a " not in part
    assert HINT in part


def test_recommend_hidden_window_from_ausgeblendet():
    """Артборд M5dG4 «Block 3: Empfehlungen»: строка скрыта по умолчанию (K3) и открывается из
    «Ausgeblendet»; в окне — что показывает, откуда, «ausgeblendet» и как включить (текст ядра,
    кнопки в окне нет); ссылка — «Sortiment»."""
    tenant, _product = _shop()
    b = Browser(tenant)
    page = b.get("?seite=confirmation")
    hidden = re.search(r"<details\b[^>]*data-schema-hidden.*?</details>", page, re.S)
    assert hidden and 'data-schema-block="recommend"' in hidden.group(0)
    assert re.search(r'href="\?seite=confirmation&amp;block=recommend[^"]*"', hidden.group(0))
    part, panel, selected, _view = _inhalt(tenant, "?seite=confirmation&block=recommend")
    assert selected["enabled"] is False and not selected["pinned"]
    text = _text(part)
    assert f"Dieser Block zeigt: {SHOWS_RECOMMEND}." in text
    assert FIXED not in part and "data-inhalt-fixed" not in part
    dts = [_text(d) for d in re.findall(r"<dt\b[^>]*>(.*?)</dt>", part, re.S)]
    assert dts == [WOHER, ON_PAGE]
    assert _dd(part, "woher") == f"{WOHER_RECOMMEND} {ONLY_IF_RECOMMEND}"
    assert _dd(part, "visibility") == f"{HIDDEN} {ACT_SHOW}"
    assert 'value="toggle"' not in part
    a = re.search(r"<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert a and "data-inhalt-link" in a.group(1)
    assert _text(a.group(2)) == "Inhalt bearbeiten: Sortiment"
    assert f'href="{reverse("sellable-manage")}"' in a.group(0)
    assert "data-inhalt-only-here" not in part and "data-bw-preview" not in panel


def test_recommend_shown_window():
    """Строку включили («Einblenden») — «sichtbar.» и «Ausblenden über „⋯“.» (не двигается)."""
    tenant, _product = _shop()
    b = Browser(tenant)
    b.post(seite="confirmation", ref="recommend", op="toggle", zeile="1")
    html, _view, selected = _capture(b, "?seite=confirmation&block=recommend")
    assert selected["enabled"] is True
    assert selected["content"]["visibility"] == VISIBLE
    assert selected["content"]["actions"] == ACT_HIDE
    assert 'data-window-part="inhalt"' in _panel(html)


def test_recommend_link_module_off(monkeypatch):
    """Экран «Sortiment» этому бизнесу закрыт — ссылки нет, причина одним абзацем с
    контекстом: запись меню не видна — «Modul ist nicht aktiv»; экрана нет в пакете — «Nicht in
    Ihrem Paket enthalten»."""
    from apps.core import packages

    tenant, _product = _shop()
    query = "?seite=confirmation&block=recommend"
    visible = nav_registry.entry_visible

    def without_assortment(entry, *args, **kwargs):
        return entry.url_name != "sellable-manage" and visible(entry, *args, **kwargs)

    monkeypatch.setattr(nav_registry, "entry_visible", without_assortment)
    part, _panel_html, selected, _view = _inhalt(tenant, query)
    assert selected["content"]["link"] is None
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == f"Inhalt bearbeiten: Sortiment — {MODULE_OFF}"
    assert "<a" not in para.group(1) and "data-inhalt-link" not in part
    monkeypatch.undo()
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "sellable-manage")
    part, _panel_html, selected, _view = _inhalt(tenant, query)
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == "Inhalt bearbeiten: Sortiment — Nicht in Ihrem Paket enthalten"


def test_recommend_link_needs_the_right_to_open_the_assortment():
    """Право ссылки — открыть «Sortiment» (как у G2, ответ владельца §11)."""
    tenant, _product = _shop()
    blind = _staff(["sortiment.view", "sortiment.edit", "sortiment.delete"])
    part = _staff_part(tenant, blind, "?seite=confirmation&block=recommend")
    assert "data-inhalt-link" not in part and "<a " not in part
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == f"Inhalt bearbeiten: Sortiment — {NO_RIGHT}"
    reader = _staff(["sortiment.edit", "sortiment.delete"])
    part = _staff_part(tenant, reader, "?seite=confirmation&block=recommend")
    assert "data-inhalt-link" in part and NO_RIGHT not in part


# --- №13, №16: ru и каталоги -----------------------------------------------------------------------------


@pytest.mark.parametrize("code, ref", ROWS)
def test_window_in_russian(code, ref):
    tenant, _product = _shop()
    with translation.override("ru"):
        part, _panel_html, _selected, _view = _inhalt(tenant, f"?seite={code}&block={ref}")
    text = _text(part)
    assert not [g for g in GERMAN if g in text], text


def test_new_msgids_in_all_po():
    """Строки G4 есть во всех пяти каталогах (без дублей пары msgctxt/msgid), переведены."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {(e.msgctxt, e.msgid): e.msgstr for e in entries}
        for msgid in MSGIDS:
            assert (None, msgid) in have, (lang, msgid)
            if lang != "de":
                assert have[(None, msgid)] and have[(None, msgid)] != msgid, (lang, msgid)


# --- Y8: без скриптов — колонка ---------------------------------------------------------------------------


@pytest.mark.parametrize("code, ref", ROWS)
def test_nojs_column(code, ref):
    """Без скриптов окно — колонка панели: раздел виден, полосы вкладок и пустого `tablist`
    нет, «Fertig» и «Abbrechen» — обычные кнопки формы."""
    tenant, _product = _shop()
    html, _view, _selected = _capture(Browser(tenant), f"?seite={code}&block={ref}")
    panel = _panel(html)
    assert 'data-window-part="inhalt"' in panel
    sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
    assert sec and " hidden" not in sec.group(0)
    assert "data-window-tabs" not in panel and "tablist" not in panel
    assert 'value="window_done"' in panel and 'value="revert"' in panel


# --- №31: запросы -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("code, ref", ROWS)
def test_inhalt_queries(monkeypatch, code, ref):
    """Часть «Inhalt» строк корзины и подтверждения запросов не добавляет."""
    tenant, _product = _shop()
    b = Browser(tenant)
    query = f"?seite={code}&block={ref}"
    assert 'data-window-part="inhalt"' in b.get(query)
    with_part = _warm_count(b, query)
    monkeypatch.setattr(window_parts, "content_part", lambda *args, **kwargs: None)
    assert with_part - _warm_count(b, query) <= 0
