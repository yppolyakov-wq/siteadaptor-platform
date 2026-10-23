"""ЛК клиента на витрине бизнеса (CA1): magic-link вход + главная.

Гейтинг — модуль customer_account (тумблер владельца в /dashboard/modules/).
Личность — promotions.Customer в схеме бизнеса (apps.account.auth).
"""

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit

from . import auth
from .tasks import send_customer_magic_link

IP_RL_LIMIT = 5
IP_RL_WINDOW = 600
# T-8.30l: вход через Telegram — попыток с одного адреса за 10 минут.
TG_RL_LIMIT = 10
TG_RL_WINDOW = 600
# Окно Mini App часто открыто дольше 5 минут до нажатия «Mit Telegram anmelden».
TG_MAX_AGE = 15 * 60


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


@require_POST
def telegram_login(request):
    """T-8.30l: вход в ЛК по подписанному initData бота ЭТОГО магазина.

    Подписи чужих ботов не принимаем: владелец другого бота знает свой токен и мог бы
    подписать initData с любым uid. CSRF — штатный (обычная форма на странице входа).
    """
    from django.http import HttpResponse

    from apps.platform_bot import webapp_auth
    from apps.telegram.notify import active_bot

    _require_account_active(request)
    bot = active_bot()
    if bot is None:
        raise Http404
    ip = ratelimit.client_ip(request)
    # Лимит считает только НЕУДАЧИ: за общим IP мобильного оператора много клиентов.
    if ratelimit.peek("acct_tg_ip", ip) >= TG_RL_LIMIT:
        return HttpResponse(
            _("Zu viele Anmeldeversuche. Bitte in ein paar Minuten erneut."), status=429
        )
    failed = HttpResponse(_("Anmeldung über Telegram fehlgeschlagen."), status=403)
    try:
        data = webapp_auth.verify(
            request.POST.get("init_data", ""),
            bot.token,
            now=int(timezone.now().timestamp()),
            max_age=TG_MAX_AGE,
            allow_replay=True,  # повтор допустим только с того же адреса (ниже)
        )
    except webapp_auth.InitDataError:
        ratelimit.hit("acct_tg_ip", ip, limit=TG_RL_LIMIT, window=TG_RL_WINDOW)
        return failed
    # Повтор той же подписи (двойной тап) — только с адреса первого входа: перехваченная
    # строка initData с другого адреса не входит (как у Mini App владельца, T-8.30f).
    from django.core.cache import cache

    seen_key = f"acct_tg_seen:{data['digest']}"
    if data.get("replay"):
        if cache.get(seen_key) != ip:
            ratelimit.hit("acct_tg_ip", ip, limit=TG_RL_LIMIT, window=TG_RL_WINDOW)
            return failed
    else:
        cache.set(seen_key, ip, TG_MAX_AGE + 60)
    request.session.cycle_key()  # без фиксации сессии
    auth.login_telegram(request, uid=data["uid"], name=data.get("first_name") or "")
    return redirect("account-home")


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
    from .account_data import sections_for

    return render(
        request,
        "konto/home.html",
        {"customer": customer, "sections": sections_for(request, customer)},
    )


def profile_view(request):
    """CA3: профиль + согласие на маркетинг + DSGVO (экспорт/удаление)."""
    _require_account_active(request)
    customer = auth.current_customer(request)
    if customer is None:
        return redirect("account-login")
    if request.method == "POST":
        customer.name = request.POST.get("name", "").strip()[:200]
        customer.phone = request.POST.get("phone", "").strip()[:40]
        # PMS-B2: опциональный ДР (пусто = стереть; кривая дата — прежнее значение).
        raw_birthday = request.POST.get("birthday", "").strip()
        try:
            from datetime import date as _date

            customer.birthday = _date.fromisoformat(raw_birthday) if raw_birthday else None
        except ValueError:
            pass
        # UWG §7: галка = получать рассылки (opt_in + снять one-click отписку).
        opt = request.POST.get("marketing") == "on"
        # PMS-аудит 2026-07-27: фиксируем МОМЕНТ согласия (доказательство UWG §7).
        if opt and not customer.marketing_opt_in:
            customer.marketing_opt_in_at = timezone.now()
        customer.marketing_opt_in = opt
        if opt:
            customer.unsubscribed = False
        customer.save(
            update_fields=[
                "name",
                "phone",
                "birthday",
                "marketing_opt_in",
                "marketing_opt_in_at",
                "unsubscribed",
                "updated_at",
            ]
        )
        messages.success(request, _("Saved."))
        return redirect("account-profile")
    from apps.telegram.notify import deep_link

    return render(
        request,
        "konto/profile.html",
        {"customer": customer, "telegram_link": deep_link(customer)},
    )


def export_data(request):
    """CA3: экспорт данных клиента (DSGVO Art. 15/20) — JSON-загрузка."""
    _require_account_active(request)
    customer = auth.current_customer(request)
    if customer is None:
        return redirect("account-login")
    import json

    from django.http import HttpResponse

    from apps.promotions.management.commands.dsgvo_customer import _export_payload

    payload = _export_payload(customer.email, customer=customer)
    resp = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json"
    )
    resp["Content-Disposition"] = 'attachment; filename="meine-daten.json"'
    return resp


@require_POST
def cancel_booking(request, code):
    """CA4: клиент отменяет свой Termin из ЛК (BookingSM cancel + возврат депозита)."""
    _require_account_active(request)
    customer = auth.current_customer(request)
    if customer is None:
        return redirect("account-login")
    from apps.booking.models import Booking
    from apps.booking.state_machine import BookingSM
    from apps.core.fsm import IllegalTransition

    booking = Booking.objects.filter(reference_code=code, customer=customer).first()
    if booking is None:
        raise Http404
    try:
        BookingSM().apply(booking, "cancelled", actor=None)
    except IllegalTransition:
        messages.error(request, _("This booking can no longer be cancelled."))
        return redirect("account-home")
    # Возврат депозита (анти-фрод, как в кабинете), если был оплачен. KA-H4:
    # общая функция — захват + ключ идемпотентности, при отказе Stripe письмо владельцу.
    from apps.core import refunds

    refunds.refund_payment("booking", booking, getattr(request, "tenant", None))
    messages.success(request, _("Your booking was cancelled."))
    return redirect("account-home")


@require_POST
def delete_account(request):
    """CA3: удаление/анонимизация данных (DSGVO Art. 17) → выход."""
    _require_account_active(request)
    customer = auth.current_customer(request)
    if customer is None:
        return redirect("account-login")
    from django.core.management.base import CommandError

    from apps.promotions.management.commands.dsgvo_customer import _erase

    try:
        _erase(customer.email, customer=customer)
    except CommandError as exc:
        messages.error(request, str(exc))
        return redirect("account-profile")
    auth.logout(request)
    messages.success(request, _("Your data has been deleted."))
    return redirect("storefront-home")
