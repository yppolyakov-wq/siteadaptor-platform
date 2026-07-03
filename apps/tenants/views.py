"""Публичные вьюхи онбординга (живут в public-схеме, см. urls_public)."""

from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import BusinessSignupForm
from .models import Tenant
from .services import login_url_for, start_business_provisioning


class BusinessSignupView(View):
    template_name = "tenants/onboarding.html"

    def get(self, request):
        # D3: реф-код партнёра переживает GET→POST через сессию (?ref=<code>).
        ref = (request.GET.get("ref") or "").strip()[:40]
        if ref:
            request.session["partner_ref"] = ref
        return render(request, self.template_name, {"form": BusinessSignupForm()})

    def post(self, request):
        form = BusinessSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        cd = form.cleaned_data
        # Мгновенный ответ: схема строится в фоне (~1 мин), пользователь ждёт
        # на странице с автообновлением — UX-решение владельца 2026-06-12.
        tenant = start_business_provisioning(
            business_name=cd["business_name"],
            slug=cd["slug"],
            business_type=cd["business_type"],
            city=cd["city"],
            email=cd["email"],
            password=cd["password1"],
            partner_code=request.session.get("partner_ref", ""),
        )
        return redirect("signup-waiting", slug=tenant.slug)


def signup_waiting(request, slug):
    """Страница «Ihre Website wird eingerichtet…»: meta-refresh каждые 4 сек,
    по готовности — редирект на логин субдомена; письмо со ссылкой уходит
    параллельно (tasks._send_ready_email)."""
    tenant = get_object_or_404(Tenant, slug=slug)
    if tenant.provisioning_status == Tenant.PROVISIONING_READY:
        return redirect(login_url_for(tenant))
    return render(
        request,
        "tenants/provisioning.html",
        {
            "tenant": tenant,
            "failed": tenant.provisioning_status == Tenant.PROVISIONING_FAILED,
        },
        status=200,
    )
