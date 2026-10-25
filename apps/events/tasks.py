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
        .exclude(event__status=Event.STATUS_CANCELLED)  # KA-H8: отменённое не «оценивают»
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


def send_due_payment_reminders(now=None) -> int:
    """B2.3: платный билет создан, оплата не пришла N часов — одно напоминание."""
    now = now or timezone.now()
    hours = getattr(settings, "EVENTS_PAYREMIND_HOURS", 6)
    upper = now - timezone.timedelta(hours=hours)
    lower = upper - timezone.timedelta(days=7)
    due = Ticket.objects.filter(
        status=Ticket.STATUS_PENDING,
        payment_state=Ticket.PAYMENT_PENDING,
        payment_reminder_sent_at__isnull=True,
        event__starts_at__gt=now,
        created_at__gte=lower,
        created_at__lte=upper,
    )
    sent = 0
    for ticket in due:
        enqueue_ticket_email(ticket, "payment_reminder")
        ticket.payment_reminder_sent_at = timezone.now()
        ticket.save(update_fields=["payment_reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_ticket_payment_reminders():
    """Beat (раз в час): напоминания о неоплаченном билете по всем схемам."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_payment_reminders()
    return total


@shared_task(name="apps.events.tasks.cancel_event_tickets")
def cancel_event_tickets(*, tenant_schema, event_id, actor_id=None):
    """KA-H8: отмена события → отмена его активных билетов (возврат, письмо, стоп
    рассрочки) по одному через `apply_action`. Повтор безопасен: билет перечитывается
    под блокировкой, возврат захватывается условным UPDATE (refunds.py)."""
    from django.contrib.auth import get_user_model

    from .services import cancel_event_tickets_now

    with schema_context("public"):
        tenant = get_tenant_model().objects.filter(schema_name=tenant_schema).first()
    if tenant is None:
        return {"skipped": True}
    # Настоящий тенант (а не FakeTenant schema_context): без stripe_connect_id
    # возвраты молча не прошли бы.
    from django_tenants.utils import tenant_context

    with tenant_context(tenant):
        event = Event.objects.filter(pk=event_id).first()
        if event is None or event.status != Event.STATUS_CANCELLED:
            return {"skipped": True}
        actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
        return cancel_event_tickets_now(event, actor=actor, tenant=tenant)


def check_due_min_participants(now=None) -> int:
    """KA-12 T-3: за `min_deadline_days` до старта — письмо владельцу, если минимум
    участников не набран. Отмену владелец делает сам (О-1); повтор письма гасит дедуп."""
    from .notifications import enqueue_min_participants_owner

    now = now or timezone.now()
    candidates = Event.objects.filter(
        status=Event.STATUS_PUBLISHED,
        min_participants__gt=0,
        starts_at__gt=now,
        starts_at__lte=now + timezone.timedelta(days=366),
    )
    sent = 0
    for event in candidates:
        if event.starts_at - timezone.timedelta(days=event.min_deadline_days) > now:
            continue  # срок проверки ещё не наступил
        if event.min_missing and enqueue_min_participants_owner(event):
            sent += 1
    return sent


@shared_task
def check_min_participants():
    """Beat (раз в сутки): минимум участников по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += check_due_min_participants()
    return total
