"""T-8.7 «Folgen»: HTTP-слой подписок жителя (портал и /entdecken/).

* Кнопка на кэшируемых страницах — ССЫЛКА на /folgen/ (форма с CSRF здесь, иначе главная,
  страницы раздела и района перестали бы кэшироваться — P0-1).
* POST формы: honeypot + метка времени → лимит на IP → лимит на e-mail → письмо DOI.
  Ответ ОДИНАКОВЫЙ при любом исходе (анти-энумерация, как у magic-link).
* GET по ссылке из письма ничего не меняет (сканеры ссылок); подтверждение/отписка — POST.
  One-click отписка почтовика (RFC 8058) — POST без CSRF, токен в пути = авторизация.
* Страницы с токеном в пути: Referrer-Policy: no-referrer + no-store.
"""

from __future__ import annotations

import hashlib

from django import forms
from django.core.cache import cache
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core import ratelimit
from apps.tenants import quickstart

from . import auth, follow, follow_query
from .models import FollowSubscription, PortalUser

IP_RL = (10, 600)
EMAIL_RL = (3, 3600)
EMAIL_RL_DAY = (10, 86400)
GLOBAL_RL = (300, 3600)  # писем DOI в час на всю платформу — потолок e-mail-бомбинга
STAMP_TTL = 24 * 3600


class FollowForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"))
    frequency = forms.ChoiceField(
        label=_("Wie oft?"),
        choices=FollowSubscription.FREQUENCIES,
        initial=FollowSubscription.FREQ_DAILY,
    )
    website = forms.CharField(required=False)  # honeypot
    stamp = forms.CharField(required=False, widget=forms.HiddenInput)


def _stamp_fresh(stamp: str) -> bool:
    """Метка формы одноразовая: повтор POST с той же меткой письма не шлёт."""
    key = f"follow_stamp:{hashlib.sha256((stamp or '').encode()).hexdigest()}"
    try:
        return bool(cache.add(key, "1", STAMP_TTL))
    except Exception:  # noqa: BLE001 — кэш недоступен: fail-open, лимиты ниже держат
        return True


def _base_template(portal) -> str:
    return "aggregator/portal_base.html" if portal else "aggregator/_base.html"


def _token_response(response):
    response["Referrer-Policy"] = "no-referrer"
    add_never_cache_headers(response)
    return response


def _safe_next(request, fallback: str) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


def _home_url(portal) -> str:
    return reverse("portal-home") if portal else reverse("aggregator-index")


def follow_page(request):
    """GET: форма подписки на цель из `?unternehmen=|bereich=|stadtteil=`; POST: DOI."""
    portal = getattr(request, "portal", None)
    target = follow.parse_target(request.GET, portal=portal)
    if target is None:
        raise Http404
    user = auth.current_portal_user(request) if portal else None
    frequencies = [
        (k, label)
        for k, label in FollowSubscription.FREQUENCIES
        if k != FollowSubscription.FREQ_INSTANT or target.allows_instant
    ]
    context = {
        "portal": portal,
        "base_template": _base_template(portal),
        "target": target,
        "frequencies": frequencies,
        "user": user,
        "following": follow.is_following(user, target),
        "back_url": _safe_next(request, _home_url(portal)),
        # T-8.10d: что из фильтров поиска подписка не переносит (дата, «geöffnet», радиус).
        "dropped_filters": follow_query.dropped(request.GET)
        if target.kind == FollowSubscription.TARGET_QUERY
        else [],
    }
    if request.method == "POST":
        form = FollowForm(request.POST)
        if user is not None:  # вошедший — без DOI
            frequency = request.POST.get("frequency", "")
            try:
                follow.follow_now(
                    user, target, frequency=frequency, portal=portal, source_host=request.get_host()
                )
            except follow.FollowLimitReached:
                return render(request, "aggregator/follow.html", {**context, "limit_reached": True})
            return render(request, "aggregator/follow_done.html", {**context, "following": True})
        ip = ratelimit.client_ip(request)
        if (
            form.is_valid()
            and not form.cleaned_data["website"]
            and not quickstart.too_fast(form.cleaned_data["stamp"])
            and _stamp_fresh(form.cleaned_data["stamp"])
            and not ratelimit.hit("follow_ip", ip, limit=IP_RL[0], window=IP_RL[1])
        ):
            email = form.cleaned_data["email"].lower()
            # В ключах лимита — хэш, не адрес (e-mail не должен лежать в Redis открыто).
            ident = hashlib.sha256(email.encode()).hexdigest()
            over = (
                ratelimit.hit("follow_email", ident, limit=EMAIL_RL[0], window=EMAIL_RL[1])
                | ratelimit.hit(
                    "follow_email_day", ident, limit=EMAIL_RL_DAY[0], window=EMAIL_RL_DAY[1]
                )
                | ratelimit.hit("follow_global", "all", limit=GLOBAL_RL[0], window=GLOBAL_RL[1])
            )
            if not over:
                from .tasks import send_follow_confirm_email

                locale = follow.normalize_locale(getattr(request, "LANGUAGE_CODE", "") or "")
                token = follow.make_doi_token(
                    email=email,
                    target=target,
                    frequency=form.cleaned_data["frequency"],
                    portal=portal,
                    locale=locale,
                )
                send_follow_confirm_email.delay(
                    dedupe_key=f"follow-doi:{hashlib.sha256(token.encode()).hexdigest()}",
                    email=email,
                    url=follow.confirm_url(portal, token),
                    locale=locale,
                )
        # ответ одинаков при любом исходе (анти-энумерация / тихий rate-limit)
        return render(request, "aggregator/follow_check_inbox.html", context)
    form = FollowForm(initial={"stamp": quickstart.form_stamp()})
    return render(request, "aggregator/follow.html", {**context, "form": form})


