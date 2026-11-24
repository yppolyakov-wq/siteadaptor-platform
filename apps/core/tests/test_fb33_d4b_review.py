"""FB-33 D4b, ревью диффа (план §10.7): у записи, номера, билета нет пометки
«Rückerstattung offen» — любой несостоявшийся возврат второго платежа (сбой кода, NONE,
UNCERTAIN) = письмо владельцу `duplicate` (одно на платёж); повтор возврата — общий с заказом
beat; сбой возврата поздней оплаты не роняет вебхук и даёт письмо.
"""

import logging

import pytest
import stripe
from django.db import connection
from django.utils import timezone

from apps.core import payment_holds, refunds
from apps.core.models import DealPayment
from apps.core.tests.test_fb33_d4b_second_intent import KINDS, _make, _pay, _rows
from apps.core.tests.test_ka_h4_refunds import _urlconf  # noqa: F401
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
_RED = pytest.mark.xfail(strict=True, reason="FB-33 D4b ревью: до правки")


@pytest.fixture(autouse=True)
def biz():
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id="acct_d4b",
        payments_enabled=True,
        owner_email="chef@example.com",
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def stripe_refunds(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _mails(kind, obj, reason="duplicate"):
    return Notification.objects.filter(
        dedupe_key__contains=f":{kind}:{obj.pk}:{reason}", type="refund_failed_owner"
    )


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_settle_crash_mails_owner(kind, monkeypatch):
    obj = _pay(kind, _make(kind), "pi_main")

    def boom(*a, **kw):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(payment_holds, "settle_extra_payment", boom)
    _pay(kind, obj, "pi_second")
    assert _mails(kind, obj).count() == 1


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_refund_none_mails_owner(kind, monkeypatch):
    obj = _pay(kind, _make(kind), "pi_main")
    monkeypatch.setattr(refunds, "refund_intent", lambda *a, **kw: refunds.RefundResult.NONE)
    _pay(kind, obj, "pi_second")
    assert _mails(kind, obj).count() == 1


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_row_is_marked_extra(kind, stripe_refunds):
    obj = _pay(kind, _make(kind), "pi_main")
    _pay(kind, obj, "pi_second")
    assert _rows(kind, obj)["pi_second"].source == payment_holds.EXTRA_SOURCE


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_refund_retried_by_the_beat(kind, monkeypatch):
    """Повтор возврата второго платежа — общий beat (`orders.tasks.retry_late_refunds`)."""
    from datetime import timedelta

    from apps.orders import tasks

    state = {"down": True}
    calls = []

    def refund(**kw):
        calls.append(kw["payment_intent"])
        if state["down"]:
            raise stripe.error.APIConnectionError("timeout")

    monkeypatch.setattr("apps.billing.connect.refund", refund)
    obj = _pay(kind, _make(kind), "pi_main")
    _pay(kind, obj, "pi_second")
    state["down"] = False
    tasks.retry_late_refunds(timezone.now() + timedelta(hours=1))
    row = DealPayment.objects.get(deal_kind=kind, stripe_payment_intent="pi_second")
    assert row.refunded_cents == row.amount_cents and calls == ["pi_second", "pi_second"]


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_late_payment_crash_does_not_fail_webhook_and_mails(kind, monkeypatch):
    obj = _make(kind)

    def boom(*a, **kw):
        raise RuntimeError("stripe kaputt")

    monkeypatch.setattr(payment_holds, "settle_late_payment", boom)
    _pay(kind, obj, "pi_main")  # не падает
    assert _mails(kind, obj, reason="cancel").count() == 1


@_RED
@pytest.mark.parametrize("kind", KINDS)
def test_extra_without_amount_warns(kind, stripe_refunds, caplog):
    obj = _pay(kind, _make(kind), "pi_main")
    with caplog.at_level(logging.WARNING):
        _pay(kind, obj, "pi_second")
    assert any("amount" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
