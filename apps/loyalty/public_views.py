"""B1.1: витринные вьюхи Geschenkgutscheine — перенос из stays (G1) 1:1.

Гейт вместо stays-модуля — модуль `gift` (реестр apps/core/modules.py) И
онлайн-оплата (payments_enabled + Connect), как было. Движок покупки/оплаты/
выпуска не тронут (loyalty.gift + billing.webhooks + connect).
"""

import stripe
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.billing import connect
from apps.core import ratelimit

GIFT_PRESETS_CENTS = (5000, 10000, 15000, 20000)  # 50/100/150/200 €
RL_LIMIT = 5  # попыток покупки на IP
RL_WINDOW = 600  # за 10 минут


def gift_purchase_active(tenant) -> bool:
    """Продажа гутшайнов доступна: модуль gift активен И онлайн-оплата настроена."""
    if tenant is None or not tenant.is_module_active("gift"):
        return False
    return bool(getattr(tenant, "payments_enabled", False)) and connect.is_connect_configured()


def _require_gift_active(request):
    if not gift_purchase_active(getattr(request, "tenant", None)):
        raise Http404


def gutschein_index(request):
    _require_gift_active(request)
    return render(
        request,
        "storefront/gift_voucher.html",
        {"presets_eur": [c // 100 for c in GIFT_PRESETS_CENTS]},
    )


def gutschein_buy(request):
    _require_gift_active(request)
    if request.method != "POST":
        return redirect("storefront-gutschein")
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-gutschein")
    if ratelimit.hit("gift", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    from apps.loyalty import gift

    try:
        amount_cents = round(float(request.POST.get("amount_eur", "0").replace(",", ".")) * 100)
    except (TypeError, ValueError):
        amount_cents = 0
    try:
        gv = gift.create_gift_voucher(
            buyer_name=request.POST.get("name", ""),
            buyer_email=request.POST.get("email", ""),
            amount_cents=amount_cents,
            recipient_name=request.POST.get("recipient", ""),
            message=request.POST.get("message", ""),
        )
    except ValueError:
        messages.error(request, _("Please enter your name, email and a valid amount."))
        return redirect("storefront-gutschein")

    tenant = request.tenant
    ok_url = request.build_absolute_uri(reverse("storefront-gutschein-ok"))
    cancel_url = request.build_absolute_uri(reverse("storefront-gutschein"))
    try:
        url = connect.connected_checkout_session(
            connect_id=tenant.stripe_connect_id,
            amount_cents=gv.amount_cents,
            product_name=f"Geschenkgutschein {gv.amount_eur:.0f} €",
            metadata={
                "kind": "gift_voucher",
                "tenant_schema": tenant.schema_name,
                "gift_id": str(gv.id),
            },
            success_url=ok_url,
            cancel_url=cancel_url,
            business_type=getattr(tenant, "business_type", ""),
            payment_method_types=getattr(tenant, "stripe_payment_methods", None),
        )
    except stripe.error.StripeError:
        messages.error(request, _("Payment is temporarily unavailable. Please try again later."))
        return redirect("storefront-gutschein")
    return redirect(url)


def gutschein_confirmation(request):
    _require_gift_active(request)
    return render(request, "storefront/gift_voucher_ok.html", {})
