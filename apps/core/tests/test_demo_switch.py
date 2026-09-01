"""DL-8e: смена шаблона на демо-витрине (сессия посетителя, read-only).

Гейт — только демо-тенанты (слаги демо-китов); конфиг тенанта не пишется;
оверлей — тот же stateless-механизм, что у ?preview=1&bundle=.
"""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import demo_switch
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/", tenant=None, data=None):
    request = RequestFactory().get(path, data or {})
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def test_is_demo_by_kit_slug():
    assert demo_switch.is_demo_tenant(TenantFactory.build(slug="aktionsmarkt")) is True
    assert demo_switch.is_demo_tenant(TenantFactory.build(slug="hotel")) is True
    assert demo_switch.is_demo_tenant(TenantFactory.build(slug="baecker-mueller")) is False
    assert demo_switch.is_demo_tenant(None) is False


def test_switch_sets_session_and_redirects_only_on_demo():
    demo = TenantFactory.build(slug="aktionsmarkt", business_type="grocery")
    request = _req("/design-testen/", demo, {"tpl": "deal_neon", "next": "/aktionen/"})
    resp = demo_switch.demo_design_switch(request)
    assert resp.status_code == 302 and resp["Location"] == "/aktionen/"
    assert request.session[demo_switch.SESSION_KEY] == "deal_neon"
    # «standard» сбрасывает; мусорный ключ не пишется; //host не редиректим.
    request = _req("/design-testen/", demo, {"tpl": "junk", "next": "//evil.example"})
    request.session[demo_switch.SESSION_KEY] = "deal_neon"
    resp = demo_switch.demo_design_switch(request)
    assert resp["Location"] == "/" and request.session[demo_switch.SESSION_KEY] == "deal_neon"
    request = _req("/design-testen/", demo, {"tpl": "standard"})
    request.session[demo_switch.SESSION_KEY] = "deal_neon"
    demo_switch.demo_design_switch(request)
    assert demo_switch.SESSION_KEY not in request.session
    # Не-демо тенант → 404 (у живого бизнеса посетитель ничего не переключит).
    with pytest.raises(Http404):
        demo_switch.demo_design_switch(
            _req("/design-testen/", TenantFactory.build(slug="realshop"), {"tpl": "deal_neon"})
        )


def test_session_overlay_renders_choice_on_demo_home():
    """Выбор из сессии красит витрину (кожа + композиция), пилюля показывает
    список; конфиг тенанта не тронут. На не-демо сессия игнорируется."""
    from apps.promotions.public_views import storefront_home

    demo = TenantFactory.build(slug="aktionsmarkt", business_type="grocery")
    request = _req("/", demo)
    request.session[demo_switch.SESSION_KEY] = "deal_neon"
    html = storefront_home(request).content.decode()
    assert ' data-sf-look="neon"' in html
    assert 'var tenantDark = "dark" === "dark"' in html  # кожа neon
    assert "data-demo-design" in html  # пилюля «Design testen»
    assert demo.site_config in (None, {}, demo.site_config)  # read-only

    other = TenantFactory.build(slug="realshop", business_type="grocery")
    request = _req("/", other)
    request.session[demo_switch.SESSION_KEY] = "deal_neon"
    html = storefront_home(request).content.decode()
    assert ' data-sf-look="neon"' not in html
    assert "data-demo-design" not in html
