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
#: ревью 1 (№7): «Kategorien» и «Sets & Menüs» — только у страниц каталога
CATALOG_HOSTS = ("catalog", "category", "catalog:kaffee")
#: ревью 1 (№2): хосты основного списка без экрана — у их списка нет источника «Liste»
NO_SCREEN = {"team", "gallery", "wishlist", "lookbook"}
#: ревью 1 (№2): источник основного списка → экран его правки
SOURCE_SCREENS = {
    "promotions": "promotions:promotion-list",
    "products": "sellable-manage",
    "services": "booking:services",
    "stays": "stays:units",
    "events": "events:list",
    "tours": "events:tour-list",
    "combos": "catalog:combo-list",
    "categories": "catalog:category-list",
    "reviews": "reviews:list",
    "blog": "blog-list",
}
#: пункты «Kontakt» (de) — артборд M5eInhalt + ревью 1 №4 (e-mail и карта тоже открывают блок)
CONTACT_ITEMS = 5
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


def test_page_sources_in_contentsource():
    """№2: источники страниц — те же `DetailSection` с `ContentSource` в `PAGE_SOURCES` по семье;
    ключей семей нет среди модулей деталей; экран у каждой строки — запись `nav_registry`
    (у ★ — из записи источника, своего `content_nav` нет)."""
    sources = detail_sections.PAGE_SOURCES
    assert set(sources) == {"home", "list", "catalog_list"}
    assert not set(sources) & set(detail_sections.DETAIL_SECTIONS)
    keys = {fam: {s.key for s in rows} for fam, rows in sources.items()}
    assert keys == {"home": set(HOME), "list": {"main"}, "catalog_list": {*LISTING, "main"}}
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
    assert all(s.source.subject == "" for s in (*sources["list"], *sources["catalog_list"]))
    # прежние источники деталей — без `subject`; своё имя ссылки — только у «Angebot» акции
    for module, rows in detail_sections.DETAIL_SECTIONS.items():
        for s in rows:
            if s.source is not None:
                assert s.source.subject == "", s.key
                assert bool(s.source.link_text) == ((module, s.key) == ("promo", "offer"))


@pytest.mark.parametrize("host", sorted(MAIN_SCREENS))
def test_main_screen_from_source_record(host):
    """№2: экран ★ — из записи источника основного списка; у списков без источника блока
    «Liste» (Team, Galerie, Merkzettel, Lookbook) — нет."""
    assert window_parts.main_list_screen(host) == MAIN_SCREENS[host]
    for none in ("team", "gallery", "wishlist", "lookbook", "", "cart"):
        assert window_parts.main_list_screen(none) == ""


def test_main_list_screen_covers_all_list_sources():
    """Ревью 1 №2: у каждого хоста основного списка — экран, кроме явного списка без источника;
    у каждого источника `LIST_SOURCES` — экран."""
    from apps.tenants import siteconfig

    for host in siteconfig.MAIN_LIST_HOSTS:
        got = window_parts.main_list_screen(host)
        assert bool(got) == (host not in NO_SCREEN), (host, got)
    assert set(SOURCE_SCREENS) == set(siteconfig.LIST_SOURCES)


@pytest.mark.parametrize("source", sorted(SOURCE_SCREENS))
def test_main_list_screen_expected_url_per_source(source):
    """Ревью 1 №2: экран источника — по таблице (точный модуль раньше «ядра»)."""
    assert window_parts.list_source_screen(source) == SOURCE_SCREENS[source]


def test_main_section_without_screen_logged(monkeypatch, caplog):
    """Ревью 1 №2: у настоящего источника экран не нашёлся — предупреждение в журнал."""
    monkeypatch.setattr(window_parts, "list_source_screen", lambda source: "")
    request = _request(_tenant("online_shop", disabled=[]))
    with caplog.at_level(logging.WARNING, logger="apps.core.window_parts"):
        assert _content(request, "catalog", "main") is None
    assert any("no screen" in r.getMessage() for r in caplog.records)


# --- №2/№3: «ausgefüllt» = гейт витрины -----------------------------------------------------------


def _storefront(tenant, style="") -> str:
    req = RequestFactory().get("/")
    req.tenant = tenant
    with translation.override("de"):
        return render_to_string(
            "storefront/sections/_contact.html", {"section_row": {"style": style}, "request": req}
        )


def _hours_shown(html, style):
    return ("Heute: " in html) if style == "compact" else ("Öffnungszeiten</p>" in html)


def _map_shown(html, _style):
    return "sf-contact-map" in html or "maps.example" in html


