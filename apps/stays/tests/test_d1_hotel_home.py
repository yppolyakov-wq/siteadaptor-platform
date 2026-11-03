"""UX-D D1.4: главная отеля = сводка дня (макет Home)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import views as core_views
from apps.core.tests.test_x3_home_cockpit import _req, _tenant
from apps.stays import services, views
from apps.stays.models import Room, StayBooking, StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(quantity=2, name=None):
    return StayUnit.objects.create(
        name=name or f"DZ {uuid4().hex[:6]}", quantity=quantity, price_cents=10000
    )


def _book(unit, start, nights=2, name="Gast", **kw):
    today = timezone.localdate()
    return services.book_stay(
        unit,
        arrival=today + timedelta(days=start),
        departure=today + timedelta(days=start + nights),
        name=name,
        auto_confirm=kw.pop("auto_confirm", True),
        **kw,
    )


def _owner_req(tenant, **kw):
    from apps.core.models import Membership

    req = _req(tenant, path="/dashboard/", **kw)
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def _home(tenant=None, role=None):
    from apps.core.models import Membership

    tenant = tenant or _tenant("hotel")
    req = _owner_req(tenant)
    if role:
        Membership.objects.filter(user=req.user).update(role=role)
    return core_views.dashboard(req).content.decode()


def test_hotel_home_is_the_day_summary_not_the_grid():
    unit = _unit()
    _book(unit, 0, name="Familie Sommer")
    html = _home()
    assert "data-hotel-home" in html
    assert 'id="bp-region"' not in html  # шахматка — на «Verkäufe»
    assert "Familie Sommer" in html  # заезд сегодня
    assert "Belegung 7 Tage" in html and "Braucht Aufmerksamkeit" in html


def test_kpis_use_the_same_sources_as_the_screens():
    a = _unit(quantity=2)
    b = _unit(quantity=1)
    _book(a, 0, name="Anreise A")
    _book(a, -1, nights=1, name="Abreise A")  # выезд сегодня
    _book(b, -2, nights=4, name="Im Haus B")
    html = _home()
    # занято сегодня: A — 1 из 2, B — 1 из 1 → 2 von 3
    assert "2 von 3" in html
    assert "1 / 1" in html  # Anreisen / Abreisen


def test_unpaid_kpi_counts_transfer_bookings_not_pay_on_site():
    unit = _unit()
    _book(unit, 3, name="Vor Ort")  # оплата на месте — не долг
    _book(unit, 5, name="Vorkasse", payment_method="vorkasse")
    html = _home()
    assert "1 Buchung" in html
    assert "200,00 €" in html or "200.00 €" in html


def test_dirty_room_has_clean_button_that_returns_home():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="101", housekeeping=Room.HK_DIRTY)
    html = _home()
    assert f'action="/dashboard/stays/zimmer/{room.pk}/sauber/"' in html
    assert 'name="next" value="/dashboard/"' in html


def test_room_clean_respects_local_next_only():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="7", housekeeping=Room.HK_DIRTY)
    for nxt, expected in (("/dashboard/", "/dashboard/"), ("//evil.example", None)):
        req = RequestFactory().post("/x/", {"next": nxt})
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = _req(_tenant("hotel")).user
        resp = views.room_clean(req, pk=room.pk)
        if expected:
            assert resp.url == expected
        else:
            assert "evil" not in resp.url
    room.refresh_from_db()
    assert room.housekeeping == Room.HK_CLEAN


def test_attention_lists_unconfirmed_and_missing_room():
    unit = _unit()
    Room.objects.create(unit=unit, number="1")
    _book(unit, 4, name="Ohne Zimmer")  # подтверждена, номер не назначен
    _book(unit, 6, name="Offen", auto_confirm=False)  # ждёт подтверждения
    html = _home()
    assert "1 Buchung unbestätigt" in html
    assert "ohne Zimmer" in html


def test_query_count_does_not_grow_with_bookings(django_assert_max_num_queries):
    tenant = _tenant("hotel")
    unit = _unit(quantity=20)
    for i in range(3):
        _book(unit, 0, name=f"G{i}")
    req = _owner_req(tenant)
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as small:
        core_views.dashboard(req)
    for i in range(12):
        _book(unit, i % 3, name=f"H{i}")
    req2 = _owner_req(tenant)
    with CaptureQueriesContext(connection) as big:
        core_views.dashboard(req2)
    # +4 запаса: списки «Heute» ограничены LIST_LIMIT, загрузка — два запроса на окно
    assert len(big) <= len(small) + 4, (len(small), len(big))


def test_other_archetypes_keep_their_loop():
    html = _home(_tenant("friseur"))
    assert "data-hotel-home" not in html and "Tage blockieren" in html


def test_hotel_home_has_no_scripts_or_inline_handlers():
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "templates/stays/_hotel_home.html").read_text()
    assert "<script" not in text and not re.search(r"\son[a-z]+=", text)


def test_new_booking_button_opens_drawer():
    html = _home()
    assert 'href="/dashboard/stays/neu/" data-drawer' in html


def test_cancelled_booking_is_not_counted_as_arrival():
    unit = _unit()
    b = _book(unit, 0, name="Storniert")
    StayBooking.objects.filter(pk=b.pk).update(status="cancelled")
    html = _home()
    assert "Storniert" not in html
