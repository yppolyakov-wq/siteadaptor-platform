"""Beat-задачи записи по времени (Track D / D3c).

Напоминание клиенту за BOOKING_REMINDER_HOURS до начала: ровно одно на запись
(reminder_sent_at + БД-дедуп Notification). Прошедшие записи не трогаем.
"""

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import Booking
from .notifications import enqueue_booking_email


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


def send_due_reminders(now=None) -> int:
    """Чистая логика для текущей схемы: вернуть число отправленных напоминаний."""
    now = now or timezone.now()
    horizon = now + timezone.timedelta(hours=getattr(settings, "BOOKING_REMINDER_HOURS", 24))
    due = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED,
        reminder_sent_at__isnull=True,
        start__gt=now,
        start__lte=horizon,
    )
    sent = 0
    for booking in due:
        enqueue_booking_email(booking, "reminder")
        booking.reminder_sent_at = now
        booking.save(update_fields=["reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_booking_reminders():
    """Beat (раз в час): напоминания по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_reminders()
    return total


def send_due_post_visits(now=None) -> int:
    """UA4-4b wiring: post-visit письмо (danke + запрос отзыва об услуге) после
    завершения записи — ровно одно на запись (post_visit_sent_at + БД-дедуп).
    Окно [end ≥ N+7 дней назад … end ≤ N дней назад] (подхват пропусков, как
    post-stay у stays); только состоявшиеся записи УСЛУГ (есть что оценивать)."""
    now = now or timezone.now()
    days = getattr(settings, "BOOKING_POSTVISIT_DAYS", 1)
    upper = now - timezone.timedelta(days=days)  # закончилась хотя бы N дней назад
    lower = upper - timezone.timedelta(days=7)  # окно подхвата пропусков
    due = Booking.objects.filter(
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_FULFILLED),
        post_visit_sent_at__isnull=True,
        service__isnull=False,
        end__gte=lower,
        end__lte=upper,
    )
    sent = 0
    for booking in due:
        enqueue_booking_email(booking, "post_visit")
        booking.post_visit_sent_at = timezone.now()
        booking.save(update_fields=["post_visit_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_booking_post_visits():
    """Beat (раз в сутки): post-visit письма по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_post_visits()
    return total


def send_due_payment_reminders(now=None) -> int:
    """B2.2: депозит запрошен, но не оплачен N часов — одно напоминание
    (transactional-гейт в enqueue). Только будущие записи."""
    now = now or timezone.now()
    hours = getattr(settings, "BOOKING_PAYREMIND_HOURS", 6)
    upper = now - timezone.timedelta(hours=hours)
    lower = upper - timezone.timedelta(days=7)
    due = Booking.objects.filter(
        payment_state=Booking.PAYMENT_PENDING,
        payment_reminder_sent_at__isnull=True,
        start__gt=now,
        created_at__gte=lower,
        created_at__lte=upper,
    )
    sent = 0
    for booking in due:
        enqueue_booking_email(booking, "payment_reminder")
        booking.payment_reminder_sent_at = timezone.now()
        booking.save(update_fields=["payment_reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_booking_payment_reminders():
    """Beat (раз в час): напоминания о неоплаченном депозите по всем схемам."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_payment_reminders()
    return total
