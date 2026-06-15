"""Шаблоны витрины (ранний срез M20): пресеты site_config + применение + галерея."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.views import site_view
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _enabled(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [s["key"] for s in cfg["sections"] if s["enabled"]]


def _request(rf, method, user, tenant, data=None):
    request = getattr(rf, method)("/dashboard/site/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def test_templates_for_puts_recommended_first():
    order = [t["key"] for t in sitetemplates.templates_for("cafe")]
    assert order[0] == "gastro"  # cafe → рекомендован «gastro»
    # все шаблоны присутствуют ровно один раз
    assert sorted(order) == sorted(t["key"] for t in sitetemplates.TEMPLATES)


def test_apply_template_sets_layout_and_keeps_texts_and_onboarding():
    tenant = TenantFactory(
        schema_name="t_tpl",
        business_type="bakery",
        site_config={"hero_title": "Mein Laden", "onboarding": {"step": 2}},
    )
    assert sitetemplates.apply_template(tenant, "minimal") is True
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "contact"]  # раскладка «minimal»
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"] == "Mein Laden"  # непустой текст сохранён
    assert tenant.site_config["onboarding"] == {"step": 2}  # onboarding не затёрт


def test_apply_template_fills_empty_texts():
    tenant = TenantFactory(schema_name="t_tpl2", business_type="bakery", site_config={})
    sitetemplates.apply_template(tenant, "laden")
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "promotions", "products", "about", "contact"]
    assert siteconfig.normalize(tenant.site_config)["hero_title"]  # дефолт шаблона подставлен


def test_apply_unknown_template_is_noop():
    tenant = TenantFactory(schema_name="t_tpl3")
    assert sitetemplates.apply_template(tenant, "does-not-exist") is False


def test_site_view_apply_template(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="t_view", business_type="cafe", site_config={})
    user = get_user_model().objects.create_user("u", "u@test.de", "pw12345678")

    resp = site_view(
        _request(rf, "post", user, tenant, {"action": "apply_template", "template": "gastro"})
    )
    assert resp.status_code in (301, 302)
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "products", "promotions", "contact"]


def test_site_view_gallery_renders(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="t_view2", business_type="bakery", disabled_modules=[])
    user = get_user_model().objects.create_user("u2", "u2@test.de", "pw12345678")

    html = site_view(_request(rf, "get", user, tenant)).content.decode()
    assert "Klassischer Laden" in html  # карточка шаблона в галерее
    assert "Café &amp; Restaurant" in html
