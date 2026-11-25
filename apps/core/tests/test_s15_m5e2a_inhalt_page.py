"""FB-33 стопка 15 M5e-2a: часть «Inhalt» (механизм M5d) у окон главной и листингов.

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.1 №2, §0.2 «M5eInhalt», §0.3 №1–2, §2 и §4
«M5e-2a», §14.2 Y4. Тот же `detail_sections.DetailSection`/`ContentSource` и та же часть
`window_parts.content_part` (второго механизма нет): `detail_sections.PAGE_SOURCES` — по семье
страницы (`home`, `list`), `ContentSource.link_text` — своё имя ссылки, `subject="tenant"` —
«ausgefüllt» по данным бизнеса через закрытые пробы `_PROBES` (тот же гейт, что у витрины
`storefront/sections/_contact.html`). Экран ★ основного списка — из записи источника
(`siteconfig.LIST_SOURCES` и `nav_registry`), не из нового словаря.
"""

import logging
import re
from pathlib import Path

import polib
import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.core import detail_sections, nav_registry, window_parts
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
LANGS = ("de", "en", "tr", "ru", "uk")
#: §5.2 «M5e-2a» — строки P0 (во всех пяти `.po`) и E7, которые часть берёт повторно
MSGIDS = (
    "Die Angaben kommen aus Ihren Geschäftsdaten.",
    "Geschäftsdaten bearbeiten",
    "%(n)s von %(m)s ausgefüllt",
    "„%(field)s“ — ausgefüllt",
    "„%(field)s“ — leer",
)
#: артборд M5eInhalt «Куда ведёт «Inhalt»»: семья → строка → экран (запись `nav_registry`)
HOME = {
    "contact": "settings",
    "reviews": "reviews:list",
    "finder": "finder-settings",
    "gallery": "site-home",
}
LISTING = {"categories": "catalog:category-list", "combos": "catalog:combo-list"}
#: ★ основного списка: хост → экран списка этой сущности
MAIN_SCREENS = {
    "catalog": "sellable-manage",
    "category": "sellable-manage",
    "catalog:kaffee": "sellable-manage",
    "services": "booking:services",
    "stay_rooms": "stays:units",
    "events": "events:list",
    "tours": "events:tour-list",
    "combos": "catalog:combo-list",
    "promos": "promotions:promotion-list",
    "reviews": "reviews:list",
    "blog": "blog-list",
}
NO_RIGHT = "Nur mit Berechtigung bearbeitbar"
MODULE_OFF = "Modul ist nicht aktiv"
NO_PACKAGE = "Nicht in Ihrem Paket enthalten"
MISSING = pytest.mark.xfail(strict=True, reason="M5e-2a: части «Inhalt» у главной и листингов нет")


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="cafe", disabled=None, **fields):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt) if disabled is None else disabled),
        **fields,
    )
    connection.tenant = tenant
    return tenant


def _part(html: str) -> str:
    m = re.search(r'<div data-window-part="inhalt">(.*?)</div>\s*(?:<div data-window-part|</section>)',
                  html, re.S)  # fmt: skip
    return m.group(1) if m else ""


def _inhalt(tenant, query):
    html, _view, selected = _capture(Browser(tenant), query)
    return _part(_panel(html)), selected


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _request(tenant):
    """Запрос окна, каким его видит часть (тот же, что у экрана)."""
    seen = []
    real = window_parts.content_part

    def spy(selected, host, request, **kw):
        seen.append(request)
        return real(selected, host, request, **kw)

    window_parts.content_part = spy
    try:
        Browser(tenant).get("?seite=home&block=contact")
    finally:
        window_parts.content_part = real
    return seen[-1]


def _content(request, host, key, **row):
    selected = {"key": key, "ref": key, "label": key, "enabled": True, **row}
    window_parts.content_part(selected, host, request, code=host or "home")
    return selected.get("content")


# --- №2: один реестр -----------------------------------------------------------------------------


