"""Онлайн-оплата записи: депозит через Stripe Connect (P2.5b).

Checkout создаётся НА connected account бизнеса (деньги идут ему напрямую;
вариант B — application_fee=0). Подтверждение оплаты ставит вебхук на
public-схеме (apps.billing.webhooks → mark_deposit_paid), кросс-схемно через
schema_context (бронь живёт в TENANT-схеме).
"""

from apps.billing import connect


def deposit_checkout_url(booking, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты депозита за бронь (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=booking.deposit_cents,
        product_name=f"Anzahlung {booking.reference_code}",
        metadata={
            "kind": "booking_deposit",
            "tenant_schema": tenant.schema_name,
            "booking_id": str(booking.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
    )


def mark_deposit_paid(*, tenant_schema: str, booking_id: str, payment_intent: str = "") -> bool:
    """Вебхук: депозит оплачен → payment_state=paid + авто-confirm (если ресурс
    не требует ручного подтверждения). Кросс-схемно, идемпотентно."""
    from django_tenants.utils import schema_context

    from apps.core.fsm import IllegalTransition

    from .models import Booking
    from .state_machine import BookingSM

    if not tenant_schema or not booking_id:
        return False
    with schema_context(tenant_schema):
        booking = Booking.objects.filter(id=booking_id).select_related("resource").first()
        if booking is None:
            return False
        fields = []
        if booking.payment_state != Booking.PAYMENT_PAID:
            booking.payment_state = Booking.PAYMENT_PAID
            fields.append("payment_state")
        if payment_intent and booking.stripe_payment_intent != payment_intent:
            booking.stripe_payment_intent = payment_intent
            fields.append("stripe_payment_intent")
        if fields:
            fields.append("updated_at")
            booking.save(update_fields=fields)
        # Авто-подтверждение, если ресурс не требует ручной проверки (анти-фрод).
        if not booking.resource.require_manual_confirm and booking.status == Booking.STATUS_PENDING:
            try:
                BookingSM().apply(booking, Booking.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
    return True
