"""A9: TÜV/Service-Reminder — beat-логика (apps.jobs.tasks.send_due_service_reminders)."""

import datetime

import pytest
from django.utils import timezone

from apps.jobs import services
from apps.jobs.tasks import send_due_service_reminders
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 6, 30)


def _job(due, *, email="kunde@test.de"):
    job = services.create_job(title="Inspektion", name="Kunde", email=email)
    job.service_due_date = due
    job.save(update_fields=["service_due_date"])
    return job


def test_sends_reminder_within_lead_window():
    job = _job(TODAY + datetime.timedelta(days=10))  # внутри 21-дневного окна
    assert send_due_service_reminders(today=TODAY) == 1
    job.refresh_from_db()
    assert job.service_reminder_sent_at is not None
    assert Notification.objects.filter(
        dedupe_key=f"job:{job.id}:service_reminder:{job.service_due_date.isoformat()}:customer"
    ).exists()


def test_idempotent_does_not_resend():
    job = _job(TODAY + datetime.timedelta(days=5))
    job.service_reminder_sent_at = timezone.now()
    job.save(update_fields=["service_reminder_sent_at"])
    assert send_due_service_reminders(today=TODAY) == 0


def test_skips_outside_lead_window():
    _job(TODAY + datetime.timedelta(days=40))  # дальше горизонта (21 дн.)
    assert send_due_service_reminders(today=TODAY) == 0


def test_skips_past_due_date():
    _job(TODAY - datetime.timedelta(days=1))  # уже прошло
    assert send_due_service_reminders(today=TODAY) == 0


def test_skips_without_email():
    _job(TODAY + datetime.timedelta(days=5), email="")
    assert send_due_service_reminders(today=TODAY) == 0


def test_rearm_after_new_date_resends():
    """Смена даты (sent_at сброшен в кабинете) → напоминание уходит снова, на новую дату."""
    job = _job(TODAY + datetime.timedelta(days=5))
    assert send_due_service_reminders(today=TODAY) == 1
    # Бизнес поставил новую дату (как _save_lines: сбрасывает sent_at).
    job.service_due_date = TODAY + datetime.timedelta(days=8)
    job.service_reminder_sent_at = None
    job.save(update_fields=["service_due_date", "service_reminder_sent_at"])
    assert send_due_service_reminders(today=TODAY) == 1  # вторая дата → второе письмо
