"""FB-33 M5d-3 (G3 стопки 12): часть окна «Inhalt» у закреплённых строк текстовых страниц —
«Text» («Über uns», «Versand», своя «Seite») и «Versandkosten».

План — `docs/fb33-stack12-plan-2026-11-23.md` §0 «M5dG3», §3, §4 «G3», правки §10 (Y8), ответы
владельца §11. Срез добавляет только записи реестра (`detail_sections.py`: `pagetext` у хостов
`info`, `page`, `versand` — источник `page`; `costs` у `versand` — источник `setting`); ядро
части — M5d-2 (`test_fb33_m5d2_core.py`).

Отступления от артборда (план §0, §9 №2–3): числа «(3 aktiv)» нет; галочка названа как на форме
страницы («Ihre Versandarten mit Preisen unter dem Text anzeigen»); вкладка экрана «Zahlarten &
Lieferung» названа как в коде («Lieferung & Abholung»).
"""

import html as html_lib
import logging
import re
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.urls import reverse
from django.utils import translation

from apps.core import content_pages, detail_sections, nav_registry, window_parts
from apps.core.models import ContentPage
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import _inventory
from apps.core.tests.test_fb33_m5d2_core import (
    FIXED,
    HINT,
    NO_RIGHT,
    _inhalt,
    _req,
    _row,
    _shop,
    _staff,
    _staff_part,
    _text,
    _warm_count,
)

pytestmark = [
    pytest.mark.django_db,
]

ROOT = Path(__file__).resolve().parents[3]

SHOWS_TEXT = "den Text der Seite „%(page)s“"
SHOWS_COSTS = "Ihre Versandarten mit Preisen"
#: подпись галочки — как на форме страницы «Versand» (`content_page_form.html`)
CHECKBOX = "Ihre Versandarten mit Preisen unter dem Text anzeigen"
NOTE_COSTS = (
    "Hierhin führt „zzgl. Versandkosten“ bei jedem Preis. Die Liste lässt sich nur auf der "
    "Seite „Versand“ abschalten (Häkchen „Ihre Versandarten mit Preisen unter dem Text "
    "anzeigen“) — und nur mit eigenem Text."
)
#: подпись вкладки экрана «Zahlarten & Lieferung» (`payment_settings.html`)
TAB = "Lieferung & Abholung"
MSGIDS = (SHOWS_TEXT, SHOWS_COSTS, NOTE_COSTS)
TEXT_HOSTS = ("info", "page", "versand")
#: немецкие подписи части, которых нет в окне на русском
GERMAN = ("Dieser Block zeigt", "Inhalt bearbeiten", "den Text der Seite", "Versandarten", "fest")


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _page(slug, title):
    return ContentPage.objects.create(slug=slug, title=title, body="<p>Text</p>", is_published=True)


def _section(module, key):
    return next(s for s in detail_sections.sections_for(module) if s.key == key)


def _msgid(value) -> str:
    with translation.override(None):  # без языка ленивая строка отдаёт msgid
        return str(value)


# --- №2: реестр — один источник; подписи сверены с кодом экранов -----------------------------------


def test_g3_sources_in_the_registry():
    """`pagetext` трёх хостов — источник `page` на «Seiten»; `costs` — `setting` на вкладку
    «Lieferung & Abholung» экрана «Zahlarten & Lieferung»; записи `nav_registry` есть."""
    for module in TEXT_HOSTS:
        s = _section(module, "pagetext")
        assert s.content_nav == "content-pages", module
        assert s.source is not None and s.source.kind == "page", module
        assert _msgid(s.source.shows) == SHOWS_TEXT, module
        assert not s.source.woher and not s.source.only_if and not s.source.object_only, module
    costs = _section("versand", "costs")
    assert costs.content_nav == "payment-settings"
    src = costs.source
    assert src is not None and src.kind == "setting"
    assert (src.query, _msgid(src.sub)) == ("?tab=lieferung", TAB)
    assert _msgid(src.shows) == SHOWS_COSTS and _msgid(src.note) == NOTE_COSTS
    assert "aktiv" not in _msgid(src.shows)  # §9 №2: без числа
    for url_name in ("content-pages", "payment-settings"):
        assert nav_registry.entry_by_url(url_name) is not None, url_name
    assert _msgid(nav_registry.entry_by_url("payment-settings").label) == "Zahlarten & Lieferung"
    assert _msgid(nav_registry.entry_by_url("content-pages").label) == "Seiten"


