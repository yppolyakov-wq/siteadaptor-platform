"""Онлайн-предоплата Click&Collect через Stripe Connect (P2.5c).

Checkout создаётся НА connected account бизнеса (деньги идут ему; вариант B —
application_fee=0). Подтверждение оплаты ставит вебхук на public-схеме
(apps.billing.webhooks → mark_order_paid), кросс-схемно через schema_context.
"""

from apps.billing import connect


def available_methods(tenant, *, customer_type=None) -> list[str]:
    """E7-2: способы оплаты, доступные на checkout этого бизнеса.

    SH-23: правила переехали в ОБЩИЙ реестр `apps.core.payment_methods` (тот же
    порядок и те же guard'ы — stripe при prepay+Connect, vorkasse при IBAN,
    on_site всегда), потому что способ оплаты теперь есть у всех видов сделок.
    Новое здесь одно: фирме дополнительно предлагается счёт (решение Р-3), если
    бизнес включил `invoice_b2b_enabled`."""
    from apps.core import payment_methods as pm

    return pm.available(tenant, "order", customer_type=customer_type or pm.PRIVATE)


def order_checkout_url(order, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты заказа (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=int(round(order.total * 100)),
        product_name=f"Bestellung {order.reference_code}",
        metadata={
            "kind": "order_payment",
            "tenant_schema": tenant.schema_name,
            "order_id": str(order.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
        currency=(order.currency or "EUR").lower(),
    )


def mark_order_paid(*, tenant_schema: str, order_id: str, payment_intent: str = "") -> bool:
    """Вебхук: заказ оплачен → payment_state=paid + авто-confirm (new→confirmed).
    Кросс-схемно, идемпотентно."""
    from django_tenants.utils import schema_context

    from apps.core.fsm import IllegalTransition

    from .models import Order
    from .state_machine import OrderSM

    if not tenant_schema or not order_id:
        return False
    with schema_context(tenant_schema):
        order = Order.objects.filter(id=order_id).first()
        if order is None:
            return False
        fields = []
        if order.payment_state != Order.PAYMENT_PAID:
            order.payment_state = Order.PAYMENT_PAID
            fields.append("payment_state")
        if payment_intent and order.stripe_payment_intent != payment_intent:
            order.stripe_payment_intent = payment_intent
            fields.append("stripe_payment_intent")
        if fields:
            fields.append("updated_at")
            order.save(update_fields=fields)
        if order.status == Order.STATUS_NEW:
            try:
                OrderSM().apply(order, Order.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
    return True