@MISSING
def test_page_sources_in_contentsource():
    """№2: источники страниц — те же `DetailSection` с `ContentSource` в `PAGE_SOURCES` по семье;
    ключей семей нет среди модулей деталей; экран у каждой строки — запись `nav_registry`
    (у ★ — из записи источника, своего `content_nav` нет)."""
    sources = detail_sections.PAGE_SOURCES
    assert set(sources) == {"home", "list"}
    assert not set(sources) & set(detail_sections.DETAIL_SECTIONS)
    keys = {fam: {s.key for s in rows} for fam, rows in sources.items()}
    assert keys == {"home": set(HOME), "list": {*LISTING, "main"}}
    for fam, rows in sources.items():
        for s in rows:
            assert isinstance(s, detail_sections.DetailSection)
            assert isinstance(s.source, detail_sections.ContentSource), (fam, s.key)
            want = {**HOME, **LISTING}.get(s.key, "")
            assert s.content_nav == want, (fam, s.key)
            if want:
                assert nav_registry.entry_by_url(want) is not None, want
    contact = next(s for s in sources["home"] if s.key == "contact")
    assert contact.source.subject == "tenant"
    assert str(contact.source.link_text) == "Geschäftsdaten bearbeiten"
    assert all(s.source.subject == "" for s in sources["list"])
    # прежние источники деталей — без новых полей
    for rows in detail_sections.DETAIL_SECTIONS.values():
        for s in rows:
            if s.source is not None:
                assert s.source.subject == "" and not s.source.link_text, s.key


@MISSING
@pytest.mark.parametrize("host", sorted(MAIN_SCREENS))
def test_main_screen_from_source_record(host):
    """№2: экран ★ — из записи источника основного списка; у списков без источника блока
    «Liste» (Team, Galerie, Merkzettel, Lookbook) — нет."""
    assert window_parts.main_list_screen(host) == MAIN_SCREENS[host]
    for none in ("team", "gallery", "wishlist", "lookbook", "", "cart"):
        assert window_parts.main_list_screen(none) == ""


# --- №2/№3: «ausgefüllt» = гейт витрины -----------------------------------------------------------


def _storefront(tenant) -> str:
    req = RequestFactory().get("/")
    req.tenant = tenant
    with translation.override("de"):
        return render_to_string(
            "storefront/sections/_contact.html", {"section_row": {}, "request": req}
        )


#: пункт → (поля бизнеса, при которых витрина его рисует; как узнать по выводу витрины)
GATES = {
    "Adresse": ({"address": "Hauptstr. 1, 42651 Solingen"}, "Hauptstr. 1"),
    "Telefon": ({"contact_phone": "+49 212 123456"}, 'href="tel:'),
    # структурные часы без текста: витрина рисует «Öffnungszeiten» по `open_status` —
    # по имени поля `opening_hours` окно сказало бы «leer»
    "Öffnungszeiten": (
        {"opening_hours_structured": {"mon": [["08:00", "18:00"]]}},
        "Öffnungszeiten</p>",
    ),
}


@MISSING
@pytest.mark.parametrize("item", sorted(GATES))
def test_filled_matches_storefront_gate(item):
    """№2/№3: «„X“ — ausgefüllt» ровно тогда, когда витрина рисует этот пункт контактов
    (поведенческий замок: по выводу `_contact.html`, не по именам полей)."""
    fields, marker = GATES[item]
    for case in ({}, fields):
        tenant = _tenant(owner_phone="", **case)
        shown = marker in _storefront(tenant)
        assert shown == bool(case), (item, case)
        with translation.override("de"):
            part, _selected = _inhalt(tenant, "?seite=home&block=contact")
        word = "ausgefüllt" if shown else "leer"
        assert f"„{item}“ — {word}" in _text(part), (item, case, _text(part))


@MISSING
def test_zero_two_three_of_three():
    """№14: итог «N von M ausgefüllt» считает пункты (0, 2 и 3 из 3); значок — украшение,
    состояние — словом."""
    cases = (
        ({"owner_phone": ""}, 0),
        ({"address": "Markt 2", "contact_phone": "0212 1", "owner_phone": ""}, 2),
        (
            {
                "address": "Markt 2",
                "contact_phone": "0212 1",
                "opening_hours": "Mo–Fr 8–18",
            },
            3,
        ),
    )
    for fields, n in cases:
        with translation.override("de"):
            part, selected = _inhalt(_tenant(**fields), "?seite=home&block=contact")
        text = _text(part)
        assert f"{n} von 3 ausgefüllt" in text, (n, text)
        assert text.count("— ausgefüllt") == n and text.count("— leer") == 3 - n, text
        assert "Die Angaben kommen aus Ihren Geschäftsdaten." in text
        assert "aria-live" not in part and 'role="status"' not in part  # Y4: статичный итог


