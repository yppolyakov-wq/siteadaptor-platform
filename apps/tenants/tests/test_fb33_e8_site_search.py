"""FB-33 стопка 14 E8: блок «Suche» (`site_search`) — только на странице 404.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 E8, §4 E8, §10 (architect M8). Запрет блоков
по хосту — один вопрос `siteconfig.banned_blocks`: normalize (страницы и главная), показ
(`siteui.page_blocks`) и «+ Block» (`site_schema.add_options`) отвечают одинаково. Старый
конфиг с поиском вне 404 (импорт, ассистент) его не рисует.
"""

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

SEARCH = {"key": "site_search", "id": "s1", "enabled": True, "data": {}}
TEXT = {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Infotext"}}
#: (код строки «+ Block», хост страницы)
PAGES = (
    ("catalog", "catalog"),
    ("services", "services"),
    ("cart", "cart"),
    ("confirmation", "confirmation"),
    ("not_found", "not_found"),
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(site_config):
    tenant = TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config=site_config,
    )
    connection.tenant = tenant
    return tenant


def _render(tenant, host):
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)
    source = "{% load siteui %}{% page_blocks " + f'"{host}"' + " %}"
    ctx = {"request": request, "storefront_search_url": "/suche/"}
    return Template(source).render(Context(ctx))


def _kept(host) -> bool:
    cfg = siteconfig.normalize({"page_blocks": {host: [SEARCH]}})
    return any(
        b.get("key") == "site_search" for b in (cfg.get("page_blocks") or {}).get(host) or []
    )


@pytest.mark.parametrize(("code", "host"), PAGES)
def test_site_search_ban_one_source(code, host):
    """№2: normalize, показ и «+ Block» дают один ответ — `banned_blocks(host)`."""
    banned = "site_search" in siteconfig.banned_blocks(host)
    assert banned is (host != "not_found")
    assert _kept(host) is not banned
    assert ("site_search" in dict(site_schema.add_options(code))) is not banned
    if host != "not_found":
        html = _render(_tenant({"page_blocks": {host: [TEXT, SEARCH]}}), host)
        assert "data-block-site-search" not in html


@pytest.mark.parametrize("host", ["home", "seite:x", "catalog"])
def test_old_config_site_search_elsewhere(host):
    """№6: старый конфиг с «Suche» вне 404 — normalize его снимает, страница не рисует."""
    if host == "home":
        cfg = siteconfig.normalize({"sections": [SEARCH, TEXT]})
        assert "site_search" not in [s.get("key") for s in cfg["sections"]]
        assert "text" in [s.get("key") for s in cfg["sections"]]
        return
    config = {"page_blocks": {host: [TEXT, SEARCH]}}
    cfg = siteconfig.normalize(config)
    assert [b.get("key") for b in cfg["page_blocks"][host]] == ["text"]
    html = _render(_tenant(config), host)
    assert "Infotext" in html and "data-block-site-search" not in html


def test_page_blocks_render_unchanged_outside_formless():
    """M8 (охранный): вне `FORMLESS_HOSTS` обычные блоки рисуются полным контекстом, как
    раньше — фильтр запретов не уводит их в ветку чистого контекста."""
    tenant = _tenant({"page_blocks": {"catalog": [TEXT]}})
    html = _render(tenant, "catalog")
    assert "Infotext" in html
    assert html.count("Infotext") == _render(tenant, "catalog").count("Infotext")


def test_not_found_keeps_its_search_block():
    """Охранный: на 404 поиск остаётся (умолчание страницы и сохранённый список)."""
    rows = siteconfig.page_rows(siteconfig.normalize({}), "not_found")
    assert "site_search" in [r["key"] for r in rows]
    assert _kept("not_found")
