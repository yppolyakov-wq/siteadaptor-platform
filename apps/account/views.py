"""ЛК клиента на витрине бизнеса (CA1): magic-link вход + главная.

Гейтинг — модуль customer_account (тумблер владельца в /dashboard/modules/).
Личность — promotions.Customer в схеме бизнеса (apps.account.auth).
"""

from django import forms
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core import ratelimit

from . import auth
from .tasks import send_customer_magic_link

IP_RL_LIMIT = 5
IP_RL_WINDOW = 600


class LoginForm(forms.Form):
    email = forms.EmailField()
    website = forms.CharField(required=False)  # honeypot


def _require_account_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("customer_account"):
        raise Http404


def login_view(request):
    _require_account_active(request)
    if auth.current_customer(request):
        return redirect("account-home")
    if request.method == "POST":
        form = LoginForm(request.POST)
        ip = ratelimit.client_ip(request)
        if (
            form.is_valid()
            and not form.cleaned_data["website"]
            and not ratelimit.hit("acct_ml_ip", ip, limit=IP_RL_LIMIT, window=IP_RL_WINDOW)
        ):
            email = form.cleaned_data["email"].lower()
            token = auth.issue_magic_link(email)
            if token:
                url = request.build_absolute_uri(reverse("account-verify") + f"?t={token}")
                send_customer_magic_link.delay(
                    dedupe_key=f"acct_ml:{auth._hash(token)}",
                    email=email,
                    url=url,
                    business_name=getattr(request.tenant, "name", ""),
                )
        # ответ одинаков при любом исходе (анти-энумерация / тихий rate-limit)
        return render(request, "konto/check_inbox.html", {})
    return render(request, "konto/login.html", {"form": LoginForm()})


def login_verify(request):
    _require_account_active(request)
    payload = auth.consume_magic_link(request.GET.get("t", ""))
    if payload is None:
        return render(request, "konto/link_invalid.html", {}, status=400)
    auth.login(request, payload["email"])
    return redirect("account-home")


@require_POST
def logout_view(request):
    _require_account_active(request)
    auth.logout(request)
    return redirect("storefront-home")


def account_home(request):
    _require_account_active(request)
    customer = auth.current_customer(request)
    if customer is None:
        return redirect("account-login")
    return render(request, "konto/home.html", {"customer": customer})
