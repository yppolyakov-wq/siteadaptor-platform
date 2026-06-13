"""Stripe-вебхуки биллинга: верификация подписи + диспетчер на SubscriptionSM.

Свой эндпоинт (не webhook-view dj-stripe) — полный контроль и тестируемость без
внешних вызовов. Идемпотентность: по event.id (Redis cache.add) + сама SM
(повтор статуса = no-op). Эндпоинт смонтирован на public-схеме (Stripe шлёт на
один URL — см. config/urls_public). Резолв арендатора — по stripe_customer_id
или metadata.tenant_id / client_reference_id.
"""

import logging
from datetime import UTC, datetime

import stripe
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.tenants.models import Tenant

from . import connect, services

logger = logging.getLogger("billing")

# Окно дедупликации event.id (Stripe ретраит вебхуки до 3 суток).
_EVENT_TTL = 60 * 60 * 24 * 3


def _epoch_to_dt(epoch):
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=UTC)


def _tenant_from_object(obj: dict) -> Tenant | None:
    customer_id = obj.get("customer")
    if not customer_id and obj.get("object") == "customer":
        customer_id = obj.get("id")
    meta = obj.get("metadata") or {}
    tenant_id = meta.get("tenant_id") or obj.get("client_reference_id")

    qs = Tenant.objects.all()
    if customer_id:
        tenant = qs.filter(stripe_customer_id=customer_id).first()
        if tenant:
            return tenant
    if tenant_id:
        return qs.filter(id=tenant_id).first()
    return None


def handle_event(event_type: str, obj: dict) -> None:
    """Применить эффект события к арендатору (идемпотентно через SM)."""
    meta = obj.get("metadata") or {}

    # Разовый платёж за продвижение листинга (P2.4b) — не подписка: ставим срок
    # на сам листинг (public-схема), статус подписки не трогаем. Различаем по
    # metadata.kind, проставленному в create_featured_checkout_session.
    if event_type == "checkout.session.completed" and meta.get("kind") == "featured":
        ok = services.apply_featured_purchase(
            tenant_schema=meta.get("tenant_schema", ""),
            promo_uuid=meta.get("promo_uuid", ""),
            days=meta.get("days", 0),
        )
        if not ok:
            logger.warning("stripe webhook featured: listing not found %s", meta)
        return

    # Депозит за бронь (P2.5b): Checkout на connected account → бронь оплачена.
    # Бронь живёт в TENANT-схеме (tenant_schema из metadata), статус подписки не трогаем.
    if event_type == "checkout.session.completed" and meta.get("kind") == "booking_deposit":
        from apps.booking.payments import mark_deposit_paid

        ok = mark_deposit_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            booking_id=meta.get("booking_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            logger.warning("stripe webhook booking_deposit: booking not found %s", meta)
        return

    # Stripe Connect (P2.5): статус connected-аккаунта бизнеса. obj — это Account,
    # его id == Tenant.stripe_connect_id. Подписку не трогаем.
    if event_type == "account.updated":
        connect.set_connect_status(obj.get("id", ""), bool(obj.get("charges_enabled")))
        return

    tenant = _tenant_from_object(obj)
    if tenant is None:
        logger.warning("stripe webhook %s: tenant not resolved", event_type)
        return

    if event_type == "checkout.session.completed":
        services.activate_subscription(tenant)
    elif event_type == "invoice.payment_failed":
        services.mark_past_due(tenant)
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        status = obj.get("status")
        ends_at = _epoch_to_dt(obj.get("current_period_end"))
        if event_type.endswith("deleted") or status in (
            "past_due",
            "unpaid",
            "canceled",
            "incomplete_expired",
        ):
            services.mark_past_due(tenant)
        elif status in ("active", "trialing"):
            services.activate_subscription(tenant, ends_at=ends_at)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Эндпоинт Stripe-вебхука (public-схема)."""
    payload = request.body
    sig = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return HttpResponseBadRequest("invalid payload")
    except stripe.error.SignatureVerificationError:
        return HttpResponseBadRequest("invalid signature")

    # Дедупликация по event.id: первый приход выигрывает cache.add, повторы — no-op.
    if not cache.add(f"stripe_evt:{event['id']}", "1", timeout=_EVENT_TTL):
        return HttpResponse(status=200)

    handle_event(event["type"], event["data"]["object"])
    return HttpResponse(status=200)
