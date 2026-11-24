"""FB-33 стопка 14 E1: «Auf der Seite bearbeiten» и «Vorschau» окна блока — на объекте, с
которого пришли (план `docs/fb33-stack14-plan-2026-11-24.md` §2 «E1», §4 «E1», §10 M1–M3, L6).

Путь страницы витрины `von` — из ⚙ Студии (`window_links.studio_settings_url`) в адрес окна;
экран принимает его, только если чистка ничего не отрезала (`_safe_preview_page(raw) == raw`),
длина ≤ `VON_MAX` и код страницы пути — код открытой схемы (объект своего типа — §9 №1).
Сверка — один раз на запрос, в вызывающем; POST сверяет заново (подделка отбрасывается).

Красные (strict xfail до кода): ⚙ несёт `von`, один `code_for_path` на запрос; точная сверка
кода; кадр «Vorschau» по `von`; `von` переживает действия окна; число запросов. Охранные:
отказы чистки, подделка в POST, без `von` вывод байт-в-байт, ссылка простая.
"""

import copy
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.signals import template_rendered
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.core import site_schema, window_links
from apps.core.tests import test_fb33_e3_wie_nojs as e3
from apps.core.tests import test_fb33_m3_3_nojs as m33
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CFG
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

RED = pytest.mark.xfail(strict=True, reason="E1: von до кода не принимается")
OPEN = "/dashboard/site/aufbau/oeffnen/"
#: запас запросов окна со `von` сверх окна без него (замер E1: 27 и 27 — 0; один — на
#: объект со своими блоками, `site_schema._own_code`)
VON_EXTRA_QUERIES = 1


def _shop():
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant()
    tenant.site_config = copy.deepcopy(CFG)
    tenant.save()
    urls = {ProductFactory().get_absolute_url() for _i in range(2)}
    # образец типа — первый по pk (uuid): «первый» — тот, что выбрал экран, второй — другой
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    first = next(r for r in rows if r.code == "product").preview_url
    (second,) = urls - {first}
    return tenant, first, second


def _ctx(b, query):
    seen = []

    def grab(sender, template, context, **kw):
        if getattr(template, "name", "") == "tenant/site_schema.html":
            seen.append(context)

    template_rendered.connect(grab)
    try:
        with translation.override("de"):
            html = b.get(query)
    finally:
        template_rendered.disconnect(grab)
    return html, seen[-1]


def _q(url) -> dict:
    return parse_qs(urlsplit(url).query)


def _studio_page(ctx) -> str:
    return (_q(ctx["studio_url"]).get("page") or [""])[0]


def _req(tenant):
    req = RequestFactory().get(OPEN)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _spy(monkeypatch):
    calls = []
    real = site_schema.code_for_path

    def spy(tenant, path):
        calls.append(path)
        return real(tenant, path)

    monkeypatch.setattr(site_schema, "code_for_path", spy)
    return calls


# ───────────── красные ─────────────


@RED
def test_studio_gear_passes_path_once(monkeypatch):
    """№3: ⚙ с объекта — адрес окна несёт путь объекта; `code_for_path` — раз на запрос."""
    tenant, first, second = _shop()
    calls = _spy(monkeypatch)
    url = window_links.studio_settings_url(_req(tenant), second, "related")
    assert len(calls) == 1
    assert _q(url)["von"] == [second] and _q(url)["seite"] == ["product"]
    calls.clear()
    _html, ctx = _ctx(Browser(tenant), "?" + urlsplit(url).query)
    assert len(calls) == 1
    assert _studio_page(ctx) == second and ctx["preview_url"] == second != first
    assert _q(ctx["bw_preview"]["src"]) and ctx["bw_preview"]["src"].startswith(second + "?")


@pytest.mark.parametrize(
    "found,ok",
    [
        pytest.param("text@seite:x", True, marks=RED),
        ("text@seite:x-2", False),  # соседний ключ — не префиксом
        ("text@seite:", False),
        ("text", False),
    ],
)
def test_von_must_match_code_exactly(monkeypatch, found, ok):
    """№5: соседние свои страницы `seite:x` и `seite:x-2` — только точный код. Код пути
    подставлен: `code_for_path` у своей страницы сегодня даёт «text» (хост `info` канвы)."""
    from apps.core import content_pages
    from apps.core.models import ContentPage

    tenant = _tenant()
    ContentPage.objects.create(slug="x", title="X", body="<p>x</p>", is_published=True)
    ContentPage.objects.create(slug="x-2", title="X2", body="<p>x</p>", is_published=True)
    monkeypatch.setattr(site_schema, "code_for_path", lambda t, p: found)
    mine = content_pages.content_url("x")
    _html, ctx = _ctx(Browser(tenant), f"?seite=text%40seite%3Ax&von={mine}")
    assert ("von=" in ctx["keep_q"]) is ok
    assert _studio_page(ctx) == mine  # образец своей страницы — она сама


@pytest.mark.parametrize(
    "found,ok",
    [
        # §9 №1: объект своего типа со своими блоками; принятые — красные до кода
        pytest.param("product@product:abc", True, marks=RED),
        pytest.param("product", True, marks=RED),
        ("catalog", False),
        ("tour@tour:abc", False),  # объект чужого типа
        ("", False),
    ],
)
def test_object_code_of_the_type_is_accepted(monkeypatch, found, ok):
    """§9 №1: общая схема типа со страницы объекта со своими блоками (`<тип>@…`)."""
    tenant, _first, second = _shop()
    monkeypatch.setattr(site_schema, "code_for_path", lambda t, p: found)
    _html, ctx = _ctx(Browser(tenant), f"?seite=product&block=related&von={second}")
    assert (_studio_page(ctx) == second) is ok
    assert ("von=" in ctx["keep_q"]) is ok


