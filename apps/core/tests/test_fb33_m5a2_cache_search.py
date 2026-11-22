"""FB-33 M5a-2: короткий кэш HTML страницы 404 витрины и `noindex,follow` листингов при `?q=`.

План — `docs/fb33-stack9-plan-2026-11-22.md` §1.C, строки «C» §2, решения владельца §4 п. 4–7
(переключатель языка и баннер демо на 404 ведут на главную; хост в ключе; `noindex` и у
категории, и у «Nur Aktionen» — только мета-тегом; демо кэшируются наравне) и находки
`seo-specialist` по плану (пагинация — `?cursor=` и `?seite=`, на поиске нет canonical).

В тестах TTL кэша 0 и хост `testserver` — замки сами включают TTL и берут хост `<uuid>.test`:
ключи в общем Redis не пересекаются между тестами и прогонами.
"""

import inspect
import logging
import re
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connections
from django.http import Http404
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import translation

from apps.core import pagecache
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

rf = RequestFactory()
#: маршруты листингов витрины, читающие `?q=` (решение владельца §4 п. 6 — с категорией и акциями)
LISTING_ROUTES = (
    "storefront-products",
    "storefront-category",
    "storefront-aktionen",
    "storefront-termin",
    "storefront-unterkunft",
    "storefront-events",
)
ROBOTS = re.compile(r'<meta name="robots"')


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def cached(settings):
    """Кэш включён (в тестах TTL 0 — как на проде 120)."""
    settings.PUBLIC_PAGE_CACHE_TTL = 60
    return settings


def _views():
    from apps.core import not_found_views

    return not_found_views


def _tenant(**kw):
    kw.setdefault("business_type", "bakery")
    kw.setdefault("enabled_locales", ["de", "en"])
    return TenantFactory(disabled_modules=[], **kw)


def _host():
    return f"{uuid.uuid4().hex}.test"


def _req(tenant, path="/gibt-es-nicht/", *, host=None, method="get", lang="de", data=None, **extra):
    req = getattr(rf, method)(path, data or {}, HTTP_HOST=host or _host(), **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    req.user = AnonymousUser()
    req.portal = None
    req.tenant = tenant
    req.LANGUAGE_CODE = lang
    return req


def _nf(req):
    with translation.override(req.LANGUAGE_CODE):
        return _views().storefront_404(req, Http404())


@pytest.fixture
def renders(monkeypatch):
    """Счётчик рендеров страницы с блоками: замок «второй адрес не рендерит» может упасть."""
    views = _views()
    calls = []
    real = views.render

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(views, "render", counting)
    return calls


# ── (а) кэш 404: один ключ через pagecache ─────────────────────────────────────────────


def test_404_cache_ttl_is_short(settings):
    assert pagecache.NOT_FOUND_CACHE_TTL == 60
    settings.PUBLIC_PAGE_CACHE_TTL = 120
    assert pagecache.not_found_ttl() == 60
    settings.PUBLIC_PAGE_CACHE_TTL = 30
    assert pagecache.not_found_ttl() == 30
    settings.PUBLIC_PAGE_CACHE_TTL = 0
    assert pagecache.not_found_ttl() == 0  # 0 выключает и кэш 404


def test_404_cache_goes_through_pagecache_key(cached, renders):
    """Одна точка: запись лежит под ключом `pagecache._nf_key` (без пути), второго кэша нет."""
    from django.core.cache import cache

    tenant, host = _tenant(), _host()
    req = _req(tenant, "/a-m5a2/", host=host)
    resp = _nf(req)
    key = pagecache._nf_key(tenant.schema_name, "de", host)
    assert "/a-m5a2/" not in key and key.startswith(f"sf404:{host}:{tenant.schema_name}:de:v")
    assert cache.get(key) == pagecache._pack(resp)
    src = inspect.getsource(_views())
    assert "cache.set(" not in src and "cache.get(" not in src  # только журнал (cache.add)
    assert "pagecache.cached_not_found(" in src


def test_second_broken_address_renders_nothing(cached, renders):
    tenant, host = _tenant(), _host()
    first = _nf(_req(tenant, "/eins-m5a2/", host=host))
    assert len(renders) == 1
    req = _req(tenant, "/zwei-m5a2/", host=host)
    with CaptureQueriesContext(connections["default"]) as ctx:
        second = _nf(req)
    assert len(renders) == 1, "второй битый адрес снова отрендерил страницу"
    assert len(ctx.captured_queries) == 0, [q["sql"] for q in ctx.captured_queries]
    assert second.content == first.content


def test_different_paths_share_one_entry(cached, renders):
    tenant, host = _tenant(), _host()
    for path in ("/x1-m5a2/", "/x2-m5a2/", "/x3/y/z-m5a2/"):
        _nf(_req(tenant, path, host=host))
    assert len(renders) == 1


def test_cached_404_hit_returns_404_status(cached, renders):
    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))
    hit = _nf(_req(tenant, "/andere-m5a2/", host=host))
    assert len(renders) == 1 and hit.status_code == 404


