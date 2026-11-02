"""SEC волна 1 (аудит безопасности, решение владельца 2026-11-02): деньги.

План — `docs/sec-wave1-money-plan-2026-11-02.md`. Каждый замок был красным до фикса.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.booking.tests.test_deposit import _booking
from apps.finance import services
from apps.finance.models import Invoice
from apps.finance.services import issue_invoice
from apps.finance.state_machine import InvoiceSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LINES = [{"text": "Essen", "qty": 1, "unit_price": "100.00"}]


def _draft():
    net, vat, gross = services.compute_totals(LINES, Decimal("19.00"))
    return Invoice.objects.create(
        lines=LINES, vat_rate=Decimal("19.00"), net=net, vat_amount=vat, gross=gross
    )


# --- SEC-D4: переход считается от статуса в БД, а не от устаревшего объекта ----------------


def test_stale_double_cancel_runs_side_effects_once(monkeypatch):
    inv = _draft()
    issue_invoice(inv)
    first = Invoice.objects.get(pk=inv.pk)
    second = Invoice.objects.get(pk=inv.pk)  # вторая вкладка / двойной клик
    hooks = []
    real = InvoiceSM.on_transition
    monkeypatch.setattr(
        InvoiceSM,
        "on_transition",
        lambda self, i, t, **kw: hooks.append(t.dst) or real(self, i, t, **kw),
    )
    InvoiceSM().apply(first, "cancelled")
    InvoiceSM().apply(second, "cancelled")  # раньше: эффекты отмены второй раз
    assert hooks == ["cancelled"]
    assert second.status == "cancelled"


def test_stale_object_uses_actual_status_as_source():
    from apps.core.fsm import IllegalTransition

    inv = _draft()
    stale = Invoice.objects.get(pk=inv.pk)  # в памяти draft
    issue_invoice(inv)
    InvoiceSM().apply(Invoice.objects.get(pk=inv.pk), "cancelled")
    with pytest.raises(IllegalTransition):  # cancelled → issued запрещён — не draft → issued
        InvoiceSM().apply(stale, "issued")


# --- SEC-D5: повторный выпуск не тратит номер -----------------------------------------------


def test_double_issue_keeps_single_number():
    inv = _draft()
    stale = Invoice.objects.get(pk=inv.pk)
    issue_invoice(inv)
    number = Invoice.objects.get(pk=inv.pk).number
    issue_invoice(stale)  # второй клик «Rechnung stellen»
    from apps.finance.models import InvoiceCounter

    assert Invoice.objects.get(pk=inv.pk).number == number  # номер не переписан
    assert InvoiceCounter.objects.get(pk=1).last_number == number  # и не потрачен


# --- SEC-D6: удержание на время оплаты не продлевается бесконечно ---------------------------


def test_online_hold_is_capped_from_creation():
    from apps.core.payment_holds import ONLINE_HOLD, start_online_hold

    booking = _booking()
    created = booking.created_at
    start_online_hold(booking, now=created + timedelta(hours=1))
    start_online_hold(booking, now=created + timedelta(hours=20))  # открыл страницу снова
    booking.refresh_from_db()
    assert booking.payment_due_at <= created + ONLINE_HOLD


def test_online_hold_near_ceiling_gives_session_without_own_expiry():
    from apps.core.payment_holds import ONLINE_HOLD, start_online_hold

    booking = _booking()
    start_online_hold(booking, now=booking.created_at + timedelta(minutes=5))
    late = booking.created_at + ONLINE_HOLD - timedelta(minutes=20)
    # Stripe требует ≥ 30 мин до expires_at: сессия без своего срока, поздняя оплата
    # возвращается автоматически (settle_late_payment).
    assert start_online_hold(booking, now=late) is None


def test_old_deal_gets_fresh_hold_not_a_past_one():
    """Ревью волны 1 (H1): ссылка на оплату по брони трёхдневной давности — срок от
    сейчас, а не в прошлом (иначе beat снял бы бронь, пока клиент платит)."""
    from apps.core.payment_holds import start_online_hold

    booking = _booking()
    now = booking.created_at + timedelta(days=3)
    assert start_online_hold(booking, now=now) is not None
    booking.refresh_from_db()
    assert booking.payment_due_at > now + timedelta(hours=23)


def test_processing_payment_extends_hold(calls):
    """Ревью волны 1 (M3): SEPA в пути — бронь не снимается по суткам онлайн-оплаты."""
    from django.db import connection

    from apps.billing import webhooks
    from apps.core.payment_holds import PROCESSING_HOLD

    booking = _booking()
    event = _deposit_event(booking, "unpaid")
    event["metadata"]["tenant_schema"] = connection.schema_name
    TenantFactory(schema_name=connection.schema_name, stripe_connect_id="acct_cur")
    webhooks.handle_event("checkout.session.completed", event, account="acct_cur")
    booking.refresh_from_db()
    assert calls == []
    assert booking.payment_due_at > timezone.now() + PROCESSING_HOLD - timedelta(hours=1)


# --- SEC-D3: отложенные способы (SEPA) — оплата только после зачисления ---------------------


def _deposit_event(booking, status):
    return {
        "payment_intent": "pi_x",
        "payment_status": status,
        "metadata": {
            "kind": "booking_deposit",
            "tenant_schema": "biz_w1",
            "booking_id": str(booking.id),
        },
    }


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "apps.booking.payments.mark_deposit_paid", lambda **kw: seen.append(kw) or True
    )
    TenantFactory(schema_name="biz_w1", stripe_connect_id="acct_w1")
    return seen


def test_completed_with_unpaid_sepa_is_not_booked(calls):
    from apps.billing import webhooks

    webhooks.handle_event(
        "checkout.session.completed", _deposit_event(_booking(), "unpaid"), account="acct_w1"
    )
    assert calls == []


def test_async_payment_succeeded_books_payment(calls):
    from apps.billing import webhooks

    webhooks.handle_event(
        "checkout.session.async_payment_succeeded",
        _deposit_event(_booking(), "paid"),
        account="acct_w1",
    )
    assert len(calls) == 1


def test_async_payment_failed_is_not_booked(calls):
    from apps.billing import webhooks

    webhooks.handle_event(
        "checkout.session.async_payment_failed",
        _deposit_event(_booking(), "unpaid"),
        account="acct_w1",
    )
    assert calls == []


def test_paid_completed_still_books(calls):
    from apps.billing import webhooks

    webhooks.handle_event(
        "checkout.session.completed", _deposit_event(_booking(), "paid"), account="acct_w1"
    )
    assert len(calls) == 1


# --- SEC-D4b: публикация в каналы — после коммита ------------------------------------------


def test_promotion_publish_is_enqueued_after_commit(
    monkeypatch, django_capture_on_commit_callbacks
):
    from apps.promotions.models import Promotion
    from apps.promotions.state_machine import PromotionSM
    from apps.publishing import services as pub_services
    from apps.publishing.models import Channel

    Channel.objects.create(is_enabled=True)
    seen = []
    monkeypatch.setattr(pub_services.publish_to_channel, "delay", lambda **kw: seen.append(kw))
    promo = Promotion.objects.create(status="draft", title={"de": "A"})
    with django_capture_on_commit_callbacks(execute=True):
        PromotionSM().apply(promo, "active")
        assert seen == []  # воркер не должен брать задачу до коммита Publication
    assert len(seen) == 1
