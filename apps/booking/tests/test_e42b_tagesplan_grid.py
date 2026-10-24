"""KA-12 E4.2b (B5): Tagesplan «ресурс × время» + перенос перетаскиванием.

Сервис `move` умеет сменить ресурс (мастер/стол): все проверки — по ЦЕЛЕВОМУ ресурсу
(закрытие, часы, буфер, ёмкость), двигаются только активные записи, письмо клиенту —
только при смене времени. Кабинетный приёмник отвечает fetch-у 204 / 409 JSON."""

import json

import pytest

from apps.booking import services
from apps.booking.models import Booking, ClosedDate
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


def _book(resource, day, h0, h1, service=None, party=1):
    return services.book(
        resource,
        start=_aware(day, h0),
        end=_aware(day, h1),
        name="Gast",
        email="g@t.de",
        service=service,
        party_size=party,
        auto_confirm=True,
    )


def _two(day):
    anna, ben = _resource(type="staff"), _resource(type="staff")
    _rule(anna, day, "09:00", "18:00")
    _rule(ben, day, "09:00", "18:00")
    return anna, ben


def test_move_to_other_resource_changes_resource_and_buffer():
    day = _future_day()
    anna, ben = _two(day)
    svc = _service(duration_minutes=60, buffer_after_minutes=15)
    b = _book(anna, day, 10, 11, service=svc)
    services.move(b, start=_aware(day, 12), end=_aware(day, 13), resource=ben)
    b.refresh_from_db()
    assert b.resource_id == ben.pk
    assert b.occupied_until == _aware(day, 13, 15)


def test_target_busy_with_its_buffer_is_slot_taken():
    day = _future_day()
    anna, ben = _two(day)
    svc = _service(duration_minutes=60, buffer_after_minutes=30)
    _book(ben, day, 11, 12, service=svc)  # держит Ben до 12:30
    b = _book(anna, day, 10, 11)
    with pytest.raises(services.SlotTaken):
        services.move(b, start=_aware(day, 12), end=_aware(day, 13), resource=ben)
    b.refresh_from_db()
    assert b.resource_id == anna.pk and b.start == _aware(day, 10)


def test_target_capacity_counts_party():
    day = _future_day()
    big = _resource(capacity=6, counts_party_size=True)
    small = _resource(capacity=2, counts_party_size=True)
    _rule(big, day, "09:00", "18:00")
    _rule(small, day, "09:00", "18:00")
    b = _book(big, day, 10, 11, party=4)
    with pytest.raises(services.SlotTaken):
        services.move(b, start=_aware(day, 10), end=_aware(day, 11), resource=small)


def test_closed_target_refused_even_with_override():
    day = _future_day()
    anna, ben = _two(day)
    ClosedDate.objects.create(resource=ben, date=day)
    b = _book(anna, day, 10, 11)
    with pytest.raises(services.ResourceClosed):
        services.move(
            b, start=_aware(day, 10), end=_aware(day, 11), resource=ben, override_hours=True
        )


def test_outside_target_hours_needs_override():
    day = _future_day()
    anna = _resource(type="staff")
    ben = _resource(type="staff")
    _rule(anna, day, "09:00", "18:00")
    _rule(ben, day, "14:00", "18:00")
    b = _book(anna, day, 10, 11)
    with pytest.raises(services.OutsideHours):
        services.move(b, start=_aware(day, 10), end=_aware(day, 11), resource=ben)
    services.move(b, start=_aware(day, 10), end=_aware(day, 11), resource=ben, override_hours=True)
    b.refresh_from_db()
    assert b.resource_id == ben.pk


@pytest.mark.parametrize("status", ["fulfilled", "no_show", "cancelled"])
def test_finished_bookings_are_not_movable(status):
    day = _future_day()
    anna, _ben = _two(day)
    b = _book(anna, day, 10, 11)
    Booking.objects.filter(pk=b.pk).update(status=status)
    b.refresh_from_db()
    with pytest.raises(services.NotMovable):
        services.move(b, start=_aware(day, 12), end=_aware(day, 13))


