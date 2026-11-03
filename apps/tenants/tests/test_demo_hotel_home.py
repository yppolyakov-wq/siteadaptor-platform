"""UX-D D1.6: демо отеля показывает каждый блок новой главной (сводка дня)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_hotel_demo_fills_every_home_block():
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership
    from apps.stays import home_summary

    tenant = TenantFactory(schema_name="public", slug="hh", name="Hotel", business_type="hotel")
    assert demo_kits.apply_kit(tenant, "hotel") is True
    tenant.refresh_from_db()
    req = RequestFactory().get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = get_user_model().objects.create_user(username="hh-owner", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    ctx = home_summary.summary(req)
    assert ctx["hh_arrivals"] and ctx["hh_departures"]  # стойка: заезд и выезд сегодня
    assert ctx["hh_dirty"]  # уборка
    assert ctx["hh_unconfirmed"] >= 1  # бронь ждёт подтверждения
    assert ctx["hh_unpaid"]["count"] >= 1  # Vorkasse без оплаты
    assert ctx["hh_no_room"] >= 1  # бронь без номера
    assert ctx["hh_unread"] >= 1  # вопрос гостя
    assert ctx["hh_gap"] is not None  # окно для Lücken-Rabatt
    assert ctx["hh_week"] and ctx["hh_today_occ"]["occupied"] >= 1
