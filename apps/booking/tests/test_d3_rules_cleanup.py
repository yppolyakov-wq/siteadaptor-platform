"""UX-D D3.3/D3.4: правило онлайн-брони столов и виджет записи — на «Buchungsregeln»;
со списка ресурсов ушли панели статусов (они на «Abläufe») и форма закрытых дней."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import views
from apps.booking.models import ClosedDate, Resource
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER, path="/dashboard/booking/regeln/"):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def test_table_rule_card_only_with_tables():
    assert "data-table-rules" not in views.booking_rules_view(_req()).content.decode()
    Resource.objects.create(name="Tisch 1", type=Resource.TYPE_TABLE)
    html = views.booking_rules_view(_req()).content.decode()
    assert "data-table-rules" in html and 'action="/dashboard/booking/tische/regeln/"' in html


def test_staff_sees_table_rule_as_text_without_form():
    Resource.objects.create(name="Tisch 1", type=Resource.TYPE_TABLE)
    html = views.booking_rules_view(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert "data-table-rules-readonly" in html
    assert "/dashboard/booking/tische/regeln/" not in html


def test_table_rule_save_returns_to_booking_rules(monkeypatch):
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    req = _req("post", {"enabled": "1", "instant_max": "4", "online_max": "10"})
    req.tenant = TenantFactory(
        schema_name=f"t_{uuid.uuid4().hex[:8]}",
        slug=f"t{uuid.uuid4().hex[:6]}",
        auto_create_schema=False,
    )
    resp = views.table_rules_save.__wrapped__.__wrapped__(req)
    assert resp.status_code == 302 and resp.url == "/dashboard/booking/regeln/"


def test_widget_is_copied_with_a_button_on_booking_rules():
    html = views.booking_rules_view(_req()).content.decode()
    assert 'data-copy-target="booking-widget-code"' in html and "embed=1" in html
    assert "this.select()" not in html


def test_resources_list_has_no_rules_widget_status_panels_or_closed_form():
    Resource.objects.create(name="Tisch 1", type=Resource.TYPE_TABLE)
    ClosedDate.objects.create(date=timezone.localdate() + timedelta(days=3), reason="Inventur")
    html = views.resources(_req(path="/dashboard/booking/ressourcen/")).content.decode()
    for marker in ("data-table-rules", "embed=1", "this.select()", 'value="closed"'):
        assert marker not in html, marker
    assert "status-labels-save" not in html and "transitions-save" not in html
    assert "Inventur" in html and "/dashboard/booking/verfuegbarkeit/" in html
    assert "data-ablaeufe-link" in html


def test_calendar_context_drops_unused_settings_keys():
    ctx = views.calendar_context(_req(path="/dashboard/booking/"))
    for key in ("embed_url", "status_label_rows", "transition_rows"):
        assert key not in ctx