def test_inactive_target_refused():
    day = _future_day()
    anna, ben = _two(day)
    ben.is_active = False
    ben.save(update_fields=["is_active"])
    b = _book(anna, day, 10, 11)
    with pytest.raises(services.ResourceInactive):
        services.move(b, start=_aware(day, 10), end=_aware(day, 11), resource=ben)


def test_resource_only_move_sends_no_mail(django_capture_on_commit_callbacks, monkeypatch):
    sent = []
    from apps.booking import notifications

    monkeypatch.setattr(notifications, "enqueue_booking_email", lambda b, kind: sent.append(kind))
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    with django_capture_on_commit_callbacks(execute=True):
        services.move(b, start=_aware(day, 10), end=_aware(day, 11), resource=ben)
    assert "moved" not in sent
    with django_capture_on_commit_callbacks(execute=True):
        services.move(b, start=_aware(day, 12), end=_aware(day, 13), resource=ben)
    assert "moved" in sent


# --- приёмник кабинета ------------------------------------------------------------


def _post(booking, data, fetch=True):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    req = _req("post", f"/dashboard/booking/{booking.pk}/action/", {"action": "move", **data})
    if fetch:
        req.META["HTTP_X_REQUESTED_WITH"] = "fetch"
    return views.booking_action(req, pk=booking.pk), req


def _local(day, h, m=0):
    return f"{day.isoformat()}T{h:02d}:{m:02d}"


