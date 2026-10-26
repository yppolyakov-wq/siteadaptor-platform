"""KA-12 GA-0: серверный золотой путь направления «Gastro» (cafe, restaurant).

Бронь стола онлайн и со стойки, пул мест, подтверждение, Mittagstisch. Сегодняшние
дефекты зафиксированы `xfail(strict=True)` с кодом инкремента, который их закрывает
(план `docs/ka-12-w4-gastro-plan-2026-10-26.md`): когда инкремент чинит — xfail
становится XPASS и падает, его снимают. Браузерный двойник — GP-7 в
`scripts/golden_paths.py`."""

import datetime
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Resource
from apps.booking.state_machine import BookingSM
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _start(hours=48):
    return (timezone.now() + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)


def _pool(capacity=40):
    return Resource.objects.create(name="Tische", capacity=capacity, counts_party_size=True)


def _table(seats=2):
    return Resource.objects.create(name="Tisch 4", capacity=1, seats=seats)


def test_online_table_booking_waits_for_confirmation():
    pool = _pool()
    start = _start()
    b = services.book(pool, start=start, end=start + timedelta(hours=2), name="Gast", party_size=2)
    assert b.status == "pending"
    BookingSM().apply(b, "confirmed", actor=None)
    assert b.status == "confirmed"


def test_pool_counts_guests_not_bookings():
    pool = _pool(capacity=10)
    start = _start()
    services.book(pool, start=start, end=start + timedelta(hours=2), name="A", party_size=8)
    with pytest.raises(services.SlotTaken):
        services.book(pool, start=start, end=start + timedelta(hours=2), name="B", party_size=3)


def test_walk_in_from_counter_is_confirmed():
    pool = _pool()
    booking, _warn = services.create_manual(
        pool, start=_start(), minutes=120, party_size=4, name="Laufkundschaft", override_hours=True
    )
    assert booking.status == "confirmed" and booking.party_size == 4


def test_two_seat_table_refuses_eight_guests():
    table = _table()
    with pytest.raises(services.ManualBookingRefused):
        services.create_manual(
            table, start=_start(), minutes=120, party_size=8, name="Gruppe", override_hours=True
        )


def test_counter_booking_mail_says_confirmed(django_capture_on_commit_callbacks):
    pool = _pool()
    with django_capture_on_commit_callbacks(execute=True):
        services.create_manual(
            pool,
            start=_start(),
            minutes=120,
            party_size=2,
            name="Gast",
            email="gast@example.com",
            override_hours=True,
        )
    assert not Notification.objects.filter(
        recipient="gast@example.com", type="booking_created"
    ).exists()


def test_weekday_lunch_skips_weekend():
    from apps.promotions.models import Promotion
    from apps.promotions.tasks import roll_due_recurring
    from apps.promotions.tests.factories import PromotionFactory

    # пятница 11–15, правило «Mo–Fr»
    friday = datetime.date(2026, 10, 30)
    tz = timezone.get_current_timezone()
    starts = timezone.make_aware(datetime.datetime.combine(friday, datetime.time(11)), tz)
    PromotionFactory(
        status="ended",
        recurrence="daily",
        starts_at=starts,
        ends_at=starts + timedelta(hours=4),
        target_rules={"weekdays": [0, 1, 2, 3, 4], "hour_from": 11, "hour_to": 15},
    )
    roll_due_recurring(starts + timedelta(hours=5))
    heir = Promotion.objects.get(status="scheduled")
    assert timezone.localtime(heir.starts_at).weekday() == 0  # понедельник