def follow_confirm(request, token):
    """GET — страница с кнопкой (без побочных эффектов); POST — подтверждение."""
    portal = getattr(request, "portal", None)
    payload = follow.load_doi_token(token)
    context = {
        "portal": portal,
        "base_template": _base_template(portal),
        "home_url": _home_url(portal),
    }
    if payload is None:
        return _token_response(
            render(request, "aggregator/follow_invalid.html", context, status=400)
        )
    target = follow.target_from_payload(payload)
    if target is None:
        return _token_response(
            render(request, "aggregator/follow_invalid.html", context, status=400)
        )
    if request.method == "POST":
        try:
            sub = follow.confirm(payload, source_host=request.get_host())
        except follow.FollowLimitReached:
            return _token_response(
                render(
                    request,
                    "aggregator/follow_confirm.html",
                    {**context, "target": target, "limit_reached": True},
                )
            )
        if sub is None:
            return _token_response(
                render(request, "aggregator/follow_invalid.html", context, status=400)
            )
        return _token_response(
            render(
                request,
                "aggregator/follow_done.html",
                {**context, "target": target, "following": True, "sub": sub, "confirmed": True},
            )
        )
    return _token_response(
        render(request, "aggregator/follow_confirm.html", {**context, "target": target})
    )


def follow_manage(request, token):
    """Управление всеми подписками по ссылке из письма (без входа)."""
    portal = getattr(request, "portal", None)
    user = follow.user_by_follow_token(token)
    if user is None:
        raise Http404
    context = {
        "portal": portal,
        "base_template": _base_template(portal),
        "home_url": _home_url(portal),
    }
    if request.method == "POST":
        action = request.POST.get("action", "")
        sub = follow.by_token(request.POST.get("sub", ""))
        if sub is not None and sub.user_id == user.pk:
            if action == "remove":
                follow.unsubscribe(sub)
                # Последняя подписка неявного жителя удаляет и его самого — редирект на
                # страницу управления дал бы 404; показываем «отписаны».
                if not PortalUser.objects.filter(pk=user.pk).exists():
                    return _token_response(
                        render(
                            request,
                            "aggregator/follow_unsubscribed.html",
                            {**context, "all": False},
                        )
                    )
            elif action == "frequency":
                follow.set_frequency(sub, request.POST.get("frequency", ""))
        elif action == "remove_all":
            follow.unsubscribe_all(user)
            return _token_response(
                render(request, "aggregator/follow_unsubscribed.html", {**context, "all": True})
            )
        return _token_response(redirect(request.path))
    rows = [
        {
            "sub": sub,
            "label": follow.describe(sub),
            "frequencies": [
                (k, label)
                for k, label in FollowSubscription.FREQUENCIES
                if k != FollowSubscription.FREQ_INSTANT
                or follow.target_from_follow(sub).allows_instant
            ],
        }
        for sub in follow.user_follows(user)
    ]
    return _token_response(
        render(request, "aggregator/follow_manage.html", {**context, "user": user, "rows": rows})
    )


@csrf_exempt
def follow_unsubscribe(request, token):
    """Отписка: GET — страница с кнопкой; POST — отписка (RFC 8058 one-click без CSRF).

    `token` — токен ОДНОЙ подписки или `follow_token` жителя с `?alle=1` (все)."""
    portal = getattr(request, "portal", None)
    context = {
        "portal": portal,
        "base_template": _base_template(portal),
        "home_url": _home_url(portal),
    }
    all_mode = request.GET.get("alle") == "1"
    sub = None if all_mode else follow.by_token(token)
    user = follow.user_by_follow_token(token) if sub is None else None
    if sub is None and user is None:
        return _token_response(
            render(request, "aggregator/follow_invalid.html", context, status=404)
        )
    if request.method == "POST":
        if sub is not None:
            follow.unsubscribe(sub)
            return _token_response(
                render(request, "aggregator/follow_unsubscribed.html", {**context, "all": False})
            )
        follow.unsubscribe_all(user)
        return _token_response(
            render(request, "aggregator/follow_unsubscribed.html", {**context, "all": True})
        )
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    return _token_response(
        render(
            request,
            "aggregator/follow_unsubscribe.html",
            {
                **context,
                "label": follow.describe(sub) if sub is not None else "",
                "all": sub is None,
                "manage_url": follow.manage_url(user, portal) if user is not None else "",
            },
        )
    )


@require_POST
def follow_toggle(request):
    """Вошедший житель: подписка/отписка с кнопки или смена частоты в /konto/."""
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    user = auth.current_portal_user(request)
    if user is None:
        return redirect("portal-login")
    fallback = reverse("portal-account")
    action = request.POST.get("action", "")
    sub = follow.by_token(request.POST.get("sub", ""))
    if sub is not None and sub.user_id == user.pk:
        if action == "remove":
            follow.unsubscribe(sub)
        elif action == "frequency":
            follow.set_frequency(sub, request.POST.get("frequency", ""))
        return redirect(_safe_next(request, fallback))
    target = follow.parse_target(request.POST, portal=portal)
    if target is None:
        return redirect(_safe_next(request, fallback))
    existing = follow.find(user, target)
    if existing is not None:
        follow.unsubscribe(existing)
    else:
        try:
            follow.follow_now(
                user,
                target,
                frequency=request.POST.get("frequency", ""),
                portal=portal,
                source_host=request.get_host(),
            )
        except follow.FollowLimitReached:  # T-8.10d: лимит — понятное сообщение, не 500
            return redirect(f"{fallback}?limit=1#folgen")
    return redirect(_safe_next(request, fallback))
