"""KA-12 E4.4a: буфер после записи, минимальный срок и горизонт записи услуги.

Буфер (`Service.buffer_after_minutes`) — уборка/подготовка после визита: запись
держит ресурс до `occupied_until` (NULL = `end`, старые записи как раньше); сетка
и проверка брони учитывают буфер и своей записи, и чужих; буфер может выходить
за часы работы. Минимальный срок (`min_lead_minutes`) и горизонт
(`max_days_ahead`) действуют только на витрине — ручная запись в кабинете их не
знает."""

import pathlib
import re
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import availability, services
from apps.booking.models import Booking
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


def _book(resource, start, end, service=None):
    return services.book(
        resource, start=start, end=end, name="Gast", email="g@t.de", service=service
    )


def test_null_occupied_until_equals_end():
    """Старая запись без буфера держит ровно [start, end)."""
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00", slot=60)
    _book(r, _aware(day, 9), _aware(day, 10))
    starts = [s for s, _e in availability.free_slots(r, day)]
    assert _aware(day, 10) in starts and _aware(day, 9) not in starts


def test_buffer_blocks_next_slot():
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00", slot=30)
    svc = _service(duration_minutes=60, buffer_after_minutes=30)
    b = _book(r, _aware(day, 9), _aware(day, 10), service=svc)
    b.refresh_from_db()
    assert b.occupied_until == _aware(day, 10, 30)
    starts = availability.service_slots(svc, day)
    assert _aware(day, 10) not in starts
    assert _aware(day, 10, 30) in starts


def test_own_buffer_must_fit_before_next_booking():
    """Новая запись с буфером не встаёт вплотную перед чужой."""
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00", slot=30)
    _book(r, _aware(day, 10), _aware(day, 11))
    svc = _service(duration_minutes=60, buffer_after_minutes=30)
    starts = availability.service_slots(svc, day)
    assert _aware(day, 9) not in starts  # 9–10 + буфер до 10:30 залезает на 10:00
    with pytest.raises(services.SlotTaken):
        _book(r, _aware(day, 9), _aware(day, 10), service=svc)


def test_buffer_may_extend_past_opening_hours():
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00", slot=60)
    svc = _service(duration_minutes=60, buffer_after_minutes=30)
    assert _aware(day, 11) in availability.service_slots(svc, day)


def test_move_shifts_occupied_until():
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "14:00", slot=30)
    svc = _service(duration_minutes=60, buffer_after_minutes=15)
    b = _book(r, _aware(day, 9), _aware(day, 10), service=svc)
    services.move(b, start=_aware(day, 12), end=_aware(day, 13))
    b.refresh_from_db()
    assert b.occupied_until == _aware(day, 13, 15)


def test_lead_time_hides_near_slots():
    today = timezone.localdate()
    r = _resource()
    _rule(r, today + timedelta(days=1), "00:00", "23:30", slot=30)
    svc = _service(duration_minutes=30, min_lead_minutes=48 * 60)
    assert availability.service_slots(svc, today + timedelta(days=1)) == []
    plain = _service(duration_minutes=30)
    assert availability.service_slots(plain, today + timedelta(days=1))


def test_max_days_ahead_closes_far_days():
    r = _resource()
    far = _future_day(10)
    _rule(r, far, "09:00", "12:00")
    svc = _service(duration_minutes=60, max_days_ahead=7)
    assert availability.service_slots(svc, far) == []
    assert availability.next_free_slot(svc, from_day=far) is None
    svc.max_days_ahead = None
    assert availability.service_slots(svc, far)


def test_cabinet_manual_booking_bypasses_lead():
    """Ручная запись владельцем — без минимального срока (сервис book его не знает)."""
    soon = timezone.now() + timedelta(hours=2)
    r = _resource()
    svc = _service(duration_minutes=30, min_lead_minutes=48 * 60)
    b = _book(r, soon, soon + timedelta(minutes=30), service=svc)
    assert b.pk


def test_no_bare_end_overlap_on_booking():
    """Пересечения записей считаются по занятости (`occupied_until`), а не по `end`:
    голый `end__gt` в booking-пересечениях молча проигнорировал бы буфер."""
    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("services.py", "availability.py"):
        for line in (root / name).read_text().splitlines():
            if re.search(r"\bend__gt\s*=", line):
                # допустима только грубая индексная граница «end > start − потолок буфера»
                assert "MAX_BUFFER_MINUTES" in line, (name, line)


def test_occupied_until_ignored_for_unbuffered_service():
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00")
    b = _book(r, _aware(day, 9), _aware(day, 10), service=_service(duration_minutes=60))
    b.refresh_from_db()
    assert b.occupied_until is None
    assert Booking.objects.filter(pk=b.pk).exists()


