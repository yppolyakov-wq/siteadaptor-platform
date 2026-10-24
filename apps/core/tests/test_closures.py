"""KA-12 E4.1a: Betriebsferien на весь сайт — одна точка чтения `core.closures`."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking.models import ClosedDate
from apps.core import closures

pytestmark = pytest.mark.django_db


def _close(days=3, offset=0, reason="Urlaub"):
    today = timezone.localdate()
    closures.set_range(
        today + timedelta(days=offset), today + timedelta(days=offset + days - 1), reason=reason
    )
    return today


def test_set_and_clear_range_idempotent():
    today = _close()
    assert closures.set_range(today, today + timedelta(days=2)) == 0
    assert ClosedDate.objects.filter(resource__isnull=True).count() == 3
    closures.clear_range(today, today + timedelta(days=2))
    assert not ClosedDate.objects.exists()


def test_current_or_next_range():
    today = _close(days=4, offset=2)
    got = closures.current_or_next(today)
    assert got["von"] == today + timedelta(days=2) and got["bis"] == today + timedelta(days=5)
    assert got["now"] is False and got["reason"] == "Urlaub"


def test_other_tenant_schema_reads_nothing():
    from types import SimpleNamespace

    _close()
    assert (
        closures.closed_days(
            timezone.localdate(), timezone.localdate(), SimpleNamespace(schema_name="other")
        )
        == {}
    )


def test_open_status_and_presence_closed_during_holidays():
    from apps.core import presence
    from apps.tenants.tests.factories import TenantFactory

    hours = {str(d): ["00:00", "23:59"] for d in range(7)}
    tenant = TenantFactory(schema_name="public", opening_hours_structured=hours)
    tenant.site_config = {"presence": "auto"}
    assert tenant.open_status()["open"] is True
    _close()
    tenant = type(tenant).objects.get(pk=tenant.pk)  # окно закрытий — одно на запрос
    tenant.site_config = {"presence": "auto"}
    assert tenant.open_status()["open"] is False
    assert presence.available_now(tenant) is False


def test_pickup_slots_skip_holidays():
    from apps.orders import pickup_slots
    from apps.tenants.tests.factories import TenantFactory

    hours = {str(d): ["08:00", "20:00"] for d in range(7)}
    tenant = TenantFactory(schema_name="public", opening_hours_structured=hours)
    cfg = {"lead": 0, "step": 60, "capacity": 0, "days": 5}
    before = {day for day, _ in pickup_slots.slots_for(tenant, cfg=cfg)}
    today = _close(days=2, offset=1)
    after = {day for day, _ in pickup_slots.slots_for(tenant, cfg=cfg)}
    assert today + timedelta(days=1) in before
    assert today + timedelta(days=1) not in after and today + timedelta(days=2) not in after


def test_banner_shows_closure():
    from django.template import Context, Template
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    _close(reason="Sommerpause")
    request = RequestFactory().get("/")
    request.tenant = TenantFactory(schema_name="public")
    html = Template("{% load siteui %}{% holiday_banner %}").render(Context({"request": request}))
    assert "data-holiday-banner" in html and "Sommerpause" in html


def test_screen_creates_and_reopens(client, settings):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.views import betriebsferien_view

    settings.ROOT_URLCONF = "config.urls_tenant"
    user = get_user_model().objects.create_user(username="bf-owner", password="pw12345678")
    from apps.core.models import Membership

    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)  # только владелец
    today = timezone.localdate()

    def _post(data):
        req = RequestFactory().post("/dashboard/settings/betriebsferien/", data)
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = user
        return betriebsferien_view(req)

    von, bis = today.isoformat(), (today + timedelta(days=1)).isoformat()
    assert _post({"von": von, "bis": bis, "reason": "Inventur"}).status_code == 302
    assert ClosedDate.objects.filter(resource__isnull=True).count() == 2
    _post({"von": von, "bis": bis, "mode": "open"})
    assert not ClosedDate.objects.exists()
    _post({"von": bis, "bis": von})  # перевёрнутый диапазон — отказ
    assert not ClosedDate.objects.exists()


def test_one_query_per_request_for_banner_open_status_and_presence(
    django_assert_num_queries, monkeypatch
):
    """Ревью: баннер, «открыто сейчас» и присутствие делили бы три запроса — окно одно."""
    from types import SimpleNamespace

    from django.db import connection
    from django.utils import timezone

    holder = SimpleNamespace(schema_name=connection.schema_name)
    monkeypatch.setattr(connection, "tenant", holder, raising=False)  # объект запроса
    today = timezone.localdate()
    closures.set_range(today, today, reason="Urlaub")
    with django_assert_num_queries(1):
        assert closures.is_closed(today, holder)
        assert closures.current_or_next(today, holder)["now"]
        assert closures.is_closed(today, holder)
