"""KA-D3 (решение владельца 2026-10-23): отмена ОПЛАЧЕННОЙ картой брони номера из
кабинета требует явного выбора «erstatten / nicht erstatten» — раньше возврат был
всегда 100 %, даже по невозвратному тарифу. Без выбора отмена не происходит."""

import pytest

from apps.core import refunds, transactions
from apps.core.tests.test_ka_h4_refunds import (  # noqa: F401 — фикстуры/хелперы
    _board_post,
    _paid,
    _stay,
    _tenant,
    _urlconf,
    stripe_calls,
)
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db


def _paid_stay(intent="pi_s"):
    stay = _stay()
    StayBookingSM().apply(stay, "confirmed")
    return _paid(stay, intent=intent)


def test_cancel_without_choice_is_refused(stripe_calls):  # noqa: F811
    stay = _paid_stay()
    with pytest.raises(refunds.RefundChoiceRequired):
        transactions.apply_action("stay", stay, "cancelled", tenant=_tenant())
    stay.refresh_from_db()
    assert stay.status == "confirmed" and stripe_calls == []


def test_cancel_with_refund_returns_money(stripe_calls):  # noqa: F811
    stay = _paid_stay()
    result = transactions.apply_action(
        "stay", stay, "cancelled", extra={"refund": "1"}, tenant=_tenant()
    )
    stay.refresh_from_db()
    assert result == refunds.RefundResult.REFUNDED and stay.payment_state == "refunded"


def test_cancel_without_refund_keeps_money(stripe_calls):  # noqa: F811
    stay = _paid_stay()
    result = transactions.apply_action(
        "stay", stay, "cancelled", extra={"refund": "0"}, tenant=_tenant()
    )
    stay.refresh_from_db()
    assert stay.status == "cancelled" and stay.payment_state == "paid"
    assert result == refunds.RefundResult.NONE and stripe_calls == []


def test_unpaid_stay_needs_no_choice(stripe_calls):  # noqa: F811
    stay = _stay()
    transactions.apply_action("stay", stay, "cancelled", tenant=_tenant())
    stay.refresh_from_db()
    assert stay.status == "cancelled"


def test_board_without_choice_shows_message_and_keeps_status(stripe_calls):  # noqa: F811
    stay = _paid_stay()
    resp, req = _board_post("stay", stay.pk, "cancelled", _tenant())
    stay.refresh_from_db()
    assert stay.status == "confirmed"
    assert any("erstatten" in str(m) for m in req._messages)


def test_board_fetch_without_choice_is_409(stripe_calls):  # noqa: F811
    stay = _paid_stay()
    resp, _req = _board_post("stay", stay.pk, "cancelled", _tenant(), fetch=True)
    assert resp.status_code == 409


def test_deal_status_dialog_offers_choice_for_paid_stay():
    from django.template.loader import render_to_string

    stay = _paid_stay()
    deal = transactions.transaction_for("stay", stay)
    html = render_to_string(
        "core/_deal_status_form.html", {"deal": deal, "deal_kind": "stay", "refund_choice": True}
    )
    assert 'name="refund" value="1"' in html and 'name="refund" value="0"' in html
