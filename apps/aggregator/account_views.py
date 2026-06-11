"""Клиентский аккаунт на порталах (P2.3a): magic-link вход, профиль, выход.

Анти-энумерация: на запрос ссылки ответ всегда «проверьте почту» — есть email
в базе или нет. Rate-limit: на IP (запросы формы) и на email (выпуск ссылок,
внутри issue_magic_link). Страница /konto/ — задел: в P2.3b сюда придёт
избранное, в P2.3c — брони по всем бизнесам.
"""

from django import forms
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core import ratelimit

from . import auth
from .models import AggregatorListing, FavoriteListing
from .tasks import send_magic_link_email

IP_RL_LIMIT = 5
IP_RL_WINDOW = 600


class LoginForm(forms.Form):
    email = forms.EmailField()
    website = forms.CharField(required=False)  # honeypot, как на витрине


def _portal_or_404(request):
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return portal


def login_view(request):
    portal = _portal_or_404(request)
    if auth.current_portal_user(request):
        return redirect("portal-account")

    if request.method == "POST":
        form = LoginForm(request.POST)
        ip = ratelimit.client_ip(request)
        if (
            form.is_valid()
            and not form.cleaned_data["website"]
            and not ratelimit.hit("magiclink_ip", ip, limit=IP_RL_LIMIT, window=IP_RL_WINDOW)
        ):
            email = form.cleaned_data["email"].lower()
            token = auth.issue_magic_link(email)
            if token:
                url = request.build_absolute_uri(reverse("portal-login-verify") + f"?t={token}")
                send_magic_link_email.delay(
                    dedupe_key=f"magiclink:{auth._hash(token)}", email=email, url=url
                )
        # ответ одинаков при любом исходе (анти-энумерация / тихий rate-limit)
        return render(request, "aggregator/portal_check_inbox.html", {"portal": portal})

    return render(request, "aggregator/portal_login.html", {"portal": portal, "form": LoginForm()})


def login_verify(request):
    portal = _portal_or_404(request)
    payload = auth.consume_magic_link(request.GET.get("t", ""))
    if payload is None:
        return render(
            request, "aggregator/portal_link_invalid.html", {"portal": portal}, status=400
        )
    auth.login(request, payload["email"])
    return redirect("portal-account")


def account(request):
    portal = _portal_or_404(request)
    user = auth.current_portal_user(request)
    if user is None:
        return redirect("portal-login")
    favorites = list(
        AggregatorListing.objects.filter(favorited_by__user=user, is_active=True).order_by(
            "-favorited_by__created_at"
        )
    )
    from .account_services import reservations_for_email

    return render(
        request,
        "aggregator/portal_account.html",
        {
            "portal": portal,
            "user": user,
            "favorites": favorites,
            "fav_ids": {listing.pk for listing in favorites},
            "reservations": reservations_for_email(user.email),
        },
    )


@require_POST
def favorite_toggle(request):
    """Сохранить/убрать листинг из избранного; редирект назад (next)."""
    _portal_or_404(request)
    user = auth.current_portal_user(request)
    if user is None:
        return redirect("portal-login")
    try:
        listing_pk = int(request.POST.get("listing", ""))
    except (TypeError, ValueError):
        listing_pk = None
    listing = AggregatorListing.objects.filter(pk=listing_pk, is_active=True).first()
    if listing is not None:
        favorite, created = FavoriteListing.objects.get_or_create(user=user, listing=listing)
        if not created:
            favorite.delete()
    next_url = request.POST.get("next", "")
    # только локальный путь — внешние редиректы через next не пускаем
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = reverse("portal-home")
    return redirect(next_url)


@require_POST
def logout_view(request):
    _portal_or_404(request)
    auth.logout(request)
    return redirect("portal-home")