#: случай → (пункт окна, поля бизнеса, «рисует ли витрина пункт» по её выводу)
GATES = {
    "address": ("Adresse", {"address": "Hauptstr. 1, Solingen"}, lambda h, s: "Hauptstr. 1" in h),
    "phone": ("Telefon", {"contact_phone": "+49 212 1"}, lambda h, s: 'href="tel:' in h),
    # телефон владельца, когда своего нет (`public_phone`)
    "owner-phone": ("Telefon", {"owner_phone": "+49 212 2"}, lambda h, s: 'href="tel:' in h),
    "email": ("E-Mail", {"contact_email": "a@b.de"}, lambda h, s: 'href="mailto:' in h),
    # структурные часы без текста: витрина рисует по `open_status`
    "hours-structured": (
        "Öffnungszeiten",
        {"opening_hours_structured": {str(d): ["00:00", "23:59"] for d in range(7)}},
        _hours_shown,
    ),
    # часы текстом: у вида «compact» витрина их НЕ рисует (только «Heute» по статусу)
    "hours-text": ("Öffnungszeiten", {"opening_hours": "Mo–Fr 8–18"}, _hours_shown),
    # ссылка на карту сама блок не открывает (гейт `_contact.html`) — с адресом
    "map-link": (
        "Karten-Link",
        {"map_url": "https://maps.example/x", "address": "Markt 2"},
        _map_shown,
    ),
    # точка на карте без ссылки: карта рисуется у всех видов, кроме «compact»
    "map-point": ("Karten-Link", {"latitude": "51.1", "longitude": "7.08"}, _map_shown),
}
EMPTY = {"owner_phone": "", "owner_email": ""}


def _window_word(tenant, item, style=""):
    if style:
        tenant.site_config = {
            **(tenant.site_config or {}),
            "sections": [{"key": "contact", "enabled": True, "style": style}],
        }
        tenant.save()
    with translation.override("de"):
        part, _selected = _inhalt(tenant, "?seite=home&block=contact")
    text = _text(part)
    found = re.search(rf"„{re.escape(item)}“ — (ausgefüllt|leer)", text)
    return found.group(1) if found else text


@pytest.mark.parametrize("style", ["", "compact"])
@pytest.mark.parametrize("case", sorted(GATES))
def test_filled_matches_storefront_gate(case, style):
    """№2/№3, ревью 1 №3/№4: «„X“ — ausgefüllt» ровно тогда, когда витрина рисует этот пункт
    контактов у этого вида блока (поведенческий замок: по выводу `_contact.html`)."""
    if (case, style) in XFAIL_GATES:
        pytest.xfail("ревью 1: ещё не сделано")
    item, fields, shown_by = GATES[case]
    assert not shown_by(_storefront(_tenant(**EMPTY), style), style), case
    tenant = _tenant(**{**EMPTY, **fields})
    shown = shown_by(_storefront(tenant, style), style)
    assert _window_word(tenant, item, style) == ("ausgefüllt" if shown else "leer"), (case, shown)


#: красные случаи ревью 1 до кода (e-mail, карта, часы текстом у «compact»); после кода — пусто
XFAIL_GATES: set = set()


def test_holiday_hours_match_storefront(monkeypatch):
    """Ревью 1 №3: каникулы без часов — витрина рисует «Heute: …» (статус «закрыто»); окно
    говорит то же."""
    from datetime import date

    from apps.core import closures

    rng = {"von": date(2026, 12, 24), "bis": date(2026, 12, 27), "reason": ""}
    monkeypatch.setattr(closures, "closed_range_for", lambda tenant, day: rng)
    for style in ("", "compact"):
        tenant = _tenant(**EMPTY)
        shown = _hours_shown(_storefront(tenant, style), style)
        assert _window_word(tenant, "Öffnungszeiten", style) == (
            "ausgefüllt" if shown else "leer"
        ), style


def test_zero_two_three_of_three():
    """№14: итог «N von M ausgefüllt» считает пункты (0, 2 и 3 из 3); значок — украшение,
    состояние — словом."""
    m = CONTACT_ITEMS
    cases = (
        ({}, 0),
        ({"address": "Markt 2", "contact_phone": "0212 1"}, 2),
        (
            {
                "address": "Markt 2",
                "contact_phone": "0212 1",
                "opening_hours": "Mo–Fr 8–18",
                "contact_email": "a@b.de",
                "map_url": "https://maps.example/x",
            },
            m,
        ),
    )
    for fields, n in cases:
        with translation.override("de"):
            part, selected = _inhalt(_tenant(**EMPTY, **fields), "?seite=home&block=contact")
        text = _text(part)
        assert f"{n} von {m} ausgefüllt" in text, (n, text)
        assert text.count("— ausgefüllt") == n and text.count("— leer") == m - n, text
        assert "Die Angaben kommen aus Ihren Geschäftsdaten." in text
        assert "aria-live" not in part and 'role="status"' not in part  # Y4: статичный итог


