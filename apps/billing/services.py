"""Stripe-интеграция биллинга: Checkout, Customer Portal, активация подписки.

Все внешние вызовы Stripe изолированы здесь — в тестах патчатся (Stripe-ключей в
CI нет). Состояние подписки живёт на Tenant (см. state_machine.SubscriptionSM);
смена статуса — только через SM.apply().
"""

import stripe
from django.conf import settings

from apps.tenants.models import Tenant

from .plans import modules_for_tier
from .state_machine import ACTIVE, PAST_DUE, SubscriptionSM


def _client():
    """Stripe SDK с секретным ключом (test/live по STRIPE_LIVE_MODE)."""
    stripe.api_key = (
        settings.STRIPE_LIVE_SECRET_KEY
        if settings.STRIPE_LIVE_MODE
        else settings.STRIPE_TEST_SECRET_KEY
    )
    return stripe


def ensure_stripe_customer(tenant: Tenant) -> str:
    """Вернуть stripe_customer_id, создав Stripe Customer при отсутствии."""
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id
    customer = _client().Customer.create(
        email=tenant.public_email or tenant.owner_email or None,
        name=tenant.name,
        metadata={"tenant_id": str(tenant.id), "schema": tenant.schema_name},
    )
    tenant.stripe_customer_id = customer["id"]
    tenant.save(update_fields=["stripe_customer_id", "updated_at"])
    return customer["id"]


def create_checkout_session(tenant: Tenant, *, success_url: str, cancel_url: str) -> str:
    """Checkout Session подписки (тариф Standard). Возвращает URL оплаты."""
    customer_id = ensure_stripe_customer(tenant)
    session = _client().checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(tenant.id),
        metadata={"tenant_id": str(tenant.id)},
        subscription_data={"metadata": {"tenant_id": str(tenant.id)}},
    )
    return session["url"]


def create_billing_portal_session(tenant: Tenant, *, return_url: str) -> str:
    """Customer Portal (карта/отмена/инвойсы). Возвращает URL портала."""
    customer_id = ensure_stripe_customer(tenant)
    session = _client().billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return session["url"]


def create_usage_invoice_item(
    tenant: Tenant, *, amount_cents: int, description: str, currency: str = "eur"
) -> str:
    """Строка Nutzungsgebühr в Stripe-счёт подписки бизнеса (вариант B, P2.5-fee).

    InvoiceItem без явного invoice попадает в следующий счёт подписки (тот же
    Customer/карта). Возвращает id позиции.
    """
    customer_id = ensure_stripe_customer(tenant)
    item = _client().InvoiceItem.create(
        customer=customer_id,
        amount=amount_cents,
        currency=currency,
        description=description,
    )
    return item["id"]


def create_featured_checkout_session(
    tenant: Tenant,
    *,
    promo_uuid: str = "",
    listing_kind: str = "",
    source_ref: str = "",
    days: int,
    title: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Разовый Checkout (mode="payment") за продвижение листинга (P2.4b/D2.4).

    Сумму передаём inline price_data (без заведения Price в Stripe). Эффект —
    в metadata: вебхук на public-схеме проставит featured_until нужному листингу.
    Адресация листинга: (listing_kind, source_ref) — generic (D2.4: stays/events);
    promo_uuid — легаси-ключ акций (эквивалент kind=promotion, source_ref=uuid).
    Привязываем к Customer арендатора, чтобы платёж попал в его историю/чеки.
    Возвращает URL оплаты.
    """
    from .featured import get_plan

    plan = get_plan(days)
    if plan is None:
        raise ValueError(f"unknown featured plan: {days}")
    if not (promo_uuid or (listing_kind and source_ref)):
        raise ValueError("featured checkout needs promo_uuid or (listing_kind, source_ref)")
    customer_id = ensure_stripe_customer(tenant)
    meta = {
        "kind": "featured",
        "tenant_id": str(tenant.id),
        "tenant_schema": tenant.schema_name,
        "promo_uuid": str(promo_uuid or ""),
        "listing_kind": listing_kind or "",
        "source_ref": str(source_ref or ""),
        "days": str(plan.days),
    }
    session = _client().checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "unit_amount": plan.amount_cents,
                    "product_data": {"name": f"Empfehlung {plan.days} Tage – {title}"[:250]},
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(tenant.id),
        metadata=meta,
        payment_intent_data={"metadata": meta},
    )
    return session["url"]


def apply_featured_purchase(
    *,
    tenant_schema: str,
    promo_uuid: str = "",
    listing_kind: str = "",
    source_ref: str = "",
    days,
    payment_ref: str = "",
) -> bool:
    """Оплата прошла → продлить featured_until листинга (public-схема, P2.4b).

    Срок продлеваем от max(now, текущий) — повторная покупка добавляет дни, а не
    сбрасывает. Идемпотентность одного платежа — двухуровневая: дедуп вебхука по
    event.id (Redis) + персистентный `featured_payment_ref` на листинге (переживает
    потерю кэша: тот же payment_intent не продлевает срок повторно). Листинг
    существует, только пока акция active (sync_listing); если его нет — no-op (False).
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.aggregator.models import AggregatorListing

    days = int(days or 0)
    if days <= 0:
        return False
    if listing_kind and source_ref:  # D2.4: generic-адресация (stay/event/…)
        lookup = {"listing_kind": listing_kind, "source_ref": str(source_ref)}
    elif promo_uuid:  # легаси-metadata незакрытых сессий
        lookup = {"promo_uuid": promo_uuid}
    else:
        return False
    listing = AggregatorListing.objects.filter(tenant_schema=tenant_schema, **lookup).first()
    if listing is None:
        return False
    # тот же платёж уже применён (реплей вебхука при утрате Redis-дедупа) → no-op
    if payment_ref and listing.featured_payment_ref == payment_ref:
        return False
    now = timezone.now()
    base = listing.featured_until if listing.is_featured_now else now
    listing.featured_until = base + timedelta(days=days)
    if payment_ref:
        listing.featured_payment_ref = payment_ref
    listing.save(update_fields=["featured_until", "featured_payment_ref", "updated_at"])
    return True


def activate_subscription(tenant: Tenant, *, ends_at=None) -> None:
    """Оплата прошла → active: SM-переход + полный набор модулей (+ дата конца)."""
    SubscriptionSM().apply(tenant, ACTIVE)
    fields = []
    full = modules_for_tier()
    if list(tenant.enabled_modules or []) != full:
        tenant.enabled_modules = full
        fields.append("enabled_modules")
    if ends_at is not None and tenant.subscription_ends_at != ends_at:
        tenant.subscription_ends_at = ends_at
        fields.append("subscription_ends_at")
    if fields:
        fields.append("updated_at")
        tenant.save(update_fields=fields)


def mark_past_due(tenant: Tenant) -> None:
    """Неудачный платёж/отмена: active → past_due (далее suspend по grace в beat)."""
    if tenant.subscription_status == ACTIVE:
        SubscriptionSM().apply(tenant, PAST_DUE)
