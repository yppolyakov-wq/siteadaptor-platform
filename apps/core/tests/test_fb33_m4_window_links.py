"""FB-33 M4: замки ДО кода — ⚙ Студии открывает окно блока «Seitenaufbau».

Окно блока уже открывается адресом `?seite=<код>&block=<строка>[&tab=]` (M3-0…M3-2). Студия
знает только путь канвы и ключ секции (`data-sf-section`) — сервер переводит их в этот адрес:
`apps/core/window_links.py` и GET-эндпоинт `site-schema-open` (только 302, внутри экрана
«Seitenaufbau», ничего не пишет). Неизвестная строка — страница без блока и подсказка.

L1 адреса окна по CASES окна · L2 `url_for_path` прежний · L3 эндпоинт: 302, open redirect,
XSS, права, без записи · L4 после 302 — тот же экран, что эталон окна · L5 ⚙ Студии ведёт
на эндпоинт, а не в старую панель · L6 эндпоинт — осознанно вне навигации.
"""

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse
from django.utils import translation

from apps.core import site_schema
from apps.core.tests.test_fb27_r2_draft import _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
STUDIO_TPL = ROOT / "templates" / "tenant" / "site_home.html"
NOT_FOUND = "Diesen Block finden Sie im Seitenaufbau nicht."
SCHEMA = "/dashboard/site/aufbau/"
OPEN = "/dashboard/site/aufbau/oeffnen/"

#: CASES окна без доп. запроса (окно — по паре «страница, строка»)
PAIRS = tuple(c for c in CASES if len(c) == 2)

#: до кода M4 — поведения ещё нет (снимается в коммите кода)
_todo = pytest.mark.xfail(strict=True, reason="FB-33 M4: до кода")


def _shop():
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant()
    tenant.site_config = copy.deepcopy(CFG)
    tenant.save()
    ProductFactory()  # образец для превью строки «Produkt»
    return tenant


def _path(tenant, code: str) -> str:
    """Путь витрины строки `code` — тот, что канва Студии показывает для этой страницы."""
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    row = next(r for r in rows if r.code == code)
    assert row.preview_url, f"у строки {code} нет превью — случай бессмысленен"
    return row.preview_url


