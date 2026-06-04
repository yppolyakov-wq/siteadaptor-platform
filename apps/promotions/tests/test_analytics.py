"""Тесты аналитики акций (просмотры + конверсия)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views, views
from apps.promotions.models import Promotion
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory


def _attach(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_detail_view_increments_views():
    promo = PromotionFactory(status="active")
    public_views.promotion_detail(_attach(RequestFactory().get("/"), AnonymousUser()), pk=promo.pk)
    public_views.promotion_detail(_attach(RequestFactory().get("/"), AnonymousUser()), pk=promo.pk)
    promo.refresh_from_db()
    assert promo.views == 2


@pytest.mark.django_db
def test_promo_stats_conversion(user):
    promo = PromotionFactory(status="active", available_quantity=10)
    reserve(promo, name="A", email="a@test.de")
    Promotion.objects.filter(pk=promo.pk).update(views=4)
    promo.refresh_from_db()
    stats = views._promo_stats(promo)
    assert stats["views"] == 4
    assert stats["total"] == 1
    assert stats["conversion"] == 25.0


@pytest.mark.django_db
def test_analytics_overview_renders(user):
    PromotionFactory(status="active", title={"de": "Aktion A"})
    resp = views.analytics_overview(_attach(RequestFactory().get("/promotions/analytics/"), user))
    assert resp.status_code == 200
    assert b"Aktion A" in resp.content