@MISSING
def test_state_word_not_icon_only():
    """Y4: значок состояния `aria-hidden`, слово — в тексте пункта."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant(address="Markt 2"), "?seite=home&block=contact")
    items = re.findall(r"<li data-inhalt-woher-item>(.*?)</li>", part, re.S)
    assert len(items) == 3
    for it in items:
        assert re.match(r'<span aria-hidden="true">[✓–]</span> ', it), it
        assert re.search(r"— (ausgefüllt|leer)$", _text(it)), it


# --- №5: ключ строки — точно ------------------------------------------------------------------------


@MISSING
@pytest.mark.parametrize(
    "host,key,screen",
    [("catalog", "main", "sellable-manage"), *[("catalog", k, v) for k, v in LISTING.items()]],
)
def test_section_key_exact(host, key, screen):
    """№5: строка листинга находит свой источник по точному ключу; похожий ключ, C-блок и
    `ref` ≠ ключу части не получают."""
    request = _request(_tenant("online_shop", disabled=[]))
    content = _content(request, host, key)
    assert content and content["sourced"], key
    got = content["link"]["url"] if content["link"] else ""
    assert got.startswith(reverse(nav_registry.entry_by_url(screen).url_name)), (key, got)
    for other in (f"{key}x", key.upper(), f"{key}:1"):
        assert _content(request, host, other) is None, other
    assert _content(request, host, key, cblock=True) is None
    selected = {"key": key, "ref": "l1", "enabled": True}
    window_parts.content_part(selected, host, request, code=host)
    assert "content" not in selected


@MISSING
@pytest.mark.parametrize("key", sorted(HOME))
def test_home_rows_have_the_part(key):
    """Главная: у contact, reviews, finder, gallery — часть «Inhalt» на «Was»."""
    with translation.override("de"):
        html, _view, selected = _capture(Browser(_tenant(disabled=[])), f"?seite=home&block={key}")
    assert selected["content"]["sourced"], key
    panel = _panel(html)
    assert "Dieser Block zeigt" in _part(panel)
    assert re.search(r'data-window-tab="was"', panel), key


# --- №6: незнакомая семья ----------------------------------------------------------------------


def test_unknown_family_no_part():
    """№6: у страницы без семьи (корзина без раздела, оформление, незнакомый хост) и у строки
    главной без источника — части нет."""
    request = _request(_tenant())
    assert _content(request, "nope", "main") is None
    assert _content(request, "checkout", "contact") is None
    assert _content(request, "", "about") is None
    assert _content(request, "", "main") is None
    assert _content(request, "team", "main") is None


# --- №8: проба незнакомая — в журнал --------------------------------------------------------------


@MISSING
def test_probe_unknown_logged(monkeypatch, caplog):
    """№8: незнакомая проба — ошибка в журнал, состояние «неизвестно» (пункт без слова),
    экран не падает."""
    import dataclasses

    rows = detail_sections.PAGE_SOURCES["home"]
    contact = next(s for s in rows if s.key == "contact")
    fields = tuple(
        dataclasses.replace(f, probe="nope") if f.path == "address" else f
        for f in contact.source.fields
    )
    bad = dataclasses.replace(contact, source=dataclasses.replace(contact.source, fields=fields))
    monkeypatch.setitem(
        detail_sections.PAGE_SOURCES,
        "home",
        tuple(bad if s.key == "contact" else s for s in rows),
    )
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        with translation.override("de"):
            part, _selected = _inhalt(_tenant(address="Markt 2"), "?seite=home&block=contact")
    assert any("unknown probe 'nope'" in r.getMessage() for r in caplog.records)
    text = _text(part)
    assert "„Adresse“ — " not in text and "2 von 2 ausgefüllt" not in text
    assert "von 2 ausgefüllt" in text  # неизвестное не считается


# --- №13: подписи на языке окна -------------------------------------------------------------------


@MISSING
@pytest.mark.parametrize(
    "lang,words",
    [
        ("de", ("„Adresse“", "„Telefon“", "„Öffnungszeiten“", "Geschäftsdaten bearbeiten")),
        ("ru", ("Адрес", "Телефон", "Часы работы")),
    ],
)
def test_labels_ru_de(lang, words):
    """№13: подписи пунктов — те же msgid, что на форме «Mein Geschäft», на языке окна."""
    with translation.override(lang):
        part, _selected = _inhalt(_tenant(), "?seite=home&block=contact")
    text = _text(part)
    for w in words:
        assert w in text, (lang, w, text)
    if lang == "ru":
        assert "Adresse" not in text and "Geschäftsdaten" not in text


# --- №22, Y4: имя ссылки -------------------------------------------------------------------------


@MISSING
@pytest.mark.parametrize(
    "query,name",
    [
        ("?seite=home&block=contact", "Geschäftsdaten bearbeiten"),
        ("?seite=home&block=reviews", "Inhalt bearbeiten: Bewertungen"),
        ("?seite=home&block=finder", "Inhalt bearbeiten: Finder"),
        ("?seite=home&block=gallery", "Inhalt bearbeiten: Galerie"),
        ("?seite=catalog&block=main", "Inhalt bearbeiten: Sortiment"),
        ("?seite=catalog&block=categories", "Inhalt bearbeiten: Kategorien"),
    ],
)
def test_link_purpose_names_screen(query, name):
    """№22, Y4: имя ссылки — видимый текст (без `aria-label`), называет экран; подпись — один
    `<span>` внутри ссылки."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant("online_shop", disabled=[]), query)
    links = re.findall(r"<a [^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert len(links) == 1, part
    assert re.fullmatch(r"<span>[^<]*</span>", links[0]), links[0]
    assert _text(links[0]) == name
    assert "aria-label" not in re.search(r"<a [^>]*data-inhalt-link[^>]*>", part).group(0)


def test_link_name_starts_with_visible():
    """№22: у прежних окон M5d имя ссылки — по-прежнему видимый текст (охранный)."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant("friseur", disabled=[]), "?seite=finder&block=wizard")
    link = re.search(r"<a [^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert link and _text(link.group(1)).startswith("Inhalt bearbeiten: ")


# --- №28: экран закрыт -----------------------------------------------------------------------------


@MISSING
def test_link_closed_module():
    """№28 (модуль): экран выключенного модуля — абзац причины без `<a>`."""
    with translation.override("de"):
        part, selected = _inhalt(_tenant(disabled=["reviews"]), "?seite=home&block=reviews")
    assert selected["content"]["link"] is None
    assert "<a " not in part and MODULE_OFF in part and "data-inhalt-reason" in part


@MISSING
def test_link_closed_package(monkeypatch):
    """№28 (пакет): экрана нет в пакете — причина без ссылки."""
    from apps.core import packages

    monkeypatch.setattr(packages, "view_allowed", lambda tenant, name: name != "settings")
    with translation.override("de"):
        part, selected = _inhalt(_tenant(), "?seite=home&block=contact")
    assert selected["content"]["link"] is None
    assert "<a " not in part and NO_PACKAGE in part
    assert "Geschäftsdaten bearbeiten" not in part  # имя ссылки — только у ссылки


@MISSING
def test_no_anchor_when_closed():
    """№28 (право), Y4: сотрудник без права на экран — абзац `ct.reason` без `<a>` (не
    `aria-disabled`); владелец — со ссылкой."""
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open as walk_open
    from apps.core.tests.test_staff_walk import _user

    tenant = _tenant()
    path = "/dashboard/site/aufbau/?seite=home&block=contact"
    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={"add": ["website.view", "website.edit"], "remove": ["settings.view"]}
    )
    with translation.override("de"):
        resp = walk_open(path, tenant, staff)
        assert resp.status_code == 200
        part = _part(_panel(resp.content.decode()))
        assert part and "<a " not in part and "aria-disabled" not in part
        assert NO_RIGHT in part and "data-inhalt-reason" in part
        owner = _user(Membership.ROLE_OWNER)
        part = _part(_panel(walk_open(path, tenant, owner).content.decode()))
    assert "data-inhalt-link" in part and NO_RIGHT not in part


# --- №31: запросы ---------------------------------------------------------------------------------


@MISSING
def test_inhalt_page_queries(monkeypatch):
    """№31: часть «Inhalt» у строки главной и ★ стоит не больше двух запросов поверх окна без
    неё (каникулы для `open_status`)."""
    tenant = _tenant("online_shop", disabled=[], address="Markt 2")
    b = Browser(tenant)
    real = window_parts.content_part

    def count(query):
        b.get(query)
        with CaptureQueriesContext(connection) as q:
            b.get(query)
        return len(q.captured_queries)

    for query in ("?seite=home&block=contact", "?seite=catalog&block=main"):
        monkeypatch.setattr(window_parts, "content_part", real)
        with_part = count(query)
        monkeypatch.setattr(window_parts, "content_part", lambda *a, **kw: None)
        assert with_part - count(query) <= 2, query
        monkeypatch.setattr(window_parts, "content_part", real)
        _part_html, selected = _inhalt(tenant, query)
        assert selected["content"]["sourced"], query


# --- №16: строки ---------------------------------------------------------------------------------


def test_m5e2a_msgids_in_all_po():
    """№16: строки части есть во всех пяти `.po`, плейсхолдеры совпадают."""
    for lang in LANGS:
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        have = {e.msgid: e.msgstr for e in po if not e.obsolete and not e.msgctxt}
        for msgid in MSGIDS:
            assert msgid in have, (lang, msgid)
            got = have[msgid] or msgid
            names = sorted(re.findall(r"%\((\w+)\)s", msgid))
            assert sorted(re.findall(r"%\((\w+)\)s", got)) == names, (lang, msgid)
