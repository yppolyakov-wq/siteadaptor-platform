"""Тесты листа ожидания (sold-out)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import WaitlistEntry
from apps.promotions.tests.factories import PromotionFactory


def _req(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def test_is_sold_out():
    assert PromotionFactory.build(available_quantity=0).is_sold_out is True
    assert PromotionFactory.build(available_quantity=5).is_sold_out is False
    assert PromotionFactory.build(available_quantity=None).is_sold_out is False


@pytest.mark.django_db
def test_waitlist_join_creates_entry():
    promo = PromotionFactory(status="active", available_quantity=0)
    req = _req(
        RequestFactory().post(f"/p/{promo.pk}/waitlist/", {"name": "Ann", "email": "Ann@Test.de"})
    )
    resp = public_views.waitlist_join(req, pk=promo.pk)
    assert resp.status_code == 302
    e = WaitlistEntry.objects.get()
    assert e.email == "ann@test.de"  # нормализуем
    assert e.notified is False


@pytest.mark.django_db
def test_waitlist_dedupes_by_email():
    promo = PromotionFactory(status="active", available_quantity=0)
    for _ in range(2):
        public_views.waitlist_join(
            _req(RequestFactory().post(f"/p/{promo.pk}/waitlist/", {"email": "x@test.de"})),
            pk=promo.pk,
        )
    assert WaitlistEntry.objects.filter(promotion=promo, email="x@test.de").count() == 1


@pytest.mark.django_db
def test_waitlist_honeypot_ignored():
    promo = PromotionFactory(status="active", available_quantity=0)
    req = _req(
        RequestFactory().post(
            f"/p/{promo.pk}/waitlist/", {"email": "bot@test.de", "website": "spam"}
        )
    )
    public_views.waitlist_join(req, pk=promo.pk)
    assert WaitlistEntry.objects.count() == 0
