"""Решение владельца 2026-10-24: отмена, которая возвращает клиенту деньги, —
только владелец или бухгалтер (admin). Сотрудник получает отказ, статус и
деньги не трогаются. Одна проверка в `transactions.apply_action` закрывает все
поверхности: доску, карточки, списки, массовые действия."""

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.core import bulk_actions, refunds, transactions
from apps.core.models import Membership
from apps.core.tests.test_kanban import _make_order

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    from apps.tenants.tests.factories import TenantFactory

    return TenantFactory.build(schema_name="public", stripe_connect_id="acct_stand")


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []

    def fake(kind, obj, tenant=None):
        if getattr(obj, "payment_state", "") != "paid":
            return refunds.RefundResult.NONE
        calls.append(obj.pk)
        return refunds.RefundResult.REFUNDED

    monkeypatch.setattr(refunds, "refund_payment", fake)
    return calls


def _user(role):
    user = get_user_model().objects.create_user(username=f"u-{uuid.uuid4().hex[:8]}")
    Membership.objects.create(user=user, role=role)
    return user


def _paid_order():
    order = _make_order()
    type(order).objects.filter(pk=order.pk).update(
        payment_state="paid", stripe_payment_intent="pi_stand"
    )
    order.refresh_from_db()
    return order


def test_staff_cannot_cancel_paid_order(tenant, stripe_calls):
    order = _paid_order()
    with pytest.raises(refunds.RefundNotAllowed):
        transactions.apply_action(
            "order", order, "cancelled", actor=_user(Membership.ROLE_STAFF), tenant=tenant
        )
    order.refresh_from_db()
    assert order.status == "new" and stripe_calls == []


@pytest.mark.parametrize("role", [Membership.ROLE_OWNER, Membership.ROLE_ADMIN])
def test_owner_and_accountant_may_cancel_with_refund(tenant, stripe_calls, role):
    order = _paid_order()
    result = transactions.apply_action(
        "order", order, "cancelled", actor=_user(role), tenant=tenant
    )
    assert result == refunds.RefundResult.REFUNDED and stripe_calls == [order.pk]


def test_staff_may_cancel_unpaid_order(tenant, stripe_calls):
    order = _make_order()
    transactions.apply_action(
        "order", order, "cancelled", actor=_user(Membership.ROLE_STAFF), tenant=tenant
    )
    order.refresh_from_db()
    assert order.status == "cancelled"


def test_staff_may_change_paid_order_without_refund(tenant, stripe_calls):
    order = _paid_order()
    transactions.apply_action(
        "order", order, "confirmed", actor=_user(Membership.ROLE_STAFF), tenant=tenant
    )
    order.refresh_from_db()
    assert order.status == "confirmed"


def test_system_paths_without_actor_still_refund(tenant, stripe_calls):
    order = _paid_order()
    transactions.apply_action("order", order, "cancelled", actor=None, tenant=tenant)
    assert stripe_calls == [order.pk]


def test_bulk_skips_paid_for_staff_with_reason(tenant, stripe_calls):
    paid, unpaid = _paid_order(), _make_order()
    res = bulk_actions.apply_bulk(
        tenant,
        "order",
        [paid.pk, unpaid.pk],
        "cancelled",
        confirm=True,
        actor=_user(Membership.ROLE_STAFF),
    )
    assert res.changed == 1 and sum(res.skipped.values()) == 1
    assert stripe_calls == []


def test_board_action_refuses_staff_with_403_on_fetch(tenant, stripe_calls):
    from django.test import RequestFactory

    from apps.core import views

    order = _paid_order()
    req = RequestFactory().post(
        f"/dashboard/board/order/{order.pk}/action/",
        {"action": "cancelled"},
        HTTP_X_REQUESTED_WITH="fetch",
    )
    req.user = _user(Membership.ROLE_STAFF)
    req.tenant = tenant
    resp = views.kanban_action(req, "order", order.pk)
    assert resp.status_code == 403
    order.refresh_from_db()
    assert order.status == "new"
