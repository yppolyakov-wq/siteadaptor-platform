"""Спринт D.2b: билдер C-блоков — добавление, правка, порядок, удаление, round-trip."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data, tenant):
    request = RequestFactory().post("/dashboard/site/home/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    return request


def _cblocks(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [s for s in cfg["sections"] if s["key"] in siteconfig.REPEATABLE_BLOCKS]


def test_add_block_appends_empty_cblock():
    tenant = TenantFactory(slug="cb1", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    blocks = _cblocks(tenant)
    assert len(blocks) == 1 and blocks[0]["key"] == "text"


def test_save_persists_cblock_edits_and_keeps_fixed_sections():
    tenant = TenantFactory(slug="cb2", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    # основное сохранение: правим текст блока + он включён, фикс-секции тоже шлём.
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"order_cb_{bid}": "3",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "Mein Titel",
        f"cb_{bid}_body": "Mein Text",
        "enabled_contact": "on",
        "order_contact": "5",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    blocks = _cblocks(tenant)
    assert len(blocks) == 1  # C-блок НЕ потерян при сохранении главной
    assert blocks[0]["data"]["title"] == "Mein Titel"
    assert blocks[0]["data"]["body"] == "Mein Text"
    # фикс-секция contact сохранилась включённой
    cfg = siteconfig.normalize(tenant.site_config)
    assert any(s["key"] == "contact" and s["enabled"] for s in cfg["sections"])


def test_delete_checkbox_removes_cblock():
    tenant = TenantFactory(slug="cb3", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "button"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "button",
        f"delete_cb_{bid}": "on",
        f"cb_{bid}_label": "X",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    assert _cblocks(tenant) == []
