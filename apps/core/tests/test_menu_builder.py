"""S7b: билдер меню /dashboard/site/menu/ — сохранение дерева + рендер.

Редактор на клиенте; сервер принимает JSON (menus_json), санитайзит через
siteconfig.normalize и мёржит в site_config. site_view («Site») больше НЕ
правит nav — переносит как есть (регрессия: пустая форма не гасит меню).
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def test_menu_builder_saves_tree_and_preserves_design():
    tenant = TenantFactory(
        schema_name="public", slug="mb", name="MB", site_config={"hero_title": "Hi"}
    )
    menus = {
        "top": {
            "style": "centered",
            "sticky": False,
            "items": [
                {
                    "label": "Speisekarte",
                    "type": "group",
                    "children": [
                        {"label": "Fastfood", "type": "category", "target": "ff"},
                        {"label": "Tisch", "type": "archetype", "target": "booking"},
                    ],
                },
                {"label": "Aktionen", "type": "anchor", "target": "aktionen"},
            ],
        },
        "bottom": {
            "enabled": True,
            "items": [{"label": "Korb", "type": "archetype", "target": "orders"}],
        },
    }
    resp = views.menu_builder_view(
        _request("post", "/dashboard/site/menu/", {"menus_json": json.dumps(menus)}, tenant)
    )
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    top = cfg["menus"]["top"]
    assert top["style"] == "centered" and top["sticky"] is False
    assert top["items"][0]["label"] == "Speisekarte"
    assert [c["label"] for c in top["items"][0]["children"]] == ["Fastfood", "Tisch"]
    assert cfg["menus"]["bottom"]["enabled"] is True
    assert cfg["hero_title"] == "Hi"  # дизайн не затёрт


def test_menu_builder_bad_json_is_ignored():
    tenant = TenantFactory(schema_name="public", slug="mb2", name="MB2")
    resp = views.menu_builder_view(
        _request("post", "/dashboard/site/menu/", {"menus_json": "{not json"}, tenant)
    )
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    # битый JSON → menus={} → выводится из nav (легаси-шапка), без падения.
    assert cfg["menus"]["top"]["items"]


def test_menu_builder_get_renders_with_targets():
    tenant = TenantFactory(schema_name="public", slug="mb3", name="MB3")
    resp = views.menu_builder_view(_request("get", "/dashboard/site/menu/", tenant=tenant))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'id="builder-data"' in body  # данные для JS-редактора
    assert "menus_json" in body  # скрытое поле сериализации


def test_site_view_does_not_touch_legacy_nav():
    # S7b: «Site» переносит nav как есть (меню правится в билдере).
    tenant = TenantFactory(
        schema_name="public",
        slug="sv2",
        name="SV2",
        site_config={
            "nav": {
                "style": "minimal",
                "sticky": False,
                "items": [
                    {"key": "offers", "enabled": True},
                ],
            }
        },
    )
    resp = views.site_view(_request("post", "/dashboard/site/", {"font": "serif"}, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["nav"]["style"] == "minimal"  # не сброшен в classic
    assert cfg["font"] == "serif"  # дизайн-поле сохранилось
