"""FB-33 стопка 14 E8: блок «Suche» (`site_search`) — только на странице 404.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 E8, §4 E8, §10 (architect M8). Запрет блоков
по хосту — один вопрос `siteconfig.banned_blocks`: normalize (страницы и главная), показ
(`siteui.page_blocks`) и «+ Block» (`site_schema.add_options`) отвечают одинаково. Старый
конфиг с поиском вне 404 (импорт, ассистент) его не рисует.
"""

import logging
from unittest import mock

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.templatetags import siteui
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


def _render(tenant, host, **extra):
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)
    source = "{% load siteui %}{% page_blocks " + f'"{host}"' + " %}"
    ctx = {"request": request, "storefront_search_url": "/suche/", **extra}
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


@pytest.mark.parametrize("host", ["catalog", "seite:x"])
def test_tag_filters_unnormalized_site_search(host):
    """M1 (ревью E8): показ сам спрашивает `banned_blocks` — даже если строки пришли мимо
    normalize (`page_rows` подменён), «Suche» вне 404 не рисуется, соседний блок — да."""
    tenant = _tenant({"page_blocks": {host: [TEXT]}})
    with mock.patch.object(siteconfig, "page_rows", return_value=[dict(TEXT), dict(SEARCH)]):
        html = _render(tenant, host)
    assert "Infotext" in html
    assert "data-block-site-search" not in html


def test_tag_keeps_site_search_on_not_found():
    """Охранный к M1: тот же путь на 404 поиск рисует (фильтр — по хосту, не по ключу)."""
    tenant = _tenant({"page_blocks": {"not_found": [TEXT, SEARCH]}})
    html = _render(tenant, "not_found")
    assert "data-block-site-search" in html


PROBE = "e8_view_probe"


def _block_context(host):
    """Контекст, с которым тег рисует `_page_blocks.html` на хосте (вьюха кладёт `PROBE`)."""
    tenant = _tenant({"page_blocks": {host: [TEXT]}})
    with mock.patch.object(siteui, "render_to_string", wraps=siteui.render_to_string) as spy:
        html = _render(tenant, host, **{PROBE: "x"})
    [ctx] = [c.args[1] for c in spy.call_args_list if c.args[0] == "storefront/_page_blocks.html"]
    return html, ctx


def test_page_blocks_full_context_outside_formless():
    """M2 (ревью E8): вне `FORMLESS_HOSTS` блоки получают ПОЛНЫЙ контекст вьюхи (фильтр
    запретов не уводит их в ветку чистого контекста)."""
    html, ctx = _block_context("catalog")
    assert "Infotext" in html
    assert ctx.get(PROBE) == "x"


@pytest.mark.parametrize("host", ["confirmation", "not_found"])
def test_page_blocks_clean_context_on_formless(host):
    """M2 / M2h (ПДн): на подтверждении и 404 — чистый контекст, данных вьюхи в блоках нет."""
    html, ctx = _block_context(host)
    assert "Infotext" in html
    assert PROBE not in ctx and "request" not in ctx


@pytest.mark.parametrize(
    ("config", "host"),
    [
        ({"sections": [SEARCH, TEXT]}, "home"),
        ({"page_blocks": {"catalog": [TEXT, SEARCH]}}, "catalog"),
    ],
)
def test_normalize_logs_dropped_site_search(caplog, config, host):
    """Находка silent-failure-hunter: снятие «Suche» оставляет след в логе (хост, без ПДн)."""
    with caplog.at_level(logging.INFO, logger="apps.tenants.siteconfig"):
        siteconfig.normalize(config)
    assert f"siteconfig: dropped site_search from {host}" in caplog.messages


def test_normalize_no_log_when_nothing_dropped(caplog):
    with caplog.at_level(logging.INFO, logger="apps.tenants.siteconfig"):
        siteconfig.normalize({"page_blocks": {"catalog": [TEXT]}, "sections": [TEXT]})
    assert not any("dropped site_search" in m for m in caplog.messages)


@pytest.mark.parametrize("host", ["catalog:x", "catalog", "seite:x"])  # хост категории — `catalog:`
def test_only_site_search_keeps_empty_page(host):
    """Находка silent-failure-hunter: страница, где «Suche» был единственным блоком, после
    снятия хранит пустой список (`[]`), а не уходит молча к блокам по умолчанию."""
    cfg = siteconfig.normalize({"page_blocks": {host: [SEARCH]}})
    assert cfg["page_blocks"].get(host, "missing") == []


def test_not_found_keeps_its_search_block():
    """Охранный: на 404 поиск остаётся (умолчание страницы и сохранённый список)."""
    rows = siteconfig.page_rows(siteconfig.normalize({}), "not_found")
    assert "site_search" in [r["key"] for r in rows]
    assert _kept("not_found")