def test_fetch_move_returns_204(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    resp, _ = _post(b, {"start": _local(day, 14), "resource": str(ben.pk)})
    assert resp.status_code == 204
    b.refresh_from_db()
    assert b.resource_id == ben.pk and b.start == _aware(day, 14)


@pytest.mark.parametrize(
    "case,code",
    [
        ("busy", "slot_taken"),
        ("hours", "outside_hours"),
        ("junk", "invalid"),
        ("done", "not_movable"),
    ],
)
def test_fetch_move_conflicts_are_409_json(settings, case, code):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    start = _local(day, 14)
    if case == "busy":
        _book(ben, day, 14, 15)
    if case == "hours":
        start = _local(day, 20)
    if case == "junk":
        start = "kaputt"
    if case == "done":
        Booking.objects.filter(pk=b.pk).update(status="fulfilled")
    resp, _ = _post(b, {"start": start, "resource": str(ben.pk)})
    assert resp.status_code == 409
    assert json.loads(resp.content)["code"] == code


def test_fetch_override_hours_passes(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    resp, _ = _post(b, {"start": _local(day, 20), "override_hours": "1"})
    assert resp.status_code == 204


def test_foreign_or_inactive_resource_is_404(settings):
    from django.http import Http404

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    ben.is_active = False
    ben.save(update_fields=["is_active"])
    b = _book(anna, day, 10, 11)
    for raw in (str(ben.pk), "abc"):
        with pytest.raises(Http404):
            _post(b, {"start": _local(day, 14), "resource": raw})


def test_move_to_unskilled_master_warns(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.contrib.messages import get_messages

    day = _future_day()
    anna, ben = _two(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([anna])
    b = _book(anna, day, 10, 11, service=svc)
    resp, req = _post(b, {"start": _local(day, 14), "resource": str(ben.pk)})
    assert resp.status_code == 204
    assert any("Hinweis" in str(m) for m in get_messages(req))


def test_form_move_without_fetch_still_redirects(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    resp, _ = _post(b, {"start": _local(day, 14), "resource": str(ben.pk)}, fetch=False)
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.resource_id == ben.pk


# --- сетка ------------------------------------------------------------------------


def _render(day, compact=False):
    from django.template.loader import render_to_string

    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    req = _req("get", "/dashboard/booking/", {"tag": day.isoformat()})
    ctx = views.calendar_context(req)
    ctx["deal_calendar_compact"] = compact
    return ctx, render_to_string("booking/_tagesplan_body.html", ctx, request=req)


def test_grid_geometry_and_buffer(settings):
    from apps.booking import tagesplan

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)  # 09–18, шаг 30
    svc = _service(duration_minutes=60, buffer_after_minutes=30)
    b = _book(anna, day, 10, 11, service=svc)
    grid = tagesplan.build([anna, ben], day, [b], active_statuses=("confirmed",))
    assert grid.step == 30 and grid.rows[0][1] == "09:00"
    blk = grid.columns[0].blocks[0]
    assert (blk.row, blk.span, blk.buffer_span, blk.movable) == (3, 2, 1, True)
    assert grid.columns[1].blocks == []


def test_grid_extends_to_booking_outside_hours():
    from apps.booking import tagesplan

    day = _future_day()
    anna, _ben = _two(day)
    b = _book(anna, day, 19, 20)
    grid = tagesplan.build([anna], day, [b])
    assert grid.rows[-1][1] == "19:30"
    assert grid.columns[0].blocks[0].movable is False  # без active_statuses — не двигается


def test_grid_fallback_without_hours():
    from apps.booking import tagesplan

    day = _future_day()
    r = _resource()
    grid = tagesplan.build([r], day, [])
    assert grid.rows[0][1] == "08:00" and grid.rows[-1][1] == "19:30"


def test_render_grid_columns_blocks_and_form_stays(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two(day)
    b = _book(anna, day, 10, 11)
    _ctx, body = _render(day)
    assert f'data-tp-col="{anna.pk}"' in body and f'data-tp-col="{ben.pk}"' in body
    assert f'data-tp-block="{b.pk}"' in body and 'draggable="true"' in body
    assert "grid-row:3 / span 2" in body
    # W0: форма переноса строки (время + ресурс) — в DOM вместе с сеткой.
    assert 'name="start"' in body and 'name="resource"' in body and 'name="override_hours"' in body


def test_compact_grid_has_no_drag(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, _ben = _two(day)
    _book(anna, day, 10, 11)
    _ctx, body = _render(day, compact=True)
    assert "data-tp-grid" in body
    assert 'draggable="true"' not in body and "__tpBound" not in body


def test_grid_queries_do_not_grow_with_bookings(settings, django_assert_max_num_queries):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    rs = [_resource(type="staff") for _ in range(5)]
    for r in rs:
        _rule(r, day, "08:00", "20:00")
    svc = _service(duration_minutes=30)
    for r in rs:
        for h in (9, 11, 13, 15):
            _book(r, day, h, h + 1, service=svc)
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    req = _req("get", "/dashboard/booking/", {"tag": day.isoformat()})
    with django_assert_max_num_queries(30):
        views.calendar_context(req)


def test_booking_of_inactive_resource_still_moves_in_time():
    """Ревью B5: выключенный ресурс запрещён только как ЦЕЛЬ — запись мастера,
    которого выключили, по-прежнему переносится по времени (как до B5)."""
    day = _future_day()
    anna, _ben = _two(day)
    b = _book(anna, day, 10, 11)
    anna.is_active = False
    anna.save(update_fields=["is_active"])
    services.move(b, start=_aware(day, 12), end=_aware(day, 13))
    b.refresh_from_db()
    assert b.start == _aware(day, 12) and b.resource_id == anna.pk


def test_cancelled_between_show_and_move_is_not_movable():
    day = _future_day()
    anna, _ben = _two(day)
    b = _book(anna, day, 10, 11)
    Booking.objects.filter(pk=b.pk).update(status="cancelled")  # объект в памяти — confirmed
    with pytest.raises(services.NotMovable):
        services.move(b, start=_aware(day, 12), end=_aware(day, 13))


def test_closed_dates_read_once_for_grid(django_assert_num_queries):
    from apps.booking import tagesplan
    from apps.booking.models import Resource

    day = _future_day()
    for _ in range(4):
        _rule(_resource(), day, "09:00", "12:00")
    rs = list(Resource.objects.prefetch_related("rules"))
    with django_assert_num_queries(1):
        tagesplan.build(rs, day, [])
