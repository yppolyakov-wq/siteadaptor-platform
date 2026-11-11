"""FB-27 R0: предохранители «два писателя структуры».

Студия и «Seitenaufbau» пишут одни ключи (`sections`, `page_blocks`). Открытая вкладка
Студии не должна откатывать схему, сохранённую тем временем в другом месте.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import site_schema, views
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, data=None, tenant=None, **kwargs):
    req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {}, **kwargs)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _toggle_first_section(tenant_pk):
    """«Другой писатель»: меняет видимость первой секции прямо в базе."""
    row = Tenant.objects.get(pk=tenant_pk)
    cfg = siteconfig.normalize(row.site_config)
    cfg["sections"][0]["enabled"] = not cfg["sections"][0]["enabled"]
    Tenant.objects.filter(pk=tenant_pk).update(site_config=cfg)
    return cfg["sections"][0]["key"], cfg["sections"][0]["enabled"]


def test_structure_hash_ignores_texts_and_sees_structure():
    cfg = siteconfig.normalize({})
    h0 = site_schema.structure_hash(cfg)
    texts = {**cfg, "hero_title": "Neuer Titel", "about_text": "Anders"}
    assert site_schema.structure_hash(texts) == h0
    moved = {**cfg, "sections": [cfg["sections"][1], cfg["sections"][0], *cfg["sections"][2:]]}
    assert site_schema.structure_hash(moved) != h0
    toggled = json.loads(json.dumps(cfg))
    toggled["sections"][0]["enabled"] = not toggled["sections"][0]["enabled"]
    assert site_schema.structure_hash(toggled) != h0
    blocks = {
        **cfg,
        "page_blocks": {"info": [{"id": "pb-1", "key": "text", "enabled": True, "data": {}}]},
    }
    assert site_schema.structure_hash(blocks) != h0


def test_autosave_keeps_structure_saved_meanwhile():
    """Автосейв черновика писал `{**published}` из данных начала запроса и стирал
    схему, сохранённую между загрузкой и записью."""
    tenant = TenantFactory(site_config=siteconfig.normalize({}))
    req = _request(
        "post",
        json.dumps({"hero_title": "Entwurf"}),
        tenant,
        content_type="application/json",
    )
    key, enabled = _toggle_first_section(tenant.pk)  # после того, как запрос «загрузил» тенанта
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    stored = Tenant.objects.get(pk=tenant.pk).site_config
    assert isinstance(stored.get("_draft"), dict)
    row = next(s for s in siteconfig.normalize(stored)["sections"] if s["key"] == key)
    assert row["enabled"] is enabled


def test_builder_renders_structure_hash():
    tenant = TenantFactory(site_config=siteconfig.normalize({}))
    html = views.home_builder_view(_request("get", tenant=tenant)).content.decode()
    h = site_schema.structure_hash(tenant.site_config)
    assert f'name="struct_hash" value="{h}"' in html


def test_save_with_stale_structure_is_refused():
    tenant = TenantFactory(site_config=siteconfig.normalize({}))
    stale = site_schema.structure_hash(tenant.site_config)
    key, enabled = _toggle_first_section(tenant.pk)
    req = _request("post", {"struct_hash": stale, "hero_title": "Aus alter Registerkarte"}, tenant)
    resp = views.home_builder_view(req)
    assert resp.status_code == 302
    stored = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    row = next(s for s in stored["sections"] if s["key"] == key)
    assert row["enabled"] is enabled  # чужая правка цела
    assert stored.get("hero_title") != "Aus alter Registerkarte"  # ничего не записано
    assert any("Seitenaufbau" in str(m) for m in get_messages(req))


def test_save_with_current_structure_passes():
    tenant = TenantFactory(site_config=siteconfig.normalize({}))
    h = site_schema.structure_hash(tenant.site_config)
    req = _request("post", {"struct_hash": h, "content_sections_present": "1"}, tenant)
    assert views.home_builder_view(req).status_code == 302
    assert not any("Seitenaufbau" in str(m) for m in get_messages(req))


def test_save_without_hash_field_keeps_working():
    """Старые формы и прочие вызовы без поля — как прежде."""
    tenant = TenantFactory(site_config=siteconfig.normalize({}))
    req = _request("post", {}, tenant)
    assert views.home_builder_view(req).status_code == 302
    assert not any("Seitenaufbau" in str(m) for m in get_messages(req))


def test_refusal_drops_stale_draft_and_keeps_other_keys():
    """Отказ убирает черновик Студии (он собран от устаревшей структуры), но не трогает
    остальное — в том числе ключи, которых `normalize` не знает."""
    base = {**siteconfig.normalize({}), "notify": {"order": {"email": False}}}
    tenant = TenantFactory(site_config=base)
    stale = site_schema.structure_hash(tenant.site_config)
    _toggle_first_section(tenant.pk)
    row = Tenant.objects.get(pk=tenant.pk)
    Tenant.objects.filter(pk=tenant.pk).update(
        site_config={**row.site_config, "_draft": {"x": 1}, "_draft_ts": "t", "_draft_lang": "de"}
    )
    req = _request("post", {"struct_hash": stale}, tenant)
    req.session["site_preview_draft"] = {"x": 1}
    views.home_builder_view(req)
    stored = Tenant.objects.get(pk=tenant.pk).site_config
    assert not [k for k in stored if k.startswith("_draft")]
    assert "site_preview_draft" not in req.session
    assert stored["notify"] == {"order": {"email": False}}


def test_hash_does_not_depend_on_draft_keys():
    cfg = siteconfig.normalize({})
    with_draft = {**cfg, "_draft": {"sections": []}, "_draft_ts": "t"}
    assert site_schema.structure_hash(with_draft) == site_schema.structure_hash(cfg)


def test_hash_sees_category_and_page_hosts():
    cfg = siteconfig.normalize({})
    h0 = site_schema.structure_hash(cfg)
    for host in ("catalog", "info"):
        blocks = {**cfg, "page_blocks": {host: [{"id": "pb-9", "key": "text", "enabled": True}]}}
        assert site_schema.structure_hash(blocks) != h0, host
