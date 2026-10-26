"""Beat-задачи заявок Handwerker/Werkstatt.

A9: TÜV/Service-Reminder — за SERVICE_REMINDER_LEAD_DAYS до `Job.service_due_date`
шлём клиенту одно письмо (service_reminder_sent_at + БД-дедуп Notification по дате).
Идём по всем схемам арендаторов (как booking/stays reminders).
"""

import logging

from celery import shared_task
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context, tenant_context

from .models import Job, Vehicle
from .notifications import enqueue_job_email

logger = logging.getLogger(__name__)


def _iter_tenants():
    with schema_context("public"):
        return list(get_tenant_model().objects.exclude(schema_name="public"))


def send_due_service_reminders(today=None, tenant=None) -> int:
    """Чистая логика для текущей схемы: число отправленных TÜV/Service-напоминаний.

    Окно — от сегодня до сегодня+LEAD дней (прошедшие даты не трогаем; смена даты в
    кабинете сбрасывает sent_at). Одно письмо на (заявку, дату)."""
    today = today or timezone.localdate()
    lead = getattr(settings, "SERVICE_REMINDER_LEAD_DAYS", 21)
    horizon = today + timezone.timedelta(days=lead)
    from apps.core import status_registry

    # KA-H7: отменённая/отклонённая заявка напоминаний не шлёт (вкл. свои статусы).
    due = (
        Job.objects.select_related("customer")
        .filter(
            service_reminder_sent_at__isnull=True,
            service_due_date__isnull=False,
            service_due_date__gte=today,
            service_due_date__lte=horizon,
        )
        .exclude(status__in=status_registry.cancelled_statuses_for("job", tenant))
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


def send_due_hu_reminders(today=None, tenant=None) -> int:
    """KA-12 A-6b: HU-напоминания по карточкам машин (`Vehicle.hu_due`) текущей схемы.

    Окно и переключатель канала — как у TÜV/Service (A9). Одно письмо на дату HU:
    отметка `hu_reminder_sent_for` + дедуп Notification по дате. Если у живой заявки
    этой машины тот же срок в `service_due_date`, письмо шлёт A9 — машину только
    помечаем. Нет почты/отписан/канал выключен — не помечаем (письмо уйдёт, когда
    станет можно)."""
    from apps.core import status_registry
    from apps.notifications.prefs import channel_enabled
    from apps.notifications.services import notify
    from apps.promotions.notifications import _render, _tenant

    today = today or timezone.localdate()
    lead = getattr(settings, "SERVICE_REMINDER_LEAD_DAYS", 21)
    horizon = today + timezone.timedelta(days=lead)
    due = Vehicle.objects.select_related("customer").filter(
        hu_due__isnull=False, hu_due__gte=today, hu_due__lte=horizon
    )
    tenant_obj = tenant or _tenant(connection.schema_name)
    if not channel_enabled(tenant_obj, "customer", "job", "service_reminder", "email"):
        return 0
    cancelled = status_registry.cancelled_statuses_for("job", tenant)
    sent = 0
    for vehicle in due.iterator():
        if vehicle.hu_reminder_sent_for == vehicle.hu_due:
            continue
        customer = vehicle.customer
        if not (customer.email and not customer.unsubscribed):
            continue
        covered = (
            vehicle.jobs.filter(service_due_date=vehicle.hu_due)
            .exclude(status__in=cancelled)
            .exists()
        )
        if not covered:
            subject, body, html = _render(
                "vehicle_hu_reminder", {"vehicle": vehicle, "customer": customer}
            )
            notify(
                dedupe_key=f"vehicle:{vehicle.pk}:hu:{vehicle.hu_due.isoformat()}:customer",
                type="vehicle_hu_reminder",
                recipient=customer.email,
                subject=subject,
                body=body,
                html=html,
            )
            sent += 1
        Vehicle.objects.filter(pk=vehicle.pk).update(hu_reminder_sent_for=vehicle.hu_due)
    return sent


@shared_task
def send_service_reminders():
    """Beat (раз в сутки): TÜV/Service- и HU-напоминания по всем схемам арендаторов.

    Сбой одного бизнеса пишется в лог и не останавливает остальных."""
    total = 0
    for tenant in _iter_tenants():
        # KA-H7: tenant_context — настоящий тенант (свои статусы отмены в site_config);
        # schema_context даёт FakeTenant без конфига.
        try:
            with tenant_context(tenant):
                total += send_due_service_reminders(tenant=tenant)
                total += send_due_hu_reminders(tenant=tenant)
        except Exception:
            logger.exception("service reminders failed for %s", tenant.schema_name)
    return total
