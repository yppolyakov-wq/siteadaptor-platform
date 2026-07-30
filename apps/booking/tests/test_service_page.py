"""Фидбэк 2026-07-30: у каждой услуги своя страница (как у номера) — «Bearbeiten»
из хаба «Angebote» и мастера больше не высаживает в общий список."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.booking.models import Service
from apps.booking.views import services_view
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/booking/leistungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    request.tenant = TenantFactory.build(business_type="friseur")
    return request


def test_service_page_shows_only_this_service():
    a = Service.objects.create(name="Haarschnitt", price_cents=3500)
    Service.objects.create(name="Färben", price_cents=8000)
    body = services_view(_req(), pk=a.pk).content.decode()
    assert "Haarschnitt" in body and "Färben" not in body
    assert "Create service" not in body or 'value="create"' not in body  # без формы создания


def test_list_links_each_service_to_its_page():
    a = Service.objects.create(name="Haarschnitt", price_cents=3500)
    body = services_view(_req()).content.decode()
    assert reverse("booking:service-edit", args=[a.pk]) in body


def test_post_from_service_page_returns_to_page():
    a = Service.objects.create(name="Haarschnitt", price_cents=3500)
    resp = services_view(
        _req("post", {"action": "update", "service": str(a.pk), "price_eur": "40"}), pk=a.pk
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("booking:service-edit", args=[a.pk])


def test_sellable_manage_edit_url_is_per_service():
    from apps.core import sellable_manage

    a = Service.objects.create(name="Haarschnitt", price_cents=3500)
    tenant = TenantFactory.build(business_type="friseur")
    sections = sellable_manage.sellable_manage_sections_for(tenant)
    rows = [s for s in sections if s["kind"] == "service"]
    assert rows, "секция услуг должна быть в обзоре"
    assert rows[0]["items"][0].edit_url == reverse("booking:service-edit", args=[a.pk])
