"""FB-33 M5d-4e (G1e стопки 12): часть окна «Inhalt» у разделов детальных акции, Kombi и записи
блога.

План — `docs/fb33-stack12-plan-2026-11-23.md` §3 (карта источников), §4 «G1a…e» и «G1e», правки
ревью §10 (A7б, A8, A13, Y8), ответы владельца §11. Срез правит ТОЛЬКО метаданные окна в реестре
(`detail_sections.DETAIL_SECTIONS`: `content_nav` и `source` у модулей `promo`, `combo`,
`blog_post`): ключи, подписи, порядок и флаги разделов — прежние, витрина не меняется.

У Kombi и записи блога своей схемы объекта нет — часть есть только у типа страницы; строка одной
акции части не получает (как до среза). «Angebot» акции, отзывы и «Sie planen…» у Kombi — со
своим окном, срез их не трогает.
"""

import dataclasses
import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import detail_parts, detail_sections, nav_registry, object_structure, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.core.tests.test_fb33_m5d1_inhalt import _part
from apps.core.tests.test_fb33_m5d_inventory import _script
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
BASE_REGISTRY = Path(__file__).parent / "golden_fb33m5d2" / "registry.json"
ANCHOR = "fb33-stack-anchor-m5d4e"

ACT_HIDE = "Ausblenden über „⋯“."
ACT_SHOW = "Schließen Sie das Fenster; dann „Einblenden“ unter „Ausgeblendet“."
FIXED = "Er gehört fest zur Seite und lässt sich nicht ausblenden oder verschieben."
NOTHING_TO_DO = "Nichts zu pflegen."

#: (модуль, раздел) → (вид источника, экран ссылки, есть ли presence-гейт на витрине).
#: Карта плана §3, сверена с шаблонами и вьюхами витрины.
MAP = {
    # FB-33 стопка 15 M5e-2a (ревью 1, осознанно): «Angebot» — экран акций, «Aktion bearbeiten»
    ("promo", "offer"): ("setting", "promotions:promotion-list", False),
    ("promo", "share"): ("auto", "", False),
    ("promo", "card"): ("setting", "settings", True),
    ("promo", "related"): ("auto", "", True),
    ("combo", "config"): ("setting", "catalog:combo-list", False),
    # писатель `site_config["gallery"]` — Студия; FB-33 стопка 14 E6 (осознанно, решение
    # владельца 2026-11-24): запись «Galerie» `site-home?page=%2F&block=gallery`
    ("combo", "examples"): ("setting", "site-home", True),
    ("combo", "related"): ("auto", "", True),
    ("blog_post", "article"): ("setting", "blog-list", False),
    ("blog_post", "more"): ("auto", "", True),
}
#: код страницы типа → модуль реестра
PAGES = {"promo": "promo", "combo": "combo", "blog_post": "blog_post"}
#: FB-33 стопка 15 M5e-2a: фраза «Woher» у «Angebot» ждёт строки в `.po` (координатор)
NO_WOHER_YET = {("promo", "offer")}
#: окно у этих строк уже есть — срез их не трогает
UNTOUCHED = {("combo", "reviews"), ("combo", "cta")}
LINK_LABELS = {
    "settings": "Mein Geschäft",
    "promotions:promotion-list": "Aktionen",
    "catalog:combo-list": "Kombi",
    "blog-list": "Blog",
    "site-home": "Galerie",
}
#: FB-33 стопка 14 E6: у этих экранов запись реестра одна и с query (вход, а не сам экран)
QUERY_ONLY = {"site-home": "?page=%2F&block=gallery"}
#: FB-33 стопка 14 E6: прежний «Woher» у «Beispiele» снят из кода и из пяти `.po` (координатор)
RETIRED_MSGIDS = {"automatisch — die ersten Fotos der Galerie Ihrer Website."}


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(**site_config):
    tenant = TenantFactory(business_type="friseur", disabled_modules=[], site_config=site_config)
    connection.tenant = tenant
    return tenant


def _section(module, key):
    return next(s for s in detail_sections.sections_for(module) if s.key == key)


def _sources() -> dict:
    return {
        (module, s.key): s.source
        for module in PAGES.values()
        for s in detail_sections.sections_for(module)
        if s.source
    }


def _open(tenant, query):
    html, _view, selected = _capture(Browser(tenant), query)
    return html, selected


def _inhalt(tenant, query):
    html, selected = _open(tenant, query)
    assert selected and "content" in selected, query
    return _part(_panel(html), "inhalt"), selected["content"]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _msgids() -> list[str]:
    with translation.override(None):
        out = []
        for source in _sources().values():
            for text in (source.shows, source.woher, source.note, source.only_if):
                if text and str(text) not in out:
                    out.append(str(text))
    return out


