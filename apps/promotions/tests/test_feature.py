"""P2.4b: кабинет — страница продвижения акции + Stripe-Checkout (вьюхи)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory

from apps.aggregator.models import AggregatorListing
from apps.promotions import views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory


def _attach(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner", email="owner@test.de", password="pw12345678"
    )


def _listing_for(promo):
    """Листинг для текущей (тестовой) схемы — как его увидит _featured_listing."""
    return AggregatorListing.objects.create(
        tenant_schema=connection.schema_name,
        tenant_slug="x",
        business_name="X",
        promo_uuid=promo.id,
        title={"de": "Brot"},
        detail_url="https://x.siteadaptor.de/p/1/",
        is_active=True,
    )


@pytest.mark.django_db
def test_feature_requires_login():
    promo = PromotionFactory(status="active")
    req = _attach(RequestFactory().get(f"/promotions/{promo.pk}/feature/"), AnonymousUser())
    resp = views.promotion_feature(req, pk=promo.pk)
    assert resp.status_code in (301, 302)


@pytest.mark.django_db
def test_feature_page_shows_plans_when_listed(user, settings):
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    promo = PromotionFactory(status="active")
    _listing_for(promo)
    req = _attach(RequestFactory().get(f"/promotions/{promo.pk}/feature/"), user)
    resp = views.promotion_feature(req, pk=promo.pk)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "9 €" in body and "30 Tage" in body  # планы видны


@pytest.mark.django_db
def test_feature_page_hint_when_not_active(user, settings):
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    promo = PromotionFactory(status="draft")  # нет листинга → не продвигается
    req = _attach(RequestFactory().get(f"/promotions/{promo.pk}/feature/"), user)
    body = views.promotion_feature(req, pk=promo.pk).content.decode()
    assert "Nur aktive Aktionen" in body
    assert "9 €" not in body  # кнопок покупки нет


@pytest.mark.django_db
def test_feature_checkout_redirects_to_stripe(user, settings, monkeypatch):
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    promo = PromotionFactory(status="active")
    monkeypatch.setattr("apps.aggregator.tasks.sync_listing", lambda *a, **k: "upserted")
    monkeypatch.setattr(
        "apps.billing.services.create_featured_checkout_session",
        lambda t, **kw: "https://checkout/featured",
    )
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/feature/checkout/", {"days": "7"}), user
    )
    req.tenant = TenantFactory()
    resp = views.promotion_feature_checkout(req, pk=promo.pk)
    assert resp.status_code == 302
    assert resp.url == "https://checkout/featured"


@pytest.mark.django_db
def test_feature_checkout_rejects_non_active(user, settings, monkeypatch):
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    promo = PromotionFactory(status="draft")
    called = {"stripe": False}
    monkeypatch.setattr(
        "apps.billing.services.create_featured_checkout_session",
        lambda *a, **k: called.__setitem__("stripe", True) or "x",
    )
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/feature/checkout/", {"days": "7"}), user
    )
    req.tenant = TenantFactory()
    resp = views.promotion_feature_checkout(req, pk=promo.pk)
    assert resp.status_code == 302  # назад на feature-страницу
    assert called["stripe"] is False  # Stripe не вызван


@pytest.mark.django_db
def test_feature_checkout_disabled_without_stripe(user, settings, monkeypatch):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = ""  # оплата не настроена
    promo = PromotionFactory(status="active")
    called = {"stripe": False}
    monkeypatch.setattr(
        "apps.billing.services.create_featured_checkout_session",
        lambda *a, **k: called.__setitem__("stripe", True) or "x",
    )
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/feature/checkout/", {"days": "7"}), user
    )
    req.tenant = TenantFactory()
    resp = views.promotion_feature_checkout(req, pk=promo.pk)
    assert resp.status_code == 302
    assert called["stripe"] is False


@pytest.mark.django_db
def test_feature_checkout_rejects_unknown_days(user, settings, monkeypatch):
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    promo = PromotionFactory(status="active")
    called = {"stripe": False}
    monkeypatch.setattr(
        "apps.billing.services.create_featured_checkout_session",
        lambda *a, **k: called.__setitem__("stripe", True) or "x",
    )
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/feature/checkout/", {"days": "99"}), user
    )
    req.tenant = TenantFactory()
    resp = views.promotion_feature_checkout(req, pk=promo.pk)
    assert resp.status_code == 302
    assert called["stripe"] is False  # неизвестный план — отказ
