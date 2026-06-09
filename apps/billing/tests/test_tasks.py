from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing import tasks
from apps.billing.state_machine import ACTIVE, PAST_DUE, SUSPENDED, TRIAL, TRIAL_EXPIRED
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_trial_expires_after_deadline():
    now = timezone.now()
    tenant = TenantFactory(subscription_status=TRIAL, trial_ends_at=now - timedelta(hours=1))
    res = tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == TRIAL_EXPIRED
    assert res["trial_expired"] == 1


def test_trial_in_future_untouched():
    now = timezone.now()
    tenant = TenantFactory(subscription_status=TRIAL, trial_ends_at=now + timedelta(days=5))
    tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == TRIAL


def test_trial_expired_suspends_after_grace(settings):
    settings.BILLING_GRACE_DAYS = 7
    now = timezone.now()
    tenant = TenantFactory(subscription_status=TRIAL_EXPIRED, trial_ends_at=now - timedelta(days=8))
    tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == SUSPENDED
    assert tenant.is_active is False


def test_trial_expired_within_grace_untouched(settings):
    settings.BILLING_GRACE_DAYS = 7
    now = timezone.now()
    tenant = TenantFactory(subscription_status=TRIAL_EXPIRED, trial_ends_at=now - timedelta(days=2))
    tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == TRIAL_EXPIRED


def test_past_due_suspends_after_grace(settings):
    settings.BILLING_GRACE_DAYS = 7
    now = timezone.now()
    tenant = TenantFactory(
        subscription_status=PAST_DUE, subscription_ends_at=now - timedelta(days=8)
    )
    tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == SUSPENDED


def test_active_untouched():
    now = timezone.now()
    tenant = TenantFactory(subscription_status=ACTIVE, trial_ends_at=now - timedelta(days=30))
    tasks.roll_subscription_lifecycle(now)
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE


def test_enqueue_trial_reminders_for_due_days(monkeypatch):
    now = timezone.now()
    calls = []
    monkeypatch.setattr(tasks.send_trial_reminder, "delay", lambda **kw: calls.append(kw))
    TenantFactory(subscription_status=TRIAL, trial_ends_at=now + timedelta(days=1, hours=1))
    TenantFactory(
        subscription_status=TRIAL, trial_ends_at=now + timedelta(days=7)
    )  # не день-напоминание
    count = tasks.enqueue_trial_reminders(now)
    assert count == 1
    assert calls[0]["days_left"] == 1
    assert calls[0]["dedupe_key"].endswith(":1")
