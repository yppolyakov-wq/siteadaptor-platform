"""Track B3b: авто-повтор завершившихся акций (beat клонирует со сдвигом окна).

Тестируем чистый helper roll_due_recurring в текущей (public) схеме — обход
схем арендаторов в самой beat-задаче тривиален.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions.models import Promotion
from apps.promotions.tasks import roll_due_recurring
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _ended(recurrence="daily", ago_hours=1, duration_hours=1, **extra):
    """Завершившаяся акция с окном в прошлом и заданным повтором."""
    now = timezone.now()
    ends = now - timedelta(hours=ago_hours)
    return PromotionFactory(
        status="ended",
        recurrence=recurrence,
        starts_at=ends - timedelta(hours=duration_hours),
        ends_at=ends,
        **extra,
    )


def test_spawns_scheduled_heir_in_future():
    promo = _ended(recurrence="daily")
    now = timezone.now()

    assert roll_due_recurring(now) == 1

    heir = Promotion.objects.get(status="scheduled")
    assert heir.pk != promo.pk
    assert heir.recurrence == "daily"  # цепочка продолжается через наследника
    assert heir.starts_at > now and heir.ends_at > now  # окно в будущем
    # длительность сохранена
    assert heir.ends_at - heir.starts_at == promo.ends_at - promo.starts_at


def test_parent_recurrence_cleared_one_heir_only():
    _ended(recurrence="weekly")
    now = timezone.now()

    assert roll_due_recurring(now) == 1
    # повторный прогон не плодит наследников: у родителя recurrence погашен,
    # наследник в scheduled (не ended) — ни один не подходит под фильтр
    assert roll_due_recurring(now) == 0
    assert Promotion.objects.count() == 2  # родитель + один наследник


def test_skips_missed_cycles_single_heir():
    # beat «молчал» 5 дней — наследник один, окно ближайшее будущее, без догона пачкой
    promo = _ended(recurrence="daily", ago_hours=24 * 5)
    now = timezone.now()

    assert roll_due_recurring(now) == 1
    heir = Promotion.objects.get(status="scheduled")
    assert heir.ends_at > now
    assert heir.ends_at <= now + timedelta(days=1)  # именно следующий цикл, не +5 дней
    promo.refresh_from_db()
    assert promo.recurrence == ""


def test_weekly_shifts_by_one_week():
    promo = _ended(recurrence="weekly")
    roll_due_recurring()
    heir = Promotion.objects.get(status="scheduled")
    assert heir.starts_at - promo.starts_at == timedelta(weeks=1)
    assert heir.ends_at - promo.ends_at == timedelta(weeks=1)


def test_non_recurring_ended_is_ignored():
    promo = _ended(recurrence="")
    assert roll_due_recurring() == 0
    promo.refresh_from_db()
    assert promo.status == "ended"
    assert Promotion.objects.count() == 1


def test_active_recurring_not_yet_spawned():
    # повтор срабатывает только по завершении, активную не трогаем
    PromotionFactory(
        status="active",
        recurrence="daily",
        starts_at=timezone.now() - timedelta(hours=1),
        ends_at=timezone.now() + timedelta(hours=1),
    )
    assert roll_due_recurring() == 0


def test_heir_copies_offer_fields():
    promo = _ended(
        recurrence="daily",
        is_surprise=True,
        discount_percent=30,
        available_quantity=7,
        max_per_customer=3,
    )
    roll_due_recurring()
    heir = Promotion.objects.get(status="scheduled")
    assert heir.is_surprise is True
    assert heir.discount_percent == 30
    assert heir.available_quantity == 7
    assert heir.max_per_customer == 3
    assert heir.title == promo.title
