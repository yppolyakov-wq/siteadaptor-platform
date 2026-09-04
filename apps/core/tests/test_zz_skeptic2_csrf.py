"""ВРЕМЕННЫЙ пробник скептика: CSRF-кука/Vary/токен на кэш-хите главной."""

import re

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, override_settings

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _get(tenant, cookies=None):
    request = RequestFactory().get("/")
    if cookies:
        request.COOKIES.update(cookies)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    mw = CsrfViewMiddleware(lambda r: public_views.storefront_home(r))
    return request, mw(request)


@override_settings(CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=120)
def test_probe_csrf_cookie_on_cache_hit():
    cache.clear()
    from apps.catalog.tests.factories import CategoryFactory
    ProductFactory(name={"de": "AktivBrot"}, category=CategoryFactory(name={"de": "Brot"}))
    tenant = TenantFactory(slug="probe2", name="Hofladen")
    from apps.core import modules

    print("orders active:", modules.is_module_active(tenant, "orders"))

    r1, resp1 = _get(tenant)
    b1 = resp1.content.decode()
    tok1 = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', b1)
    print("R1 status", resp1.status_code)
    print("R1 csrf form in body:", bool(tok1), "| <form:", b1.count("<form"), "| product:", "AktivBrot" in b1)
    print("R1 Set-Cookie keys:", list(resp1.cookies.keys()))
    print("R1 Vary:", resp1.get("Vary"))

    r2, resp2 = _get(tenant)
    b2 = resp2.content.decode()
    tok2 = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', b2)
    print("R2 identical body:", b1 == b2)
    print("R2 Set-Cookie keys:", list(resp2.cookies.keys()))
    print("R2 Vary:", resp2.get("Vary"))
    print("R2 token equals R1 token:", bool(tok2) and bool(tok1) and tok1.group(1) == tok2.group(1))

    # третий посетитель СО СВОЕЙ csrftoken-кукой (из прежнего визита)
    from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret

    own_secret = _get_new_csrf_string()
    r3, resp3 = _get(tenant, cookies={"csrftoken": _mask_cipher_secret(own_secret)})
    b3 = resp3.content.decode()
    tok3 = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', b3)
    print("R3 body served from cache (== R1):", b1 == b3)
    print("R3 token == R1 token (чужой):", bool(tok3) and tok3.group(1) == tok1.group(1))

    # POST на storefront-cart-add токеном из кэшированной страницы, без csrf-куки
    if tok1:
        post = RequestFactory().post("/warenkorb/add/", {"csrfmiddlewaretoken": tok1.group(1)})
        SessionMiddleware(lambda r: None).process_request(post)
        post.tenant = tenant
        mw = CsrfViewMiddleware(lambda r: None)
        mw.process_request(post)
        rej = mw.process_view(post, lambda r: None, (), {})
        print("POST без куки → status:", getattr(rej, "status_code", None))
        # и посетитель со своей кукой, но чужим (кэшированным) токеном
        post2 = RequestFactory().post("/warenkorb/add/", {"csrfmiddlewaretoken": tok1.group(1)})
        post2.COOKIES["csrftoken"] = _mask_cipher_secret(own_secret)
        SessionMiddleware(lambda r: None).process_request(post2)
        post2.tenant = tenant
        mw2 = CsrfViewMiddleware(lambda r: None)
        mw2.process_request(post2)
        rej2 = mw2.process_view(post2, lambda r: None, (), {})
        print("POST со СВОЕЙ кукой + чужим токеном → status:", getattr(rej2, "status_code", None))
