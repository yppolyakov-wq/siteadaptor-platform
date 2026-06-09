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
