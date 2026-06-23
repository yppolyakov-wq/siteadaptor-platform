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


def send_due_post_stay(today=None) -> int:
    """G2: post-stay письмо после выезда — ровно одно на бронь. Окно [departure не
    раньше N+7 дней назад … departure ≤ N дней назад], только состоявшиеся брони."""
    today = today or timezone.localdate()
    days = getattr(settings, "STAY_POSTSTAY_DAYS", 1)
    upper = today - timezone.timedelta(days=days)  # выехали хотя бы N дней назад
    lower = upper - timezone.timedelta(days=7)  # окно подхвата пропусков
    due = StayBooking.objects.filter(
        status__in=(StayBooking.STATUS_CONFIRMED, StayBooking.STATUS_FULFILLED),
        post_stay_sent_at__isnull=True,
        departure__gte=lower,
        departure__lte=upper,
    )
    sent = 0
    for booking in due:
        enqueue_stay_email(booking, "post_stay")
        booking.post_stay_sent_at = timezone.now()
        booking.save(update_fields=["post_stay_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_stay_post_stay():
    """Beat (раз в сутки): post-stay письма по всем схемам арендаторов (G2)."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_post_stay()
    return total


def purge_due_registrations(today=None) -> int:
    """G6: удалить Meldescheine старше года после выезда (DSGVO Löschpflicht /
    Aufbewahrung 1 Jahr). Чистая логика для текущей схемы — число удалённых."""
    from .models import GuestRegistration

    today = today or timezone.localdate()
    cutoff = today - timezone.timedelta(days=365)
    deleted, _ = GuestRegistration.objects.filter(booking__departure__lt=cutoff).delete()
    return deleted


@shared_task
def purge_old_registrations():
    """Beat (раз в сутки): удалять просроченные Meldescheine по всем схемам (G6)."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += purge_due_registrations()
    return total


@shared_task
def sync_ical_sources():
    """Beat (раз в час): тянуть внешние iCal-фиды и обновлять блоки (A5b)."""
    from .models import ICalSource
    from .services import sync_ical_source

    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            for source in ICalSource.objects.filter(is_active=True):
                total += sync_ical_source(source)
    return total
