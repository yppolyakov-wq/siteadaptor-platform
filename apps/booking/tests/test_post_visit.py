"""UA4-4b wiring: post-visit письмо после записи услуги — ровно одно на запись,
ссылка ведёт на generic-форму отзыва `/leistung/<pk>/bewerten/` (абсолютная)."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.booking.models import Booking, Resource, Service
from apps.booking.tasks import send_due_post_visits
from apps.notifications.models import Notification
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _booking(end_days_ago, status=Booking.STATUS_FULFILLED, with_service=True, **kw):
    resource = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    svc = (
        Service.objects.create(name=f"S {uuid.uuid4().hex[:6]}", price_cents=4900)
        if with_service
        else None
    )
    cust = Customer.objects.create(name="Kunde", email=f"{uuid.uuid4().hex[:6]}@t.de")
    end = timezone.now() - timedelta(days=end_days_ago)
    return Booking.objects.create(
        resource=resource,
        service=svc,
        customer=cust,
        reference_code="T-" + uuid.uuid4().hex[:6].upper(),
        start=end - timedelta(hours=1),
        end=end,
        status=status,
        **kw,
    )


def test_post_visit_sent_once_with_absolute_review_link():
    from apps.tenants.tests.factories import DomainFactory, TenantFactory

    tenant = TenantFactory(schema_name=connection.schema_name)
    DomainFactory(tenant=tenant, domain="salon.example.de", is_primary=True)
    b = _booking(end_days_ago=2)
    assert send_due_post_visits() == 1
    b.refresh_from_db()
    assert b.post_visit_sent_at is not None
    n = Notification.objects.get(dedupe_key=f"booking:{b.id}:post_visit:customer")
    # абсолютная ссылка на generic-форму отзыва об услуге (GET → деталь с формой)
    assert f"https://salon.example.de/leistung/{b.service_id}/bewerten/" in n.payload["body"]
    # повторный прогон — не дублирует (idempotent)
    assert send_due_post_visits() == 0


def test_post_visit_without_domain_sends_without_link():
    b = _booking(end_days_ago=1)
    assert send_due_post_visits() == 1
    n = Notification.objects.get(dedupe_key=f"booking:{b.id}:post_visit:customer")
    assert "/bewerten/" not in n.payload["body"]  # нет домена → письмо без ссылки


def test_post_visit_skips_booking_without_service():
    _booking(end_days_ago=2, with_service=False)  # общая бронь стола — нечего оценивать
    assert send_due_post_visits() == 0


def test_post_visit_skips_cancelled_and_no_show():
    _booking(end_days_ago=2, status=Booking.STATUS_CANCELLED)
    _booking(end_days_ago=2, status=Booking.STATUS_NO_SHOW)
    assert send_due_post_visits() == 0


def test_post_visit_respects_window():
    _booking(end_days_ago=0)  # закончилась сегодня — рано (нужно ≥1 день назад)
    _booking(end_days_ago=30)  # слишком давно — вне окна подхвата (7 дней)
    assert send_due_post_visits() == 0
