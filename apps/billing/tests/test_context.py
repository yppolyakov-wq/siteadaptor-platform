from datetime import timedelta

from django.utils import timezone

from apps.billing.context import subscription
from apps.billing.state_machine import SUSPENDED, TRIAL


class _Tenant:
    def __init__(self, status, schema="acme", trial_ends_at=None):
        self.subscription_status = status
        self.schema_name = schema
        self.trial_ends_at = trial_ends_at


class _Request:
    pass


def test_trial_days_left_computed():
    req = _Request()
    req.tenant = _Tenant(TRIAL, trial_ends_at=timezone.now() + timedelta(days=5, hours=1))
    ctx = subscription(req)
    assert ctx["subscription_status"] == TRIAL
    assert ctx["subscription_gated"] is False
    assert ctx["trial_days_left"] == 5


def test_gated_status_flagged():
    req = _Request()
    req.tenant = _Tenant(SUSPENDED)
    ctx = subscription(req)
    assert ctx["subscription_gated"] is True
    assert ctx["trial_days_left"] is None
