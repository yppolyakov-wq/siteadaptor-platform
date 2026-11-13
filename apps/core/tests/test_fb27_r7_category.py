"""FB-27 R7: своя схема у категории — заменяет блоки каталога на её странице."""

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.catalog.forms import CategoryForm, move_category_blocks
from apps.catalog.models import Category
from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    """`_tenant()` ставит арендатора в соединение (перенос блоков читает его оттуда) —
    после теста возвращаем прежнего, иначе следующие тесты окажутся в чужой схеме."""
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _text(i, title):
    return {"key": "text", "id": f"b{i}", "enabled": True, "data": {"title": title}}


def _tenant(page_blocks=None):
    tenant = TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config={"page_blocks": page_blocks or {}},
    )
    connection.tenant = tenant
    return tenant


def _cat(slug="tee", name="Tee"):
    return Category.objects.create(slug=slug, name={"de": name})


def _cfg(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _hosts(tenant):
    return _cfg(tenant).get("page_blocks") or {}


def _site(tenant, host):
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)
    tpl = Template(
        "{% load siteui %}{% category_blocks host part='before' %}{% category_blocks host %}"
    )
    return tpl.render(Context({"request": request, "host": host}))


# ───────────── R7a: данные ─────────────


def test_category_hosts_and_page_hosts_have_separate_caps():
    raw = {f"catalog:c{i:03d}": [_text(i, "x")] for i in range(45)}
    raw.update({f"seite:s{i:03d}": [_text(i, "y")] for i in range(45)})
    out = siteconfig.normalize({"page_blocks": raw})["page_blocks"]
    assert sum(k.startswith("catalog:") for k in out) == 40
    assert sum(k.startswith("seite:") for k in out) == 40


def test_address_change_moves_the_schema_with_its_translations():
    tenant = _tenant({"catalog:tee": [_text(1, "Tee-Welt")]})
    cfg = dict(tenant.site_config)
    cfg["i18n"] = {"en": {"page_blocks": {"catalog:tee": [{"data": {"title": "Tea"}}]}}}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    cat = _cat()
    form = CategoryForm(
        {"name_de": "Tee", "slug": "tees", "is_active": "on", "sort_order": "0"}, instance=cat
    )
    assert form.is_valid(), form.errors
    form.save()
    raw = Tenant.objects.get(pk=tenant.pk).site_config
    assert "catalog:tees" in raw["page_blocks"] and "catalog:tee" not in raw["page_blocks"]
    assert "catalog:tees" in raw["i18n"]["en"]["page_blocks"]


def test_deleted_category_frees_its_host():
    tenant = _tenant({"catalog:tee": [_text(1, "Tee-Welt")], "catalog": [_text(2, "Alle")]})
    assert move_category_blocks("tee", None) is True
    assert list(_hosts(tenant)) == ["catalog"]


def test_too_long_address_drops_the_schema_instead_of_leaving_a_ghost():
    tenant = _tenant({"catalog:tee": [_text(1, "Tee-Welt")]})
    move_category_blocks("tee", "x" * 80)
    assert _hosts(tenant) == {}


# ───────────── R7b: витрина ─────────────


def test_category_without_own_schema_shows_the_catalog_blocks():
    tenant = _tenant({"catalog": [_text(1, "Für alle Kategorien")]})
    assert "Für alle Kategorien" in _site(tenant, "catalog:tee")
    assert "Für alle Kategorien" in _site(tenant, "")


def test_own_schema_replaces_the_catalog_blocks():
    tenant = _tenant(
        {"catalog": [_text(1, "Für alle Kategorien")], "catalog:tee": [_text(2, "Nur Tee")]}
    )
    html = _site(tenant, "catalog:tee")
    assert "Nur Tee" in html and "Für alle Kategorien" not in html
    other = _site(tenant, "catalog:kaffee")
    assert "Für alle Kategorien" in other and "Nur Tee" not in other


def test_hidden_own_blocks_still_count_as_own_schema():
    hidden = {**_text(2, "Nur Tee"), "enabled": False}
    tenant = _tenant({"catalog": [_text(1, "Für alle Kategorien")], "catalog:tee": [hidden]})
    html = _site(tenant, "catalog:tee")
    assert "Für alle Kategorien" not in html and "Nur Tee" not in html


def test_rubbish_host_falls_back_to_the_catalog():
    assert not siteconfig.has_own_schema({"page_blocks": {"seite:x": [_text(1, "a")]}}, "seite:x")
    assert not siteconfig.has_own_schema(None, "catalog:tee")
    assert not siteconfig.has_own_schema({"page_blocks": {"catalog:tee": "x"}}, "catalog:tee")
    # только маркер основного списка — это ещё не своя схема
    assert not siteconfig.has_own_schema(
        {"page_blocks": {"catalog:tee": [{"key": "main"}]}}, "catalog:tee"
    )


