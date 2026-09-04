import pytest, re
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, override_settings
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"

def _req(tenant, path="/"):
    r = RequestFactory().get(path)
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.tenant = tenant
    return r

@override_settings(PUBLIC_PAGE_CACHE_TTL=0)
def test_probe_body():
    ProductFactory(name={"de": "AktivBrot"})
    tenant = TenantFactory(schema_name="public", slug="probe2", name="Hofladen")
    body = public_views.storefront_home(_req(tenant)).content.decode()
    i = body.find("js-add-form")
    print("\n--- around js-add-form ---")
    print(body[i-300:i+500])
    print("--- csrf occurrences:", body.count("csrf"), "---")
    # для сравнения: страница каталога (не кэшируется)
    body2 = public_views.product_list(_req(tenant, "/sortiment/")).content.decode()
    print("catalog has csrfmiddlewaretoken:", "csrfmiddlewaretoken" in body2)
