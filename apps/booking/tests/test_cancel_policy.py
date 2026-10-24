"""KA-12 E4.4b (B6): правила отмены записи — снимок и отмена гостем.

Политика на услуге, СНИМКОМ в записи; бесплатное окно → возврат; поздняя отмена с
«Anzahlung einbehalten» → депозит остаётся бизнесу (выручка); ЛК больше не обходит
правила; повтор по отменённой записи доводит недошедший возврат."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking import cancel_policy, services
from apps.booking.models import Booking, Service
from apps.booking.tests.test_services import _resource, _service
from apps.core import money_contract, refunds

pytestmark = pytest.mark.django_db


def _book(service, hours_ahead=48, **kw):
    start = timezone.now() + timedelta(hours=hours_ahead)
    return services.book(
        _resource(),
        start=start,
        end=start + timedelta(hours=1),
        name="Gast",
        email="g@t.de",
        service=service,
        auto_confirm=True,
        **kw,
    )


@pytest.fixture
def money(monkeypatch):
    calls = {"refund": [], "retain": []}

    def fake_refund(kind, obj, tenant=None):
        calls["refund"].append(obj.pk)
        return refunds.RefundResult.REFUNDED

    monkeypatch.setattr(refunds, "refund_payment", fake_refund)

    def fake_retain(kind, obj, tenant=None):
        calls["retain"].append(obj.pk)
        return Decimal(obj.deposit_cents or 0) / 100

    monkeypatch.setattr(money_contract, "retain_on_cancel", fake_retain)
    return calls


def _paid_deposit(b, cents=1000):
    Booking.objects.filter(pk=b.pk).update(
        payment_state=Booking.PAYMENT_DEPOSIT, deposit_cents=cents, stripe_payment_intent="pi_x"
    )
    b.refresh_from_db()


def test_snapshot_written_from_fresh_service_row():
    svc = _service(cancel_window_hours=12, late_cancel="refund")
    Service.objects.filter(pk=svc.pk).update(cancel_window_hours=6)  # объект в памяти — 12
    b = _book(svc)
    assert b.cancel_policy == {"v": 1, "window_h": 6, "late": "refund", "resched_max": 2}


def test_booking_without_service_has_empty_policy():
    start = timezone.now() + timedelta(days=2)
    b = services.book(_resource(), start=start, end=start + timedelta(hours=1), name="G")
    assert b.cancel_policy == {}


def test_policy_change_does_not_touch_existing_booking():
    svc = _service(cancel_window_hours=24)
    b = _book(svc, hours_ahead=30)
    Service.objects.filter(pk=svc.pk).update(cancel_window_hours=48)
    b.refresh_from_db()
    assert cancel_policy.state(b).free is True


def test_database_caps():
    svc = _service()
    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.filter(pk=svc.pk).update(cancel_window_hours=721)
    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.filter(pk=svc.pk).update(late_cancel="x")
    b = _book(svc)
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.filter(pk=b.pk).update(reschedule_count=11)


def test_state_window_boundary_and_closed():
    svc = _service(cancel_window_hours=24)
    b = _book(svc, hours_ahead=48)
    deadline = b.start - timedelta(hours=24)
    assert cancel_policy.state(b, now=deadline).free is True
    assert cancel_policy.state(b, now=deadline + timedelta(seconds=1)).free is False
    assert cancel_policy.state(b, now=b.start).can_cancel is False
    Booking.objects.filter(pk=b.pk).update(status="fulfilled")
    b.refresh_from_db()
    assert cancel_policy.state(b).can_cancel is False


def test_legacy_booking_is_free_until_start_without_reschedule():
    svc = _service()
    b = _book(svc, hours_ahead=2)
    Booking.objects.filter(pk=b.pk).update(cancel_policy={})
    b.refresh_from_db()
    st = cancel_policy.state(b)
    assert st.free and st.can_cancel and not st.can_reschedule


def test_cancel_in_window_refunds(money):
    b = _book(_service(cancel_window_hours=24), hours_ahead=48)
    _paid_deposit(b)
    result, kept = cancel_policy.guest_cancel(b)
    b.refresh_from_db()
    assert b.status == "cancelled" and money["refund"] == [b.pk] and kept == 0


def test_late_cancel_keeps_deposit(money):
    b = _book(_service(cancel_window_hours=24, late_cancel="keep_deposit"), hours_ahead=5)
    _paid_deposit(b, 1500)
    result, kept = cancel_policy.guest_cancel(b)
    assert money["refund"] == [] and money["retain"] == [b.pk] and kept == 1500


def test_late_cancel_refund_mode_refunds(money):
    b = _book(_service(cancel_window_hours=24, late_cancel="refund"), hours_ahead=5)
    _paid_deposit(b)
    cancel_policy.guest_cancel(b)
    assert money["refund"] == [b.pk]


def test_repeat_on_cancelled_finishes_refund_without_error(money):
    b = _book(_service(cancel_window_hours=24), hours_ahead=48)
    _paid_deposit(b)
    cancel_policy.guest_cancel(b)
    cancel_policy.guest_cancel(b)  # повтор: не ошибка, возврат доводится (идемпотентен)
    assert money["refund"] == [b.pk, b.pk]


def test_late_cancel_with_full_payment_needs_contact(money):
    b = _book(
        _service(cancel_window_hours=24, late_cancel="keep_deposit"),
        hours_ahead=5,
        price_cents=5000,
    )
    Booking.objects.filter(pk=b.pk).update(
        payment_state=Booking.PAYMENT_PAID, deposit_cents=1000, stripe_payment_intent="pi_x"
    )
    b.refresh_from_db()
    with pytest.raises(cancel_policy.NotCancellable) as exc:
        cancel_policy.guest_cancel(b)
    assert exc.value.reason == "contact"
    b.refresh_from_db()
    assert b.status == "confirmed"


def test_group_cancel_cancels_all_members_once(money):
    svc = _service(cancel_window_hours=24)
    start = timezone.now() + timedelta(days=3)
    r = _resource()
    created = services.book_many(
        [
            (r, start, start + timedelta(hours=1), 1000),
            (r, start + timedelta(hours=2), start + timedelta(hours=3), 1000),
        ],
        name="G",
        email="g@t.de",
        service=svc,
    )
    _paid_deposit(created[0])
    cancel_policy.guest_cancel(created[1])
    assert set(
        Booking.objects.filter(group_code=created[0].group_code).values_list("status", flat=True)
    ) == {"cancelled"}
    assert money["refund"] == [created[0].pk]


def test_account_cancel_respects_late_policy(settings, money, monkeypatch):
    """Обход через ЛК закрыт: после дедлайна при «Anzahlung einbehalten» — без возврата."""
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.account import auth
    from apps.account import views as account_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    b = _book(_service(cancel_window_hours=24, late_cancel="keep_deposit"), hours_ahead=5)
    _paid_deposit(b)
    req = RequestFactory().post("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req._messages = FallbackStorage(req)
    req.tenant = TenantFactory.build(schema_name="public")
    monkeypatch.setattr(auth, "current_customer", lambda request: b.customer)
    monkeypatch.setattr(account_views, "_require_account_active", lambda request: None)
    account_views.cancel_booking(req, b.reference_code)
    b.refresh_from_db()
    assert b.status == "cancelled" and money["refund"] == [] and money["retain"] == [b.pk]


def test_free_cancel_returns_pass_credit_once_late_burns(money):
    """В-1: в окне визит Mehrfachkarte возвращается (и только раз), поздно — сгорает."""
    svc = _service(cancel_window_hours=24)
    card = services.issue_pass(name="G", email="g@t.de", credits=5)
    b = _book(svc, hours_ahead=48)
    services.redeem_pass(card, booking=b)
    cancel_policy.guest_cancel(b)
    cancel_policy.guest_cancel(b)
    card.refresh_from_db()
    b.refresh_from_db()
    assert card.credits_used == 0 and b.card_id is None

    late = _book(svc, hours_ahead=5)
    services.redeem_pass(card, booking=late)
    cancel_policy.guest_cancel(late)
    card.refresh_from_db()
    assert card.credits_used == 1


# --- ревью B6: повтор отмены не переигрывает решение владельца и само решение -----


def test_owner_cancelled_booking_cannot_be_refunded_by_guest(money):
    b = _book(_service(cancel_window_hours=24), hours_ahead=48)
    _paid_deposit(b)
    Booking.objects.filter(pk=b.pk).update(status="cancelled")  # отменил владелец
    b.refresh_from_db()
    with pytest.raises(cancel_policy.NotCancellable):
        cancel_policy.guest_cancel(b)
    assert money["refund"] == [] and money["retain"] == []


def test_no_show_keeps_deposit_against_guest_retry(money):
    b = _book(_service(cancel_window_hours=24, late_cancel="refund"), hours_ahead=48)
    _paid_deposit(b)
    Booking.objects.filter(pk=b.pk).update(status="no_show")
    b.refresh_from_db()
    with pytest.raises(cancel_policy.NotCancellable):
        cancel_policy.guest_cancel(b)
    assert money["refund"] == []


def test_retry_uses_decision_from_cancel_time(money, monkeypatch):
    """Бесплатная отмена, возврат сорвался; повтор ПОСЛЕ дедлайна всё равно возвращает."""
    b = _book(_service(cancel_window_hours=24, late_cancel="keep_deposit"), hours_ahead=48)
    _paid_deposit(b)
    monkeypatch.setattr(refunds, "refund_payment", lambda *a, **k: refunds.RefundResult.FAILED)
    result, _kept = cancel_policy.guest_cancel(b)
    assert result == refunds.RefundResult.FAILED
    b.refresh_from_db()
    assert b.cancel_policy["guest_cancel"]["free"] is True
    calls = []
    monkeypatch.setattr(
        refunds,
        "refund_payment",
        lambda kind, obj, tenant=None: calls.append(obj.pk) or refunds.RefundResult.REFUNDED,
    )
    later = b.start - timedelta(hours=1)
    cancel_policy.guest_cancel(b, now=later)
    assert calls == [b.pk] and money["retain"] == []


def test_refund_due_but_not_made_is_flagged_not_booked_as_revenue(money, monkeypatch):
    b = _book(_service(cancel_window_hours=24), hours_ahead=48)
    _paid_deposit(b)
    monkeypatch.setattr(refunds, "refund_payment", lambda *a, **k: refunds.RefundResult.NONE)
    told = []
    monkeypatch.setattr(refunds, "_notify_owner_failed", lambda *a, **k: told.append(1))
    result, kept = cancel_policy.guest_cancel(b)
    assert result == refunds.RefundResult.FAILED and told and money["retain"] == []


def test_money_step_exception_does_not_propagate(money, monkeypatch):
    b = _book(_service(cancel_window_hours=24), hours_ahead=48)
    _paid_deposit(b)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(refunds, "refund_payment", boom)
    monkeypatch.setattr(refunds, "_notify_owner_failed", lambda *a, **k: None)
    result, _ = cancel_policy.guest_cancel(b)
    b.refresh_from_db()
    assert result == refunds.RefundResult.FAILED and b.status == "cancelled"


def test_full_prepaid_deposit_equals_price_is_honestly_kept(money):
    svc = _service(cancel_window_hours=24, late_cancel="keep_deposit")
    b = _book(svc, hours_ahead=5, price_cents=2000)
    Booking.objects.filter(pk=b.pk).update(
        payment_state=Booking.PAYMENT_PAID, deposit_cents=2000, stripe_payment_intent="pi_x"
    )
    b.refresh_from_db()
    st = cancel_policy.state(b)
    assert st.can_cancel and st.kept_cents == 2000 and st.keep_after_cents == 2000