# --- реестр: флаги прежние, источники — по карте -------------------------------------------------


def test_registry_flags_as_on_the_base():
    """Ключи, порядок, подписи и флаги разделов трёх модулей — как на базе P0: витрина читает
    только их. Зелёный и до записей, и после."""
    modules = set(PAGES.values())
    base = [row[:7] for row in json.loads(BASE_REGISTRY.read_text()) if row[0] in modules]
    with translation.override(None):
        got = [
            [module, s.key, str(s.label), s.hideable, s.orderable, s.in_place, s.only]
            for module in detail_sections.DETAIL_SECTIONS
            if module in modules
            for s in detail_sections.sections_for(module)
        ]
    assert got == base and len(got) == 11


def test_sources_follow_the_map():
    sources = _sources()
    assert set(sources) == set(MAP)
    for (module, key), (kind, nav, _gate) in MAP.items():
        section = _section(module, key)
        assert (section.source.kind, section.content_nav) == (kind, nav), (module, key)
        assert not section.source.object_only and not section.source.fields, (module, key)
    for module, key in UNTOUCHED:
        section = _section(module, key)
        assert section.source is None and not section.content_nav, (module, key)


def test_source_texts_are_well_formed():
    """Тексты — ленивые; «zeigt» без точки в конце; «Woher» — фразой с точкой; A7б: у раздела
    с presence-гейтом на витрине есть `only_if`, у раздела без гейта его нет."""
    sources = _sources()
    assert sources
    for (module, key), source in sources.items():
        where = (module, key)
        for text in (source.shows, source.woher, source.note, source.only_if):
            assert not text or type(text).__name__ == "__proxy__", where
        shows = str(source.shows)
        assert shows and not shows.endswith(".") and "%(" not in shows, where
        if where not in NO_WOHER_YET:
            assert str(source.woher).endswith("."), where
        assert bool(source.only_if) == MAP[where][2], where
        assert not source.only_if or str(source.only_if).endswith("."), where
        if source.kind == "auto":
            assert str(source.woher).startswith("automatisch"), where
    # «Beispiele» берут фото галереи сайта — их пополняет владелец, «Nichts zu pflegen» неверно
    assert NOTHING_TO_DO not in str(sources[("combo", "examples")].woher)


# --- №2: строк без окна нет -----------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(PAGES))
def test_no_g1_row_without_window(code):
    """Логикой `scripts/fb33_m5d_inventory.py` (ответ — разметка вьюхи): у каждой строки
    раздела страницы окно есть; у разделов среза в нём часть «Inhalt». Y8: без JS — та же
    часть колонкой в панели (ответ сервера и есть она)."""
    tenant = _tenant()
    module = PAGES[code]
    window_tabs = _script().window_tabs
    seen = []
    for section in detail_sections.sections_for(module):
        key = section.key
        html, selected = _open(tenant, f"?seite={code}&block={key}")
        assert selected and selected["ref"] == key, (code, key)
        assert window_tabs(html) is not None and 'value="window_done"' in html, (code, key)
        if (module, key) in UNTOUCHED:
            assert "content" not in selected, (code, key)
            continue
        assert 'data-window-part="inhalt"' in _panel(html), (code, key)
        seen.append(key)
    assert seen == [k for (m, k) in MAP if m == module]


# --- свои замки G1e: только тип ---------------------------------------------------------------------


def test_blog_type_only():
    """Запись блога — только тип страницы: своей схемы объекта нет, слов «dieses …» нет;
    «Text» закреплён (фраза «fest», без «Auf der Seite»), ссылка — список «Blog»."""
    assert "post" not in site_schema.OBJECT_KINDS
    assert "this" not in site_schema.OBJECT_WORDS["post"]
    assert not site_schema.is_object_code(f"post@post:{uuid.uuid4().hex}")
    assert not detail_parts.object_kind("blog_post")
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=blog_post&block=article")
    assert ct["fixed"] is True and FIXED in _text(part)
    assert ct["visibility"] == "" and ct["actions"] == "" and ct["filled"] == ""
    assert ct["link"] == {"label": "Blog", "url": reverse("blog-list"), "only_here": False}
    assert "Auf der Seite:" not in part and "data-inhalt-only-here" not in part
    assert "Inhalt bearbeiten: Blog" in _text(part) and part.count("<a ") == 1
    part, ct = _inhalt(tenant, "?seite=blog_post&block=more")
    assert ct["link"] is None and "<a " not in part
    assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE  # A13: не двигается
    assert ct["woher"].startswith("automatisch") and "Erscheint nur" in ct["woher"]


