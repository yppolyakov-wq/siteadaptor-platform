"""UD4d: кабинет «Benachrichtigungen» — рендер матрицы + сохранение/сброс."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _req(method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/settings/notifications/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory(business_type="restaurant")
    return req


def test_get_renders_matrix_and_owner_section():
    html = views.notifications_settings(_req()).content.decode()
    assert "Benachrichtigungen" in html
    assert "c-order-ready-telegram" in html  # чекбокс матрицы клиента
    assert 'name="o-email"' in html  # owner-каналы


def test_post_saves_customer_and_owner_prefs():
    tenant = TenantFactory(business_type="restaurant")
    resp = views.notifications_settings(
        _req("post", {"c-order-ready-email": "on", "o-email": "on"}, tenant=tenant)
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    node = tenant.site_config["notify"]
    assert node["customer"]["order:ready"] == {"email": True, "telegram": False}
    assert node["owner"] == {"email": True, "telegram": False}


def test_save_preserves_owner_linkage_keys():
    tenant = TenantFactory(business_type="restaurant")
    tenant.site_config = {"notify": {"owner_chat_id": "999", "owner_link_token": "tok"}}
    tenant.save(update_fields=["site_config"])
    views.notifications_settings(_req("post", {"o-email": "on"}, tenant=tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["notify"]["owner_chat_id"] == "999"
    assert tenant.site_config["notify"]["owner_link_token"] == "tok"


def test_disconnect_owner_clears_chat_id():
    tenant = TenantFactory(business_type="restaurant")
    tenant.site_config = {"notify": {"owner_chat_id": "999", "owner_link_token": "tok"}}
    tenant.save(update_fields=["site_config"])
    views.notifications_settings(_req("post", {"action": "disconnect_owner"}, tenant=tenant))
    tenant.refresh_from_db()
    assert "owner_chat_id" not in tenant.site_config["notify"]
    assert tenant.site_config["notify"]["owner_link_token"] == "tok"  # токен цел
