"""Пробник: реально ли на главной есть csrf-форма (карточка товара / сердечко / newsletter)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, override_settings

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
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
    cat = CategoryFactory(name={"de": "Brot"})
    p = ProductFactory(name={"de": "AktivBrot"}, category=cat)
    print("\nproduct active:", p.is_active, "in_stock:", p.in_stock, "cat:", p.category_id)
    tenant = TenantFactory(schema_name="public", slug="probe2b", name="Hofladen")
    from apps.core import context

    r = _req(tenant)
    ctx = context.storefront_settings(r) if hasattr(context, "storefront_settings") else None
    print("context fns:", [n for n in dir(context) if not n.startswith("_")][:20])
    body = public_views.storefront_home(r).content.decode()
    print("len body:", len(body))
    print("AktivBrot in home:", "AktivBrot" in body)
    print("csrfmiddlewaretoken count:", body.count("csrfmiddlewaretoken"))
    print("csrf count:", body.count("csrf"))
    print("<form count:", body.count("<form"))
    print("data-wish-form:", body.count("data-wish-form"))
    print("R1 NEEDS_UPDATE:", r.META.get("CSRF_COOKIE_NEEDS_UPDATE"))
    i = body.find("<form")
    print("--- first form ---")
    print(body[i : i + 300] if i >= 0 else "NO FORM")
    # каталог для сравнения
    r2 = _req(tenant, "/sortiment/")
    b2 = public_views.product_list(r2).content.decode()
    print("catalog: AktivBrot", "AktivBrot" in b2, "| csrfmiddlewaretoken", b2.count("csrfmiddlewaretoken"),
          "| <form", b2.count("<form"), "| NEEDS_UPDATE", r2.META.get("CSRF_COOKIE_NEEDS_UPDATE"))
