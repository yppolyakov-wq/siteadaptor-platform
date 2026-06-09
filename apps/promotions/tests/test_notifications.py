"""Тесты писем по броням через apps.notifications (Sprint 6).

Создание: enqueue_reservation_email → строки Notification (БД-дедуп).
Доставка: deliver() → mail.outbox (locmem backend в тестах).
"""

import pytest

from apps.notifications.models import Notification
from apps.notifications.tasks import deliver
from apps.promotions.notifications import enqueue_reservation_email
from apps.promotions.services import cancel, confirm, reserve
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def test_created_makes_customer_notification_and_delivers(mailoutbox):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anna", email="anna@test.de", quantity=2)

    n = Notification.objects.get(dedupe_key=f"resv:{res.id}:created:customer")
    assert n.recipient == "anna@test.de"
    assert res.reference_code in n.payload["body"]

    assert deliver(str(n.id)) == "sent"
    assert len(mailoutbox) == 1
    assert "anna@test.de" in mailoutbox[0].to
    assert res.reference_code in mailoutbox[0].body


def test_no_notification_when_customer_has_no_email():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anon", email="", quantity=1)
    assert not Notification.objects.filter(dedupe_key__startswith=f"resv:{res.id}:").exists()


def test_confirm_and_cancel_create_notifications():
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="Bob", email="bob@test.de")
    confirm(res)
    assert Notification.objects.filter(dedupe_key=f"resv:{res.id}:confirmed:customer").exists()

    cancel(res)
    cancelled = Notification.objects.get(dedupe_key=f"resv:{res.id}:cancelled:customer")
    assert "storniert" in cancelled.subject.lower()


def test_repeat_enqueue_keeps_single_notification():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Cara", email="cara@test.de")
    enqueue_reservation_email(res, "created")  # повтор того же события
    assert Notification.objects.filter(dedupe_key=f"resv:{res.id}:created:customer").count() == 1
