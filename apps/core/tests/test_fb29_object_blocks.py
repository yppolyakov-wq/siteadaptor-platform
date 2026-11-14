"""FB-29.4b S3: свои блоки объекта (товар, услуга) — видны только на его странице.
Хост `product:<hex>` / `service:<hex>` в `page_blocks`, правка — на экране «Seitenaufbau»."""

import uuid

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory

from apps.booking.models import Service
from apps.catalog.models import Product
from apps.core import object_structure as ost
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
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _text(i, title):
    return {"key": "text", "id": f"b{i}", "enabled": True, "data": {"title": title}}


def _tenant(page_blocks=None, bt="online_shop"):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config={"page_blocks": page_blocks or {}},
    )
    connection.tenant = tenant
    return tenant


def _product(name="Darjeeling"):
    return Product.objects.create(name={"de": name, "en": ""}, base_price="9.90")


def _hosts(tenant):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return cfg.get("page_blocks") or {}


def _site(tenant, kind, obj):
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)
    tpl = Template("{% load siteui %}{% object_blocks kind obj %}")
    return tpl.render(Context({"request": request, "kind": kind, "obj": obj}))


# ───────────── данные ─────────────


def test_object_host_is_built_from_the_primary_key_only():
    p = _product()
    host = ost.object_host("product", p)
    assert host == f"product:{p.pk.hex}" and siteconfig.is_page_block_host(host)
    assert ost.object_host("product", None) == "" and ost.object_host("stay", p) == ""
    assert not siteconfig.is_page_block_host("product:../../etc")
    assert not siteconfig.is_page_block_host("product:" + "g" * 32)


def test_object_hosts_have_their_own_cap():
    blocks = {f"product:{uuid.uuid4().hex}": [_text(i, "x")] for i in range(70)}
    blocks["catalog:tee"] = [_text(99, "Tee")]
    out = siteconfig.normalize_page_blocks(blocks)
    assert sum(1 for k in out if k.startswith("product:")) == siteconfig._MAX_OBJECT_HOSTS
    assert "catalog:tee" in out, "объекты не вытесняют схемы категорий"


# ───────────── экран «Seitenaufbau» ─────────────


def test_unknown_object_is_refused():
    tenant = _tenant()
    ghost = f"product@product:{uuid.uuid4().hex}"
    assert site_schema.host_for(ghost) == ""
    _resp, msgs = Browser(tenant).post(seite=ghost, op="add", type="text")
    assert msgs and _hosts(tenant) == {}
    assert site_schema.host_for("product@catalog:tee") == ""
    assert site_schema.host_for("stay@product:" + "a" * 32) == ""


def test_own_block_is_added_through_the_draft_and_saved_to_the_object_host():
    tenant = _tenant()
    p = _product()
    code = ost.schema_code("product", p)
    b = Browser(tenant)
    html = b.get(f"?seite={code}")
    assert "Darjeeling" in html, "строка объекта есть в выборе страницы"
    resp, msgs = b.post(seite=code, op="add", type="text")
    assert resp.status_code == 302 and not msgs
    assert _hosts(tenant) == {}, "пока черновик"
    b.post(seite=code, op="save")
    hosts = _hosts(tenant)
    assert list(hosts) == [f"product:{p.pk.hex}"]
    assert "product_detail" not in hosts, "общие блоки страницы товара не тронуты"


def test_object_page_has_no_type_settings():
    tenant = _tenant()
    p = _product()
    assert site_schema.setting_codes(tenant, ost.schema_code("product", p)) == []


def test_the_sixty_first_object_is_refused_instead_of_vanishing():
    blocks = {f"product:{uuid.uuid4().hex}": [_text(i, "x")] for i in range(60)}
    tenant = _tenant(blocks)
    p = _product()
    _resp, msgs = Browser(tenant).post(seite=ost.schema_code("product", p), op="add", type="text")
    assert msgs, "владелец видит, что места нет"


# ───────────── витрина ─────────────


def test_own_blocks_show_only_on_the_objects_page():
    a, other = _product("Darjeeling"), _product("Assam")
    tenant = _tenant({f"product:{a.pk.hex}": [_text(1, "Nur bei Darjeeling")]})
    assert "Nur bei Darjeeling" in _site(tenant, "product", a)
    assert _site(tenant, "product", other).strip() == ""
    assert _site(tenant, "product", None).strip() == ""


def test_service_gets_its_own_blocks_too():
    s = Service.objects.create(name="Schnitt")
    tenant = _tenant({f"service:{s.pk.hex}": [_text(1, "Nur beim Schnitt")]}, bt="friseur")
    assert "Nur beim Schnitt" in _site(tenant, "service", s)


def test_detail_templates_place_the_object_blocks():
    import pathlib

    for name, kind in (("product_detail.html", "product"), ("service_detail.html", "service")):
        src = pathlib.Path("templates/storefront", name).read_text()
        assert f'{{% object_blocks "{kind}" {kind} %}}' in src, name


# ───────────── уборка ─────────────


def test_deleting_the_object_frees_its_host_with_translations():
    p = _product()
    host = f"product:{p.pk.hex}"
    tenant = _tenant({host: [_text(1, "Nur hier")]})
    cfg = dict(tenant.site_config)
    cfg["i18n"] = {"en": {"page_blocks": {host: [{"id": "b1", "data": {"title": "Only here"}}]}}}
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    assert ost.drop_blocks("product", p) is True
    fresh = Tenant.objects.get(pk=tenant.pk).site_config
    assert host not in (fresh.get("page_blocks") or {})
    assert host not in fresh["i18n"]["en"]["page_blocks"]


def test_reset_on_the_tab_removes_the_own_blocks():
    p = _product()
    host = f"product:{p.pk.hex}"
    tenant = _tenant({host: [_text(1, "Nur hier")]})
    assert ost.reset(p, "product") is not None
    assert host not in _hosts(tenant)
