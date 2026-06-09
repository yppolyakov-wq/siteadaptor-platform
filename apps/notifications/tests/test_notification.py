import pytest
from django.db import IntegrityError, transaction

from apps.core.fsm import IllegalTransition
from apps.notifications.models import Notification
from apps.notifications.state_machine import FAILED, PENDING, SENT, NotificationSM

pytestmark = pytest.mark.django_db


def _notif(**kw):
    defaults = {"dedupe_key": "k1", "type": "reservation_confirmed", "recipient": "a@b.de"}
    defaults.update(kw)
    return Notification.objects.create(**defaults)


def test_dedupe_key_is_unique():
    _notif(dedupe_key="dup")
    with pytest.raises(IntegrityError), transaction.atomic():
        _notif(dedupe_key="dup")


def test_pending_to_sent():
    n = _notif(dedupe_key="s1")
    NotificationSM().apply(n, SENT)
    n.refresh_from_db()
    assert n.status == SENT


def test_pending_to_failed_then_requeue():
    n = _notif(dedupe_key="f1")
    sm = NotificationSM()
    sm.apply(n, FAILED)
    assert n.status == FAILED
    sm.apply(n, PENDING)
    n.refresh_from_db()
    assert n.status == PENDING


def test_illegal_sent_to_failed_raises():
    n = _notif(dedupe_key="i1", status="sent")
    with pytest.raises(IllegalTransition):
        NotificationSM().apply(n, FAILED)
