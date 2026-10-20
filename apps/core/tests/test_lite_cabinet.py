"""T-8.23c: лёгкий кабинет «Nur Aktionen» (план t8-23 §8)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import lite_cabinet, modules, views
from apps.promotions import views as promo_views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="lite", password="pw12345678")


def _tenant(slug, lite=True):
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {"profile": "aktionen"} if lite else {}
    t.save()
    return t


def _req(method, path, user, tenant, data=None):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user, tenant
    return req


def test_lite_sidebar_is_flat_items_full_cabinet_unchanged():
    lite = modules.sidebar_nav(_tenant("lc-nav"))
    # T-8.31a: «Start» первым, таб-бар макета = первые четыре.
    assert [i["url_name"] for i in lite] == [
        "dashboard",
        "promotions:promotion-list",
        "sellable-manage",
        "integrations-home",  # T-8.29: «Verbindungen»
        "lite-business",
        "lite-share",
    ]
    assert all(not i["children"] for i in lite)
    full = modules.sidebar_nav(_tenant("lc-full", lite=False))
    assert full[0]["url_name"] == "dashboard" and len(full) > 4


def test_lite_dashboard_opens_start(user):
    """T-8.31a: главная лёгкого кабинета — своя «Start», а не редирект на акции."""
    from apps.tenants import onboarding

    t = _tenant("lc-dash")
    onboarding.mark_complete(t)
    resp = views.dashboard(_req("get", "/dashboard/", user, t))
    assert resp.status_code == 200 and "data-lite-home" in resp.content.decode()


def test_lite_business_saves_only_its_fields_and_hours(user):
    t = _tenant("lc-biz")
    t.site_config = {"profile": "aktionen", "seo": {"x": 1}}
    t.save()
    data = {
        "name": "Krume",
        "address": "Kölner Straße 64, 42651 Solingen",
        "contact_phone": "0212 123456",
        "whatsapp_number": "",
        "oh_0_open": "07:00",
        "oh_0_close": "18:00",
    }
    resp = lite_cabinet.lite_business(_req("post", "/dashboard/geschaeft/", user, t, data))
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.address == "Kölner Straße 64, 42651 Solingen"
    assert t.opening_hours_structured.get("0") == ["07:00", "18:00"]
    assert t.site_config.get("seo") == {"x": 1}  # чужие колонки не тронуты (W0)

    bad = lite_cabinet.lite_business(
        _req("post", "/dashboard/geschaeft/", user, t, {**data, "address": " "})
    )
    assert bad.status_code == 200 and "Bitte die Adresse angeben" in bad.content.decode()


def test_lite_share_shows_link_qr_and_poster(user):
    t = _tenant("lc-share")
    body = lite_cabinet.lite_share(_req("get", "/dashboard/teilen/", user, t)).content.decode()
    assert "data-share-qr" in body and "<svg" in body
    assert "data-share-poster" in body and 'data-share-target="whatsapp"' in body


def test_promotion_list_cards_in_lite_table_otherwise(user):
    PromotionFactory(status="active", title={"de": "Maus"})
    lite = promo_views.promotion_list(
        _req("get", "/promotions/", user, _tenant("lc-list"))
    ).content.decode()
    assert "data-lite-promo-card" in lite and "<table" not in lite
    assert "data-promo-page-mode" not in lite  # настройки витрины скрыты
    full = promo_views.promotion_list(
        _req("get", "/promotions/", user, _tenant("lc-list2", lite=False))
    ).content.decode()
    assert "<table" in full and "data-lite-promo-card" not in full


def test_lite_list_shows_open_reservations_and_scanner(user):
    """Продавец видит отложенное прямо на экране акций (вопрос владельца 2026-10-11)."""
    from apps.promotions import services

    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    services.reserve(promo, name="Anna", email="anna@test.de")
    body = promo_views.promotion_list(
        _req("get", "/promotions/", user, _tenant("lc-res"))
    ).content.decode()
    assert "data-lite-reservations" in body and "1 offen" in body
    assert "/promotions/redeem/" in body
    assert f"/promotions/reservations/?promotion={promo.pk}" in body
