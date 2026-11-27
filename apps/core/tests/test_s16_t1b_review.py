"""FB-33 стопка 16 T1b, круг ревью 1 (`docs/fb33-stack16-plan-2026-11-26.md` §2 «T1b»):

- S2/S3/S4 (seo-specialist): перевод `<title>` страницы и кэш — язык посетителя из
  `Accept-Language` и из куки переключателя даёт свой `<title>`, `Vary` держит оба признака,
  хит кэша страниц не отдаёт чужой язык; `<html lang>` — язык `<title>`; canonical без query;
- S5: LocalBusiness JSON-LD — данные бизнеса (имя), не SEO страницы: с переводом не расходится;
- D2 (django-reviewer): битый ЧУЖОЙ ключ оверлея не гасит перевод валидной страницы;
  предупреждение о битом оверлее — раз на запрос (а не на каждый `{% page_seo %}`);
- V1 (после E10): `schema_ref("versand")` без заказов — `seite:versand` (страница живёт на
  `/seite/versand/` и рисует блоки и SEO этого хоста); вкладки «Blöcke» и «Suchmaschinen»
  экрана «Seiten» — тот же хост, что у витрины и Студии.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import uuid

import pytest
from django.core.cache import cache
from django.db import connections
from django.test import RequestFactory
from django.utils import translation

from apps.core import content_pages, studio_pages
from apps.core.tests.test_s16_t1b_seo_i18n import DE, RU, _cfg, _render, _shop, _title
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

EN = {"title": "About us — Tea shop", "description": "Tea from Solingen since 1990."}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _keep_language():
    """Полный стек (`LocaleMiddleware`) оставляет активным язык последнего ответа — соседние
    тесты читали бы сообщения не на том языке."""
    before = translation.get_language()
    yield
    translation.activate(before)


def _three_lang_shop():
    tenant = _shop(seo=DE, ru=RU)
    cfg = _cfg(tenant)
    cfg["i18n"]["en"] = {"seo": {"pages": {"info": dict(EN)}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    return tenant


def _html_lang(html):
    return re.search(r'<html lang="([^"]*)"', html).group(1)


def _vary(resp):
    return {v.strip() for v in resp.get("Vary", "").split(",") if v.strip()}


# ───────────── S2 / S3 / S4: полный стек middleware ─────────────


def test_full_stack_title_language_vary_and_canonical(settings):
    """S2+S3+S4: `django.test.Client` на хосте тенанта (сессия, язык, кламп, кэш включён).
    Без заголовка — немецкий `<title>`; `Accept-Language: en` — английский; снова без
    заголовка — немецкий (кэш не склеил языки); кука языка `ru` — русский. У каждого ответа
    `Vary: Accept-Language, Cookie`, `<html lang>` — язык `<title>`, canonical — без query."""
    from django.test import Client

    from apps.tenants.tests.factories import DomainFactory

    settings.PUBLIC_PAGE_CACHE_TTL = 60
    tenant = _three_lang_shop()
    Tenant.objects.filter(pk=tenant.pk).update(slug=f"t1b-{uuid.uuid4().hex[:10]}")
    tenant.refresh_from_db()
    domain = DomainFactory(tenant=tenant, domain=f"{tenant.slug}.siteadaptor.de")
    plain = Client(HTTP_HOST=domain.domain)
    english = Client(HTTP_HOST=domain.domain, HTTP_ACCEPT_LANGUAGE="en")
    by_cookie = Client(HTTP_HOST=domain.domain)
    by_cookie.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
    try:
        steps = [
            ("de", DE, plain.get("/ueber-uns/", secure=True)),
            ("en", EN, english.get("/ueber-uns/", secure=True)),
            ("de", DE, plain.get("/ueber-uns/", secure=True)),
            ("ru", RU, by_cookie.get("/ueber-uns/", secure=True)),
            ("en", EN, english.get("/ueber-uns/?lang=en&utm_source=x", secure=True)),
        ]
    finally:
        connections["default"].set_schema_to_public()
    for lang, want, resp in steps:
        assert resp.status_code == 200, lang
        html = resp.content.decode()
        assert _title(html) == want["title"], lang
        assert _html_lang(html) == lang, "S3: <html lang> — язык <title>"
        assert {"Accept-Language", "Cookie"} <= _vary(resp), (lang, resp.get("Vary"))
        canon = re.search(r'<link rel="canonical" href="([^"]*)"', html).group(1)
        assert canon.endswith("/ueber-uns/") and "?" not in canon, "S4: canonical без query"


def test_page_cache_hit_keeps_visitor_language(settings):
    """S2: хит кэша страниц (`pagecache.cache_storefront_page`) — по ключу языка: английский
    ответ не уходит немецкому посетителю и наоборот; хит несёт `Vary: Cookie` и `Vary` вьюхи.
    Страница «Über uns» в проде мимо кэша (декоратора у неё нет), замок — на случай, если он
    появится: обёртка той же вьюхи."""
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import pagecache
    from apps.promotions import public_views

    settings.PUBLIC_PAGE_CACHE_TTL = 60
    tenant = _three_lang_shop()
    tenant.schema_name = f"t1b_{uuid.uuid4().hex[:8]}"  # ключ кэша — своя схема на прогон
    calls = []

    def view(request):
        calls.append(request.LANGUAGE_CODE)
        resp = public_views.about_page(request)
        resp["Vary"] = "Accept-Language"
        return resp

    cached = pagecache.cache_storefront_page(view)
    host = f"{uuid.uuid4().hex}.test"

    def get(lang):
        req = RequestFactory().get("/ueber-uns/", HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = AnonymousUser()
        req.tenant = tenant
        req.LANGUAGE_CODE = lang
        with translation.override(lang):
            return cached(req)

    en1, de1, en2, de2 = get("en"), get("de"), get("en"), get("de")
    assert calls == ["en", "de"], "второй en/de — хит кэша"
    assert _title(en1.content.decode()) == _title(en2.content.decode()) == EN["title"]
    assert _title(de1.content.decode()) == _title(de2.content.decode()) == DE["title"]
    for hit in (en2, de2):
        assert {"Accept-Language", "Cookie"} <= _vary(hit)


# ───────────── S5: JSON-LD бизнеса ─────────────


def test_localbusiness_ld_is_business_data_not_page_seo():
    """S5: в LocalBusiness `name` — имя бизнеса, `description` нет; SEO страницы (ни немецкое,
    ни перевод) туда не попадает — с переведённым `<title>` разметка не расходится."""
    tenant = _three_lang_shop()
    for lang, want in (("ru", RU), ("en", EN), ("de", DE)):
        html = _render(tenant, "info", lang)
        assert _title(html) == want["title"]
        lds = [
            json.loads(x)
            for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        ]
        business = [d for d in lds if d.get("@type") not in ("BreadcrumbList", "WebSite")]
        assert business, "LocalBusiness на странице есть"
        for d in business:
            assert d.get("name") == tenant.name and "description" not in d
            raw = json.dumps(d, ensure_ascii=False)
            for seo in (DE, RU, EN):
                assert seo["title"] not in raw and seo["description"] not in raw


# ───────────── D2: битый чужой ключ и одно предупреждение ─────────────

FOREIGN = {
    "unknown_host": {"catalog": {"title": "Чужой"}},
    "broken_value": {"seite:zahlung": "строка"},
}


@pytest.mark.parametrize("case", sorted(FOREIGN))
def test_foreign_broken_key_keeps_valid_host_translation(case, caplog):
    tenant = _shop(seo=DE)
    cfg = _cfg(tenant)
    cfg["i18n"] = {"ru": {"seo": {"pages": {**copy.deepcopy(FOREIGN[case]), "info": dict(RU)}}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    with caplog.at_level(logging.WARNING, logger="apps.core.content_pages"):
        html = _render(tenant, "info", "ru")
    assert _title(html) == RU["title"], "перевод валидной страницы не погашен"
    assert "Чужой" not in html
    warned = [r for r in caplog.records if "broken seo overlay" in r.getMessage()]
    assert len(warned) == 1, "битый чужой ключ виден в журнале — один раз на запрос"


def test_broken_overlay_warns_once_per_request(caplog):
    """`{% page_seo %}` стоит в трёх блоках шаблона (title, description, robots) — чтение
    одно на запрос, предупреждение одно."""
    tenant = _shop(seo=DE)
    cfg = _cfg(tenant)
    cfg["i18n"] = {"ru": {"seo": "кафе"}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    with caplog.at_level(logging.WARNING, logger="apps.core.content_pages"):
        html = _render(tenant, "info", "ru")
    assert _title(html) == DE["title"]
    warned = [r for r in caplog.records if "broken seo overlay" in r.getMessage()]
    assert len(warned) == 1


# ───────────── V1: «Versand» без заказов — хост `seite:versand` ─────────────


def _versand_shop(orders: bool):
    from apps.core.models import ContentPage
    from apps.core.tests.test_fb27_r2_draft import _tenant

    tenant = _tenant()
    if not orders:
        tenant.disabled_modules = [*tenant.disabled_modules, "orders"]
    else:
        tenant.disabled_modules = [m for m in tenant.disabled_modules if m != "orders"]
    own = {"key": "text", "id": "v1own", "enabled": True, "data": {"title": "Eigener Block"}}
    tenant.site_config = {
        "page_blocks": {"seite:versand": [own], "versand": []},
        "seo": {"pages": {"seite:versand": {"title": "Eigene Versandseite"}}},
    }
    tenant.save()
    assert tenant.is_module_active("orders") is orders
    page = ContentPage.objects.create(
        slug="versand", title="Versand", body="<p>x</p>", is_published=True
    )
    return tenant, page


def _owner():
    from django.contrib.auth import get_user_model

    from apps.core.tests.test_m21_6_content_pages import _user

    return get_user_model().objects.filter(username="owner-cp").first() or _user()


def _seiten(tenant, page, query, method="get", data=None):
    from apps.core import content_page_views as views
    from apps.core.tests.test_m21_6_content_pages import _req

    before = getattr(connections["default"], "tenant", None)
    connections["default"].tenant = tenant
    try:
        req = _req(f"/x/{query}", method=method, data=data, user=_owner(), tenant=tenant)
        return views.page_edit(req, page.pk)
    finally:
        connections["default"].tenant = before


def test_versand_schema_ref_without_orders_is_own_page_host():
    tenant, _page = _versand_shop(orders=False)
    assert content_pages.schema_ref("versand", tenant) == (
        "seite:versand",
        "text@seite:versand",
    )
    # витрина и Студия: /seite/versand/ рисует хост seite:versand
    assert studio_pages.resolve_page("/seite/versand/").block_host == "seite:versand"


def test_versand_schema_ref_with_orders_stays_versand():
    tenant, _page = _versand_shop(orders=True)
    assert content_pages.schema_ref("versand", tenant) == ("versand", "text@versand")
    assert content_pages.schema_ref("ueber-uns", tenant)[0] == "info"


def test_versand_blocks_tab_without_orders_shows_own_page_blocks():
    tenant, page = _versand_shop(orders=False)
    html = _seiten(tenant, page, "?tab=bloecke").content.decode()
    assert 'data-page-block="v1own"' in html, "вкладка «Blöcke» — блоки seite:versand"
    assert "seite=text%40seite%3Aversand" in html


def test_versand_search_tab_without_orders_reads_and_writes_own_page_host():
    tenant, page = _versand_shop(orders=False)
    html = _seiten(tenant, page, "?tab=suche").content.decode()
    assert "Eigene Versandseite" in html, "вкладка «Suchmaschinen» — SEO seite:versand"
    resp = _seiten(
        tenant,
        page,
        "?tab=suche",
        method="post",
        data={"seo_present": "1", "seo_title": "Neu Versand", "seo_description": ""},
    )
    assert resp.status_code == 302
    pages = _cfg(tenant)["seo"]["pages"]
    assert pages.get("seite:versand", {}).get("title") == "Neu Versand"
    assert "versand" not in pages, "запись — в хост, который рисует /seite/versand/"
