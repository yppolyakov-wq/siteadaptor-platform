"""KA-12 E4.4b (B6): самоперенос записи гостем.

В окне бесплатной отмены, не больше двух раз, только на свободное время мастера с
навыком; своя запись не занимает слот при переносе; длина — снимок записи; другая
сезонная цена / время вне правил акции / pool-опция на другой день — отказ."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import cancel_policy, services
from apps.booking.models import Booking, ServiceSeasonRate
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


def _setup(day, minutes=60, **svc_kw):
    r = _resource(type="staff")
    _rule(r, day, "09:00", "18:00", slot=30)
    svc = _service(duration_minutes=minutes, **svc_kw)
    b = services.book(
        r,
        start=_aware(day, 10),
        end=_aware(day, 10) + timedelta(minutes=minutes),
        name="Gast",
        email="g@t.de",
        service=svc,
        auto_confirm=True,
    )
    return r, svc, b


def test_reschedule_moves_and_counts(django_capture_on_commit_callbacks, monkeypatch):
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "enqueue_booking_email", lambda b, kind: sent.append(kind))
    day = _future_day()
    r, svc, b = _setup(day)
    with django_capture_on_commit_callbacks(execute=True):
        moved = cancel_policy.guest_reschedule(b, start=_aware(day, 14))
    assert moved.start == _aware(day, 14) and moved.end == _aware(day, 15)
    assert moved.reschedule_count == 1 and moved.reminder_sent_at is None
    assert sent.count("moved") == 1 and sent.count("guest_moved") == 1


def test_third_reschedule_refused():
    day = _future_day()
    r, svc, b = _setup(day)
    b = cancel_policy.guest_reschedule(b, start=_aware(day, 12))
    b = cancel_policy.guest_reschedule(b, start=_aware(day, 14))
    with pytest.raises(cancel_policy.RescheduleRefused):
        cancel_policy.guest_reschedule(b, start=_aware(day, 16))


def test_after_deadline_refused():
    r = _resource(type="staff")
    soon = timezone.now() + timedelta(hours=5)
    svc = _service(duration_minutes=60, cancel_window_hours=24)
    b = services.book(r, start=soon, end=soon + timedelta(hours=1), name="G", service=svc)
    with pytest.raises(cancel_policy.RescheduleRefused):
        cancel_policy.guest_reschedule(b, start=soon + timedelta(hours=2))


def test_shift_inside_own_interval_allowed():
    day = _future_day()
    r, svc, b = _setup(day)
    moved = cancel_policy.guest_reschedule(b, start=_aware(day, 10, 30))
    assert moved.start == _aware(day, 10, 30)


def test_busy_current_master_assigns_other_skilled():
    day = _future_day()
    r, svc, b = _setup(day)
    other = _resource(type="staff")
    _rule(other, day, "09:00", "18:00", slot=30)
    services.book(r, start=_aware(day, 14), end=_aware(day, 15), name="X", auto_confirm=True)
    moved = cancel_policy.guest_reschedule(b, start=_aware(day, 14))
    assert moved.resource_id == other.pk


def test_unskilled_master_not_assigned():
    day = _future_day()
    r, svc, b = _setup(day)
    other = _resource(type="staff")
    _rule(other, day, "09:00", "18:00", slot=30)
    svc.resources.set([r])
    services.book(r, start=_aware(day, 14), end=_aware(day, 15), name="X", auto_confirm=True)
    with pytest.raises(services.SlotTaken):
        cancel_policy.guest_reschedule(b, start=_aware(day, 14))


def test_length_from_snapshot_not_current_service():
    day = _future_day()
    r, svc, b = _setup(day, minutes=60)
    svc.duration_minutes = 30
    svc.save(update_fields=["duration_minutes"])
    moved = cancel_policy.guest_reschedule(b, start=_aware(day, 14))
    assert moved.end - moved.start == timedelta(minutes=60)


def test_other_season_price_refused():
    day = _future_day()
    r, svc, b = _setup(day)
    other_day = day + timedelta(days=7)
    _rule(r, other_day, "09:00", "18:00", slot=30)
    ServiceSeasonRate.objects.create(
        service=svc, start_date=other_day, end_date=other_day, price_cents=9900, label="Fest"
    )
    with pytest.raises(cancel_policy.RescheduleRefused) as exc:
        cancel_policy.guest_reschedule(b, start=_aware(other_day, 10))
    assert exc.value.reason == "price"


def test_group_booking_cannot_reschedule():
    day = _future_day()
    r, svc, b = _setup(day)
    Booking.objects.filter(pk=b.pk).update(group_code="G-1")
    b.refresh_from_db()
    with pytest.raises(cancel_policy.RescheduleRefused):
        cancel_policy.guest_reschedule(b, start=_aware(day, 14))
