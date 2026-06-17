"""P1b: структурные часы работы + live-статус «Jetzt geöffnet»."""

from datetime import datetime

import pytest

from apps.tenants import openinghours

pytestmark = pytest.mark.django_db


def test_open_now_within_range():
    # Понедельник 14:00, часы Пн 09:00–18:00 → открыто до 18:00
    mon_14 = datetime(2026, 6, 15, 14, 0)  # 2026-06-15 = Monday
    st = openinghours.open_status({"0": ["09:00", "18:00"]}, mon_14)
    assert st == {"open": True, "until": "18:00", "next": None}


def test_closed_before_opening_same_day():
    mon_08 = datetime(2026, 6, 15, 8, 0)
    st = openinghours.open_status({"0": ["09:00", "18:00"]}, mon_08)
    assert st["open"] is False
    assert st["next"] == ("Mo", "09:00")


def test_closed_today_points_to_next_day():
    # Вс закрыто, Пн 09:00 — в воскресенье вечером → следующее открытие Пн
    sun_20 = datetime(2026, 6, 21, 20, 0)  # Sunday
    st = openinghours.open_status({"0": ["09:00", "18:00"]}, sun_20)
    assert st["open"] is False and st["next"] == ("Mo", "09:00")


def test_no_hours_returns_none():
    assert openinghours.open_status({}, datetime(2026, 6, 15, 12, 0)) is None


def test_normalize_drops_invalid():
    out = openinghours.normalize({"0": ["09:00", "18:00"], "1": ["18:00", "09:00"], "2": ["x"]})
    assert out == {"0": ["09:00", "18:00"]}  # open<close only, валидный формат


def test_today_label():
    mon = datetime(2026, 6, 15, 10, 0)
    assert openinghours.today_label({"0": ["09:00", "18:00"]}, mon) == "09:00–18:00"
    assert openinghours.today_label({}, mon) == "Geschlossen"


def test_tenant_open_status_method():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory.build(opening_hours_structured={"0": ["00:00", "23:59"]})
    # метод не падает и возвращает dict|None
    assert t.open_status() is None or isinstance(t.open_status(), dict)


def test_settings_view_saves_structured_hours():
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="x", name="X")
    data = {
        "name": "X",
        "oh_0_open": "09:00",
        "oh_0_close": "18:00",
        "oh_1_open": "10:00",
        "oh_1_close": "16:00",
    }
    req = RequestFactory().post("/dashboard/settings/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:6]}", email="o@test.de", password="pw12345678"
    )
    resp = core_views.settings_view(req)
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.opening_hours_structured == {"0": ["09:00", "18:00"], "1": ["10:00", "16:00"]}
