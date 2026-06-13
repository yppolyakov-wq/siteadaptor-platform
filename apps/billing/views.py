"""Billing-вьюхи кабинета владельца: страница подписки, Checkout, Customer Portal.

Живут в схеме арендатора (под логином). Внешние вызовы Stripe — в services
(в тестах патчатся). Маршруты `/dashboard/billing*` остаются доступны даже при
gated-статусе (см. middleware), чтобы владелец мог оплатить.
"""

import secrets

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import connect, services


@login_required
def billing(request):
    return render(
        request,
        "billing/billing.html",
        {
            "nav": "billing",
            "price_configured": bool(settings.STRIPE_PRICE_ID),
            "checkout_status": request.GET.get("status", ""),
        },
    )


def _absolute(request, name: str) -> str:
    return request.build_absolute_uri(reverse(name))


@login_required
@require_POST
def checkout(request):
    if not settings.STRIPE_PRICE_ID:
        messages.error(request, _("Billing is not configured yet."))
        return redirect("billing")
    url = services.create_checkout_session(
        request.tenant,
        success_url=_absolute(request, "billing") + "?status=success",
        cancel_url=_absolute(request, "billing") + "?status=cancel",
    )
    return redirect(url)


@login_required
@require_POST
def portal(request):
    if not request.tenant.stripe_customer_id:
        messages.error(request, _("No billing account yet — start a subscription first."))
        return redirect("billing")
    url = services.create_billing_portal_session(
        request.tenant, return_url=_absolute(request, "billing")
    )
    return redirect(url)


# ---------------------------------------------------------------------------
# Приём оплаты от клиентов через Stripe Connect (P2.5a, Standard/OAuth)
# ---------------------------------------------------------------------------


@login_required
def payments(request):
    """Статус приёма оплаты клиентов + подключение Stripe (Connect, Standard)."""
    tenant = request.tenant
    return render(
        request,
        "billing/payments.html",
        {
            "nav": "billing",
            "connect_configured": connect.is_connect_configured(),
            "connected": bool(tenant.stripe_connect_id),
            "payments_enabled": tenant.payments_enabled,
            "fee_percent": connect.application_fee_percent(tenant.business_type),
            "status": request.GET.get("status", ""),
        },
    )


@login_required
@require_POST
def payments_connect(request):
    """Старт Connect OAuth: state в сессию → редирект на Stripe."""
    if not connect.is_connect_configured():
        messages.error(request, _("Online payments are not available yet."))
        return redirect("billing-payments")
    state = secrets.token_urlsafe(24)
    request.session["stripe_connect_state"] = state
    url = connect.oauth_authorize_url(
        state=state, redirect_uri=_absolute(request, "billing-payments-callback")
    )
    return redirect(url)


@login_required
def payments_callback(request):
    """Возврат из Stripe OAuth: проверяем state, меняем code на account id."""
    if request.GET.get("error"):
        messages.error(request, _("Connection was cancelled."))
        return redirect("billing-payments")
    expected = request.session.pop("stripe_connect_state", None)
    code = request.GET.get("code", "")
    if not code or not expected or request.GET.get("state", "") != expected:
        messages.error(request, _("Invalid response — please try connecting again."))
        return redirect("billing-payments")
    try:
        account_id = connect.complete_oauth(code)
    except stripe.error.StripeError:
        messages.error(request, _("Could not connect Stripe — please try again."))
        return redirect("billing-payments")
    tenant = request.tenant
    # Standard-аккаунт после OAuth обычно сразу charges_enabled; вебхук
    # account.updated держит payments_enabled в синхроне.
    tenant.stripe_connect_id = account_id
    tenant.payments_enabled = True
    tenant.save(update_fields=["stripe_connect_id", "payments_enabled", "updated_at"])
    messages.success(request, _("Stripe connected — you can now accept customer payments."))
    return redirect(reverse("billing-payments") + "?status=connected")
