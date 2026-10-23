"""Онлайн-оплата билета через Stripe Connect (A6c).

Checkout на connected account бизнеса (деньги ему; вариант B → application_fee=0).
Подтверждение ставит вебхук на public-схеме (billing.webhooks → mark_ticket_paid),
кросс-схемно. Зеркало apps.stays.payments / booking.payments.
"""

import stripe

from apps.billing import connect
from apps.core.payment_holds import settle_late_payment, start_online_hold


def ticket_checkout_url(ticket, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты билета (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=ticket.amount_due_now_cents,  # R4: депозит или вся payable
        product_name=f"{ticket.event.title} ×{ticket.quantity}",
        metadata={
            "kind": "event_ticket",
            "tenant_schema": tenant.schema_name,
            "ticket_id": str(ticket.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
        # KA-P6: брошенная оплата не держит ресурс бессрочно (expire_payment_holds).
        expires_at=start_online_hold(ticket),
    )


def installment_checkout_url(ticket, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты первой доли рассрочки (R10b; сохраняет мандат)."""
    from . import installments

    first_cents = installments.first_installment_cents(ticket.event, ticket.payable_cents)
    return connect.installment_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=first_cents,
        product_name=f"{ticket.event.title} ×{ticket.quantity} (Rate 1)",
        metadata={
            "kind": "event_installment",
            "tenant_schema": tenant.schema_name,
            "ticket_id": str(ticket.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        # E7-3: payment_method_types тут НЕ прокидываем — рассрочка требует карту
        # с мандатом (setup_future_usage=off_session), klarna/paypal неприменимы.
        business_type=getattr(tenant, "business_type", ""),
    )


def create_installment_plan(
    *, tenant_schema: str, ticket_id: str, payment_intent: str = ""
) -> bool:
    """Вебхук: первая доля рассрочки оплачена → создать план + график (R10b).

    Достаёт мандат (customer/payment_method) из PaymentIntent на connected account,
    создаёт план/доли (1-я = paid). Кросс-схемно, идемпотентно."""
    from django_tenants.utils import schema_context

    from apps.tenants.models import Tenant

    from . import installments
    from .models import Ticket

    if not tenant_schema or not ticket_id:
        return False
    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    connect_id = getattr(tenant, "stripe_connect_id", "") if tenant else ""
    customer_id = payment_method_id = ""
    if connect_id and payment_intent:
        try:
            customer_id, payment_method_id = connect.mandate_from_payment_intent(
                connect_id=connect_id, payment_intent=payment_intent
            )
        except Exception:  # noqa: BLE001 — мандат можно дозаполнить позже; план создаём
            pass
    with schema_context(tenant_schema):
        ticket = Ticket.objects.filter(id=ticket_id).select_related("event").first()
        if ticket is None:
            return False
        installments.create_plan(
            ticket,
            payment_intent=payment_intent,
            customer_id=customer_id,
            payment_method_id=payment_method_id,
        )
    return True


def charge_due_installments(connect_id: str, today=None) -> dict:
    """R10c: списать наступившие доли рассрочки off-session (в текущей схеме).

    По каждой scheduled-доле с due_date ≤ today (план active): off-session
    PaymentIntent на connected account. Успех → mark_charge_paid (план/билет
    завершаются при полной оплате). Отказ (SCA/карта) → attempts++ и письмо;
    после INSTALLMENT_MAX_ATTEMPTS попыток → доля/план failed + эскалация владельцу
    (без авто-отмены билета). Возвращает счётчики {charged, failed}."""
    from django.conf import settings
    from django.utils import timezone

    from .models import InstallmentCharge, InstallmentPlan

    today = today or timezone.localdate()
    max_attempts = getattr(settings, "INSTALLMENT_MAX_ATTEMPTS", 3)
    from apps.core import status_registry

    from .models import Event

    due = (
        InstallmentCharge.objects.filter(
            status=InstallmentCharge.STATUS_SCHEDULED,
            due_date__lte=today,
            plan__status=InstallmentPlan.STATUS_ACTIVE,
        )
        # KA-H8: вторая защита — отменённый билет/событие не списываются никогда.
        .exclude(plan__ticket__status__in=status_registry.cancelled_statuses_for("ticket"))
        .exclude(plan__ticket__event__status=Event.STATUS_CANCELLED)
        .select_related("plan", "plan__ticket", "plan__ticket__event", "plan__ticket__customer")
    )
    charged = failed = 0
    for pending in due:
        if not (connect_id and pending.plan.stripe_customer_id):
            continue  # нет мандата — пропускаем (дозаполнение/ручное списание в кабинете)
        result = _charge_one(pending.pk, connect_id, max_attempts)
        charged += result == "charged"
        failed += result == "failed"
    return {"charged": charged, "failed": failed}


def _charge_one(charge_pk, connect_id: str, max_attempts: int) -> str:
    """KA-H8: одна доля — под блокировкой плана и доли (ручное «bezahlt» владельца
    ждёт её, а не проскакивает между проверкой и списанием); ключ идемпотентности
    Stripe по (доля, попытка) — повтор после сбоя не списывает дважды."""
    from django.db import transaction

    from . import installments
    from .models import InstallmentCharge, InstallmentPlan

    with transaction.atomic():
        charge = (
            InstallmentCharge.objects.select_for_update()
            .select_related("plan__ticket__event")
            .filter(pk=charge_pk)
            .first()
        )
        if charge is None or charge.status != InstallmentCharge.STATUS_SCHEDULED:
            return "skipped"
        plan = InstallmentPlan.objects.select_for_update().get(pk=charge.plan_id)
        if plan.status != InstallmentPlan.STATUS_ACTIVE or not plan.stripe_payment_method_id:
            return "skipped"
        charge.plan = plan
        try:
            pi = connect.charge_off_session(
                connect_id=connect_id,
                customer_id=plan.stripe_customer_id,
                payment_method_id=plan.stripe_payment_method_id,
                amount_cents=charge.amount_cents,
                metadata={
                    "kind": "event_installment_charge",
                    "ticket_id": str(plan.ticket_id),
                    "charge": str(charge.id),
                },
                business_type=getattr(plan.ticket.event, "business_type", ""),
                idempotency_key=f"installment:{charge.id}:{charge.attempts}",
            )
            installments.mark_charge_paid(charge, payment_intent=pi)
            return "charged"
        except stripe.error.StripeError as exc:
            charge.attempts += 1
            charge.last_error = str(getattr(exc, "user_message", "") or exc)[:300]
            reached_max = charge.attempts >= max_attempts
            if reached_max:
                charge.status = InstallmentCharge.STATUS_FAILED
                plan.status = InstallmentPlan.STATUS_FAILED
                plan.save(update_fields=["status", "updated_at"])
            charge.save(update_fields=["attempts", "last_error", "status", "updated_at"])
            from .notifications import enqueue_installment_failed

            enqueue_installment_failed(charge, escalate=reached_max)
            return "failed"


def mark_ticket_paid(*, tenant_schema: str, ticket_id: str, payment_intent: str = "") -> bool:
    """Вебхук: билет оплачен → payment_state=paid + авто-confirm (если событие не
    требует ручного подтверждения). Кросс-схемно, идемпотентно."""
    from django_tenants.utils import schema_context

    from apps.core.fsm import IllegalTransition

    from .models import Ticket
    from .state_machine import TicketSM

    if not tenant_schema or not ticket_id:
        return False
    with schema_context(tenant_schema):
        ticket = Ticket.objects.filter(id=ticket_id).select_related("event").first()
        if ticket is None:
            return False
        # R4: при депозите помечаем deposit (остаток на месте), иначе paid.
        target_state = Ticket.PAYMENT_DEPOSIT if ticket.deposit_cents else Ticket.PAYMENT_PAID
        fields = []
        if ticket.payment_state != target_state:
            ticket.payment_state = target_state
            fields.append("payment_state")
        if payment_intent and ticket.stripe_payment_intent != payment_intent:
            ticket.stripe_payment_intent = payment_intent
            fields.append("stripe_payment_intent")
        if ticket.payment_due_at is not None:  # KA-P6: оплачено — удержание снято
            ticket.payment_due_at = None
            fields.append("payment_due_at")
        if fields:
            fields.append("updated_at")
            ticket.save(update_fields=fields)
        settle_late_payment("ticket", ticket)
        if not ticket.event.require_manual_confirm and ticket.status == Ticket.STATUS_PENDING:
            try:
                TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
    return True
