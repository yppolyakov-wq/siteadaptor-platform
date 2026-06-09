"""Тесты S6.4: авто-уведомление листа ожидания при возврате остатка."""

import pytest

from apps.notifications.models import Notification
from apps.promotions.models import WaitlistEntry
from apps.promotions.services import cancel, notify_waitlist_available, reserve
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def test_cancel_notifies_waitlist_once():
    promo = PromotionFactory(available_quantity=1)
    res = reserve(promo, name="A", email="a@t.de")  # остаток 0
    entry = WaitlistEntry.objects.create(promotion=promo, email="w@t.de", name="W")

    cancel(res)  # возврат остатка → уведомление

    entry.refresh_from_db()
    assert entry.notified is True
    notification = Notification.objects.get(dedupe_key=f"waitlist:{entry.id}:available")
    assert notification.recipient == "w@t.de"
    assert "verfügbar" in notification.subject.lower()

    # повторный прогон — без новых уведомлений (флаг + dedupe)
    promo.refresh_from_db()
    assert notify_waitlist_available(promo) == 0
    assert Notification.objects.filter(dedupe_key__startswith="waitlist:").count() == 1


def test_notify_capped_by_available_quantity():
    promo = PromotionFactory(available_quantity=1)
    res = reserve(promo, name="A", email="a@t.de")
    first = WaitlistEntry.objects.create(promotion=promo, email="w1@t.de")
    second = WaitlistEntry.objects.create(promotion=promo, email="w2@t.de")

    cancel(res)  # вернулась 1 штука → уведомляем только первого в очереди

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.notified is True
    assert second.notified is False


def test_inactive_promotion_not_notified():
    promo = PromotionFactory(available_quantity=3, status="ended")
    WaitlistEntry.objects.create(promotion=promo, email="w@t.de")
    assert notify_waitlist_available(promo) == 0
    assert not Notification.objects.filter(dedupe_key__startswith="waitlist:").exists()
