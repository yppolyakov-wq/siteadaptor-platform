"""R5: платформенная BI-аналитика (MRR/churn/LTV) + staff-гейт вьюхи."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils import timezone

from apps.billing import analytics, views
from apps.billing.models import UsageFeeRecord
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_mrr_counts_active_times_price(settings):
    settings.BILLING_PLAN_PRICE_EUR = 39
    before = analytics.platform_metrics()
    TenantFactory(subscription_status="active")
    TenantFactory(subscription_status="active")
    TenantFactory(subscription_status="trial")
    after = analytics.platform_metrics()
    assert after["active"] - before["active"] == 2
    assert after["mrr"] - before["mrr"] == 78  # 2 × 39
    assert after["arpa"] == 39  # единый тариф
    assert after["counts"]["trial"] >= 1


def test_churn_and_ltv_from_recent_suspends(settings):
    settings.BILLING_PLAN_PRICE_EUR = 39
    TenantFactory(subscription_status="active")
    TenantFactory(
        subscription_status="suspended",
        subscription_ends_at=timezone.now() - timedelta(days=5),
    )
    m = analytics.platform_metrics()
    assert m["churned_30"] >= 1
    assert m["churn_pct"] > 0
    assert m["ltv"] is not None  # ARPA / churn


def test_usage_fees_current_period():
    t = TenantFactory(subscription_status="active")
    period = timezone.now().strftime("%Y-%m")
    UsageFeeRecord.objects.create(
        tenant=t, period=period, gmv_cents=100000, fee_cents=2500, fee_percent=2.5
    )
    m = analytics.platform_metrics()
    assert m["fee_eur"] == 25.0
    assert m["gmv_eur"] == 1000.0


def test_metrics_safe_with_no_active():
    m = analytics.platform_metrics()
    assert isinstance(m["mrr"], int)
    # без активных подписок — LTV не определён (без деления на ноль)
    if m["active"] == 0:
        assert m["ltv"] is None and m["arpa"] == 0


def test_platform_bi_redirects_anonymous(settings):
    settings.ROOT_URLCONF = "config.urls_public"  # admin:login живёт тут
    req = RequestFactory().get("/plattform/bi/")
    req.user = AnonymousUser()
    resp = views.platform_bi(req)
    assert resp.status_code == 302  # staff_member_required → login


def test_platform_bi_renders_for_staff(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    staff = get_user_model().objects.create_user(
        username="pa", password="x", is_staff=True, is_active=True
    )
    req = RequestFactory().get("/plattform/bi/")
    req.user = staff
    resp = views.platform_bi(req)
    assert resp.status_code == 200
    assert b"Platform BI" in resp.content
