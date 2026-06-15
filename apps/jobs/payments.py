"""Онлайн-Anzahlung за смету Handwerker (A7c) — Stripe Connect, зеркало P2.5b.

Checkout создаётся НА connected account бизнеса (деньги ему напрямую; вариант B —
application_fee=0). Подтверждение оплаты ставит вебхук на public-схеме
(apps.billing.webhooks → mark_deposit_paid), кросс-схемно через schema_context
(смета живёт в TENANT-схеме). Оплата депозита = клиент принял Angebot →
quoted→accepted.
"""

from apps.billing import connect


def deposit_checkout_url(job, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты Anzahlung за смету (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=job.deposit_cents,
        product_name=f"Anzahlung {job.reference_code}",
        metadata={
            "kind": "job_deposit",
            "tenant_schema": tenant.schema_name,
            "job_id": str(job.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
    )


def mark_deposit_paid(*, tenant_schema: str, job_id: str, payment_intent: str = "") -> bool:
    """Вебхук: Anzahlung оплачена → payment_state=paid + принять смету
    (quoted→accepted). Кросс-схемно, идемпотентно."""
    from django.utils import timezone
    from django_tenants.utils import schema_context

    from apps.core.fsm import IllegalTransition

    from .models import Job
    from .state_machine import JobSM

    if not tenant_schema or not job_id:
        return False
    with schema_context(tenant_schema):
        job = Job.objects.filter(id=job_id).first()
        if job is None:
            return False
        fields = []
        if job.payment_state != Job.PAYMENT_PAID:
            job.payment_state = Job.PAYMENT_PAID
            fields.append("payment_state")
        if payment_intent and job.stripe_payment_intent != payment_intent:
            job.stripe_payment_intent = payment_intent
            fields.append("stripe_payment_intent")
        if fields:
            fields.append("updated_at")
            job.save(update_fields=fields)
        # Оплата депозита = принятие сметы (если ещё quoted).
        if job.status == Job.STATUS_QUOTED:
            try:
                JobSM().apply(job, Job.STATUS_ACCEPTED)
                job.accepted_at = timezone.now()
                job.save(update_fields=["accepted_at", "updated_at"])
            except IllegalTransition:
                pass
    return True
