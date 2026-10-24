"""KA-12 E4.1c (решения владельца 2026-10-24): Betriebsferien закрывает только владелец;
портал, поиск «offen» и MCP видят каникулы по снимку `Tenant.closure_ranges`."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import views as booking_views
from apps.booking.models import ClosedDate, Resource
from apps.core import closures
from apps.core.models import Membership
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _user(role):
    u = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="x" * 10
    )
    Membership.objects.create(user=u, role=role)
    return u


def _req(path, data, user):
    req = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = TenantFactory.build()
    return req


def _range():
    today = timezone.localdate()
    return {"von": today.isoformat(), "bis": (today + timedelta(days=2)).isoformat()}


def test_staff_cannot_open_betriebsferien_screen():
    from apps.core.views import betriebsferien_view

    resp = betriebsferien_view(
        _req("/dashboard/settings/betriebsferien/", _range(), _user("staff"))
    )
    assert resp.status_code == 403
    assert not ClosedDate.objects.exists()


def test_owner_only_prefix_covers_screen():
    from apps.core import roles

    assert (
        roles.required_role_for_path("/dashboard/settings/betriebsferien/") == roles.ROLE_OWNER_ONLY
    )


def test_staff_cannot_close_business_in_booking_calendar():
    data = {"action": "range", **_range()}
    booking_views.availability_calendar(
        _req("/dashboard/booking/verfuegbarkeit/", data, _user("staff"))
    )
    assert not ClosedDate.objects.exists()
    day = {"date": timezone.localdate().isoformat()}
    booking_views.availability_calendar(
        _req("/dashboard/booking/verfuegbarkeit/", day, _user("staff"))
    )
    assert not ClosedDate.objects.exists()
    booking_views.resources(
        _req("/dashboard/booking/resources/", {"action": "closed", **day}, _user("admin"))
    )
    assert not ClosedDate.objects.exists()


def test_staff_may_still_close_a_single_resource():
    r = Resource.objects.create(name="Stuhl 1")
    url = f"/dashboard/booking/verfuegbarkeit/?resource={r.pk}"
    req = _req(url, {"action": "range", **_range()}, _user("staff"))
    req.GET = req.GET.copy()
    req.GET["resource"] = str(r.pk)
    booking_views.availability_calendar(req)
    assert ClosedDate.objects.filter(resource=r).count() == 3


def test_owner_closes_business():
    data = {"action": "range", **_range()}
    booking_views.availability_calendar(
        _req("/dashboard/booking/verfuegbarkeit/", data, _user("owner"))
    )
    assert ClosedDate.objects.filter(resource__isnull=True).count() == 3


# --- снимок для портала / MCP ---------------------------------------------------


def _public_tenant():
    return TenantFactory(schema_name="public", slug=f"t-{uuid.uuid4().hex[:6]}")


def test_set_range_writes_snapshot_and_clear_removes_it():
    tenant = _public_tenant()
    today = timezone.localdate()
    closures.set_range(today, today + timedelta(days=2), reason="Urlaub")
    tenant.refresh_from_db()
    assert tenant.closure_ranges == [
        {
            "von": today.isoformat(),
            "bis": (today + timedelta(days=2)).isoformat(),
            "reason": "Urlaub",
        }
    ]
    closures.clear_range(today, today + timedelta(days=2))
    tenant.refresh_from_db()
    assert tenant.closure_ranges == []


def _other(ranges):
    hours = {str(d): ["00:00", "23:59"] for d in range(7)}
    return TenantFactory(
        schema_name=f"t_{uuid.uuid4().hex[:8]}",
        opening_hours_structured=hours,
        closure_ranges=ranges,
    )


def _today_range():
    today = timezone.localdate()
    return [
        {"von": today.isoformat(), "bis": (today + timedelta(days=4)).isoformat(), "reason": ""}
    ]


def test_cross_schema_open_status_sees_snapshot():
    t = _other(_today_range())
    st = t.open_status()
    assert (
        st["open"] is False
        and st["holiday"]
        and st["holiday_until"] == timezone.localdate() + timedelta(days=4)
    )
    assert _other([]).open_status()["open"] is True


def test_portal_open_filter_and_cards_honour_snapshot():
    from apps.aggregator.views import _attach_open_status, _open_now_schemas

    closed, open_ = _other(_today_range()), _other([])
    assert _open_now_schemas([closed.schema_name, open_.schema_name]) == {open_.schema_name}
    cards = [
        SimpleNamespace(tenant_schema=closed.schema_name),
        SimpleNamespace(tenant_schema=open_.schema_name),
    ]
    _attach_open_status(cards)
    assert cards[0].holiday_until and not cards[0].open_now and cards[0].opens_next == ""
    assert cards[1].holiday_until is None and cards[1].open_now


def test_past_snapshot_range_is_ignored():
    past = timezone.localdate() - timedelta(days=5)
    t = _other(
        [{"von": past.isoformat(), "bis": (past + timedelta(days=1)).isoformat(), "reason": ""}]
    )
    assert t.open_status()["open"] is True


def test_snapshot_never_reaches_other_tenant_row():
    other = _other([])
    _public_tenant()
    closures.set_range(timezone.localdate(), timezone.localdate())
    assert Tenant.objects.get(pk=other.pk).closure_ranges == []
