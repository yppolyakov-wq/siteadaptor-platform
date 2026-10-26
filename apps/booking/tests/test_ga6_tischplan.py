"""KA-12 GA-6 (Gastro): экран «Tischplan» — состояние столов на момент времени
(свободен/скоро/занят, через комбинацию, пул по местам), walk-in и «Tisch zuweisen»
штатными путями с возвратом на Tischplan."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking import occupancy, services, tischplan, views
from apps.booking.models import AvailabilityRule, Booking, Resource
from apps.core import nav_registry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)
TZ = timezone.get_current_timezone()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _table(name="T", seats=4, **kw):
    r = Resource.objects.create(
        name=f"{name} {uuid.uuid4().hex[:4]}",
        type=Resource.TYPE_TABLE,
        capacity=kw.pop("capacity", 1),
        seats=seats,
        **kw,
    )
    AvailabilityRule.objects.create(
        resource=r, weekday=DAY.weekday(), start_time=time(17), end_time=time(23), slot_minutes=30
    )
    return r


def _at(h, m=0):
    return datetime.combine(DAY, time(h, m), tzinfo=TZ)


def _book(resource, h=18, party=2, minutes=90):
    return services.book(
        resource,
        start=_at(h),
        end=_at(h) + timedelta(minutes=minutes),
        name="Gast",
        party_size=party,
    )


def _tiles(tables, bookings, at):
    tables = list(Resource.objects.filter(pk__in=[t.pk for t in tables]).prefetch_related("parts"))
    return {t.table.pk: t for _z, tiles in tischplan.build(tables, bookings, at) for t in tiles}


def test_free_soon_busy_and_free_until():
    a, b, c = _table("A"), _table("B"), _table("C")
    ba = _book(a, 18)
    bb = _book(b, 19)
    tiles = _tiles([a, b, c], [ba, bb], _at(18, 45))
    assert tiles[a.pk].state == "busy" and tiles[a.pk].current == ba
    assert tiles[b.pk].state == "soon" and tiles[b.pk].free_until == bb.start
    assert tiles[c.pk].state == "free" and tiles[c.pk].free_until is None
    early = _tiles([b], [bb], _at(17))
    assert early[b.pk].state == "free" and early[b.pk].free_until == bb.start


def test_combo_blocks_parts_and_part_blocks_combo_with_via():
    t3, t4, t5 = _table("T3"), _table("T4"), _table("T5")
    combo = _table("T3+4", None)
    occupancy.set_parts(combo, [t3.pk, t4.pk])
    bc = _book(combo, 18, party=6)
    tiles = _tiles([t3, t4, t5, combo], [bc], _at(18, 30))
    assert tiles[t3.pk].state == "busy" and tiles[t3.pk].via.pk == combo.pk
    assert tiles[t4.pk].state == "busy"
    assert tiles[t5.pk].state == "free"
    bc.delete()
    b3 = _book(t3, 20)
    tiles = _tiles([t3, t4, combo], [b3], _at(20, 15))
    assert tiles[combo.pk].state == "busy" and tiles[combo.pk].via.pk == t3.pk
    assert tiles[t4.pk].state == "free"


def test_pool_counts_seats():
    pool = _table("Terrasse", None, capacity=10, counts_party_size=True)
    b1 = _book(pool, 18, party=4)
    tile = _tiles([pool], [b1], _at(18, 15))[pool.pk]
    assert tile.state == "free" and tile.seats_taken == 4
    b2 = _book(pool, 18, party=6)
    assert _tiles([pool], [b1, b2], _at(18, 15))[pool.pk].state == "full"


def test_default_moment_rounds_and_tolerates_garbage():
    assert tischplan.default_moment(DAY, "19:52") == _at(19, 45)
    assert tischplan.default_moment(DAY, "99:99") == _at(18)
    assert tischplan.default_moment(DAY, "x") == _at(18)


def _get(path):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    request.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    return request


def _post(path, data):
    request = RequestFactory().post(path, data)
    request.META["REMOTE_ADDR"] = "10.9.8.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    request.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    return request


def test_view_renders_tiles_and_query_count_is_flat():
    tables = [_table(f"T{i}", zone="Saal" if i % 2 else "Terrasse") for i in range(6)]
    for t in tables[:3]:
        _book(t, 18)
    url = f"/dashboard/booking/tische/plan/?tag={DAY.isoformat()}&zeit=18:30"
    with CaptureQueriesContext(connection) as ctx:
        response = views.tischplan(_get(url))
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count("data-table-tile=") >= 6
    assert "Saal" in html and "Terrasse" in html
    assert len(ctx.captured_queries) < 20, len(ctx.captured_queries)
    # мусорные параметры — дефолт, не 500
    assert views.tischplan(_get("/x/?tag=nope&zeit=25:99")).status_code == 200


def test_walkin_returns_to_tischplan_and_ignores_foreign_next():
    table = _table("W", seats=4)
    here = f"/dashboard/booking/tische/plan/?tag={DAY.isoformat()}&zeit=18:00"
    data = {
        "resource": str(table.pk),
        "start": _at(18).strftime("%Y-%m-%dT%H:%M"),
        "party_size": "3",
        "minutes": "90",
        "next": here,
    }
    response = views.booking_create(_post("/dashboard/booking/new/", data))
    assert response.status_code == 302 and response.url == here
    booking = Booking.objects.get(resource=table)
    assert booking.party_size == 3 and booking.status == "confirmed"
    other = _table("W2", seats=4)
    response = views.booking_create(
        _post(
            "/dashboard/booking/new/", {**data, "resource": str(other.pk), "next": "//evil.example"}
        )
    )
    assert response.url.startswith(reverse("booking:calendar"))


def test_create_with_garbage_resource_is_404_not_500():
    from django.http import Http404

    with pytest.raises(Http404):
        views.booking_create(_post("/dashboard/booking/new/", {"resource": "nope"}))


def test_assign_table_moves_and_refuses_taken_combo():
    t3, t4, t5 = _table("T3"), _table("T4"), _table("T5")
    combo = _table("T3+4", None)
    occupancy.set_parts(combo, [t3.pk, t4.pk])
    on_t5 = _book(t5, 18)
    _book(t3, 18)
    here = f"/dashboard/booking/tische/plan/?tag={DAY.isoformat()}"
    data = {
        "action": "move",
        "resource": str(combo.pk),
        "start": timezone.localtime(on_t5.start).strftime("%Y-%m-%dT%H:%M"),
        "next": here,
    }
    response = views.booking_action(_post("/x/", data), pk=on_t5.pk)
    assert response.url == here
    on_t5.refresh_from_db()
    assert on_t5.resource_id == t5.pk  # комбинация занята через Tisch 3
    views.booking_action(_post("/x/", {**data, "resource": str(t4.pk)}), pk=on_t5.pk)
    on_t5.refresh_from_db()
    assert on_t5.resource_id == t4.pk


def test_nav_entry_only_for_table_businesses():
    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "booking:tischplan")
    assert entry.business_types == nav_registry.TABLE_TYPES
    assert nav_registry.allowed_for_business(
        "booking:tischplan", TenantFactory.build(business_type="restaurant")
    )
    assert not nav_registry.allowed_for_business(
        "booking:tischplan", TenantFactory.build(business_type="friseur")
    )


def test_inactive_combo_booking_still_blocks_its_tables_on_screen():
    t3, t4 = _table("T3"), _table("T4")
    combo = _table("T3+4", None)
    occupancy.set_parts(combo, [t3.pk, t4.pk])
    _book(combo, 18, party=6)
    Resource.objects.filter(pk=combo.pk).update(is_active=False)
    url = f"/dashboard/booking/tische/plan/?tag={DAY.isoformat()}&zeit=18:30"
    html = views.tischplan(_get(url)).content.decode()
    assert f'data-table-tile="{t3.pk}" data-state="busy"' in html
    assert f'data-table-tile="{t4.pk}" data-state="busy"' in html
