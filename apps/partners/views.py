"""D3: кабинет партнёра на public-домене (v1 — read-only список клиентов)."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Partner


def _base_domain() -> str:
    return getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")


@login_required
def dashboard(request):
    """Список клиентов партнёра + реф-ссылка + счётчики (всё из public-схемы)."""
    partner = Partner.objects.filter(user=request.user, is_active=True).first()
    if partner is None:
        return render(request, "partners/no_profile.html", status=403)

    tenants = list(partner.tenants.order_by("-created_at"))
    active = [t for t in tenants if t.subscription_status == "active"]
    trial = [t for t in tenants if t.subscription_status == "trial"]

    revshare_month_eur = None
    if partner.reward_kind == Partner.REWARD_REVSHARE and partner.revshare_percent:
        price = getattr(settings, "BILLING_PLAN_PRICE_EUR", 39)
        revshare_month_eur = round(len(active) * price * partner.revshare_percent / 100, 2)

    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return render(
        request,
        "partners/dashboard.html",
        {
            "partner": partner,
            "tenants": tenants,
            "n_active": len(active),
            "n_trial": len(trial),
            "ref_url": f"{scheme}://{_base_domain()}/?ref={partner.code}",
            "revshare_month_eur": revshare_month_eur,
            "base_domain": _base_domain(),
        },
    )
