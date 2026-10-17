"""Г4-1: дневные просмотры акций и дата погашения купона (основа недельного блока дайджеста).

План — docs/g3-g4-freshness-digest-plan-2026-10-17.md §4.1–4.2.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.loyalty.models import Voucher
from apps.promotions import channels, public_views, services
from apps.promotions.models import PromotionDailyView
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("ends_at", timezone.now() + timedelta(days=3))
    return PromotionFactory(**kw)


def _detail(promo):
    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build()
    return public_views.promotion_detail(request, pk=promo.pk)


def test_two_views_same_day_make_one_row():
    promo = _promo()
    channels.count_day(promo)
    channels.count_day(promo)
    row = PromotionDailyView.objects.get(promotion=promo)
    assert row.views == 2 and row.day == timezone.localdate()


def test_new_day_gets_its_own_row():
    promo = _promo()
    channels.count_day(promo)
    PromotionDailyView.objects.filter(promotion=promo).update(
        day=timezone.localdate() - timedelta(days=1)
    )
    channels.count_day(promo)
    assert PromotionDailyView.objects.filter(promotion=promo).count() == 2


def test_detail_page_counts_the_day():
    promo = _promo()
    assert _detail(promo).status_code == 200
    assert PromotionDailyView.objects.get(promotion=promo).views == 1


def test_counter_failure_never_breaks_the_page():
    promo = _promo()
    with mock.patch.object(
        PromotionDailyView.objects, "filter", side_effect=RuntimeError("db hiccup")
    ):
        assert _detail(promo).status_code == 200


def test_redeem_stamps_the_moment():
    promo = _promo()
    voucher = Voucher.objects.create(code="C-G4TEST", promotion=promo, max_uses=1)
    Voucher.objects.filter(pk=voucher.pk).update(updated_at=timezone.now() - timedelta(days=9))
    services.redeem_voucher("C-G4TEST")
    voucher.refresh_from_db()
    assert voucher.used_count == 1
    assert timezone.now() - voucher.updated_at < timedelta(minutes=1)