def test_labels_are_the_ones_on_the_screens():
    """Подпись вкладки и подпись галочки в тексте — те, что стоят на экранах кабинета."""
    tabs = (ROOT / "templates/tenant/payment_settings.html").read_text(encoding="utf-8")
    assert re.search(r'\?tab=lieferung"[^>]*>\{% trans "' + re.escape(TAB) + '" %}', tabs)
    form = (ROOT / "templates/tenant/content_page_form.html").read_text(encoding="utf-8")
    assert f'{{% trans "{CHECKBOX}" %}}' in form
    assert f"„{CHECKBOX}“" in NOTE_COSTS
    src = _section("versand", "costs").source
    assert src is not None and f"„{CHECKBOX}“" in _msgid(src.note)


def test_g3_no_row_without_window(monkeypatch):
    """Логикой `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): у всех строк текстовых
    страниц («Über uns», «Versand», своя «Seite») окно есть."""
    from apps.core import view_perms
    from apps.core.tests.test_fb33_m5d_inventory import view_fetch
    from apps.tenants import siteconfig

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant, _product = _shop()
    _page("lieferzeiten", "Lieferzeiten")
    mod = _inventory()
    saved = siteconfig.normalize(tenant.site_config)
    codes = {
        r.code
        for r in mod.schema_pages(tenant, saved)
        if mod.group_of(r.code, r.host or "") == "G3"
    }
    assert {"text", "text@versand", "text@seite:lieferzeiten"} <= codes, codes
    lines = mod.inventory(tenant, view_fetch(tenant), codes=codes)
    assert not [ln for ln in lines if ln.get("skipped")]
    rows = {(ln["host"], ln["key"]) for ln in lines if ln.get("key")}
    assert {("info", "pagetext"), ("versand", "pagetext"), ("versand", "costs")} <= rows, rows
    assert ("seite:lieferzeiten", "pagetext") in rows, rows
    bare = [(ln["host"], ln["ref"]) for ln in lines if ln.get("key") and not ln["window"]]
    assert not bare, bare


# --- тексты артборда --------------------------------------------------------------------------------


