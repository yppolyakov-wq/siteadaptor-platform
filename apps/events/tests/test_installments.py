"""R10a: рассрочка билета — модель + расчёт графика (без Stripe).

Чистая логика `installments.py` (eligibility, сплит сумм, даты) + свойства
`InstallmentPlan` (paid/remaining). Списания/Stripe — R10b+.
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.events import installments
from apps.events.models import Event, InstallmentCharge, InstallmentPlan
from apps.events.services import book_ticket

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Teures Retreat",
        "starts_at": timezone.now() + timedelta(days=90),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 150000,
        "allow_installments": True,
        "installment_count": 3,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- split_amounts ------------------------------------------------------------


def test_split_amounts_exact():
    assert installments.split_amounts(9000, 3) == [3000, 3000, 3000]


def test_split_amounts_remainder_frontloaded():
    out = installments.split_amounts(10000, 3)
    assert out == [3334, 3333, 3333]
    assert sum(out) == 10000  # без потери центов


def test_split_amounts_single():
    assert installments.split_amounts(5000, 1) == [5000]


# --- schedule_dates / build_schedule -----------------------------------------


def test_fixed_mode_monthly_dates():
    event = _event(installment_mode=Event.INSTALLMENT_FIXED, installment_count=3)
    today = date(2026, 1, 31)
    dates = installments.schedule_dates(event, today, None)
    # помесячно с клампом дня (фев → 28/29)
    assert dates[0] == date(2026, 1, 31)
    assert dates[1] == date(2026, 2, 28)
    assert dates[2] == date(2026, 3, 31)


def test_until_event_spreads_to_lead_deadline():
    event = _event(
        installment_mode=Event.INSTALLMENT_UNTIL_EVENT,
        installment_count=3,
        installment_lead_days=10,
    )
    today = date(2026, 1, 1)
    start = date(2026, 4, 1)  # last_due = 2026-03-22
    dates = installments.schedule_dates(event, today, start)
    assert dates[0] == today
    assert dates[-1] == date(2026, 3, 22)
    assert dates[0] < dates[1] < dates[2]  # монотонно


def test_build_schedule_sums_to_total():
    event = _event(installment_count=4)
    today = date(2026, 1, 1)
    start = date(2026, 6, 1)
    sched = installments.build_schedule(event, 100000, today, start)
    assert [c["sequence"] for c in sched] == [1, 2, 3, 4]
    assert sum(c["amount_cents"] for c in sched) == 100000


# --- eligibility --------------------------------------------------------------


def test_available_happy_path():
    event = _event()
    today = timezone.localdate()
    start = today + timedelta(days=90)
    assert installments.installments_available(event, 150000, today, start) is True


def test_not_available_when_disabled():
    event = _event(allow_installments=False)
    today = timezone.localdate()
    assert (
        installments.installments_available(event, 150000, today, today + timedelta(days=90))
        is False
    )


def test_not_available_below_min():
    event = _event(installment_min_cents=200000)
    today = timezone.localdate()
    assert (
        installments.installments_available(event, 150000, today, today + timedelta(days=90))
        is False
    )


def test_not_available_single_installment():
    event = _event(installment_count=1)
    today = timezone.localdate()
    assert (
        installments.installments_available(event, 150000, today, today + timedelta(days=90))
        is False
    )


def test_not_available_event_too_soon_until_mode():
    event = _event(installment_mode=Event.INSTALLMENT_UNTIL_EVENT, installment_lead_days=14)
    today = timezone.localdate()
    start = today + timedelta(days=10)  # last_due = start-14 < today
    assert installments.installments_available(event, 150000, today, start) is False


# --- модель -------------------------------------------------------------------


def test_plan_paid_and_remaining():
    event = _event()
    ticket = book_ticket(event, name="A", email="a@test.de")
    plan = InstallmentPlan.objects.create(ticket=ticket, total_cents=90000, count=3)
    InstallmentCharge.objects.create(
        plan=plan,
        sequence=1,
        due_date=date(2026, 1, 1),
        amount_cents=30000,
        status=InstallmentCharge.STATUS_PAID,
    )
    InstallmentCharge.objects.create(
        plan=plan,
        sequence=2,
        due_date=date(2026, 2, 1),
        amount_cents=30000,
        status=InstallmentCharge.STATUS_SCHEDULED,
    )
    InstallmentCharge.objects.create(
        plan=plan,
        sequence=3,
        due_date=date(2026, 3, 1),
        amount_cents=30000,
        status=InstallmentCharge.STATUS_SCHEDULED,
    )
    assert plan.paid_cents == 30000
    assert plan.remaining_cents == 60000
    assert plan.paid_count == 1
