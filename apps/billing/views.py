"""Billing-вьюхи кабинета владельца: страница подписки, Checkout, Customer Portal.

Живут в схеме арендатора (под логином). Внешние вызовы Stripe — в services
(в тестах патчатся). Маршруты `/dashboard/billing*` остаются доступны даже при
gated-статусе (см. middleware), чтобы владелец мог оплатить.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services


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