def test_hit_keeps_404_noindex_vary(cached, renders):
    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))
    hit = _nf(_req(tenant, "/b-m5a2/", host=host))
    assert len(renders) == 1
    assert hit.status_code == 404 and hit["X-Robots-Tag"] == "noindex"
    assert "Cookie" in hit["Vary"] and not hit.cookies
    assert "Cache-Control" not in hit


def test_hit_keeps_vary_from_view(cached, monkeypatch):
    """Vary хита = Vary промаха: упаковка — прежние `_pack`/`_unpack`, второго упаковщика нет."""
    views = _views()
    real = views._page

    def with_vary(request, status, is_preview=False):
        resp = real(request, status, is_preview)
        resp["Vary"] = "Accept-Language"
        return resp

    monkeypatch.setattr(views, "_page", with_vary)
    tenant, host = _tenant(), _host()
    miss = _nf(_req(tenant, host=host))
    hit = _nf(_req(tenant, "/c-m5a2/", host=host))
    assert "Accept-Language" in miss["Vary"] and "Accept-Language" in hit["Vary"]
    assert "Cookie" in hit["Vary"]


def test_hosts_and_languages_are_separate_entries(cached, renders):
    """Решение владельца §4 п. 5: домены одного бизнеса — разные записи; язык — тоже."""
    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))
    _nf(_req(tenant, host=_host()))
    _nf(_req(tenant, host=host, lang="en"))
    assert len(renders) == 3


def test_demo_is_cached_like_everyone(cached, renders):
    """Решение владельца §4 п. 7."""
    tenant, host = _tenant(is_demo=True), _host()
    _nf(_req(tenant, host=host))
    _nf(_req(tenant, "/d-m5a2/", host=host))
    assert len(renders) == 1


@pytest.mark.parametrize(
    "case", ["lang_cookie", "any_cookie", "session_cookie_no_session", "session", "query", "post"]
)
def test_cookie_or_session_bypasses_404_cache(cached, renders, case):
    from django.core.cache import cache

    tenant, host = _tenant(), _host()

    def make():
        if case == "lang_cookie":
            req = _req(tenant, host=host)
            req.COOKIES["django_language"] = "de"
        elif case == "any_cookie":
            req = _req(tenant, host=host)
            req.COOKIES["sf_consent"] = "1"
        elif case == "session_cookie_no_session":
            # ревью безопасности L2: 404 до SessionMiddleware — сессии нет, cookie есть
            req = _req(tenant, host=host)
            del req.session
            req.COOKIES["sessionid"] = "abc"
        elif case == "session":
            req = _req(tenant, host=host)
            req.session["cart"] = {"x": 1}
        elif case == "query":
            req = _req(tenant, host=host, data={"x": "1"})
        else:
            req = _req(tenant, host=host, method="post")
        return req

    for _ in range(2):
        _nf(make())
    expected = 0 if case == "post" else 2  # POST — простая страница без блоков
    assert len(renders) == expected
    assert cache.get(pagecache._nf_key(tenant.schema_name, "de", host)) is None


def test_head_miss_does_not_write_404_cache(cached, renders):
    """Ревью безопасности L1: HEAD читает запись, но не пишет её (пишет только GET)."""
    from django.core.cache import cache

    tenant, host = _tenant(), _host()
    key = pagecache._nf_key(tenant.schema_name, "de", host)
    _nf(_req(tenant, host=host, method="head"))
    assert cache.get(key) is None and len(renders) == 1
    _nf(_req(tenant, host=host))  # GET пишет
    head = _nf(_req(tenant, "/h-m5a2/", host=host, method="head"))
    assert len(renders) == 2 and head.status_code == 404


