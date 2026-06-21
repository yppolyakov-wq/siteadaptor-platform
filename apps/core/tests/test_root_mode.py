"""S4: режим корня витрины — standalone (корень → лендинг архетипа) ↔ общая главная."""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _home_request(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return req


def test_default_root_renders_homepage():
    tenant = TenantFactory.build()
    resp = public_views.storefront_home(_home_request(tenant))
    assert resp.status_code == 200  # обычная главная


def test_standalone_root_redirects_to_archetype_landing():
    tenant = TenantFactory.build(site_config={"storefront_root": "catalog"})
    resp = public_views.storefront_home(_home_request(tenant))
    assert resp.status_code == 302
    assert resp["Location"] == "/sortiment/"


def test_standalone_ignored_when_module_inactive():
    tenant = TenantFactory.build(
        disabled_modules=["booking"], site_config={"storefront_root": "booking"}
    )
    resp = public_views.storefront_home(_home_request(tenant))
    assert resp.status_code == 200  # модуль выключен → фолбэк на главную


def test_home_builder_saves_storefront_root():
    tenant = TenantFactory(schema_name="public", slug="r4", name="R4")
    req = RequestFactory().post("/dashboard/site/home/", {"storefront_root": "catalog"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.home_builder_view(req)
    assert resp.status_code == 302
    assert siteconfig.normalize(tenant.site_config)["storefront_root"] == "catalog"
