import uuid

import pytest

from apps.notifications import adapters
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.notifications.tasks import deliver

pytestmark = pytest.mark.django_db


def _notif(**kw):
    defaults = {
        "dedupe_key": f"k-{uuid.uuid4()}",
        "type": "reservation_confirmed",
        "recipient": "a@b.de",
        "subject": "Hallo",
        "payload": {"body": "Text"},
    }
    defaults.update(kw)
    return Notification.objects.create(**defaults)


def test_notify_creates_then_dedupes():
    first = notify(dedupe_key="dup", type="t", recipient="a@b.de", subject="S", body="B")
    assert first is not None
    assert notify(dedupe_key="dup", type="t", recipient="a@b.de") is None
    assert Notification.objects.filter(dedupe_key="dup").count() == 1


def test_deliver_sends_email_and_marks_sent(mailoutbox):
    n = _notif()
    assert deliver(str(n.id)) == "sent"
    n.refresh_from_db()
    assert n.status == "sent"
    assert n.sent_at is not None
    assert n.attempts == 1
    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "Hallo"


def test_deliver_twice_skips_second(mailoutbox):
    n = _notif()
    deliver(str(n.id))
    assert deliver(str(n.id)) == "skip"
    assert len(mailoutbox) == 1


def test_deliver_missing_is_safe():
    assert deliver(str(uuid.uuid4())) == "missing"


def test_deliver_sends_html_alternative(mailoutbox):
    n = _notif(payload={"body": "Text", "html": "<p>HTML</p>"})
    deliver(str(n.id))
    assert mailoutbox[0].alternatives == [("<p>HTML</p>", "text/html")]


def test_adapter_error_marks_failed(monkeypatch):
    def _boom(notification):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(adapters, "send", _boom)
    n = _notif()
    assert deliver(str(n.id)) == "failed"
    n.refresh_from_db()
    assert n.status == "failed"
    assert "smtp down" in n.last_error


# --- SEC (ревью аудита, SM8): упавшее уведомление повторяется -----------------------


def test_failed_notification_is_retried_with_backoff(
    monkeypatch, django_capture_on_commit_callbacks
):
    from datetime import timedelta

    from django.utils import timezone

    from apps.notifications import tasks as ntasks

    sent = []
    monkeypatch.setattr(ntasks.send_notification, "delay", lambda **kw: sent.append(kw))
    n = _notif()
    Notification.objects.filter(pk=n.pk).update(status="failed", attempts=1, last_error="timeout")
    assert ntasks.retry_failed() == 0  # пауза ещё не прошла
    later = timezone.now() + timedelta(minutes=11)
    with django_capture_on_commit_callbacks(execute=True):
        assert ntasks.retry_failed(now=later) == 1
    n.refresh_from_db()
    assert n.status == "pending" and len(sent) == 1


def test_permanent_failure_is_not_retried():
    from datetime import timedelta

    from django.utils import timezone

    from apps.notifications import tasks as ntasks

    n = _notif()
    Notification.objects.filter(pk=n.pk).update(
        status="failed", attempts=1, last_error="telegram sendMessage failed (403)"
    )
    assert ntasks.retry_failed(now=timezone.now() + timedelta(hours=2)) == 0


def test_old_failures_are_not_resent_after_deploy():
    """Ревью волны 2: давно упавшие письма не рассылаются заново первым же проходом."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.notifications import tasks as ntasks

    n = _notif()
    Notification.objects.filter(pk=n.pk).update(
        status="failed",
        attempts=1,
        last_error="timeout",
        updated_at=timezone.now() - timedelta(days=30),
    )
    assert ntasks.retry_failed() == 0


def test_payload_of_old_sent_notifications_is_purged():
    """SEC-G7: тело письма и вложения не хранятся вечно."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.notifications import tasks as ntasks

    old, fresh = _notif(), _notif()
    Notification.objects.filter(pk=old.pk).update(
        status="sent", updated_at=timezone.now() - timedelta(days=40)
    )
    Notification.objects.filter(pk=fresh.pk).update(status="sent")
    assert ntasks.purge_payloads() == 1
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.payload == {} and fresh.payload == {"body": "Text"}
