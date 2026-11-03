"""UX-D D2.3: список услуг — обзор строками; правка — на странице услуги."""

import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import views
from apps.booking.models import Resource, Service, ServiceVariant
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req():
    req = RequestFactory().get("/dashboard/booking/leistungen/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def _rows(html):
    return re.findall(r"<li[^>]*data-service-row.*?</li>", html, flags=re.S)


def test_rows_have_no_editable_fields_only_a_toggle():
    s = Service.objects.create(name="Haarschnitt", duration_minutes=45, price_cents=3500)
    html = views.services_view(_req()).content.decode()
    rows = _rows(html)
    assert len(rows) == 1
    row = rows[0]
    assert not re.search(r"<input(?![^>]*type=\"hidden\")", row)
    assert "<select" not in row and "<textarea" not in row
    assert f'href="/dashboard/booking/leistungen/{s.pk}/"' in row
    assert "45" in row and "35,00" in row or "35.00" in row


def test_variants_show_from_price_and_resources_are_named():
    s = Service.objects.create(name="Färben", duration_minutes=60, price_cents=5000)
    ServiceVariant.objects.create(service=s, name="Kurz", price_delta_cents=-1000)
    r = Resource.objects.create(name="Lea")
    s.resources.add(r)
    row = _rows(views.services_view(_req()).content.decode())[0]
    assert "ab" in row and ("40,00" in row or "40.00" in row)
    assert "Lea" in row


def test_list_query_budget_does_not_grow_with_services(django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for i in range(2):
        Service.objects.create(name=f"S{i}", duration_minutes=30)
    with CaptureQueriesContext(connection) as small:
        views.services_view(_req())
    for i in range(10):
        s = Service.objects.create(name=f"T{i}", duration_minutes=30)
        ServiceVariant.objects.create(service=s, name="V")
    with CaptureQueriesContext(connection) as big:
        views.services_view(_req())
    assert len(big) <= len(small) + 2, (len(small), len(big))


def test_list_links_rules_and_new_service_drawer():
    html = views.services_view(_req()).content.decode()
    assert 'href="/dashboard/booking/regeln/"' in html
    assert 'href="/dashboard/booking/leistungen/neu/" data-drawer' in html