def test_text_window_of_the_versand_page():
    """Артборд M5dG3 «Block 1: Text 🔒 fest» дословно; `<dl>` нет (у закреплённого текста нет ни
    «Woher», ни «Auf der Seite»)."""
    tenant, _product = _shop()
    page = _page("versand", "Versand")
    part, panel, selected, _view = _inhalt(tenant, "?seite=text@versand&block=pagetext")
    text = _text(part)
    assert "Dieser Block zeigt: den Text der Seite „Versand“." in text
    assert text.count(FIXED) == 1 and part.count("data-inhalt-fixed") == 1
    assert HINT in part and "<dl" not in part
    a = re.search(r"<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert a and "data-inhalt-link" in a.group(1)
    assert _text(a.group(2)) == "Inhalt bearbeiten: Seiten › Versand"
    # правки ревью P0 (a11y M2): `lang` у имени — только когда язык окна другой
    assert "lang=" not in a.group(2)
    assert f'href="{reverse("content-page-edit", args=[page.pk])}"' in a.group(0)
    assert selected["content"]["link"]["only_here"] is False
    assert "data-inhalt-only-here" not in part and "data-inhalt-reason" not in part
    # ни «Platz», ни «Vorschau», ни переключателей
    assert "data-bw-preview" not in panel and 'value="toggle"' not in part


def test_costs_window_of_the_versand_page():
    """Артборд M5dG3 «Block 2: Versandkosten 🔒 fest»: без числа «(3 aktiv)», галочка — как на
    форме, ссылка — «Zahlarten & Lieferung › Lieferung & Abholung» на вкладку."""
    tenant, _product = _shop()
    part, _panel_html, selected, _view = _inhalt(tenant, "?seite=text@versand&block=costs")
    text = _text(part)
    assert f"Dieser Block zeigt: {SHOWS_COSTS}. {NOTE_COSTS}" in text
    assert "aktiv" not in text
    assert text.count(FIXED) == 1 and "<dl" not in part and HINT in part
    a = re.search(r"<a\b([^>]*)>(.*?)</a>", part, re.S)
    assert a and html_lib.unescape(_text(a.group(2))) == (
        f"Inhalt bearbeiten: Zahlarten & Lieferung › {TAB}"
    )
    assert f'href="{reverse("payment-settings")}?tab=lieferung"' in a.group(0)
    assert selected["content"]["link"]["only_here"] is False
    summary = re.search(r"<p\b[^>]*data-inhalt-summary[^>]*>(.*?)</p>", part, re.S)
    assert part.index(summary.group(0)) < part.index("data-inhalt-fixed") < part.index(a.group(0))


# --- №5: ссылка — по коду страницы -------------------------------------------------------------------


def test_page_link_by_code():
    """Ссылка «Text» ведёт в редактор СВОЕЙ страницы: «Über uns» и «Versand» без записи —
    системная форма; своя страница — по slug точно (`x` и `x-2` — соседи)."""
    tenant, _product = _shop()
    one, two = _page("x", "Erste"), _page("x-2", "Zweite")
    b = Browser(tenant)
    want = {
        "text": (reverse("content-page-system", args=["ueber-uns"]), "Über uns"),
        "text@versand": (reverse("content-page-system", args=["versand"]), "Versand"),
        "text@seite:x": (reverse("content-page-edit", args=[one.pk]), "Erste"),
        "text@seite:x-2": (reverse("content-page-edit", args=[two.pk]), "Zweite"),
    }
    for code, (url, name) in want.items():
        _html, _view, selected = _capture(b, f"?seite={code}&block=pagetext")
        ct = selected["content"]
        assert ct["link"]["url"] == url, code
        assert ct["summary"] == f"den Text der Seite „{name}“", code
        assert str(ct["link"]["label"]) == f"Seiten › {name}", code  # de-окно: без `lang`
    about = _page("ueber-uns", "Über uns")
    _html, _view, selected = _capture(b, "?seite=text&block=pagetext")
    assert selected["content"]["link"]["url"] == reverse("content-page-edit", args=[about.pk])


# --- №6: страницы нет ---------------------------------------------------------------------------------


def test_missing_page_no_link(caplog):
    """Своей страницы с таким slug нет (и это не системная) — часть без ссылки и без причины,
    ошибка в журнале."""
    tenant, _product = _shop()
    assert content_pages.edit_url_for_code("text@seite:weg") == ""
    row = _row(ref="pagetext", key="pagetext", pinned=True, can_hide=False)
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        window_parts.content_part(
            row, "seite:weg", _req(tenant), code="text@seite:weg", page_label="Weg"
        )
    ct = row["content"]
    assert ct["link"] is None and ct["reason"] == ""
    assert ct["summary"] == "den Text der Seite „Weg“" and ct["fixed"] is True
    assert any(r.levelno >= logging.ERROR and "weg" in r.getMessage() for r in caplog.records)


# --- №13, №16: ru и каталоги ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["?seite=text@versand&block=pagetext", "?seite=text@versand&block=costs"])  # fmt: skip
def test_window_in_russian(query):
    tenant, _product = _shop()
    _page("versand", "Versand")
    with translation.override("ru"):
        part, _panel_html, _selected, _view = _inhalt(tenant, query)
    text = _text(re.sub(r'<span lang="de">.*?</span>', "", part))
    assert not [g for g in GERMAN if g in text], text
    assert "data-inhalt-link" in part
    if query.endswith("pagetext"):  # имя системной страницы на ru переведено — без `lang` (a11y M2)
        assert "«Доставка»" in part and 'lang="de"' not in part


def test_new_msgids_in_all_po():
    """Строки G3 есть во всех пяти каталогах (без дублей пары msgctxt/msgid), переведены,
    плейсхолдеры совпадают."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {(e.msgctxt, e.msgid): e.msgstr for e in entries}
        for msgid in (*MSGIDS, TAB):
            assert (None, msgid) in have, (lang, msgid)
            if lang != "de":
                assert have[(None, msgid)] and have[(None, msgid)] != msgid, (lang, msgid)
            got = have[(None, msgid)] or msgid
            names = sorted(re.findall(r"%\((\w+)\)s", msgid))
            assert sorted(re.findall(r"%\((\w+)\)s", got)) == names, (lang, msgid)


# --- №19 / Y8: без скриптов — колонка ------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["pagetext", "costs"])
def test_nojs_column(ref):
    """Без скриптов окно — колонка панели: раздел виден, полосы вкладок и пустого `tablist`
    нет, «Fertig» и «Abbrechen» — обычные кнопки формы."""
    tenant, _product = _shop()
    html, _view, _selected = _capture(Browser(tenant), f"?seite=text@versand&block={ref}")
    panel = _panel(html)
    assert 'data-window-part="inhalt"' in panel
    sec = re.search(r'<section id="schema-tab-was"[^>]*>', panel)
    assert sec and " hidden" not in sec.group(0)
    assert "data-window-tabs" not in panel and "tablist" not in panel
    assert 'value="window_done"' in panel and 'value="revert"' in panel


# --- №28: право ссылки --------------------------------------------------------------------------------


def test_text_link_needs_the_right_to_edit_pages():
    """Ссылка «Text» — по праву цели (`seiten.edit`), не по пункту «Seiten»: без него —
    причина одним абзацем, без ссылки."""
    tenant, _product = _shop()
    part = _staff_part(tenant, _staff(["seiten.edit"]), "?seite=text@versand&block=pagetext")
    assert "data-inhalt-link" not in part and "<a " not in part
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert _text(para.group(1)) == f"Inhalt bearbeiten: Seiten › Versand — {NO_RIGHT}"
    editor = _staff([], add=["seiten.edit"])
    part = _staff_part(tenant, editor, "?seite=text@versand&block=pagetext")
    assert "data-inhalt-link" in part and NO_RIGHT not in part


def test_costs_link_needs_the_right_to_open_settings():
    """Ссылка «Versandkosten» — по праву открыть «Zahlarten & Lieferung»."""
    tenant, _product = _shop()
    blind = _staff(["einstellungen.view", "einstellungen.edit"])
    part = _staff_part(tenant, blind, "?seite=text@versand&block=costs")
    assert "data-inhalt-link" not in part and "<a " not in part
    para = re.search(r"<p\b[^>]*data-inhalt-reason[^>]*>(.*?)</p>", part, re.S)
    assert html_lib.unescape(_text(para.group(1))) == (
        f"Inhalt bearbeiten: Zahlarten & Lieferung › {TAB} — {NO_RIGHT}"
    )
    reader = _staff(["einstellungen.edit"], add=["einstellungen.view"])
    part = _staff_part(tenant, reader, "?seite=text@versand&block=costs")
    assert "data-inhalt-link" in part and NO_RIGHT not in part


# --- №31: запросы --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, extra",
    [
        ("?seite=text&block=pagetext", 1),
        ("?seite=text@versand&block=pagetext", 1),
        ("?seite=text@seite:lieferzeiten&block=pagetext", 1),
        ("?seite=text@versand&block=costs", 0),
    ],
)
def test_inhalt_queries(monkeypatch, query, extra):
    """Часть «Inhalt» текста стоит не больше одного запроса поверх экрана без неё (адрес
    редактора страницы — `edit_url_for_code`); «Versandkosten» — ни одного."""
    tenant, _product = _shop()
    _page("lieferzeiten", "Lieferzeiten")
    b = Browser(tenant)
    assert 'data-window-part="inhalt"' in b.get(query)
    with_part = _warm_count(b, query)
    monkeypatch.setattr(window_parts, "content_part", lambda *args, **kwargs: None)
    assert with_part - _warm_count(b, query) <= extra
