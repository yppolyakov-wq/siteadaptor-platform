"""Онлайн-оплата билета через Stripe Connect (A6c).

Checkout на connected account бизнеса (деньги ему; вариант B → application_fee=0).
Подтверждение ставит вебхук на public-схеме (billing.webhooks → mark_ticket_paid),
кросс-схемно. Зеркало apps.stays.payments / booking.payments.
"""

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
