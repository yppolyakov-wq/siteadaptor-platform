"""FB-33 D3, ревью диффа (план §10.7): письмо «Zahlung nicht verbucht» уходит в схеме бизнеса,
id из metadata в логе — без управляющих знаков.

`Notification` — TENANT-таблица: в проде её нет в public, а вебхук работает в public.
Тесты держат TENANT-приложения в public и такого не видят — поэтому замок смотрит, в какой
схеме зовётся `notify`.
"""

import logging
import uuid

import pytest

from apps.billing import webhooks
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_d3r"
SCHEMA = "biz_d3r"
_RED = pytest.mark.xfail(strict=True, reason="FB-33 D3 ревью: до правки")


@pytest.fixture
def spy(monkeypatch):
    from django.db import connection

    seen = []

    def notify(**kw):
        seen.append(connection.schema_name)

    monkeypatch.setattr("apps.notifications.services.notify", notify)
    return seen


@pytest.fixture
def biz():
    return TenantFactory(schema_name=SCHEMA, stripe_connect_id=ACCOUNT, owner_email="o@t.de")


def _obj(kind, id_key, deal_id=None, **meta):
    return {
        "id": "cs_d3r",
        "payment_intent": "pi_d3r",
        "payment_status": "paid",
        "amount_total": 1000,
        "metadata": {
            "kind": kind,
            "tenant_schema": SCHEMA,
            id_key: deal_id or str(uuid.uuid4()),
            **meta,
        },
    }


@_RED
def test_unbooked_mail_goes_to_tenant_schema_from_webhook(biz, spy):
    webhooks.handle_event(
        "checkout.session.completed", _obj("order_payment", "order_id"), account=ACCOUNT
    )
    assert spy == [SCHEMA]


@_RED
def test_unbooked_mail_goes_to_tenant_schema_from_deal_balance(biz, spy, monkeypatch):
    from types import SimpleNamespace

    from apps.core import balance_pay
    from apps.promotions import notifications

    monkeypatch.setattr(
        notifications,
        "_tenant",
        lambda s: SimpleNamespace(stripe_connect_id=ACCOUNT, owner_email="o@t.de"),
    )
    balance_pay.mark_balance_paid(
        tenant_schema=SCHEMA,
        deal_kind="stay",
        deal_id=str(uuid.uuid4()),
        payment_intent="pi_bal",
        amount_cents=1000,
        account=ACCOUNT,
    )
    assert spy and set(spy) == {SCHEMA}


@_RED
def test_metadata_id_in_log_has_no_control_chars(biz, spy, caplog):
    caplog.set_level(logging.INFO)
    obj = _obj("event_ticket", "ticket_id", deal_id="q5\nFAKE LINE")
    webhooks._money_not_booked("event_ticket", obj["metadata"], obj, id_key="ticket_id")
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and all("\n" not in m and "FAKE LINE" not in m for m in errors)
