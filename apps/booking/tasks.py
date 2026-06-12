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
