"""R9: beat-задачи событий — pre/post-event drip-письма.

Зеркало apps.stays.tasks (E3/G2): по одному письму на билет (поле *_sent_at +
БД-дедуп Notification). Дата-гранулярность → ежедневный прогон по всем схемам.
"""

from celery import shared_task
from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import Event, Ticket
from .notifications import enqueue_ticket_email


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


def _iter_tenant_billing():
    """[(schema, connect_id)] арендаторов с подключённой оплатой (R10c)."""
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .filter(payments_enabled=True)
            .exclude(stripe_connect_id="")
            .values_list("schema_name", "stripe_connect_id")
        )


def send_due_event_reminders(now=None) -> int:
    """Напоминание за N дней до события — ровно одно на подтверждённый билет."""
    now = now or timezone.now()
    horizon = now + timezone.timedelta(days=getattr(settings, "EVENT_REMINDER_DAYS", 7))
    due = Ticket.objects.filter(
        status=Ticket.STATUS_CONFIRMED,
        reminder_sent_at__isnull=True,
        event__status=Event.STATUS_PUBLISHED,
        event__starts_at__gte=now,
        event__starts_at__lte=horizon,
    ).select_related("event", "customer")
    sent = 0
    for ticket in due:
        enqueue_ticket_email(ticket, "reminder")
        ticket.reminder_sent_at = timezone.now()
        ticket.save(update_fields=["reminder_sent_at", "updated_at"])
        sent += 1
    return sent


def send_due_post_event(now=None) -> int:
    """Post-event письмо (благодарность + отзыв) после окончания — одно на билет.
    Окно [конец ≥ N+7 дней назад … конец ≤ N дней назад], только состоявшиеся."""
    now = now or timezone.now()
    days = getattr(settings, "EVENT_POSTEVENT_DAYS", 1)
    upper = now - timezone.timedelta(days=days)  # закончилось хотя бы N дней назад
    lower = upper - timezone.timedelta(days=7)  # окно подхвата пропусков
    due = (
        Ticket.objects.filter(
            status__in=(Ticket.STATUS_CONFIRMED, Ticket.STATUS_ATTENDED),
            post_event_sent_at__isnull=True,
        )
        .annotate(end_ref=Coalesce("event__ends_at", "event__starts_at"))
        .filter(end_ref__gte=lower, end_ref__lte=upper)
        .select_related("event", "customer")
    )
    sent = 0
    for ticket in due:
        enqueue_ticket_email(ticket, "post_event")
        ticket.post_event_sent_at = timezone.now()
        ticket.save(update_fields=["post_event_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_event_reminders():
    """Beat (раз в сутки): pre-event напоминания по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_event_reminders()
    return total


@shared_task
def send_event_post_event():
    """Beat (раз в сутки): post-event письма по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_post_event()
    return total


@shared_task
def charge_installments():
    """Beat (раз в сутки, R10c): off-session списания наступивших долей рассрочки.

    Только по арендаторам с подключённой оплатой (Stripe Connect). Безопасно при
    отсутствии Stripe: список пуст → ничего не делает."""
    from . import payments

    totals = {"charged": 0, "failed": 0}
    for schema, connect_id in _iter_tenant_billing():
        with schema_context(schema):
            r = payments.charge_due_installments(connect_id)
        totals["charged"] += r["charged"]
        totals["failed"] += r["failed"]
    return totals
