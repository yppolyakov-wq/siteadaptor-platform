"""FB-33 стопка 15 E1t (S14-E1-text): ⚙ Студии на своей текстовой странице открывает схему
ЭТОЙ страницы, а не «Über uns» (план `docs/fb33-stack15-plan-2026-11-25.md` §2 «E1t», §4 «E1t»,
§14.1 A6 — повтор находки стопки 14 №16).

Правило A6: живая своя страница (`core.ContentPage`) → `text@seite:<slug>` всегда — со своими
блоками и без (витрина своей страницы рисует блоки хоста `seite:<slug>`, блоков `info` на ней
нет); страница-призрак → "" (ссылки нет); общий `text` («Über uns») — никогда для `seite:<slug>`.
Хост берётся из `studio_pages.resolve_page(...).block_host`; запасная ветка `von` стопки 14
(`_own_text_host` в `site_schema_views`) снята.
"""

import inspect
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.core import site_schema, site_schema_views, studio_pages, window_links
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_e1_von import OWN_BLOCK, _ctx, _q, _req, _studio_page

pytestmark = pytest.mark.django_db


def _pages(settings, blocks: dict, *slugs: str):
    from apps.core.models import ContentPage

    settings.ROOT_URLCONF = "config.urls_tenant"  # короткий адрес своей страницы — витрины
    tenant = _tenant()
    tenant.site_config = {"page_blocks": blocks}
    tenant.save()
    for slug in slugs:
        ContentPage.objects.create(slug=slug, title=slug, body="<p>x</p>", is_published=True)
    return tenant


@pytest.mark.parametrize("path", ["/x/", "/seite/x/"])
def test_resolve_page_own_text_host(path):
    """Хост блоков своей страницы — `seite:<slug>` (короткий и старый адрес), не `info`."""
    ctx = studio_pages.resolve_page(path)
    assert ctx.code == site_schema.TEXT and ctx.block_host == "seite:x"


@pytest.mark.parametrize("slug", ["x", "x-2"])
def test_code_for_own_text_page(settings, slug):
    """№5: своя страница со своими блоками — её строка; соседний адрес — свой код."""
    tenant = _pages(settings, {"seite:x": [OWN_BLOCK], "seite:x-2": [OWN_BLOCK]}, "x", "x-2")
    assert site_schema.code_for_path(tenant, f"/{slug}/") == f"text@seite:{slug}"


def test_text_page_without_blocks_never_opens_info(settings):
    """A6 / №6: своя страница без своих блоков — тоже её строка, не «Über uns»."""
    tenant = _pages(settings, {}, "foo")
    assert site_schema.code_for_path(tenant, "/foo/") == "text@seite:foo"
    tenant = _pages(settings, {"info": [OWN_BLOCK]}, "bar")
    assert site_schema.code_for_path(tenant, "/bar/") == "text@seite:bar"


def test_ghost_text_page_no_link(settings):
    """A6: страницы нет — ссылки нет ("" и экран без выбора), не запасной «Über uns»."""
    tenant = _pages(settings, {"seite:ghost": [OWN_BLOCK]})
    assert site_schema.code_for_path(tenant, "/ghost/") == ""
    assert "seite=" not in site_schema.url_for_path(tenant, "/ghost/")


def test_about_page_still_text(settings):
    """Охранный: «Über uns» — общий `text` (хост `info`)."""
    tenant = _pages(settings, {})
    assert site_schema.code_for_path(tenant, "/ueber-uns/") == site_schema.TEXT


def test_fallback_branch_removed():
    """№4: запасной ветки `von` для своей страницы (стопка 14) больше нет."""
    src = inspect.getsource(site_schema_views)
    assert "_own_text_host" not in src
    assert not hasattr(site_schema_views, "_own_text_host")


@pytest.mark.parametrize("blocks", [{"seite:foo": [OWN_BLOCK]}, {}])
def test_studio_gear_opens_that_page(settings, blocks):
    """Сквозной: ⚙ Студии на `/foo/` → схема `text@seite:foo` с `von=/foo/`; экран принимает
    `von` — кадр и Студия на этой странице."""
    tenant = _pages(settings, blocks, "foo")
    url = window_links.studio_settings_url(_req(tenant), "/foo/")
    q = parse_qs(urlsplit(url).query)
    assert q["seite"] == ["text@seite:foo"] and q["von"] == ["/foo/"]
    _html, ctx = _ctx(Browser(tenant), "?" + urlsplit(url).query)
    assert "von=" in ctx["keep_q"] and _studio_page(ctx) == "/foo/"
    assert ctx["preview_url"] == "/foo/"


def test_about_schema_rejects_own_page_von(settings):
    """Охранный: схема «Über uns» путь своей страницы не принимает (код пути другой)."""
    tenant = _pages(settings, {}, "foo")
    html, ctx = _ctx(Browser(tenant), "?seite=text&von=/foo/")
    assert 'name="von"' not in html and "von=" not in ctx["keep_q"]
    assert not _q(ctx["studio_url"]).get("page") or _studio_page(ctx) != "/foo/"