def test_state_word_not_icon_only():
    """Y4: значок состояния `aria-hidden`, слово — в тексте пункта."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant(address="Markt 2"), "?seite=home&block=contact")
    items = re.findall(r"<li data-inhalt-woher-item>(.*?)</li>", part, re.S)
    assert len(items) == CONTACT_ITEMS
    for it in items:
        assert re.match(r'<span aria-hidden="true">[✓–]</span> ', it), it
        assert re.search(r"— (ausgefüllt|leer)$", _text(it)), it


# --- №5: ключ строки — точно ------------------------------------------------------------------------


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
    assert "„Adresse“ — " not in text
    assert f"von {CONTACT_ITEMS - 1} ausgefüllt" in text  # неизвестное не считается


# --- №13: подписи на языке окна -------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang,words",
    [
        (
            "de",
            (
                "„Adresse“",
                "„Telefon“",
                "„Öffnungszeiten“",
                "„E-Mail“",
                "„Karten-Link“",
                "Geschäftsdaten bearbeiten",
            ),
        ),
        ("ru", ("Адрес", "Телефон", "Часы работы", "Электронная почта", "Ссылка на карту")),
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
    assert re.fullmatch(
        r'<span class="min-w-0 \[overflow-wrap:anywhere\]">[^<]*</span>', links[0]
    ), links[0]
    assert _text(links[0]) == name
    assert "aria-label" not in re.search(r"<a [^>]*data-inhalt-link[^>]*>", part).group(0)


def test_link_name_starts_with_visible():
    """№22: у прежних окон M5d имя ссылки — по-прежнему видимый текст (охранный)."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant("friseur", disabled=[]), "?seite=finder&block=wizard")
    link = re.search(r"<a [^>]*data-inhalt-link[^>]*>(.*?)</a>", part, re.S)
    assert link and _text(link.group(1)).startswith("Inhalt bearbeiten: ")


# --- №28: экран закрыт -----------------------------------------------------------------------------


def test_link_closed_module():
    """№28 (модуль): экран выключенного модуля — абзац причины без `<a>`."""
    with translation.override("de"):
        part, selected = _inhalt(_tenant(disabled=["reviews"]), "?seite=home&block=reviews")
    assert selected["content"]["link"] is None
    assert "<a " not in part and MODULE_OFF in part and "data-inhalt-reason" in part


def test_link_closed_package(monkeypatch):
    """№28 (пакет): экрана нет в пакете — причина без ссылки."""
    from apps.core import packages

    monkeypatch.setattr(packages, "view_allowed", lambda tenant, name: name != "settings")
    with translation.override("de"):
        part, selected = _inhalt(_tenant(), "?seite=home&block=contact")
    assert selected["content"]["link"] is None
    assert "<a " not in part and NO_PACKAGE in part
    assert "Geschäftsdaten bearbeiten" not in part  # имя ссылки — только у ссылки


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
        permissions={
            "add": ["website.view", "website.edit"],
            "remove": ["einstellungen.view", "einstellungen.edit"],
        }
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


# --- ревью 1 -----------------------------------------------------------------------------------


def test_offer_part_links_to_promotions():
    """Ревью 1 №0: «Angebot» деталей акции (строка типа) — «Inhalt»: что показывает и ссылка
    «Aktion bearbeiten» на экран акций; у строки одной акции части нет (как раньше)."""
    with translation.override("de"):
        part, selected = _inhalt(_tenant(disabled=[]), "?seite=promo&block=offer")
    text = _text(part)
    assert "Dieser Block zeigt: Preis, Bedingungen und Gutscheincode der Aktion." in text
    link = re.search(r'<a href="([^"]+)"[^>]*data-inhalt-link[^>]*>(.*?)</a>', part, re.S)
    assert link and _text(link.group(2)) == "Aktion bearbeiten", part
    assert link.group(1).startswith(reverse("promotions:promotion-list"))


