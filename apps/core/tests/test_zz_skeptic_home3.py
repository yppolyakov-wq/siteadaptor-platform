import pytest
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
def test_probe():
    p = ProductFactory(name={"de": "AktivBrot"})
    print("\nstock_quantity:", p.stock_quantity, "in_stock:", p.in_stock, "has_variants:", p.has_variants)
    tenant = TenantFactory(schema_name="public", slug="probe3", name="Hofladen")
    from apps.core import context as ctx
    r = _req(tenant)
    c = ctx.storefront(r)
    print("quick_add ctx:", c.get("storefront_quick_add"), "| wishlist:", c.get("storefront_wishlist_enabled"))
    body = public_views.storefront_home(r).content.decode()
    print("AktivBrot in home:", "AktivBrot" in body)
    print("data-wish-form in home:", "data-wish-form" in body)
    print("storefront-cart-add action in home:", "hinzu" in body or "cart-add" in body)
    body2 = public_views.product_list(_req(tenant, "/sortiment/")).content.decode()
    print("AktivBrot in catalog:", "AktivBrot" in body2, "| csrf in catalog:", body2.count("csrf"))
    i = body2.find("<form")
    print("--- first form in catalog ---")
    print(body2[i:i+400] if i >= 0 else "NO FORM")
