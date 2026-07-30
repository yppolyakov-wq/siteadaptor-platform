"""Фидбэк 2026-07-30 («непонятно, где в админке задаётся календарь цен»):
входы в ценовые/временные настройки с тех экранов, где владелец их ищет.

Замки навигационные (наличие ссылки), не вёрсточные: ломается только если
вход снова исчезнет.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PRICE_SETTINGS_HREF = "?tab=einstellungen&amp;sec=preise"


def _req(path="/dashboard/", business_type="hotel"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    request.tenant = TenantFactory.build(business_type=business_type, disabled_modules=[])
    return request


def test_stays_calendar_links_to_price_settings():
    from apps.stays.views import calendar

    body = calendar(_req("/dashboard/stays/")).content.decode()
    assert PRICE_SETTINGS_HREF in body
    assert "Preise &amp; Saison" in body or "Preise & Saison" in body


def test_unit_page_price_tab_points_to_general_rules():
    """На странице номера «0 = wie allgemein» теперь ведёт в общие настройки."""
    from apps.stays.models import StayUnit
    from apps.stays.views import units

    unit = StayUnit.objects.create(name="Doppelzimmer", price_cents=9000)
    body = units(_req(f"/dashboard/stays/units/{unit.pk}/"), pk=unit.pk).content.decode()
    assert PRICE_SETTINGS_HREF in body
    assert "Saisonpreise" in body


def test_reports_links_to_price_settings():
    from apps.stays.views import reports

    body = reports(_req("/dashboard/stays/reports/")).content.decode()
    assert PRICE_SETTINGS_HREF in body


def test_services_page_links_to_hours_and_warns_when_missing():
    """Услуги: вход в «Öffnungszeiten & Ressourcen» + честная причина
    «keine freien Termine», пока часы не заданы."""
    from apps.booking.models import AvailabilityRule, Resource, Service
    from apps.booking.views import services_view

    Service.objects.create(name="Haarschnitt", price_cents=3500)
    body = services_view(_req("/dashboard/booking/leistungen/", "friseur")).content.decode()
    assert "/dashboard/booking/ressourcen/" in body
    assert "Noch keine Öffnungszeiten hinterlegt." in body

    resource = Resource.objects.create(name="Stuhl 1")
    AvailabilityRule.objects.create(
        resource=resource, weekday=0, start_time="09:00", end_time="17:00", slot_minutes=30
    )
    with_hours = services_view(_req("/dashboard/booking/leistungen/", "friseur")).content.decode()
    assert "Noch keine Öffnungszeiten hinterlegt." not in with_hours
    assert "/dashboard/booking/ressourcen/" in with_hours  # вход остаётся
