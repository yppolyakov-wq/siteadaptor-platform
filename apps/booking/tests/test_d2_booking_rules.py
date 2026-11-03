"""UX-D D2.1: экран «Buchungsregeln» в Einstellungen — правило неявок и сроки отмены
всех услуг в одном месте (раньше — свёрнутый блок над списком услуг)."""

import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import views
from apps.booking.models import Service
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(role=Membership.ROLE_OWNER, method="get", data=None):
    req = getattr(RequestFactory(), method)("/dashboard/booking/regeln/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def test_rules_screen_shows_no_show_card_and_cancel_windows():
    Service.objects.create(name="Haarschnitt", duration_minutes=30, cancel_window_hours=24)
    html = views.booking_rules_view(_req()).content.decode()
    assert "data-no-show-rule" in html
    assert 'action="/dashboard/booking/nichterscheinen/"' in html
    assert "Haarschnitt" in html and "24" in html
    assert "?tab=regeln" in html  # переход к правилам самой услуги


def test_staff_sees_rules_without_a_form():
    html = views.booking_rules_view(_req(role=Membership.ROLE_STAFF)).content.decode()
    assert "data-no-show-rule" in html
    assert "/dashboard/booking/nichterscheinen/" not in html


def test_no_show_save_returns_to_rules_screen(monkeypatch):
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    req = _req(method="post", data={"enabled": "1", "after": "2", "days": "365"})
    req.tenant = TenantFactory(
        schema_name=f"t_{uuid.uuid4().hex[:8]}",
        slug=f"t{uuid.uuid4().hex[:6]}",
        auto_create_schema=False,
    )
    resp = views.no_show_rule_save.__wrapped__.__wrapped__(req)
    assert resp.status_code == 302 and resp.url == "/dashboard/booking/regeln/"


def test_services_list_no_longer_hosts_the_rule_form():
    text = (ROOT / "templates/booking/services.html").read_text()
    assert "booking:no-show-rule" not in text
    assert "booking:booking-rules" in text  # ссылка «Regeln für alle Leistungen»


def test_rules_screen_is_in_settings_nav_with_booking_module():
    from apps.core import nav_registry

    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "booking:booking-rules")
    assert entry.hub == "settings" and entry.module_key == "booking"


def test_rules_screen_permissions_are_settings():
    from apps.core import view_perms

    rule = view_perms.RULES["booking:booking-rules"]
    assert (rule.read, rule.write) == ("einstellungen.view", "einstellungen.edit")