@pytest.mark.parametrize(
    "query", ["?seite=home&block=contact", "?seite=catalog&block=main", "?seite=promo&block=offer"]
)
def test_inhalt_link_target_44(query):
    """Ревью 1 №1 (a11y): ссылка части — цель ≥ 44 px (`inline-flex min-h-[44px]
    items-center`), подпись — один `<span>` с переносом длинного слова."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant("online_shop", disabled=[]), query)
    tag = re.search(r"<a [^>]*data-inhalt-link[^>]*>", part).group(0)
    for cls in ("inline-flex", "min-h-[44px]", "items-center"):
        assert cls in tag.split('class="')[1].split('"')[0].split(), (cls, tag)
    span = re.search(r"<a [^>]*data-inhalt-link[^>]*>(<span[^>]*>)", part).group(1)
    assert "min-w-0" in span and "[overflow-wrap:anywhere]" in span, span


@pytest.mark.parametrize(
    "query", ["?seite=home&block=contact", "?seite=catalog&block=main", "?seite=home&block=finder"]
)
def test_no_live_region_in_part(query):
    """Ревью 1 №1: в части нет живой области — итог статичный (Y4)."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant("online_shop", disabled=[]), query)
    assert part
    assert "aria-live" not in part and 'role="status"' not in part and 'role="alert"' not in part


def test_no_link_when_reason():
    """Ревью 1 №1: при причине — ни одной `<a data-inhalt-link>`."""
    with translation.override("de"):
        part, selected = _inhalt(_tenant(disabled=["reviews"]), "?seite=home&block=reviews")
    assert selected["content"]["reason"]
    assert "data-inhalt-link" not in part


def test_link_text_has_no_interpolation():
    """Ревью 1 №1: `link_text` — целая строка без подстановок имён (имя не меняет язык)."""
    rows = [s for fam in detail_sections.PAGE_SOURCES.values() for s in fam]
    rows += [s for fam in detail_sections.DETAIL_SECTIONS.values() for s in fam]
    for s in rows:
        if s.source is not None and s.source.link_text:
            text = str(s.source.link_text)
            assert "%(" not in text and "{" not in text, s.key


def test_combos_summary_uses_business_label():
    """Ревью 1 №5: «Sets & Menüs» — имя источника по типу бизнеса (`source_label`)."""
    from apps.core import list_blocks

    tenant = _tenant("restaurant", disabled=[])
    request = _request(tenant)
    with translation.override("de"):
        content = _content(request, "catalog", "combos")
        want = list_blocks.source_label("combos", tenant)
    assert content and content["summary"] == str(want)


def test_gallery_only_if_presence():
    """Ревью 1 №5: галерея главной рисуется только с фото — у «Woher» это сказано."""
    with translation.override("de"):
        part, _selected = _inhalt(_tenant(disabled=[]), "?seite=home&block=gallery")
    assert "Erscheint nur, wenn die Galerie Fotos hat." in _text(part)


def test_tenant_list_missing_label_logged(monkeypatch, caplog):
    """Ревью 1 №6: пункт без подписи — ошибка в журнал с путём поля, без списка."""
    import dataclasses

    rows = detail_sections.PAGE_SOURCES["home"]
    contact = next(s for s in rows if s.key == "contact")
    fields = tuple(
        dataclasses.replace(f, label="", field="") if f.path == "address" else f
        for f in contact.source.fields
    )
    bad = dataclasses.replace(contact, source=dataclasses.replace(contact.source, fields=fields))
    monkeypatch.setitem(
        detail_sections.PAGE_SOURCES, "home", tuple(bad if s.key == "contact" else s for s in rows)
    )
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        with translation.override("de"):
            part, selected = _inhalt(_tenant(), "?seite=home&block=contact")
    assert any("'address'" in r.getMessage() for r in caplog.records), caplog.text
    assert not selected["content"]["woher_list"] and "data-inhalt-woher-item" not in part


def test_page_family_unknown_host_empty(caplog):
    """Ревью 1 №6: хост None — не главная: части нет, ошибка в журнал."""
    request = _request(_tenant())
    selected = {"key": "contact", "ref": "contact", "enabled": True}
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        window_parts.content_part(selected, None, request, code="home")
    assert "content" not in selected
    assert any("no host" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("key", sorted(LISTING))
def test_catalog_rows_only_on_catalog_hosts(key):
    """Ревью 1 №7: «Kategorien» и «Sets & Menüs» — у страниц каталога, не у других листингов."""
    request = _request(_tenant("online_shop", disabled=[]))
    for host in CATALOG_HOSTS:
        assert _content(request, host, key), (host, key)
    for host in ("services", "promos", "events", "blog"):
        assert _content(request, host, key) is None, (host, key)


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
