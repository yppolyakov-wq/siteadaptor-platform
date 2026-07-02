"""Онлайн-продажа Mehrfachkarte через Stripe Connect (A3) — зеркало P2.5b.

Клиент покупает абонемент (PassPlan) на публичной странице → Checkout на
connected account бизнеса → вебхук (public-схема) выпускает Pass клиенту в
TENANT-схеме и шлёт код письмом. Идемпотентность — по payment_intent на Pass.
"""

from apps.billing import connect


def pass_checkout_url(plan, tenant, *, name, email, success_url, cancel_url) -> str:
    """URL Stripe-оплаты абонемента (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=plan.price_cents,
        product_name=plan.label,
        metadata={
            "kind": "pass_purchase",
            "tenant_schema": tenant.schema_name,
            "plan_id": str(plan.id),
            "name": (name or "")[:120],
            "email": (email or "")[:200],
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
    )


def purchase_pass(*, tenant_schema, plan_id, name, email, payment_intent="") -> bool:
    """Вебхук: оплата абонемента → выпустить Pass + письмо с кодом. Кросс-схемно,
    идемпотентно (по payment_intent)."""
    from datetime import timedelta

    from django.utils import timezone
    from django_tenants.utils import schema_context

    from . import services
    from .models import Pass, PassPlan

    if not tenant_schema or not plan_id:
        return False
    with schema_context(tenant_schema):
        if payment_intent and Pass.objects.filter(stripe_payment_intent=payment_intent).exists():
            return True  # уже выпущен (повтор вебхука)
        plan = PassPlan.objects.filter(id=plan_id).select_related("service").first()
        if plan is None:
            return False
        valid_until = (
            timezone.localdate() + timedelta(days=plan.valid_days) if plan.valid_days else None
        )
        card = services.issue_pass(
            name=name or "Kunde",
            email=email,
            label=plan.label,
            credits=plan.credits,
            valid_until=valid_until,
            service=plan.service,
            stripe_payment_intent=payment_intent,
        )
        _email_code(card)
    return True


def _email_code(card) -> None:
    """Письмо клиенту с кодом купленной карты (без шаблона — короткий текст)."""
    from apps.notifications.services import notify

    email = getattr(card.customer, "email", "")
    if not email:
        return
    notify(
        dedupe_key=f"pass:{card.id}:issued",
        type="pass_issued",
        recipient=email,
        subject=f"Ihre Mehrfachkarte {card.code}",
        body=(
            f"Hallo {card.customer},\n\n"
            f"vielen Dank! Ihre {card.label} ist aktiv.\n"
            f"Code: {card.code} — {card.credits_total} Besuche.\n"
            f"Geben Sie den Code bei der Online-Buchung an.\n"
        ),
    )
