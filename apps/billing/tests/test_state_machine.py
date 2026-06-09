import pytest

from apps.billing.state_machine import (
    ACTIVE,
    GATED_STATUSES,
    PAST_DUE,
    SUSPENDED,
    TRIAL,
    TRIAL_EXPIRED,
    SubscriptionSM,
)
from apps.core.fsm import IllegalTransition
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_trial_to_active_keeps_tenant_enabled():
    tenant = TenantFactory(subscription_status=TRIAL)
    SubscriptionSM().apply(tenant, ACTIVE)
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE
    assert tenant.is_active is True


def test_trial_expired_then_suspended_disables_tenant():
    tenant = TenantFactory(subscription_status=TRIAL, is_active=True)
    sm = SubscriptionSM()
    sm.apply(tenant, TRIAL_EXPIRED)
    assert tenant.subscription_status == TRIAL_EXPIRED
    assert tenant.is_active is True  # grace: read-only, но ещё не выключен

    sm.apply(tenant, SUSPENDED)
    tenant.refresh_from_db()
    assert tenant.subscription_status == SUSPENDED
    assert tenant.is_active is False  # мягкое отключение, данные не трогаем


def test_reactivation_from_suspended_restores_access():
    tenant = TenantFactory(subscription_status=TRIAL)
    sm = SubscriptionSM()
    sm.apply(tenant, TRIAL_EXPIRED)
    sm.apply(tenant, SUSPENDED)
    assert tenant.is_active is False

    sm.apply(tenant, ACTIVE)
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE
    assert tenant.is_active is True


def test_active_past_due_recovery_cycle():
    tenant = TenantFactory(subscription_status=ACTIVE)
    sm = SubscriptionSM()
    sm.apply(tenant, PAST_DUE)
    assert tenant.subscription_status == PAST_DUE
    assert tenant.is_active is True  # past_due ещё не выключает доступ

    sm.apply(tenant, ACTIVE)
    tenant.refresh_from_db()
    assert tenant.subscription_status == ACTIVE


def test_past_due_to_suspended_disables_tenant():
    tenant = TenantFactory(subscription_status=ACTIVE)
    sm = SubscriptionSM()
    sm.apply(tenant, PAST_DUE)
    sm.apply(tenant, SUSPENDED)
    tenant.refresh_from_db()
    assert tenant.subscription_status == SUSPENDED
    assert tenant.is_active is False


def test_same_status_is_idempotent_noop():
    tenant = TenantFactory(subscription_status=ACTIVE)
    result = SubscriptionSM().apply(tenant, ACTIVE)
    assert result.subscription_status == ACTIVE


@pytest.mark.parametrize(
    "src,dst",
    [
        (TRIAL, SUSPENDED),  # нельзя минуя trial_expired
        (TRIAL, PAST_DUE),
        (ACTIVE, TRIAL_EXPIRED),
        (SUSPENDED, PAST_DUE),
        (ACTIVE, TRIAL),  # назад в триал запрещено
    ],
)
def test_illegal_transitions_raise(src, dst):
    tenant = TenantFactory(subscription_status=src)
    with pytest.raises(IllegalTransition):
        SubscriptionSM().apply(tenant, dst)


def test_gated_statuses_are_trial_expired_and_suspended():
    assert GATED_STATUSES == {TRIAL_EXPIRED, SUSPENDED}