def _req(tenant, query: dict | None = None, method="get"):
    req = getattr(RequestFactory(), method)(OPEN, query or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _messages(req) -> list[str]:
    return [str(m) for m in get_messages(req)]


# ───────────── L1: адреса окна ─────────────


@_todo
def test_block_window_url_is_the_window_address():
    from apps.core import window_links

    assert (
        window_links.block_window_url("home", "t1") == f"{SCHEMA}?seite=home&block=t1#schema-panel"
    )
    assert (
        window_links.block_window_url("home", "t1", "texte")
        == f"{SCHEMA}?seite=home&block=t1&tab=texte#schema-panel"
    )
    # вкладка — только из белого списка окна; токен открытия `wopen` адрес не несёт
    assert window_links.block_window_url("home", "t1", "<x>") == (
        f"{SCHEMA}?seite=home&block=t1#schema-panel"
    )
    # объект: «@» и «:» кодируются, разметка — нет
    url = window_links.block_window_url("text@seite:a b", "x")
    assert url == f"{SCHEMA}?seite=text%40seite%3Aa+b&block=x#schema-panel"


@_todo
@pytest.mark.parametrize("case", PAIRS, ids=["|".join(c) for c in PAIRS])
def test_studio_gear_opens_the_window_of_that_block(case):
    """Путь канвы + ключ секции → окно того же блока, что открывает «Seitenaufbau»."""
    from apps.core import window_links

    code, ref = case
    tenant = _shop()
    req = _req(tenant)
    got = window_links.studio_settings_url(req, _path(tenant, code), ref)
    assert got == window_links.block_window_url(code, ref)
    assert _messages(req) == []


@_todo
def test_tab_is_carried_to_the_window():
    from apps.core import window_links

    tenant = _shop()
    got = window_links.studio_settings_url(_req(tenant), "/", "t1", "texte")
    assert got == window_links.block_window_url("home", "t1", "texte")


@_todo
def test_without_block_the_page_of_the_canvas_opens():
    """«Aufbau ändern»: без строки — схема страницы канвы (как `url_for_path`)."""
    from apps.core import window_links

    tenant = _shop()
    for code in ("home", "catalog", "cart", "text"):
        path = _path(tenant, code)
        req = _req(tenant)
        assert window_links.studio_settings_url(req, path) == site_schema.url_for_path(tenant, path)
        assert _messages(req) == []


@_todo
def test_page_key_of_the_canvas_opens_the_page_settings():
    """Ключ самой страницы (обёртка списка/детали, хост блоков) — настройки типа страницы."""
    from apps.core import window_links

    tenant = _shop()
    catalog = _path(tenant, "catalog")
    assert window_links.studio_settings_url(_req(tenant), catalog, "catalog") == (
        site_schema.settings_url("catalog")
    )
    assert window_links.studio_settings_url(_req(tenant), catalog, "pbhost:catalog") == (
        site_schema.settings_url("catalog")
    )
    product = _path(tenant, "product")
    assert window_links.studio_settings_url(_req(tenant), product, "product_detail") == (
        site_schema.settings_url("product")
    )


@_todo
def test_detail_section_key_of_the_canvas_names_the_section():
    """Раздел детали на канве — `<страница>_<раздел>` (`service_faq`), строка схемы — `faq`."""
    from apps.core import window_links

    tenant = _shop()
    product = _path(tenant, "product")
    assert window_links.studio_settings_url(_req(tenant), product, "product_related") == (
        window_links.block_window_url("product", "related")
    )


@_todo
def test_unknown_block_opens_the_page_with_a_note():
    from apps.core import window_links

    tenant = _shop()
    req = _req(tenant)
    with translation.override("de"):
        got = window_links.studio_settings_url(req, "/", "gibtsnicht")
        assert got == f"{SCHEMA}?seite=home"
        assert _messages(req) == [NOT_FOUND]


@_todo
def test_unknown_page_opens_the_screen():
    from apps.core import window_links

    tenant = _shop()
    for path in ("", "//evil.example/", "kein-pfad", "/gibt-es-nicht/x/y/"):
        req = _req(tenant)
        assert window_links.studio_settings_url(req, path) == SCHEMA


@_todo
def test_draft_block_is_found():
    """Блок, добавленный в черновик «Seitenaufbau» (ещё не сохранён), — тоже открывается."""
    from apps.core import aufbau_draft, window_links

    tenant = _shop()
    req = _req(tenant)
    saved = siteconfig.normalize(tenant.site_config)
    sections = [*saved["sections"], {"key": "text", "id": "neu1", "enabled": True, "data": {}}]
    aufbau_draft._put(req, "home", {"sections": sections})
    assert window_links.studio_settings_url(req, "/", "neu1") == (
        window_links.block_window_url("home", "neu1")
    )


# ───────────── L2: url_for_path прежний ─────────────


def test_url_for_path_is_built_from_code_for_path():
    tenant = _shop()
    for path in ("/", "/ueber-uns/", "/warenkorb/", "/sortiment/", "", "//x/", None):
        code = site_schema.code_for_path(tenant, path)
        expected = f"{SCHEMA}?{urlencode({'seite': code})}" if code else SCHEMA
        assert site_schema.url_for_path(tenant, path) == expected
    assert site_schema.url_for_path(tenant, "/") == f"{SCHEMA}?seite=home"
    assert site_schema.url_for_path(tenant, "/ueber-uns/") == f"{SCHEMA}?seite=text"


@_todo
def test_promos_page_of_the_canvas_has_its_schema():
    """Страница «Aktionen» (хост блоков — EXTRA_HOSTS) — своя схема, а не экран без выбора."""
    tenant = _shop()
    assert site_schema.code_for_path(tenant, "/aktionen/") == "promos"


# ───────────── L3: эндпоинт ─────────────


def _open(tenant, **query):
    from apps.core.window_link_views import site_schema_open

    req = _req(tenant, query)
    return site_schema_open(req), req


@_todo
def test_endpoint_redirects_to_the_window():
    tenant = _shop()
    resp, _req_ = _open(tenant, page="/", block="t1", tab="texte")
    assert resp.status_code == 302
    assert resp["Location"] == f"{SCHEMA}?seite=home&block=t1&tab=texte#schema-panel"
    assert reverse("site-schema-open") == OPEN


@_todo
def test_endpoint_is_get_only():
    from apps.core.window_link_views import site_schema_open

    tenant = _shop()
    resp = site_schema_open(_req(tenant, {"page": "/", "block": "t1"}, method="post"))
    assert resp.status_code == 405


@_todo
@pytest.mark.parametrize(
    "page",
    [
        "//evil.example/",
        "https://evil.example/",
        "\\\\evil.example\\",
        "/\\evil.example",
        "javascript:alert(1)",
        "/dashboard/",
        "http:/evil.example",
        "%2F%2Fevil.example",
    ],
)
def test_endpoint_never_leaves_the_schema_screen(page):
    tenant = _shop()
    resp, _r = _open(tenant, page=page, block="t1")
    assert resp.status_code == 302
    loc = resp["Location"]
    parts = urlsplit(loc)
    assert not parts.scheme and not parts.netloc, loc
    assert parts.path == SCHEMA, loc


@_todo
@pytest.mark.parametrize(
    "block",
    ['"><script>alert(1)</script>', "t1&seite=evil", "t1#x", "a" * 200, "t1\r\nX: y", "../t1"],
)
def test_endpoint_cleans_the_block(block):
    tenant = _shop()
    resp, _r = _open(tenant, page="/", block=block)
    loc = resp["Location"]
    assert urlsplit(loc).path == SCHEMA
    for bad in ("<", ">", '"', "\r", "\n", "evil"):
        assert bad not in loc, loc
    query = parse_qs(urlsplit(loc).query)
    assert query.get("seite") == ["home"], loc
    assert all(re.fullmatch(r"[A-Za-z0-9_:-]{1,40}", v) for v in query.get("block", [])), loc


@_todo
def test_endpoint_writes_nothing():
    from apps.core import aufbau_draft

    tenant = _shop()
    before = json.dumps(tenant.site_config, sort_keys=True)
    resp, req = _open(tenant, page="/", block="t1")
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert json.dumps(tenant.site_config, sort_keys=True) == before
    assert aufbau_draft.dirty_codes(req) == []


@_todo
def test_endpoint_rights_are_those_of_the_schema_screen():
    from apps.core import view_perms

    assert view_perms.RULES["site-schema-open"] == view_perms.RULES["site-schema"]


@_todo
def test_staff_without_website_key_gets_403(monkeypatch):
    from apps.core.tests.test_view_perms import _call, _user
    from apps.tenants.models import Membership

    user = _user(Membership.ROLE_STAFF)
    monkeypatch.setattr("apps.core.permissions.effective", lambda u: frozenset())
    resp = _call(OPEN, user, view_name="site-schema-open")
    assert resp.status_code == 403
    monkeypatch.setattr("apps.core.permissions.effective", lambda u: frozenset({"website.view"}))
    assert _call(OPEN, user, view_name="site-schema-open") is None


@_todo
def test_endpoint_needs_login():
    from django.contrib.auth.models import AnonymousUser

    from apps.core.window_link_views import site_schema_open

    tenant = _shop()
    req = _req(tenant, {"page": "/", "block": "t1"})
    req.user = AnonymousUser()
    resp = site_schema_open(req)
    assert (
        resp.status_code == 302 and "/dashboard/site/aufbau/" not in resp["Location"].split("?")[0]
    )


@_todo
def test_endpoint_unknown_block_note():
    tenant = _shop()
    with translation.override("de"):
        resp, req = _open(tenant, page="/", block="gibtsnicht")
        assert resp["Location"] == f"{SCHEMA}?seite=home"
        assert _messages(req) == [NOT_FOUND]


# ───────────── L4: после 302 — тот же экран, что эталон окна ─────────────


@_todo
@pytest.mark.parametrize("case", PAIRS[:6], ids=["|".join(c) for c in PAIRS[:6]])
def test_after_redirect_the_window_is_the_golden_one(case):
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.core.tests.test_fb33_m3_2_nojs import GOLDEN, _name, _query, _slice

    code, ref = case
    tenant = _shop()
    resp, _r = _open(tenant, page=_path(tenant, code), block=ref)
    location = resp["Location"]
    assert location == f"{SCHEMA}{_query(case)}#schema-panel"
    tenant.site_config = CFG
    tenant.save()
    with translation.override("de"):
        html = Browser(tenant).get(location[len(SCHEMA) :].split("#", 1)[0])
    assert _slice(html) == (GOLDEN / _name(case)).read_text()


# ───────────── L5: ⚙ Студии — на эндпоинт, а не в старую панель ─────────────


def _studio(tenant):
    from apps.core.tests.test_stu12_groups import _builder

    with translation.override("de"):
        return _builder(tenant)


@_todo
def test_studio_row_gear_is_a_link_to_the_window():
    from apps.core.tests.test_stu12_groups import _row

    tenant = _shop()
    body = _studio(tenant)
    row = _row(body, "faq")
    gear = re.search(r"<a [^>]*data-stu-gear[^>]*>", row)
    assert gear, "⚙ строки секции — ссылка (работает и без JS)"
    assert f'href="{OPEN}?page=%2F&amp;block=faq"' in gear.group(0)
    # имя секции по-прежнему открывает старую панель (снятие групп — M4b)
    assert re.search(r'<button type="button" class="blk-edit flex-1[^"]*" data-key="faq"', row)


@_todo
def test_studio_aufbau_link_goes_through_the_endpoint():
    tenant = _shop()
    body = _studio(tenant)
    link = re.search(r"<a [^>]*data-stu-aufbau[^>]*>", body)
    assert link, "«Aufbau ändern» помечен для обновления адреса при навигации канвы"
    assert f'href="{OPEN}?page=%2F"' in link.group(0)


@_todo
def test_studio_bar_gear_does_not_open_the_old_panel():
    src = STUDIO_TPL.read_text()
    line = next(li for li in src.splitlines() if 'act === "settings"' in li)
    assert "openBlockPopup" not in line
    assert "{% url 'site-schema-open' %}" in src
    # несохранённые правки Студии — спросить, прежде чем уйти (решение владельца 2026-11-21)
    assert "Ungespeicherte Änderungen gehen verloren." in src


# ───────────── L6: вне навигации осознанно ─────────────


@_todo
def test_endpoint_is_consciously_unlisted():
    from apps.core.tests.test_x0_x7_locks import EXPECTED_UNLISTED

    assert "site-schema-open" in EXPECTED_UNLISTED
