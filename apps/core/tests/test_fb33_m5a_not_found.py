"""FB-33 M5a: страница 404 витрины с блоками — хост `not_found`, блоки по умолчанию «Suche» и
«Beliebt» (плитки верхнего уровня меню), тип страницы в «Seitenaufbau», превью команде.

План — `docs/fb33-stack8-plan-2026-11-22.md` §1 A, §2 и §4 (поправки ревью R1–R8). Запасной
путь — прежняя standalone-страница `templates/404.html` (платформа, портал, кабинет, сбой)."""

import logging
import re
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connections
from django.http import Http404
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, reverse
from django.views.defaults import page_not_found

from apps.core import aufbau_draft, hero_tiles, page_settings, pagecache, site_schema, studio_pages
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

HOST = "not_found"
CODE = "not_found"
#: потолок запросов страницы 404 с блоками по умолчанию (после прогрева): боты бьют в 404
MAX_404_QUERIES = 6


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _views():
    from apps.core import not_found_views

    return not_found_views


def _page():
    from apps.core import not_found_page

    return not_found_page


def _tenant(**kw):
    kw.setdefault("business_type", "bakery")
    return TenantFactory(disabled_modules=[], **kw)


def _req(rf, tenant, path="/gibt-es-nicht/", method="get", **extra):
    req = getattr(rf, method)(path, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    req.user = AnonymousUser()
    req.portal = None
    if tenant is not None:
        req.tenant = tenant
    return req


def _html(rf, tenant, **kw):
    resp = _views().storefront_404(_req(rf, tenant, **kw), Http404())
    return resp, resp.content.decode()


def _block_hrefs(html, marker):
    """Ссылки внутри блока с атрибутом `marker` (до закрытия его <section>)."""
    start = html.index(marker)
    return re.findall(r'<a href="([^"]+)"', html[start : html.index("</section>", start)])


# ── обработчик: кто получает страницу с блоками ─────────────────────────────────────


def test_tenant_urlconf_uses_our_handler():
    handler = get_resolver("config.urls_tenant").resolve_error_handler(404)
    assert handler is _views().storefront_404


@pytest.mark.parametrize("urlconf", ["config.urls_public", "config.urls_portal"])
def test_platform_and_portal_urlconfs_keep_the_plain_handler(urlconf):
    """Платформа и портал: `Http404` из их вьюх — прежняя страница (своего обработчика нет)."""
    assert get_resolver(urlconf).resolve_error_handler(404) is page_not_found


@pytest.mark.parametrize("method", ["get", "head"])
def test_unknown_address_gets_the_block_page(rf, method):
    resp, html = _html(rf, _tenant(), method=method)
    assert resp.status_code == 404
    assert resp["X-Robots-Tag"].startswith("noindex")
    assert '<meta name="robots" content="noindex' in html
    assert 'rel="canonical"' not in html and "application/ld+json" not in html
    assert "data-not-found" in html and html.count("<h1") == 1
    assert 'data-stu-page="not_found"' in html  # R7: Студия не показывает блоки главной
    assert f'data-pb-host="{HOST}"' in html
    assert "data-block-site-search" in html and "data-block-quick-links" in html
    assert 'href="/"' in html  # кнопка на главную


def _plain(rf, req):
    return page_not_found(req, Http404()).content


def _fallback_cases():
    def no_tenant(rf):
        return _req(rf, None)

    def public_schema(rf):
        return _req(rf, TenantFactory.build(schema_name="public"))

    def portal(rf):
        req = _req(rf, _tenant())
        req.portal = SimpleNamespace(pk=1, show_demo=False)
        return req

    def cabinet(rf):
        return _req(rf, _tenant(), path="/dashboard/gibt-es-nicht/")

    def htmx(rf):
        return _req(rf, _tenant(), HTTP_HX_REQUEST="true")

    def post(rf):
        return _req(rf, _tenant(), method="post")

    def email_pending(rf):
        return _req(rf, _tenant(email_pending=True))

    def unpublished(rf):
        return _req(rf, _tenant(published_at=None))

    def media(rf):
        return _req(rf, _tenant(), path="/media/fehlt.jpg")

    return [
        no_tenant,
        public_schema,
        portal,
        cabinet,
        htmx,
        post,
        email_pending,
        unpublished,
        media,
    ]


@pytest.mark.parametrize("case", _fallback_cases(), ids=lambda c: c.__name__)
def test_everything_else_gets_the_plain_page(rf, case):
    """R1/R2: платформа, портал, кабинет, HTMX, не-GET, скрытая витрина, файлы — прежняя 404."""
    req = case(rf)
    resp = _views().storefront_404(req, Http404())
    assert resp.status_code == 404
    assert resp.content == _plain(rf, req)
    assert b"data-not-found" not in resp.content


def test_plain_page_is_alive_as_the_fallback(rf):
    """Запасной путь жив: standalone-шаблон рисуется без хрома витрины."""
    html = page_not_found(_req(rf, _tenant()), Http404()).content.decode()
    assert "<h1" in html and "data-stu-page" not in html and "sf-nav" not in html


# ── сбой и мусор ────────────────────────────────────────────────────────────────────


def test_block_failure_serves_the_plain_page_and_logs(rf, monkeypatch, caplog):
    def boom(*_a, **_kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(hero_tiles, "menu_tiles", boom, raising=False)
    req = _req(rf, _tenant())
    from django.core.cache import cache

    cache.clear()
    with caplog.at_level(logging.WARNING, logger="apps.core.not_found_views"):
        resp = _views().storefront_404(req, Http404())
    assert resp.status_code == 404
    assert resp.content == _plain(rf, req)
    assert any("kaputt" in (r.exc_text or "") or r.exc_info for r in caplog.records)


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_failing_plain_page_still_answers_404(rf, monkeypatch, caplog):
    """Ревью: запасная `404.html` рендерится с контекстными процессорами — сбой БД уронил бы и
    её, посетитель получил бы 500. Последний рубеж — ответ без шаблона."""

    def boom(*_a, **_kw):
        raise RuntimeError("kaputt")

    views = _views()
    monkeypatch.setattr(hero_tiles, "menu_tiles", boom, raising=False)
    monkeypatch.setattr(views, "page_not_found", boom)
    with caplog.at_level(logging.ERROR, logger="apps.core.not_found_views"):
        resp = views.storefront_404(_req(rf, _tenant()), Http404())
    assert resp.status_code == 404 and resp.content
    assert resp["X-Robots-Tag"] == "noindex"
    assert caplog.records


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_failing_gate_serves_the_plain_page(rf, monkeypatch):
    """Ревью: решение «рисовать ли блоки» стояло вне защиты — его сбой давал 500."""
    from apps.core import storefront_state

    def boom(*_a, **_kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(storefront_state, "hidden_reasons", boom)
    req = _req(rf, _tenant())
    resp = _views().storefront_404(req, Http404())
    assert resp.status_code == 404 and resp.content == _plain(rf, req)


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_failure_log_is_deduplicated_and_does_not_carry_raw_path(rf, monkeypatch, caplog):
    """Ревью безопасности: трассировка на КАЖДЫЙ битый адрес бота заливала лог, путь шёл в
    запись как есть (перевод строки = поддельная строка лога). Запись — одна на бизнес за
    окно, уровнем error (видна мониторингу), путь — через repr и с потолком длины."""
    from django.core.cache import cache

    cache.clear()

    def boom(*_a, **_kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(hero_tiles, "menu_tiles", boom, raising=False)
    tenant = _tenant()
    with caplog.at_level(logging.DEBUG, logger="apps.core.not_found_views"):
        for _ in range(3):
            _views().storefront_404(_req(rf, tenant, path="/x\nFAKE " + "a" * 500), Http404())
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and errors[0].exc_info
    text = errors[0].getMessage()
    assert "\n" not in text and len(text) < 400
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    "site_config",
    [
        {"page_blocks": {HOST: "kaputt"}},
        {"page_blocks": 5},
        {"page_blocks": {HOST: [1, None, {"key": "gibt-es-nicht", "id": "x"}, {"id": "y"}]}},
        {
            "page_blocks": {
                HOST: [
                    {"key": "quick_links", "id": "q", "data": {"set": "menu", "hidden": "zzz"}},
                    {"key": "site_search", "id": "s", "data": "kein dict"},
                    {"key": "quick_links", "id": "q2", "data": {"set": "gibt-es-nicht"}},
                ]
            }
        },
        {"menus": "kaputt", "page_blocks": {HOST: None}},
    ],
)
def test_garbage_config_is_still_the_block_page(rf, site_config):
    resp, html = _html(rf, _tenant(site_config=site_config))
    assert resp.status_code == 404 and "data-not-found" in html


# ── «Beliebt»: плитки = верхний уровень меню контекста ─────────────────────────────


def test_popular_tiles_are_the_top_level_menu_of_the_context(rf):
    from apps.core import context

    tenant = _tenant()
    req = _req(rf, tenant)
    menu = context.modules_nav(req)["storefront_menu"]
    want = [item["url"] for item in menu if item.get("url")]
    assert len(want) >= 2, "у пекарни в меню несколько разделов"
    _resp, html = _html(rf, tenant)
    assert _block_hrefs(html, "data-block-quick-links") == want[: hero_tiles.MENU_TILES_MAX]


def test_menu_tiles_take_only_top_level_items_with_an_address():
    menu = [
        {"label": "Sortiment", "url": "/sortiment/", "icon": "🥨", "children": []},
        {"label": "Mehr", "url": None, "children": [{"label": "Team", "url": "/team/"}]},
        {"label": "", "url": "/leer/", "children": []},
        {"label": "Kontakt", "url": "/kontakt/", "icon": "", "children": []},
        "kaputt",
    ]
    tiles = hero_tiles.menu_tiles(menu)
    assert [(t["label"], t["href"]) for t in tiles] == [
        ("Sortiment", "/sortiment/"),
        ("Kontakt", "/kontakt/"),
    ]
    assert hero_tiles.menu_tiles(None) == [] and hero_tiles.menu_tiles("x") == []
    many = [{"label": str(i), "url": f"/{i}/"} for i in range(30)]
    assert len(hero_tiles.menu_tiles(many)) == hero_tiles.MENU_TILES_MAX


def test_menu_set_has_no_tile_keys_and_keeps_only_the_set():
    """У набора «menu» своих ключей плиток нет: «скрыть» и «своя подпись» не хранятся."""
    assert hero_tiles.MENU_SET in hero_tiles.BLOCK_LINK_SETS
    # наборы реестра (их переносил `quick_links_migration`) прежние
    assert hero_tiles.MENU_SET not in hero_tiles.QUICK_LINK_SETS
    data = {"set": "menu", "hidden": ["sortiment"], "labels": {"sortiment": "X"}}
    assert hero_tiles.clean_data(data) == {"set": "menu"}
    panel = hero_tiles.panel({"set": "menu"})
    assert panel["rows"] == [] and "menu" in dict(panel["options"])
    assert [k for k, _lab in hero_tiles.link_set_options()] == list(hero_tiles.BLOCK_LINK_SETS)
    assert hero_tiles.update_data({"set": "menu"}, {"set": "menu", "show_x": "1"}) == {
        "set": "menu"
    }


# ── «Suche» ─────────────────────────────────────────────────────────────────────────


def test_search_block_is_a_get_form_to_the_storefront_search(rf):
    from apps.core import context

    tenant = _tenant()
    url = context.modules_nav(_req(rf, tenant))["storefront_search_url"]
    assert url
    _resp, html = _html(rf, tenant)
    start = html.index("data-block-site-search")
    form = html[start : html.index("</form>", start)]
    assert 'role="search"' in form and 'method="get"' in form and f'action="{url}"' in form
    assert 'name="q"' in form and 'type="search"' in form and "maxlength=" in form
    field_id = re.search(r'<input id="([^"]+)"', form).group(1)
    assert f'<label for="{field_id}"' in form
    assert "csrfmiddlewaretoken" not in form


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_search_form_is_a_named_landmark_and_demo_has_one_robots_tag(rf):
    """Ревью a11y: два ориентира `search` (шапка и блок) — блок назван. Ревью SEO: у демо-
    бизнеса базовый шаблон уже ставит robots — второго тега нет."""
    html = _html(rf, _tenant())
    form = re.search(r"<form[^>]*role=\"search\"[^>]*data-site-search[^>]*>", html)
    assert form and "aria-label=" in form.group(0)
    demo = _html(rf, _tenant(is_demo=True))
    assert len(re.findall(r'<meta name="robots"', demo)) == 1
    assert len(re.findall(r'<meta name="robots"', html)) == 1


def test_search_block_draws_nothing_without_a_search_address():
    from django.template.loader import render_to_string

    html = render_to_string(
        "storefront/sections/_block_site_search.html", {"block": {}, "block_id": "s1"}
    )
    assert html.strip() == ""


def test_search_block_is_offered_only_on_the_not_found_page():
    assert "site_search" in dict(site_schema.add_options(CODE))
    for code in ("home", "text", "catalog", "confirmation", "cart"):
        assert "site_search" not in dict(site_schema.add_options(code)), code


# ── умолчание и «задано пусто» ──────────────────────────────────────────────────────


def test_missing_key_means_default_rows_with_constant_ids():
    page = _page()
    first = siteconfig.page_rows(siteconfig.normalize({}), HOST)
    again = siteconfig.page_rows(siteconfig.normalize({}), HOST)
    assert [r["id"] for r in first] == ["nf-search", "nf-popular"] == [r["id"] for r in again]
    assert [r["key"] for r in first] == ["site_search", "quick_links"]
    assert first == again and first is not again
    assert first[1]["data"] == {"set": "menu"}
    # R5: умолчание не хранит текста
    assert all(not isinstance(v, str) or k == "set" for r in first for k, v in r["data"].items())
    assert page.rows({}) == first
    # умолчание — в нормализованной форме: правка в редакторе не «меняет» остальные строки
    stored = siteconfig.normalize({"page_blocks": {HOST: first}})["page_blocks"][HOST]
    assert stored == first


def test_default_does_not_materialise_a_config_key():
    assert siteconfig.normalize_page_blocks({}) == {}
    assert HOST not in (siteconfig.normalize({}).get("page_blocks") or {})


def test_empty_key_is_kept_and_means_no_blocks(rf):
    cfg = siteconfig.normalize({"page_blocks": {HOST: []}})
    assert cfg["page_blocks"][HOST] == []
    assert siteconfig.page_rows(cfg, HOST) == []
    again = siteconfig.normalize(cfg)
    assert again["page_blocks"][HOST] == []
    resp, html = _html(rf, _tenant(site_config={"page_blocks": {HOST: []}}))
    assert resp.status_code == 404 and "data-not-found" in html
    assert "data-block-site-search" not in html and "data-block-quick-links" not in html


def test_default_state_of_the_page_has_a_stable_fingerprint():
    """R4: с постоянными id сохранённое состояние страницы одно и то же в любом запросе —
    иначе открытый черновик «конфликтовал» бы сам с собой."""
    cfg = siteconfig.normalize({})
    one = aufbau_draft._fingerprint(aufbau_draft._saved_state(cfg, False, HOST))
    two = aufbau_draft._fingerprint(
        aufbau_draft._saved_state(siteconfig.normalize({}), False, HOST)
    )
    assert one == two
    assert len(aufbau_draft._saved_state(cfg, False, HOST)["items"]) == 2


def test_other_pages_drafts_do_not_see_the_new_host():
    """Отпечаток открытого черновика другой страницы не зависит от хоста 404 (ни от
    умолчания, ни от сохранённого ключа)."""
    row = {"key": "text", "id": "t1", "enabled": True, "data": {"title": "A", "body": "B"}}
    base = siteconfig.normalize({"page_blocks": {"info": [row]}})
    with_404 = siteconfig.normalize({"page_blocks": {"info": [row], HOST: []}})
    saved = aufbau_draft._saved_state(base, False, "info")
    draft = {**saved, "base": aufbau_draft._fingerprint(saved), "home": False, "host": "info"}
    assert aufbau_draft._base_fingerprint(saved, base, draft) == draft["base"]
    saved_now = aufbau_draft._saved_state(with_404, False, "info")
    assert aufbau_draft._base_fingerprint(saved_now, with_404, draft) == draft["base"]


def _browser(**kw):
    from apps.core.tests.test_fb27_r2_draft import Browser

    return Browser(_tenant(**kw))


def _saved(tenant):
    return (Tenant.objects.get(pk=tenant.pk).site_config or {}).get("page_blocks") or {}


def test_first_edit_in_the_editor_materialises_the_default():
    b = _browser()
    html = b.get(f"?seite={CODE}")
    assert 'data-schema-block="nf-search"' in html and 'data-schema-block="nf-popular"' in html
    resp, _msgs = b.post(seite=CODE, op="toggle", ref="nf-search")
    assert resp.status_code == 302
    assert HOST not in _saved(b.tenant), "правка — в черновик"
    b.post(seite=CODE, op="save")
    rows = _saved(b.tenant)[HOST]
    assert [(r["id"], r["enabled"]) for r in rows] == [("nf-search", False), ("nf-popular", True)]


def test_deleting_every_block_in_the_editor_keeps_the_empty_key(rf):
    b = _browser()
    b.post(seite=CODE, op="delete", ref="nf-search")
    b.post(seite=CODE, op="delete", ref="nf-popular")
    b.post(seite=CODE, op="save")
    assert _saved(b.tenant)[HOST] == []
    html = b.get(f"?seite={CODE}")
    assert "nf-search" not in html and "nf-popular" not in html
    b.tenant.refresh_from_db()
    _resp, page = _html(rf, b.tenant)
    assert "data-block-quick-links" not in page and "data-not-found" in page


# ── cookie, сессия, кэш ─────────────────────────────────────────────────────────────


def test_default_page_sets_no_cookie_and_stays_out_of_the_page_cache(rf, settings):
    settings.PUBLIC_PAGE_CACHE_TTL = 60
    tenant = _tenant()
    seen = {}

    def view(request):
        request.user = AnonymousUser()
        request.portal = None
        request.tenant = tenant
        seen["req"] = request
        return _views().storefront_404(request, Http404())

    resp = SessionMiddleware(view)(rf.get("/gibt-es-nicht/"))
    req = seen["req"]
    assert resp.status_code == 404 and b"data-not-found" in resp.content
    assert not resp.cookies, f"Set-Cookie на 404: {list(resp.cookies)}"
    assert not req.session.modified and req.session.session_key is None
    assert not req.META.get("CSRF_COOKIE_NEEDS_UPDATE"), "CSRF-кука анониму на 404"
    assert pagecache._cacheable(req, resp) is False


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_list_block_is_not_drawn_on_the_page_and_no_cookie_is_set(rf):
    """Ревью безопасности: «Liste» на 404 — кнопка корзины с CSRF-токеном (cookie анониму на
    любом битом адресе) и выборка товаров на каждый запрос бота. Блок на хосте запрещён; и
    старый конфиг с ним страницу не меняет."""
    rows = [{"key": "list", "id": "l1", "enabled": True, "data": {"source": "products"}}]
    tenant = _tenant()
    Tenant.objects.filter(pk=tenant.pk).update(site_config={"page_blocks": {HOST: rows}})
    tenant.refresh_from_db()
    seen = {}

    def view(request):
        request.tenant = tenant
        request.portal = None
        request.user = AnonymousUser()
        seen["req"] = request
        return _views().storefront_404(request, Http404())

    resp = SessionMiddleware(view)(rf.get("/gibt-es-nicht/"))
    assert resp.status_code == 404 and b"data-not-found" in resp.content
    assert b'data-sf-section="l1"' not in resp.content
    assert b"csrfmiddlewaretoken" not in resp.content
    assert not resp.cookies and not seen["req"].session.modified
    assert not seen["req"].META.get("CSRF_COOKIE_NEEDS_UPDATE")


# ── блоки-формы ─────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(strict=True, reason="ревью стопки 8 — до правки")
def test_form_blocks_and_list_are_banned_on_the_host():
    page = _page()
    assert {"newsletter", "anfrage_ref", "message_ref"} <= set(page.FORM_BLOCKS)
    raw = {
        "page_blocks": {
            HOST: [
                {"key": "newsletter", "id": "n1", "enabled": True, "data": {}},
                {"key": "message_ref", "id": "m1", "enabled": True, "data": {}},
                {"key": "anfrage_ref", "id": "a1", "enabled": True, "data": {}},
                {"key": "list", "id": "l1", "enabled": True, "data": {"source": "products"}},
                {"key": "text", "id": "t1", "enabled": True, "data": {"body": "ok"}},
            ],
            "info": [{"key": "newsletter", "id": "n2", "enabled": True, "data": {}}],
        }
    }
    pb = siteconfig.normalize(raw)["page_blocks"]
    assert [b["id"] for b in pb[HOST]] == ["t1"]
    assert [b["id"] for b in pb["info"]] == ["n2"]
    offered = {k for k, _lab in site_schema.add_options(CODE)}
    assert "list" in page.FORM_BLOCKS and not offered & set(page.FORM_BLOCKS)
    # подтверждение «Liste» по-прежнему держит (свой набор запретов у каждого хоста)
    assert "list" in {k for k, _lab in site_schema.add_options("confirmation")}
    items = site_schema.load_items(siteconfig.normalize({}), False, HOST)
    for key in page.FORM_BLOCKS:
        with pytest.raises(site_schema.SchemaError):
            site_schema.mutate(items, CODE, "add", block_type=key)


def test_blocks_are_drawn_with_a_clean_context(rf, monkeypatch):
    """Блоки 404 не видят контекста вьюхи (как на подтверждении) — только свои строки."""
    from apps.tenants.templatetags import siteui

    seen = {}
    real = siteui.render_to_string

    def spy(name, ctx=None, request=None):
        if name == "storefront/_page_blocks.html":
            seen.update(ctx)
        return real(name, ctx, request=request)

    monkeypatch.setattr(siteui, "render_to_string", spy)
    _html(rf, _tenant())
    assert set(seen) == {"pb_rows", "pb_page_key", "site", "is_preview"}


# ── тип страницы и превью ───────────────────────────────────────────────────────────


def test_type_is_registered_and_always_offered(monkeypatch):
    pt = studio_pages.page_type(CODE)
    assert pt.code == CODE and pt.block_host == HOST
    assert site_schema._preview_url(pt) == reverse("storefront-404-vorschau")
    assert any(CODE in codes for _k, _l, _m, codes in site_schema._TYPE_GROUPS)
    tenant = _tenant()
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: False)
    assert page_settings.type_active(tenant, CODE)


def test_seitenaufbau_offers_the_page_and_opens_the_tiles_block():
    b = _browser()
    html = b.get(f"?seite={CODE}")
    assert "Seite nicht gefunden" in html
    panel = b.get(f"?seite={CODE}&block=nf-popular")
    assert re.search(r'<option value="menu"[^>]*selected', panel)
    # у набора «menu» нет строк плиток — скрывать и переименовывать нечего
    assert 'name="show_' not in panel and 'name="label_' not in panel
    assert b.get(f"?seite={CODE}&block=nf-search")  # окно блока поиска открывается


def _preview(rf, tenant, monkeypatch, allowed=True, query=""):
    monkeypatch.setattr(page_settings, "_may_preview", lambda request: allowed)
    req = _req(rf, tenant, path=reverse("storefront-404-vorschau") + query)
    req.user = SimpleNamespace(is_authenticated=allowed)
    return _views().not_found_preview(req)


def test_preview_is_only_for_the_team(rf, monkeypatch):
    with pytest.raises(Http404):
        _preview(rf, _tenant(), monkeypatch, allowed=False)


def test_preview_answers_200_out_of_index_and_cache(rf, monkeypatch):
    resp = _preview(rf, _tenant(), monkeypatch)
    html = resp.content.decode()
    assert resp.status_code == 200
    assert resp["X-Robots-Tag"] == "noindex, nofollow" and "no-store" in resp["Cache-Control"]
    assert "data-not-found" in html and "data-block-quick-links" in html
    assert 'rel="canonical"' not in html and "application/ld+json" not in html


def test_preview_route_reports_its_page_type():
    """R7: превью — обычный маршрут витрины, тип страницы даёт реестр."""
    ctx = studio_pages.resolve_page(reverse("storefront-404-vorschau"))
    assert ctx.code == CODE and ctx.block_host == HOST


# ── запросы ─────────────────────────────────────────────────────────────────────────


def test_default_page_stays_under_the_query_ceiling(rf):
    tenant = _tenant()
    _html(rf, tenant)  # прогрев: кэш шаблонов, ContentType, версии кэша
    with CaptureQueriesContext(connections["default"]) as ctx:
        resp, _page_html = _html(rf, tenant)
    assert resp.status_code == 404
    assert len(ctx.captured_queries) <= MAX_404_QUERIES, [
        q["sql"][:120] for q in ctx.captured_queries
    ]
