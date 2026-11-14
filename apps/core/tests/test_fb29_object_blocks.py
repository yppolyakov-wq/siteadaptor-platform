"""FB-29.4b S3: свои блоки объекта (товар, услуга) — видны только на его странице.
Хост `product:<hex>` / `service:<hex>` в `page_blocks`, правка — на экране «Seitenaufbau»."""

import uuid
from types import SimpleNamespace

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
    blocks = {f"product:{_product(str(i)).pk.hex}": [_text(i, "x")] for i in range(60)}
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


def test_reset_on_the_tab_keeps_the_own_blocks():
    """Ревью: сброс вкладки — право каталога; блоки сайта он не трогает."""
    p = _product()
    host = f"product:{p.pk.hex}"
    tenant = _tenant({host: [_text(1, "Nur hier")]})
    p.page_override = {"hidden": ["reviews"]}
    changed = ost.apply_post(p, "product", {"page_override_present": "1", "ps_reset": "1"})
    assert changed == ["page_override"] and host in _hosts(tenant)


def test_ghost_hosts_are_purged_when_room_is_needed():
    """Ревью: блоки удалённых объектов освобождают место — без хука на каждое удаление."""
    blocks = {f"product:{uuid.uuid4().hex}": [_text(i, "x")] for i in range(60)}
    tenant = _tenant(blocks)
    p = _product()
    b = Browser(tenant)
    resp, msgs = b.post(seite=ost.schema_code("product", p), op="add", type="text")
    assert not msgs, "призраки убраны, место нашлось"
    assert not any(k.startswith("product:") for k in _hosts(tenant))


def test_deleted_to_trash_product_keeps_its_blocks_until_room_is_needed():
    p = _product()
    host = f"product:{p.pk.hex}"
    tenant = _tenant({host: [_text(1, "Nur hier")]})
    p.delete()  # корзина: товар можно вернуть — блоки целы
    assert host in _hosts(tenant)


def test_object_draft_survives_opening_another_page():
    tenant = _tenant()
    p = _product()
    code = ost.schema_code("product", p)
    b = Browser(tenant)
    b.post(seite=code, op="add", type="text")
    html = b.get("?seite=home")
    assert "Darjeeling" in html, "черновик объекта виден среди прочих черновиков"
    b.post(seite=code, op="save")
    assert list(_hosts(tenant)) == [f"product:{p.pk.hex}"]


def test_enter_in_the_form_does_not_press_reset():
    import pathlib

    part = pathlib.Path("templates/tenant/_object_structure.html").read_text()
    assert part.index("data-ps-default-submit") < part.index('name="ps_reset"')


def test_host_pattern_rejects_a_trailing_newline():
    assert not siteconfig.is_object_host("product:" + "a" * 32 + "\n")


def test_object_screen_links_back_to_the_object():
    """S8: со строки своих блоков — путь назад к карточке товара."""
    tenant = _tenant()
    p = _product()
    html = Browser(tenant).get(f"?seite={ost.schema_code('product', p)}")
    assert "data-schema-object-back" in html and f"/products/{p.pk}/edit/" in html
    assert "data-schema-object-back" not in Browser(tenant).get("?seite=home")


# --- R3: свои блоки объекта над общими блоками страницы ---


def test_own_blocks_can_stand_above_the_shared_ones():
    p = _product()
    tenant = _tenant({f"product:{p.pk.hex}": [_text(1, "Nur hier")]})
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)

    def render(part):
        tpl = Template("{% load siteui %}{% object_blocks 'product' obj '" + part + "' %}")
        return tpl.render(Context({"request": request, "obj": p}))

    assert "Nur hier" in render("after") and render("before").strip() == ""
    p.page_override = {"blocks_first": True}
    assert "Nur hier" in render("before") and render("after").strip() == ""


def test_position_is_saved_from_the_tab_and_is_presence_minimal():
    assert ost.clean({"blocks_first": "1"}, "catalog") == {"blocks_first": True}
    assert ost.clean({"blocks_first": ""}, "catalog") == {}
    post = {"page_override_present": "1", "ps_blocks_first": "1"}
    assert ost.from_post(post, "catalog") == {"blocks_first": True}
    assert ost.from_post({"page_override_present": "1"}, "catalog") == {}
    assert ost.deviations(SimpleNamespace(page_override={"blocks_first": True}), "catalog") == 0


def test_detail_templates_render_own_blocks_on_both_sides():
    import pathlib

    for name, kind in (("product_detail.html", "product"), ("service_detail.html", "service")):
        src = pathlib.Path("templates/storefront", name).read_text()
        before = src.index(f'{{% object_blocks "{kind}" {kind} "before" %}}')
        shared = src.index(f'{{% page_blocks "{kind}_detail" %}}')
        after = src.index(f'{{% object_blocks "{kind}" {kind} %}}')
        assert before < shared < after, name