def test_combo_type_only():
    """Kombi — только тип страницы: конфигуратор закреплён, ссылка — список «Kombi»;
    «Weitere Menüs» — авто, без ссылки; «Beispiele» (FB-33 стопка 14 E6) — ссылка «Galerie» в
    Студию на главной; оба только скрываются."""
    assert "combo" not in site_schema.OBJECT_KINDS
    assert "this" not in site_schema.OBJECT_WORDS["combo"]
    assert not site_schema.is_object_code(f"combo@combo:{uuid.uuid4().hex}")
    assert not detail_parts.object_kind("combo_detail")
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=combo&block=config")
    assert ct["fixed"] is True and FIXED in _text(part) and ct["visibility"] == ""
    assert ct["link"] == {
        "label": "Kombi",
        "url": reverse("catalog:combo-list"),
        "only_here": False,
    }
    assert "Inhalt bearbeiten: Kombi" in _text(part)
    part, ct = _inhalt(tenant, "?seite=combo&block=related")
    assert ct["link"] is None and not ct["reason"] and "<a " not in part
    assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE
    assert ct["woher"].startswith("automatisch") and "Erscheint nur" in ct["woher"]
    # FB-33 стопка 14 E6 (осознанно): «Beispiele» — ссылка «Galerie» в Студию на главной
    part, ct = _inhalt(tenant, "?seite=combo&block=examples")
    assert ct["link"] == {
        "label": nav_registry.entry_by_url("site-home").label,
        "url": reverse("site-home") + QUERY_ONLY["site-home"],
        "only_here": False,
    }
    assert not ct["reason"] and "Inhalt bearbeiten: Galerie" in _text(part)
    assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE
    assert not ct["woher"].startswith("automatisch") and "Erscheint nur" in ct["woher"]


def test_promo_rows():
    """Акция: «Teilen» и «Weitere Aktionen» — авто; визитка — экран «Mein Geschäft»; «на
    месте» и лента — только скрываются (A13)."""
    tenant = _tenant()
    part, ct = _inhalt(tenant, "?seite=promo&block=card")
    assert ct["link"] == {"label": "Mein Geschäft", "url": reverse("settings"), "only_here": False}
    assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE
    assert ct["note"] and ct["note"] in _text(part)  # при «только показать» визитка остаётся
    assert "Inhalt bearbeiten: Mein Geschäft" in _text(part)
    for key in ("share", "related"):
        part, ct = _inhalt(tenant, f"?seite=promo&block={key}")
        assert ct["link"] is None and "<a " not in part, key
        assert ct["visibility"] == "sichtbar." and ct["actions"] == ACT_HIDE, key
    assert "Erscheint" not in _inhalt(tenant, "?seite=promo&block=share")[1]["woher"]


def test_promo_object_row_gets_no_part():
    """Строка одной акции части «Inhalt» не получает — как до среза (у неё только свои
    блоки); экран отвечает."""
    from apps.promotions.tests.factories import PromotionFactory

    assert _sources()  # до записей реестра замок ничего не доказывает
    tenant = _tenant()
    promo = PromotionFactory()
    code = object_structure.schema_code("promo", promo)
    for key in ("share", "card", "related"):
        html, selected = _open(tenant, f"?seite={code}&block={key}")
        assert "data-schema-block" in html, key
        assert not selected or "content" not in selected, key
        assert 'data-window-part="inhalt"' not in html, key


@pytest.mark.parametrize(
    "code, key, flag",
    [
        ("blog_post", "more", "blog_show_more"),
        ("promo", "related", "promo_show_related"),
        ("combo", "examples", "combo_show_examples"),
    ],
)
def test_hidden_row_window_says_how_to_show(code, key, flag):
    """Скрытая строка: окно открывается из «Ausgeblendet», видимость — «ausgeblendet.» и текст
    «как вернуть» (кнопки в окне нет — ответ владельца §11)."""
    tenant = _tenant(**{flag: False})
    part, ct = _inhalt(tenant, f"?seite={code}&block={key}")
    assert ct["visibility"] == "ausgeblendet." and ct["actions"] == ACT_SHOW
    assert "<button" not in part and "<input" not in part


# --- экраны ссылок: записи реестра ---------------------------------------------------------------


