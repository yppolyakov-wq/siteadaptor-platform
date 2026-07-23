"""Шаблоны витрины (ранний срез M20): пресеты site_config + применение + галерея."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.views import site_view
from apps.promotions import public_views
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


@pytest.mark.parametrize(
    ("business_type", "template_key", "primary_section"),
    [
        ("friseur", "termine", "services"),
        ("werkstatt", "termine", "services"),
        ("handwerker", "handwerk", "before_after"),
        ("events", "veranstaltung", "events"),
        # E1 «задача-первым»: у отеля primary-задача (поиск дат/номера) должна
        # быть на дефолт-главной — раньше hotel не проверялся и дыра проскочила.
        ("hotel", "gastgeber", "stay_search"),
        ("hotel", "gastgeber", "stay_rooms"),
        # E2: tour_operator дефолтит на events-first veranstaltung (не about-first
        # dienstleister) — туры/события с датами на первом экране.
        ("tour_operator", "veranstaltung", "events"),
    ],
)
def test_s6_archetype_template_recommended_and_keeps_primary(
    business_type, template_key, primary_section
):
    # S6: у каждого нового архетипа есть рекомендованный шаблон (первым в галерее),
    # и он ВКЛЮЧАЕТ секцию-главного-товара (не прячет её, как generic-шаблоны).
    order = [t["key"] for t in sitetemplates.templates_for(business_type)]
    assert order[0] == template_key
    tpl = sitetemplates.get_template(template_key)
    assert primary_section in tpl["sections"]


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
    assert cfg["hero_style"] == "plain"  # minimal — белый баннер
    assert tenant.primary_color == "#111827"  # акцент шаблона
    assert tenant.site_config["onboarding"] == {"step": 2}  # onboarding не затёрт


def test_apply_template_fills_empty_texts():
    tenant = TenantFactory(schema_name="t_tpl2", business_type="bakery", site_config={})
    sitetemplates.apply_template(tenant, "laden")
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "promotions", "products", "about", "contact"]
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"]  # дефолт шаблона подставлен
    assert cfg["hero_style"] == "accent"
    assert tenant.primary_color == "#4f46e5"


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


def test_site_view_no_longer_touches_theme(rf, settings):
    """W6: тема (акцент/шрифт/стиль баннера) — единый источник в конструкторе главной.
    Сохранение «Site» темы НЕ трогает, даже если легаси-поля пришли в POST."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="t_acc",
        business_type="bakery",
        primary_color="#123456",
        site_config={"hero_style": "plain"},
    )
    user = get_user_model().objects.create_user("ua", "ua@test.de", "pw12345678")
    data = {"hero_accent": "on", "accent_color": "#0e7490", "enabled_hero": "on", "order_hero": "1"}

    resp = site_view(_request(rf, "post", user, tenant, data))
    assert resp.status_code in (301, 302)
    tenant.refresh_from_db()
    assert tenant.primary_color == "#123456"  # site_view тему не пишет (единый источник)
    assert siteconfig.normalize(tenant.site_config)["hero_style"] == "plain"


def test_site_view_rejects_invalid_accent(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="t_acc2", business_type="bakery", primary_color="#123456", site_config={}
    )
    user = get_user_model().objects.create_user("ub", "ub@test.de", "pw12345678")

    site_view(_request(rf, "post", user, tenant, {"accent_color": "rot"}))
    tenant.refresh_from_db()
    assert tenant.primary_color == "#123456"  # невалидный hex проигнорирован


def test_accent_hero_renders_in_storefront(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory.build(
        name="Hero Co",
        primary_color="#0e7490",
        site_config={"hero_style": "accent", "sections": [{"key": "hero", "enabled": True}]},
    )
    request = rf.get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant

    body = public_views.storefront_home(request).content.decode()
    assert "var(--accent" in body  # цветной hero использует CSS-переменную
    assert "#0e7490" in body  # переменная определена из primary_color
