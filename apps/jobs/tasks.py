"""Beat-задачи заявок Handwerker/Werkstatt.

A9: TÜV/Service-Reminder — за SERVICE_REMINDER_LEAD_DAYS до `Job.service_due_date`
шлём клиенту одно письмо (service_reminder_sent_at + БД-дедуп Notification по дате).
Идём по всем схемам арендаторов (как booking/stays reminders).
"""

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import Job
from .notifications import enqueue_job_email


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


def send_due_service_reminders(today=None) -> int:
    """Чистая логика для текущей схемы: число отправленных TÜV/Service-напоминаний.

    Окно — от сегодня до сегодня+LEAD дней (прошедшие даты не трогаем; смена даты в
    кабинете сбрасывает sent_at). Одно письмо на (заявку, дату)."""
    today = today or timezone.localdate()
    lead = getattr(settings, "SERVICE_REMINDER_LEAD_DAYS", 21)
    horizon = today + timezone.timedelta(days=lead)
    due = Job.objects.select_related("customer").filter(
        service_reminder_sent_at__isnull=True,
        service_due_date__isnull=False,
        service_due_date__gte=today,
        service_due_date__lte=horizon,
    )
    sent = 0
    for job in due:
        if not (job.customer.email and not job.customer.unsubscribed):
            continue
        enqueue_job_email(job, "service_reminder")
        job.service_reminder_sent_at = timezone.now()
        job.save(update_fields=["service_reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_service_reminders():
    """Beat (раз в сутки): TÜV/Service-напоминания по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_service_reminders()
    return total
