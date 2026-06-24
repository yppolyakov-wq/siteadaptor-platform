"""Онлайн-оплата билета через Stripe Connect (A6c).

Checkout на connected account бизнеса (деньги ему; вариант B → application_fee=0).
Подтверждение ставит вебхук на public-схеме (billing.webhooks → mark_ticket_paid),
кросс-схемно. Зеркало apps.stays.payments / booking.payments.
"""

import stripe

from apps.billing import connect


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

    from . import installments
    from .models import InstallmentCharge, InstallmentPlan

    today = today or timezone.localdate()
    max_attempts = getattr(settings, "INSTALLMENT_MAX_ATTEMPTS", 3)
    due = InstallmentCharge.objects.filter(
        status=InstallmentCharge.STATUS_SCHEDULED,
        due_date__lte=today,
        plan__status=InstallmentPlan.STATUS_ACTIVE,
    ).select_related("plan", "plan__ticket", "plan__ticket__event", "plan__ticket__customer")
    charged = failed = 0
    for charge in due:
        plan = charge.plan
        if not (connect_id and plan.stripe_customer_id and plan.stripe_payment_method_id):
            continue  # нет мандата — пропускаем (дозаполнение/ручное списание в кабинете)
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
            )
            installments.mark_charge_paid(charge, payment_intent=pi)
            charged += 1
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
            failed += 1
    return {"charged": charged, "failed": failed}


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
        if fields:
            fields.append("updated_at")
            ticket.save(update_fields=fields)
        if not ticket.event.require_manual_confirm and ticket.status == Ticket.STATUS_PENDING:
            try:
                TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
    return True