def test_preview_never_touches_404_cache(cached, monkeypatch):
    """Ревью безопасности M1: превью (200 через тот же `_page`) — вне кэша."""
    from django.core.cache import cache

    from apps.core import page_settings

    monkeypatch.setattr(page_settings, "_may_preview", lambda r: True)
    tenant, host = _tenant(), _host()
    req = _req(tenant, "/seite-nicht-gefunden/vorschau/", host=host)
    with translation.override("de"):
        resp = _views().not_found_preview(req)
    assert resp.status_code == 200
    assert cache.get(pagecache._nf_key(tenant.schema_name, "de", host)) is None


def test_sf404_rejects_200_and_page_cache_rejects_404(cached):
    """Ревью безопасности M1: код ответа — строгое равенство в обе стороны."""
    tenant = _tenant()
    req = _req(tenant)
    resp = _nf(req)
    assert resp.status_code == 404
    assert pagecache._cacheable(req, resp, status=404) is True
    assert pagecache._cacheable(req, resp) is False
    resp.status_code = 200
    assert pagecache._cacheable(req, resp, status=404) is False


def test_unknown_host_and_port_variants_make_no_404_entries(cached, renders):
    """Порт и регистр хоста — одна запись (ключ — `_cache_host`, не сырой `get_host()`)."""
    tenant, base = _tenant(), uuid.uuid4().hex
    for host in (f"{base}.test", f"{base.upper()}.TEST", f"{base}.test:1", f"{base}.test:31337"):
        _nf(_req(tenant, host=host))
    assert len(renders) == 1


def test_ttl_zero_disables_the_404_cache(settings, renders):
    settings.PUBLIC_PAGE_CACHE_TTL = 0
    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))
    _nf(_req(tenant, host=host))
    assert len(renders) == 2


def test_publication_resets_404_cache(cached, renders):
    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))
    pagecache.bump_storefront_cache(tenant.schema_name)
    _nf(_req(tenant, host=host))
    assert len(renders) == 2


def test_closed_or_media_never_served_from_cache(cached, renders):
    """Простая 404 (файлы, закрытая витрина) идёт мимо кэша и не читает запись витрины."""
    from django.core.cache import cache

    tenant, host = _tenant(), _host()
    _nf(_req(tenant, host=host))  # запись витрины есть
    key = pagecache._nf_key(tenant.schema_name, "de", host)
    assert cache.get(key) is not None
    media = _nf(_req(tenant, "/media/x-m5a2.png", host=host))
    assert b"data-not-found" not in media.content
    closed = _tenant(email_pending=True)
    cache.set(pagecache._nf_key(closed.schema_name, "de", host), cache.get(key), 60)
    resp = _nf(_req(closed, host=host))
    assert b"data-not-found" not in resp.content
    assert len(renders) == 1


def test_404_cache_failure_serves_page_and_warns(cached, renders, monkeypatch, caplog):
    from django.core.cache import cache

    def boom(*a, **kw):
        raise ConnectionError("redis down")

    tenant = _tenant()
    monkeypatch.setattr(pagecache, "_nf_warned_at", {})
    monkeypatch.setattr(cache, "get", boom)
    monkeypatch.setattr(cache, "set", boom)
    with caplog.at_level(logging.WARNING):
        first = _nf(_req(tenant))
        second = _nf(_req(tenant))
    assert first.status_code == second.status_code == 404
    # страница с блоками, не простая запасная (ревью безопасности L5)
    assert b"data-not-found" in first.content and b"data-not-found" in second.content
    assert len(renders) == 2
    warns = [r for r in caplog.records if r.name == "apps.core.pagecache"]
    # окна раздельные: чтение и запись — по одной записи за окно, со стеком (ревью LOW 6)
    assert [w.levelno for w in warns] == [logging.WARNING, logging.WARNING]
    assert all(w.exc_info for w in warns)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.parametrize("broken", ["_pack", "_cache_host", "_cacheable"])
