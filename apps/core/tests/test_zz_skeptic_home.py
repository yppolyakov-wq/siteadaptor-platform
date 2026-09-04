"""ВРЕМЕННЫЙ пробник скептика #2 — реальная главная витрины и csrf в теле."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant):
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=120)
def test_probe_home_has_csrf_and_is_cached():
    cache.clear()
    ProductFactory(name={"de": "AktivBrot"})
    tenant = TenantFactory(schema_name="public", slug="probe", name="Hofladen")
    from apps.core import modules

    print("orders active:", modules.is_module_active(tenant, "orders"))
    r1 = _req(tenant)
    body1 = public_views.storefront_home(r1).content.decode()
    print("csrfmiddlewaretoken in body:", "csrfmiddlewaretoken" in body1)
    print("CSRF_COOKIE_NEEDS_UPDATE:", r1.META.get("CSRF_COOKIE_NEEDS_UPDATE"))
    print("cart-add form:", "js-add-form" in body1, "| wish form:", "data-wish-form" in body1)
    import re

    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', body1)
    print("token1:", (m.group(1)[:12] + "...") if m else None)

    r2 = _req(tenant)
    body2 = public_views.storefront_home(r2).content.decode()
    print("second request cached (identical body):", body1 == body2)
    print("second request NEEDS_UPDATE:", r2.META.get("CSRF_COOKIE_NEEDS_UPDATE"))
    m2 = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', body2)
    print("token2 == token1:", bool(m2) and m2.group(1) == (m.group(1) if m else None))