# ───────────── R7c: экран ─────────────


def test_categories_are_listed_own_first_without_a_query_per_row():
    tenant = _tenant({"catalog:kaffee": [_text(1, "Kaffee-Welt")]})
    for slug, name in (("tee", "Tee"), ("kaffee", "Kaffee"), ("kakao", "Kakao")):
        _cat(slug, name)
    cfg = _cfg(tenant)
    with CaptureQueriesContext(connection) as ctx:
        pages = site_schema.category_pages(cfg)
    assert [p.code for p in pages] == [
        "category@catalog:kaffee",
        "category@catalog:kakao",
        "category@catalog:tee",
    ]
    assert len(ctx) == 1
    html = Browser(tenant).get("?seite=category@catalog:tee")
    assert "Kategorien" in html and 'data-schema-category="catalog"' in html


def test_unknown_category_is_refused():
    tenant = _tenant()
    _cat()
    for bad in ("category@catalog:nope", "category@seite:tee", "category@catalog:", "catalog@x"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.resolve(tenant, bad)
    assert site_schema.resolve(tenant, "category@catalog:tee")[1] == "catalog:tee"


def test_opening_and_saving_without_edits_creates_no_host():
    tenant = _tenant({"catalog": [_text(1, "Alle")]})
    _cat()
    before = Tenant.objects.get(pk=tenant.pk).site_config
    browser = Browser(tenant)
    browser.get("?seite=category@catalog:tee")
    browser.post(seite="category@catalog:tee", op="save")
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_adopt_copies_the_catalog_blocks_through_the_draft():
    catalog = [_text(1, "Oben"), {"key": "main"}, _text(2, "Unten")]
    tenant = _tenant({"catalog": catalog})
    _cat()
    browser = Browser(tenant)
    code = "category@catalog:tee"
    browser.post(seite=code, op="adopt")
    assert "catalog:tee" not in _hosts(tenant)  # пока черновик
    assert 'data-schema-category="own"' in browser.get(f"?seite={code}")
    browser.post(seite=code, op="save")
    hosts = _hosts(tenant)
    own = hosts["catalog:tee"]
    assert [b.get("key") for b in own] == ["text", "main", "text"]
    assert [b["data"]["title"] for b in own if b.get("id")] == ["Oben", "Unten"]
    assert {b["id"] for b in own if b.get("id")}.isdisjoint({"b1", "b2"})
    assert [b.get("id") for b in hosts["catalog"] if b.get("id")] == ["b1", "b2"]


def test_reset_returns_the_page_to_the_catalog_blocks():
    tenant = _tenant({"catalog": [_text(1, "Alle")], "catalog:tee": [_text(2, "Nur Tee")]})
    _cat()
    browser = Browser(tenant)
    code = "category@catalog:tee"
    browser.post(seite=code, op="reset")
    assert "catalog:tee" in _hosts(tenant)
    browser.post(seite=code, op="save")
    assert "catalog:tee" not in _hosts(tenant)
    assert "Alle" in _site(tenant, "catalog:tee")


def test_adopt_and_reset_exist_only_for_categories():
    tenant = _tenant({"catalog": [_text(1, "Alle")]})
    _resp, msgs = Browser(tenant).post(seite="catalog", op="adopt")
    assert any("nicht möglich" in m for m in msgs)
    assert [b.get("id") for b in _hosts(tenant)["catalog"] if b.get("id")] == ["b1"]


def test_preview_after_reset_shows_the_catalog_blocks_like_the_saved_page():
    tenant = _tenant({"catalog": [_text(1, "Alle")], "catalog:tee": [_text(2, "Nur Tee")]})
    # так выглядит конфиг предпросмотра черновика после «Eigene Blöcke entfernen»
    cfg = dict(tenant.site_config)
    cfg["page_blocks"] = {**cfg["page_blocks"], "catalog:tee": [{"key": "main"}]}
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    html = _site(tenant, "catalog:tee")
    assert "Alle" in html and "Nur Tee" not in html


def test_forty_first_own_schema_is_refused_instead_of_vanishing():
    full = {f"catalog:c{i:02d}": [_text(i, "x")] for i in range(40)}
    tenant = _tenant({**full, "catalog": [_text(99, "Alle")]})
    _cat()
    browser = Browser(tenant)
    for data in ({"op": "adopt"}, {"op": "add", "type": "text"}):
        _resp, msgs = browser.post(seite="category@catalog:tee", **data)
        assert any("eigenem Aufbau" in m for m in msgs), msgs
    Category.objects.create(slug="c00", name={"de": "Erste"})
    _resp, msgs = browser.post(seite="category@catalog:c00", op="add", type="text")
    assert not msgs  # у категории со своей схемой правки идут как обычно