def test_cache_layer_failure_serves_page_and_warns(cached, renders, monkeypatch, caplog, broken):
    """Ревью безопасности M1 (дифф): сбой кэшевого слоя до или после готового рендера не
    уводит во внешний except обработчика (ERROR «block-page» и простая 404) — страница с
    блоками и WARNING от pagecache."""

    def boom(*a, **kw):
        raise RuntimeError("cache layer")

    monkeypatch.setattr(pagecache, "_nf_warned_at", {})
    monkeypatch.setattr(pagecache, broken, boom)
    with caplog.at_level(logging.WARNING):
        resp = _nf(_req(_tenant()))
    assert resp.status_code == 404 and b"data-not-found" in resp.content
    assert len(renders) == 1
    assert [r.levelno for r in caplog.records if r.name == "apps.core.pagecache"] == [
        logging.WARNING
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_404_cache_key_language_is_the_active_one(cached, renders):
    """Ревью LOW 6: язык ключа — активный язык рендера (`translation.get_language()`), а не
    атрибут запроса: при расхождении запись не уносит тело одного языка под ключ другого."""
    from django.core.cache import cache

    tenant, host = _tenant(), _host()
    req = _req(tenant, host=host, lang="de")
    with translation.override("en"):
        _views().storefront_404(req, Http404())
    assert cache.get(pagecache._nf_key(tenant.schema_name, "en", host)) is not None
    assert cache.get(pagecache._nf_key(tenant.schema_name, "de", host)) is None


def test_legacy_410_does_not_leak_into_cache(cached):
    """Ревью безопасности M2: запись, созданная запросом по 410-пути, хранит и отдаёт 404."""
    from apps.core import legacy_redirects
    from apps.core.middleware import LegacyRedirectMiddleware
    from apps.core.models import LegacyRedirect

    tenant, host = _tenant(), _host()
    legacy_redirects.upsert("/weg-m5a2/", status=LegacyRedirect.STATUS_GONE)

    def call(path):
        return LegacyRedirectMiddleware(lambda r: _nf(r))(_req(tenant, path, host=host))

    assert call("/weg-m5a2/").status_code == 410
    assert call("/sonst-m5a2/").status_code == 404


def test_legacy_redirect_survives_cached_404(cached):
    """Правило переезда, созданное ПОСЛЕ закэшированной 404, срабатывает: кэш — внутри
    обработчика, middleware смотрит на код ответа."""
    from apps.core import legacy_redirects
    from apps.core.middleware import LegacyRedirectMiddleware

    tenant, host = _tenant(), _host()

    def call(path):
        req = _req(tenant, path, host=host)
        return LegacyRedirectMiddleware(lambda r: _nf(r))(req)

    assert call("/alt-m5a2/").status_code == 404
    legacy_redirects.upsert("/alt2-m5a2/", "/sortiment/")
    resp = call("/alt2-m5a2/")
    assert resp.status_code == 301 and resp["Location"] == "/sortiment/"


# ── тело 404 не зависит от пути ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("demo", [False, True])
def test_404_body_has_no_path(monkeypatch, lang, demo):
    """Решение владельца §4 п. 4: переключатель языка и баннер демо на 404 ведут на главную."""
    from apps.core import demo_switch

    if demo:
        monkeypatch.setattr(demo_switch, "is_demo_tenant", lambda t: True)
    tenant = _tenant(is_demo=demo)
    marker = "pfad-m5a2-zzq"
    resp = _nf(_req(tenant, f"/{marker}/", lang=lang))
    html = resp.content.decode()
    assert "data-not-found" in html
    assert "storefront-set-language" not in html  # имя маршрута не утекает
    assert marker not in html
    lang_url = reverse("storefront-set-language")
    assert f"{lang_url}?lang=en&amp;next=/" in html or f"{lang_url}?lang=en&next=/" in html
    if demo:
        assert "data-demo-design" in html and "&next=/" in html.replace("&amp;", "&")


def test_section_404_has_no_archetype_cover():
    """Дефект §5.6: `Http404` из вьюхи раздела показывал обложку раздела над страницей 404."""
    tenant = _tenant()
    tenant.site_config = {"archetypes": {"catalog": {"intro": "Obloshka-M5A2"}}}
    tenant.save(update_fields=["site_config"])
    req = _req(tenant, "/sortiment/gibt-es-nicht-m5a2/")
    req.resolver_match = SimpleNamespace(url_name="storefront-products", kwargs={}, args=())
    html = _nf(req).content.decode()
    assert "data-not-found" in html and "Obloshka-M5A2" not in html


#: типы бизнеса для замка независимости тела 404 от маршрута (ревью django M2 по диффу)
ROUTE_TYPES = ("bakery", "hotel", "friseur", "restaurant", "online_shop")
#: значение-заглушка для конвертеров пути при сборке адреса маршрута
_DUMMY = {"slug": "x-m5a2", "str": "x-m5a2", "path": "x/m5a2", "int": 1, "uuid": uuid.UUID(int=7)}


def _storefront_paths():
    """Адрес каждого маршрута `storefront-*` витрины (заглушки вместо параметров)."""
    from django.urls import URLPattern, URLResolver, get_resolver

    def walk(patterns, ns=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, ns)
            elif isinstance(p, URLPattern) and (p.name or "").startswith("storefront-"):
                yield p

    seen = {}
    for p in walk(get_resolver("config.urls_tenant").url_patterns):
        conv = getattr(p.pattern, "converters", {}) or {}
        kwargs = {}
        for name, c in conv.items():
            kind = type(c).__name__.replace("Converter", "").lower()
            kwargs[name] = _DUMMY.get(kind, "x-m5a2")
        try:
            seen.setdefault(p.name, reverse(p.name, kwargs=kwargs))
        except Exception:  # noqa: BLE001 — маршрут с особым конвертером: пропуск
            continue
    return seen


def test_storefront_route_sweep_covers_the_listings():
    """Сам обход не пуст: среди адресов — листинги и детальные."""
    names = set(_storefront_paths())
    assert len(names) > 40
    assert {"storefront-products", "storefront-category", "storefront-termin"} <= names


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("btype", ROUTE_TYPES)
def test_404_body_is_route_independent(lang, btype):
    """Ревью безопасности H1 и django M2: процессоры по `resolver_match` (`seo` → `seo_meta`,
    обложка раздела, флаг поиска, тип страницы Студии) не делают тело записи зависимым от
    адреса: неразрешённый путь и `Http404` из КАЖДОГО маршрута `storefront-*` — байт-в-байт
    одно тело, у пяти типов бизнеса."""
    tenant = _tenant(business_type=btype)
    plain = _nf(_req(tenant, lang=lang)).content
    differ = []
    for name, path in _storefront_paths().items():
        req = _req(tenant, path, lang=lang)
        req.resolver_match = resolve(path)
        if _nf(req).content != plain:
            differ.append(name)
    req = _req(tenant, "/entdecken-m5a2/", lang=lang)  # процессоры портала по пути
    if _nf(req).content != plain:
        differ.append("/entdecken")
    assert not differ, differ


def test_other_pages_keep_their_language_links():
    """Запасное значение шаблонов — прежнее: у листинга `next=` — сам адрес с query."""
    tenant = _tenant()
    _resp, html = _listing(tenant, "storefront-products", {"sort": "name"})
    assert "next=/sortiment/%3Fsort%3Dname" in html


# ── (б) noindex листингов при ?q= ───────────────────────────────────────────────────────


def _listing(tenant, route, params=None, **kw):
    path = reverse(route, kwargs=kw) if kw else reverse(route)
    req = _req(tenant, path, data=params)
    MessageMiddleware(lambda r: None).process_request(req)
    match = resolve(path)
    req.resolver_match = match
    resp = match.func(req, *match.args, **match.kwargs)
    if hasattr(resp, "render"):
        resp = resp.render()
    assert resp.status_code == 200, (route, resp.status_code)
    return resp, resp.content.decode()


def _listing_html(tenant, route, params=None):
    kw = {}
    if route == "storefront-category":
        from apps.catalog.tests.factories import CategoryFactory

        kw = {"slug": CategoryFactory(slug=f"kat{uuid.uuid4().hex[:6]}", name={"de": "K"}).slug}
    return _listing(tenant, route, params, **kw)


def test_noindex_routes_derive_from_search_registry():
    from apps.core import context

    assert context.SEARCH_NOINDEX_ROUTES == frozenset(context._SEARCH_ROUTES.values()) | {
        "storefront-aktionen",
        "storefront-category",
    }
    assert context.SEARCH_NOINDEX_ROUTES == frozenset(LISTING_ROUTES)
    for name in context.SEARCH_NOINDEX_ROUTES:
        path = (
            reverse(name, kwargs={"slug": "x"}) if name == "storefront-category" else reverse(name)
        )
        func = inspect.unwrap(resolve(path).func)
        assert 'request.GET.get("q")' in inspect.getsource(func), name


@pytest.mark.parametrize("route", LISTING_ROUTES)
def test_search_query_marks_listing_noindex(route):
    _resp, html = _listing_html(_tenant(), route, {"q": "brot"})
    assert len(ROBOTS.findall(html)) == 1
    assert '<meta name="robots" content="noindex,follow">' in html


@pytest.mark.parametrize("route", ["storefront-products", "storefront-category"])
@pytest.mark.parametrize(
    "params",
    [{}, {"q": " "}, {"q": " \t "}, {"cursor": "abc"}, {"seite": "2"}, {"sort": "name"}],
    ids=["plain", "space", "whitespace", "cursor", "seite", "sort"],
)
def test_listing_without_q_unchanged(route, params):
    """Пустой после strip `q`, пагинация и сорт — страница в индексе и с canonical."""
    _resp, html = _listing_html(_tenant(), route, params)
    assert not ROBOTS.findall(html)
    assert 'rel="canonical"' in html


def test_literal_percent_twenty_query_is_a_search():
    """`?q=%2520` (текст «%20», не пробел) — непустой запрос: выдача вне индекса."""
    _resp, html = _listing_html(_tenant(), "storefront-products", {"q": "%20"})
    assert '<meta name="robots" content="noindex,follow">' in html


def test_aktionen_page_without_q_unchanged():
    _resp, html = _listing_html(_tenant(), "storefront-aktionen", {"seite": "2"})
    assert not ROBOTS.findall(html) and 'rel="canonical"' in html


@pytest.mark.parametrize(
    "route,params",
    [
        ("storefront-products", {"q": "x", "cursor": "abc"}),
        ("storefront-aktionen", {"q": "x", "seite": "2"}),
    ],
)
def test_search_query_with_pagination_is_noindex(route, params):
    _resp, html = _listing_html(_tenant(), route, params)
    assert '<meta name="robots" content="noindex,follow">' in html


@pytest.mark.parametrize("route", LISTING_ROUTES)
def test_demo_with_q_has_one_robots_tag(route):
    _resp, html = _listing_html(_tenant(is_demo=True), route, {"q": "x"})
    assert len(ROBOTS.findall(html)) == 1


def test_search_query_has_noindex_and_no_canonical():
    """Находка seo-specialist M-2: noindex + canonical на чистый листинг — смешанный сигнал."""
    tenant = _tenant()
    _r, searched = _listing_html(tenant, "storefront-products", {"q": "brot"})
    _r, plain = _listing_html(tenant, "storefront-products")
    assert 'rel="canonical"' not in searched
    assert 'rel="canonical"' in plain and "?" not in re.search(
        r'<link rel="canonical" href="([^"]+)"', plain
    ).group(1)


def test_search_noindex_has_no_x_robots_header():
    resp, _html = _listing_html(_tenant(), "storefront-products", {"q": "brot"})
    assert "X-Robots-Tag" not in resp


@pytest.mark.parametrize("demo", [False, True])
def test_404_has_single_robots_tag(demo):
    """На 404 флаг поиска ложный (даже если `Http404` бросил листинг с `?q=`) — один тег
    (находки seo-specialist L-3 и security-reviewer L4)."""
    tenant = _tenant(is_demo=demo)
    req = _req(tenant, "/sortiment/gibt-es-nicht-m5a2/", data={"q": "x"})
    req.resolver_match = resolve("/sortiment/gibt-es-nicht-m5a2/")
    html = _nf(req).content.decode()
    assert "data-not-found" in html and len(ROBOTS.findall(html)) == 1


def test_robots_txt_has_no_search_disallow():
    """robots.txt не трогаем: `Disallow` прятал бы от робота сам `noindex`."""
    from django.template.loader import get_template

    try:
        tpl = get_template("robots.txt")
    except Exception:  # noqa: BLE001 — robots.txt собирается вьюхой
        tpl = None
    from apps.core import context

    src = (tpl.template.source if tpl else "") + inspect.getsource(context)
    assert "Disallow: /*?q=" not in src and "Disallow: /sortiment/?q" not in src


# ── полный стек middleware (ревью django M1 по диффу) ───────────────────────────────────


@pytest.fixture
def page_calls(monkeypatch):
    views = _views()
    calls = []
    real = views._page

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(views, "_page", counting)
    return calls


def test_full_stack_two_broken_addresses_render_once(cached, page_calls):
    """`django.test.Client` на хосте тенанта: настоящий стек middleware (сессия, язык, CSRF,
    переезд адресов). Два анонимных GET на разные битые пути и `Http404` из вьюхи категории —
    404, без Set-Cookie, один рендер, одно тело, одинаковые `Vary` и `Content-Language`."""
    from django.test import Client

    from apps.tenants.tests.factories import DomainFactory

    # слаг — свой на прогон: хост входит в ключ, а Redis переживает прогон
    tenant = _tenant(slug=f"m5a2-{uuid.uuid4().hex[:10]}")
    domain = DomainFactory(tenant=tenant, domain=f"{tenant.slug}.siteadaptor.de")
    client = Client(HTTP_HOST=domain.domain)
    paths = ("/eins-m5a2-stack/", "/zwei/m5a2-stack/", "/sortiment/keine-kategorie-m5a2/")
    try:
        responses = [client.get(path, secure=True) for path in paths]
    finally:
        # TenantMainMiddleware оставляет соединение на схеме тенанта — следующий тест
        # создавал бы тенанта «вне public»
        connections["default"].set_schema_to_public()
    for resp in responses:
        assert resp.status_code == 404 and b"data-not-found" in resp.content
        assert not resp.cookies, list(resp.cookies)
        assert resp["X-Robots-Tag"] == "noindex"
    assert len(page_calls) == 1, "второй и третий адрес снова отрендерили страницу"
    first = responses[0]

    def vary(resp):
        # порядок токенов на хите другой (Cookie ставит `_unpack` раньше LocaleMiddleware) —
        # для кэшей значим набор, не порядок
        return {v.strip() for v in resp["Vary"].split(",")}

    assert vary(first) == {"Accept-Language", "Cookie"}
    for resp in responses[1:]:
        assert resp.content == first.content
        assert vary(resp) == vary(first)
        assert resp["Content-Language"] == first["Content-Language"]


#: публичные маршруты, читающие `?q=`, которые осознанно НЕ вне индекса при поиске: имя → причина
SEARCH_NOINDEX_EXEMPT: dict[str, str] = {}


def test_every_public_view_reading_q_is_noindexed():
    """Ревью seo 1 по диффу (обратный замок): каждая публичная вьюха витрины, чей исходник
    читает `?q=`, — в `SEARCH_NOINDEX_ROUTES` (или в `SEARCH_NOINDEX_EXEMPT` с причиной).
    Кабинет (`CABINET_PREFIXES`) вне индекса и так — не считается."""
    from django.urls import URLPattern, URLResolver, get_resolver

    from apps.core import context
    from apps.core.i18n_cabinet import CABINET_PREFIXES

    reads_q = re.compile(r"GET(\.get\(|\[)\s*['\"]q['\"]")

    def walk(patterns, prefix="/"):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield prefix + str(p.pattern), p

    found = set()
    for route, p in walk(get_resolver("config.urls_tenant").url_patterns):
        if route.startswith(CABINET_PREFIXES) or not p.name:
            continue
        try:
            src = inspect.getsource(inspect.unwrap(p.callback))
        except (TypeError, OSError):
            continue
        if reads_q.search(src):
            found.add(p.name)
    assert found, "обход не нашёл ни одной вьюхи с ?q= — сломан сам замок"
    missing = found - context.SEARCH_NOINDEX_ROUTES - set(SEARCH_NOINDEX_EXEMPT)
    assert not missing, f"читают ?q=, но не вне индекса при поиске: {sorted(missing)}"


def test_seitenaufbau_publication_resets_404_cache(
    cached, renders, django_capture_on_commit_callbacks
):
    """Ревью django 3 по диффу: настоящий путь публикации блоков хоста `not_found` (черновик
    «Seitenaufbau» → «Speichern») сбрасывает запись 404: прогрев → публикация → битый адрес
    показывает новое."""
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.models import Tenant

    b = Browser(_tenant())
    host = _host()

    def page():
        return _nf(_req(Tenant.objects.get(pk=b.tenant.pk), "/alt-m5a2/", host=host)).content

    assert b"data-block-site-search" in page()
    assert b"data-block-site-search" in page() and len(renders) == 1  # из кэша
    with django_capture_on_commit_callbacks(execute=True):
        b.post(seite="not_found", op="toggle", ref="nf-search")
        b.post(seite="not_found", op="save")
    assert b"data-block-site-search" not in page()
    assert len(renders) == 2