def test_content_nav_entries_are_unambiguous():
    """Каждый `content_nav` среза — имя URL однозначной записи `nav_registry`, экран открыт
    владельцу; подпись ссылки — подпись записи. FB-33 стопка 14 E6: у галереи сайта запись одна
    и с query («Galerie», `QUERY_ONLY`)."""
    tenant = _tenant()
    req = SimpleNamespace(tenant=tenant, user=SimpleNamespace(is_authenticated=True))
    navs = {
        s.content_nav
        for module in PAGES.values()
        for s in detail_sections.sections_for(module)
        if s.content_nav
    }
    assert navs == set(LINK_LABELS)
    for url_name, label in LINK_LABELS.items():
        entries = [e for e in nav_registry.ENTRIES if e.url_name == url_name]
        if url_name in QUERY_ONLY:
            assert [e.query for e in entries] == [QUERY_ONLY[url_name]], url_name
        else:
            assert len([e for e in entries if not e.query]) == 1, url_name
        with translation.override("de"):
            assert str(nav_registry.entry_by_url(url_name).label) == label
        assert reverse(url_name)
        assert nav_registry.screen_closed(req, url_name) == "", url_name


def test_link_closed_without_the_right():
    """№28: сотрудник без права открыть «Mein Geschäft» — причина одним абзацем, без ссылки."""
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open as walk_open
    from apps.core.tests.test_staff_walk import _user

    tenant = _tenant()
    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={
            "add": ["website.view", "website.edit"],
            "remove": ["einstellungen.view", "einstellungen.edit"],
        }
    )
    resp = walk_open("/dashboard/site/aufbau/?seite=promo&block=card", tenant, staff)
    assert resp.status_code == 200
    part = _part(_panel(resp.content.decode()), "inhalt")
    assert "data-inhalt-link" not in part and "<a " not in part
    assert "data-inhalt-reason" in part
    assert "Inhalt bearbeiten: Mein Geschäft — Nur mit Berechtigung bearbeitbar" in _text(part)


# --- №31: запросов не больше базы ----------------------------------------------------------------


def _warm_count(browser, query) -> int:
    browser.get(query)
    with CaptureQueriesContext(connection) as q:
        browser.get(query)
    return len(q.captured_queries)


@pytest.mark.parametrize(
    "code, key", [("promo", "card"), ("combo", "config"), ("blog_post", "article")]
)
def test_inhalt_queries_not_above_the_base(monkeypatch, code, key):
    """Окно с частью «Inhalt» стоит не больше запросов, чем экран той же строки без источников."""
    tenant = _tenant()
    module = PAGES[code]
    assert _section(module, key).source is not None
    b = Browser(tenant)
    query = f"?seite={code}&block={key}"
    with_part = _warm_count(b, query)
    bare = tuple(
        dataclasses.replace(s, source=None, content_nav="")
        for s in detail_sections.sections_for(module)
    )
    monkeypatch.setitem(detail_sections.DETAIL_SECTIONS, module, bare)
    assert with_part <= _warm_count(b, query)


# --- №13, №16: строки `.po` -----------------------------------------------------------------------


def test_new_msgids_in_all_po():
    """Тексты источников среза есть во всех пяти каталогах, переведены (кроме de), без дублей
    пары msgctxt/msgid; новые записи — сразу после якоря среза."""
    msgids = _msgids()
    assert len(msgids) >= 12
    for lang in ("de", "en", "tr", "ru", "uk"):
        path = ROOT / f"locale/{lang}/LC_MESSAGES/django.po"
        entries = [e for e in polib.pofile(str(path)) if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {e.msgid: e.msgstr for e in entries if e.msgctxt is None}
        for msgid in msgids:
            assert msgid in have, (lang, msgid)
            if lang != "de":
                assert have[msgid] and have[msgid] != msgid, (lang, msgid)
        text = path.read_text(encoding="utf-8")
        start = text.index(f"# {ANCHOR}\n")
        block = text[start : text.index("# fb33-stack-anchor-", start + 1)]
        own = set(re.findall(r'^msgid "(.+)"$', block, re.M))
        allowed = {m.replace('"', '\\"') for m in msgids} | {ANCHOR}
        assert own and own <= allowed, (lang, own)
        assert not RETIRED_MSGIDS & set(have), (lang, RETIRED_MSGIDS & set(have))


def test_window_in_russian_has_no_german_source_text():
    """№13: окно на русском — тексты источника переведены."""
    tenant = _tenant()
    with translation.override("de"):
        de = {k: (str(s.shows), str(s.woher), str(s.note)) for k, s in _sources().items()}
    assert len(de) == len(MAP)
    with translation.override("ru"):
        for (module, key), (shows, woher, note) in de.items():
            code = next(c for c, m in PAGES.items() if m == module)
            part, ct = _inhalt(tenant, f"?seite={code}&block={key}")
            assert ct["summary"] != shows, (module, key)
            assert not woher or woher not in ct["woher"], (module, key)
            assert not note or note not in _text(part), (module, key)
            assert "automatisch" not in ct["woher"], (module, key)
