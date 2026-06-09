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
