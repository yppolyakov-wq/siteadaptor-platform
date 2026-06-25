"""M20U-7 «Pages»: per-page настройки витрины (раскладки сеток страниц)."""

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
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/site/pages/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def test_pages_view_saves_per_page_layouts():
    tenant = TenantFactory(schema_name="public", slug="pv", name="PV")
    data = {
        "catalog_preset": "gallery",
        "stay_index_preset": "cols4",
        "events_index_preset": "cols3",
    }
    resp = views.pages_view(_request("post", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_layout"]["preset"] == "gallery"
    assert cfg["stay_index_layout"]["preset"] == "cols4"
    assert cfg["events_index_layout"]["preset"] == "cols3"


def test_pages_view_saves_related_layout():
    tenant = TenantFactory(schema_name="public", slug="pvr", name="PVR")
    resp = views.pages_view(_request("post", {"related_preset": "cols3"}, tenant))
    assert resp.status_code == 302
    assert siteconfig.normalize(tenant.site_config)["detail_related_layout"]["preset"] == "cols3"


def test_pages_view_get_renders_active_pages_only():
    # catalog активен, stays/events выключены → только селектор каталога.
    tenant = TenantFactory(
        schema_name="public", slug="pv2", name="PV2", disabled_modules=["stays", "events"]
    )
    body = views.pages_view(_request("get", tenant=tenant)).content.decode()
    assert 'name="catalog_preset"' in body
    assert 'name="stay_index_preset"' not in body
    assert 'name="events_index_preset"' not in body


def test_pages_view_save_preserves_other_config():
    tenant = TenantFactory(
        schema_name="public", slug="pv3", name="PV3", site_config={"hero_title": "Hallo"}
    )
    views.pages_view(_request("post", {"catalog_preset": "cols2"}, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"] == "Hallo" and cfg["catalog_layout"]["preset"] == "cols2"
