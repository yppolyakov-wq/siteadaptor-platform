"""Beat-задачи date-range-броней (Track E / E3).

Напоминание гостю перед заездом: ровно одно на бронь (reminder_sent_at + БД-дедуп
Notification). Дата-гранулярность → достаточно ежедневного прогона.
"""

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import StayBooking
from .notifications import enqueue_stay_email


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


def send_due_stay_reminders(today=None) -> int:
    """Чистая логика для текущей схемы: вернуть число отправленных напоминаний."""
    today = today or timezone.localdate()
    horizon = today + timezone.timedelta(days=getattr(settings, "STAY_REMINDER_DAYS", 1))
    due = StayBooking.objects.filter(
        status=StayBooking.STATUS_CONFIRMED,
        reminder_sent_at__isnull=True,
        arrival__gte=today,
        arrival__lte=horizon,
    )
    sent = 0
    for booking in due:
        enqueue_stay_email(booking, "reminder")
        booking.reminder_sent_at = timezone.now()
        booking.save(update_fields=["reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_stay_reminders():
    """Beat (раз в сутки): напоминания о заезде по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_stay_reminders()
    return total