def test_service_form_saves_rules_by_sentinel(settings):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _service(buffer_after_minutes=15, min_lead_minutes=120, max_days_ahead=14)
    base = {"action": "update", "service": str(svc.pk), "duration": "60", "price_eur": "10"}
    views.services_view(_req("post", data=base))
    svc.refresh_from_db()
    assert (svc.buffer_after_minutes, svc.min_lead_minutes, svc.max_days_ahead) == (15, 120, 14)
    views.services_view(
        _req(
            "post",
            data={
                **base,
                "booking_rules_present": "1",
                "buffer_after_minutes": "abc",
                "min_lead_hours": "48",
                "max_days_ahead": "",
            },
        )
    )
    svc.refresh_from_db()
    assert (svc.buffer_after_minutes, svc.min_lead_minutes, svc.max_days_ahead) == (0, 2880, None)


def test_buffer_change_resyncs_future_bookings(settings, django_capture_on_commit_callbacks):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "12:00")
    svc = _service(duration_minutes=60)
    b = _book(r, _aware(day, 9), _aware(day, 10), service=svc)
    base = {"action": "update", "service": str(svc.pk), "duration": "60", "price_eur": "10"}
    with django_capture_on_commit_callbacks(execute=True):
        views.services_view(
            _req(
                "post",
                data={**base, "booking_rules_present": "1", "buffer_after_minutes": "20"},
            )
        )
    b.refresh_from_db()
    assert b.occupied_until == _aware(day, 10, 20)
    with django_capture_on_commit_callbacks(execute=True):
        views.services_view(
            _req("post", data={**base, "booking_rules_present": "1", "buffer_after_minutes": "0"})
        )
    b.refresh_from_db()
    assert b.occupied_until is None


def test_service_horizon_beyond_global_cap(settings):
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    far = _future_day(50)
    r = _resource(type="staff")
    _rule(r, far, "09:00", "12:00", slot=60)
    svc = _service(duration_minutes=60, max_days_ahead=90)
    req = RequestFactory().get(f"/termin/leistung/{svc.pk}/", {"tag": far.isoformat()})
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(schema_name="public")
    body = public_views.service_slots(req, pk=svc.pk).content.decode()
    assert 'data-slot="free"' in body  # день 50 открыт (общий потолок 30)


def test_default_horizon_applies_without_service_horizon():
    """Ревью: общий горизонт 30 дней действует и в проверке брони (не только в GET)."""
    r = _resource()
    far = _future_day(40)
    _rule(r, far, "09:00", "12:00")
    svc = _service(duration_minutes=60)
    assert availability.service_slots(svc, far) == []


def test_book_reads_fresh_buffer_not_stale_object():
    """Ревью (гонка с resync): объект услуги во вьюхе мог устареть — book берёт
    буфер из свежей строки под блокировкой ресурса."""
    from apps.booking.models import Service

    day = _future_day()
    r = _resource()
    svc = _service(duration_minutes=60)
    Service.objects.filter(pk=svc.pk).update(buffer_after_minutes=30)
    b = _book(r, _aware(day, 9), _aware(day, 10), service=svc)  # svc.buffer == 0 в памяти
    b.refresh_from_db()
    assert b.occupied_until == _aware(day, 10, 30)


def test_resync_reports_new_overlaps():
    day = _future_day()
    r = _resource()
    svc = _service(duration_minutes=60)
    _book(r, _aware(day, 9), _aware(day, 10), service=svc)
    _book(r, _aware(day, 10), _aware(day, 11), service=svc)
    svc.buffer_after_minutes = 30
    svc.save(update_fields=["buffer_after_minutes"])
    assert services.resync_occupancy(svc) == 2  # обе записи пары


def test_buffer_cap_enforced_by_database():
    from django.db import IntegrityError, transaction

    from apps.booking.models import MAX_BUFFER_MINUTES, Service

    svc = _service()
    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.filter(pk=svc.pk).update(buffer_after_minutes=MAX_BUFFER_MINUTES + 1)


def test_direct_resource_booking_respects_horizon(settings):
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    far = _future_day(40)
    r = _resource()
    _rule(r, far, "09:00", "12:00", slot=60)
    req = RequestFactory().post(
        f"/termin/{r.pk}/buchen/",
        {
            "start": _aware(far, 9).isoformat(),
            "end": _aware(far, 10).isoformat(),
            "name": "X",
            "email": "x@t.de",
        },
        REMOTE_ADDR="10.44.0.7",
    )
    req.tenant = TenantFactory.build(schema_name="public")
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(req)
    req._messages = FallbackStorage(req)
    public_views.termin_book(req, pk=r.pk)
    assert not Booking.objects.filter(resource=r).exists()


def test_junk_horizon_keeps_previous_value(settings):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _service(max_days_ahead=14, min_lead_minutes=90)
    views.services_view(
        _req(
            "post",
            data={
                "action": "update",
                "service": str(svc.pk),
                "duration": "60",
                "price_eur": "10",
                "booking_rules_present": "1",
                "buffer_after_minutes": "0",
                "min_lead_hours": "2",  # форма показала round(90/60) = 2
                "max_days_ahead": "abc",
            },
        )
    )
    svc.refresh_from_db()
    assert svc.max_days_ahead == 14 and svc.min_lead_minutes == 90