@RED
def test_preview_frame_uses_von():
    tenant, first, second = _shop()
    _html, ctx = _ctx(Browser(tenant), f"?seite=product&block=related&von={second}")
    assert ctx["bw_preview"]["src"].startswith(second + "?")
    assert first not in ctx["bw_preview"]["src"]


@RED
@pytest.mark.parametrize("action", ["update", "zu_tab", "revert", "window_done"])
def test_von_survives_post(action):
    """`von` — скрытым полем форм окна; POST сверяет и кладёт в адрес возврата. «Wie» — форма
    вида E3 (`bw-form-listview`), кнопка вкладки применяет её."""
    b = Browser(e3._shop(m33.CFG))
    panel = e3._get(b, e3.LIST_QUERY + "&von=/")
    assert '<input type="hidden" name="von" value="/">' in panel
    if action == "zu_tab":
        data = e3._tab_post(panel, zu_tab="was")
    elif action == "update":
        data = e3._tab_post(panel, op="update")
    else:
        data = e3._tab_post(panel, op=action)
    resp, _msgs = b.post(**data)
    assert _q(resp["Location"]).get("von") == ["/"]


@RED
def test_von_queries():
    """№31: `von` стоит не больше `VON_EXTRA_QUERIES` запросов сверх окна без него."""
    tenant, _first, second = _shop()
    b = Browser(tenant)
    b.get("?seite=product&block=related")  # прогрев сессии и кэшей
    with CaptureQueriesContext(connection) as plain:
        b.get("?seite=product&block=related")
    with CaptureQueriesContext(connection) as with_von:
        _html, ctx = _ctx(b, f"?seite=product&block=related&von={second}")
    assert _studio_page(ctx) == second
    assert len(with_von) - len(plain) <= VON_EXTRA_QUERIES


# ───────────── охранные ─────────────


@pytest.mark.parametrize(
    "seite,raw",
    [
        ("product", "//evil.example"),
        ("product", "https://x"),
        ("product", "javascript:x"),
        ("product", "/dashboard/"),
        ("product", "/\\evil"),
        ("product", "/" + "a" * 300),
        ("product", "/x&seite=event"),
        ("home", "//evil"),
        ("product", "/p/?gruppe=a"),  # код не совпал — не проходит
    ],
)
def test_von_rejected(seite, raw):
    """№6 / M1: 200, прежний образец; `von` нет ни в адресах, ни в формах."""
    tenant, first, _second = _shop()
    b = Browser(tenant)
    _html0, base = _ctx(b, f"?seite={seite}")
    req_html, ctx = _ctx(b, f"?seite={seite}&" + _enc({"von": raw}))
    assert ctx["studio_url"] == base["studio_url"]
    assert ctx["preview_url"] == base["preview_url"]
    assert 'name="von"' not in req_html and "von=" not in req_html


def _enc(d):
    from django.utils.http import urlencode

    return urlencode(d)


def test_von_post_forged_dropped(settings):
    """M2: подделанный `von` в POST (чужой объект, чужой код) — не в адресе возврата."""
    from apps.core import content_pages
    from apps.core.models import ContentPage

    settings.ROOT_URLCONF = "config.urls_tenant"

    ContentPage.objects.create(slug="x-2", title="X2", body="<p>x</p>", is_published=True)
    b = Browser(e3._shop(m33.CFG))
    panel = e3._get(b, e3.LIST_QUERY)
    for forged in ("//evil.example", content_pages.content_url("x-2"), "/x&seite=event"):
        data = e3._tab_post(panel, op="window_done", von=forged)
        resp, _msgs = b.post(**data)
        assert "von" not in _q(resp["Location"]), forged


def test_no_von_bytes_unchanged():
    """№11: без `von` вывод экрана байт-в-байт такой же, как с отвергнутым `von`, и без
    единого упоминания `von` (эталоны окна держат прежний вывод целиком)."""
    tenant, _first, _second = _shop()
    b = Browser(tenant)
    with translation.override("de"):
        html = b.get("?seite=product&block=related&wopen=fixedTok")
    assert 'name="von"' not in html and "von=" not in html
    strip = re.compile(r'name="(csrfmiddlewaretoken|wopen)" value="[^"]*"|wopen=[A-Za-z0-9_-]+')
    with translation.override("de"):
        again = b.get("?seite=product&block=related&wopen=fixedTok&von=//evil")
    assert strip.sub("", again) == strip.sub("", html)


def test_auf_der_seite_link_plain():
    """№19 / a11y M6: ссылка «Auf der Seite bearbeiten» — простая `<a href>` с видимым
    текстом, без `target`."""
    tenant, _first, second = _shop()
    with translation.override("de"):
        html = Browser(tenant).get(f"?seite=product&block=related&von={second}")
    links = re.findall(r"<a [^>]*>Auf der Seite bearbeiten</a>", html)
    assert links and all("target=" not in a and "aria-label" not in a for a in links)
