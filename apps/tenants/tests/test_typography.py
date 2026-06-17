"""P2a: выбор системного шрифта витрины (font в site_config)."""

import pytest

from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def test_normalize_font_default_and_known():
    assert siteconfig.normalize({})["font"] == "system"
    assert siteconfig.normalize({"font": "serif"})["font"] == "serif"
    assert siteconfig.normalize({"font": "bogus"})["font"] == "system"  # неизвестный → дефолт


def test_font_stacks_mapping():
    body, head = siteconfig.font_stacks("serif")
    assert "serif" in head.lower()  # serif-заголовки
    assert "sans-serif" in body  # тело — sans
    # неизвестный ключ → system (sans/sans)
    b2, h2 = siteconfig.font_stacks("nope")
    assert b2 == h2 and "sans-serif" in b2


def test_storefront_home_injects_font_vars():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(site_config={"font": "serif"})
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "--font-head:" in body and "Georgia" in body  # serif-стек заголовков в :root
