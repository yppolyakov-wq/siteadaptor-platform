"""Track C2: конструктор витрины v1 — нормализация конфига, рендер, кабинет."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/", data=None, tenant=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build(name="Bäckerei X")
    if user is not None:
        request.user = user
    return request


def _owner():
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


# --- normalize -----------------------------------------------------------------


def test_jobs_vehicle_flag_defaults_false():
    # A9: режим Kfz-Werkstatt (структурные авто-поля) выключен по умолчанию
    assert siteconfig.normalize({})["jobs_vehicle"] is False
    assert siteconfig.normalize({"jobs_vehicle": True})["jobs_vehicle"] is True


def test_quick_add_defaults_true_and_can_disable():
    # T2c: быстрый заказ включён по умолчанию; владелец может вернуть «как раньше».
    assert siteconfig.normalize({})["quick_add"] is True
    assert siteconfig.normalize({"quick_add": False})["quick_add"] is False


def test_normalize_empty_gives_defaults():
    config = siteconfig.normalize({})
    keys = [s["key"] for s in config["sections"]]
    # порядок реестра SECTIONS (M20 ⑤ + P3 trust — все новые по умолчанию выкл)
    assert keys == [
        "hero",
        "usp_bar",
        "stay_search",
        "stay_rooms",
        "services",
        "promotions",
        "categories",
        "products",
        "events",
        "archetypes",
        "about",
        "process",
        "team",
        "cta",
        "testimonials",
        "trust",
        "reviews",
        "faq",
        "gallery",
        "before_after",
        "contact",
    ]
    enabled = {s["key"] for s in config["sections"] if s["enabled"]}
    assert enabled == {"promotions", "products", "contact"}  # новые — по умолчанию выкл
    assert config["hero_title"] == ""


def test_normalize_drops_unknown_and_appends_missing():
    config = siteconfig.normalize(
        {"sections": [{"key": "evil"}, {"key": "about", "enabled": True}], "hero_title": 42}
    )
    keys = [s["key"] for s in config["sections"]]
    assert "evil" not in keys
    assert keys[0] == "about"  # сохранённый порядок — впереди
    assert set(keys) == {k for k, _l, _d in siteconfig.SECTIONS}
    assert config["hero_title"] == ""  # не-строка затёрта


def test_normalize_tolerates_garbage():
    assert siteconfig.normalize(None)["sections"]
    assert siteconfig.normalize([1, 2])["sections"]
    assert siteconfig.normalize({"sections": "nope"})["sections"]


# --- витрина -------------------------------------------------------------------


def test_home_respects_disabled_promotions():
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "promotions", "enabled": False}]}
    )
    body = public_views.storefront_home(_req(tenant=tenant)).content.decode()
    assert "Current offers" not in body


def test_home_renders_hero_and_about_in_order():
    tenant = TenantFactory.build(
        name="Bäckerei X",
        site_config={
            "sections": [
                {"key": "about", "enabled": True},
                {"key": "hero", "enabled": True},
                {"key": "promotions", "enabled": False},
                {"key": "products", "enabled": False},
                {"key": "contact", "enabled": False},
            ],
            "hero_title": "Willkommen!",
            "about_text": "Seit 1950 backen wir Brot.",
        },
    )
    body = public_views.storefront_home(_req(tenant=tenant)).content.decode()
    assert "Willkommen!" in body
    assert "Seit 1950" in body
    assert body.index("Seit 1950") < body.index("Willkommen!")  # about раньше hero


def test_home_contact_section_shows_tenant_data():
    tenant = TenantFactory.build(
        address="Hauptstr. 1",
        opening_hours="Mo–Fr 7–18",
        site_config={"sections": [{"key": "contact", "enabled": True}]},
    )
    body = public_views.storefront_home(_req(tenant=tenant)).content.decode()
    assert "Hauptstr. 1" in body
    assert "Mo–Fr 7–18" in body


# --- кабинет «Site» ------------------------------------------------------------


def test_site_view_get_links_to_homepage_builder():
    # S2b: композиция секций уехала на /dashboard/site/home/ — на «Site»
    # остаётся ссылка-карточка на конструктор главной.
    body = core_views.site_view(_req("get", "/dashboard/site/", user=_owner())).content.decode()
    assert "Homepage builder" in body
    assert "site/home/" in body


def test_site_view_post_saves_texts_and_preserves_sections():
    # S2b: site_view сохраняет тексты/дизайн, но НЕ перестраивает секции из
    # своей формы — композицию ведёт home_builder. Пустые order_/enabled_ не
    # должны гасить блоки.
    tenant = TenantFactory(site_config={"sections": [{"key": "promotions", "enabled": True}]})
    data = {
        "hero_title": "Willkommen!",
        "hero_text": "  Schön, dass Sie da sind.  ",
        "about_title": "",
        "about_text": "Familienbetrieb.",
    }
    resp = core_views.site_view(
        _req("post", "/dashboard/site/", data, tenant=tenant, user=_owner())
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    config = tenant.site_config
    assert config["hero_title"] == "Willkommen!"
    assert config["hero_text"] == "Schön, dass Sie da sind."  # trim
    enabled = {s["key"] for s in config["sections"] if s["enabled"]}
    assert "promotions" in enabled  # секция не погашена пустой формой
