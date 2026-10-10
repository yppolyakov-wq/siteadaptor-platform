"""T-8.5: вход владельца без пароля + подтверждение почты лёгкой регистрации.

План — docs/t8-5-quick-start-plan-2026-10-10.md §1.

- Одноразовый токен входа (Redis ``owner_login:<schema>:<sha256>``) — по паттерну
  приглашения в команду (`core/team.py`). Сессии не делятся между хостами (HIGH-10),
  поэтому логин происходит запросом НА ПОДДОМЕНЕ: ``/start/<token>/``. GET токен не
  расходует (почтовые сканеры открывают ссылки), POST — расходует и логинит.
- «Login-Link per E-Mail» (``/anmelden/link/``) — тот же токен письмом, TTL 15 минут,
  нейтральный ответ (по ответу нельзя узнать, есть ли такой адрес).
- Подтверждение почты (Р-3): подписанная ссылка ``/start/bestaetigen/<signed>/`` снимает
  ``Tenant.email_pending`` и выкладывает активные акции в городской каталог.
"""

from __future__ import annotations

import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import connection
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit
from apps.core.models import Membership

HANDOFF_TTL = 3600  # переход со страницы ожидания на поддомен
LINK_TTL = 15 * 60  # ссылка входа письмом
CONFIRM_SALT = "t85-confirm"
CONFIRM_MAX_AGE = 30 * 24 * 3600
DEFAULT_NEXT = "/promotions/"
# Ссылки на поддомен строятся и из Celery (urlconf там публичный) — явно tenant-urlconf.
TENANT_URLCONF = "config.urls_tenant"


def _key(schema: str, token: str) -> str:
    return f"owner_login:{schema}:{hashlib.sha256(token.encode()).hexdigest()}"


def issue_token(schema: str, email: str, *, ttl: int = HANDOFF_TTL) -> str:
    """Одноразовый токен входа владельца в схему ``schema``."""
    token = secrets.token_urlsafe(32)
    cache.set(_key(schema, token), {"email": (email or "").strip().lower()}, ttl)
    return token


def peek_token(schema: str, token: str) -> dict | None:
    return cache.get(_key(schema, token))


def consume_token(schema: str, token: str) -> dict | None:
    """Payload с удалением ДО использования (одноразовость)."""
    key = _key(schema, token)
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload


def safe_next(request, value: str) -> str:
    value = (value or "").strip()
    if (
        value.startswith("/")
        and not value.startswith(("//", "/\\"))
        and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()})
    ):
        return value
    return DEFAULT_NEXT


def _owner(email: str):
    """Пользователь с членством в этой схеме (иначе None — вход не даём)."""
    user = get_user_model().objects.filter(username=(email or "").strip().lower()).first()
    if user is None or not user.is_active or not Membership.objects.filter(user=user).exists():
        return None
    return user


def owner_start(request, token):
    """/start/<token>/: GET — кнопка «Jetzt anmelden», POST — вход."""
    schema = connection.schema_name
    next_url = safe_next(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        payload = consume_token(schema, token)
        user = _owner(payload["email"]) if payload else None
        if user is None:
            raise Http404
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(next_url)
    if peek_token(schema, token) is None:
        return render(request, "account/owner_start.html", {"invalid": True}, status=404)
    return render(request, "account/owner_start.html", {"next": next_url})


def tenant_url(tenant) -> str:
    from apps.tenants.services import site_url_for

    return site_url_for(tenant)


def send_login_link(tenant, email: str) -> None:
    from apps.notifications.services import email_locale

    token = issue_token(tenant.schema_name, email, ttl=LINK_TTL)
    url = f"{tenant_url(tenant)}{reverse('owner-start', args=[token], urlconf=TENANT_URLCONF)}"
    with translation.override(email_locale()):
        subject = _("Ihr Anmeldelink — %(name)s") % {"name": tenant.name}
        body = _(
            "Hallo,\n\nhier ist Ihr Link zur Anmeldung (15 Minuten gültig):\n%(url)s\n\n"
            "Falls Sie das nicht angefordert haben, ignorieren Sie diese E-Mail."
        ) % {"url": url}
    send_mail(subject, body, None, [email], fail_silently=True)


def owner_link_request(request):
    """/anmelden/link/: ссылка входа письмом. Ответ один и тот же для любого адреса."""
    sent = False
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        ip = ratelimit.client_ip(request)
        blocked = ratelimit.hit("owner-link", ip, limit=10, window=3600) or ratelimit.hit(
            "owner-link-mail", f"{connection.schema_name}:{email}", limit=3, window=3600
        )
        if email and not blocked and _owner(email) is not None:
            send_login_link(request.tenant, email)
        sent = True
    return render(request, "account/owner_link.html", {"sent": sent})


# --- подтверждение почты (Р-3) -------------------------------------------------------


def confirm_token(tenant, email: str) -> str:
    return signing.dumps({"t": str(tenant.pk), "e": email}, salt=CONFIRM_SALT)


def confirm_url(tenant, email: str) -> str:
    return f"{tenant_url(tenant)}{reverse('owner-confirm-email', args=[confirm_token(tenant, email)], urlconf=TENANT_URLCONF)}"


def send_confirmation(tenant, email: str) -> None:
    from apps.notifications.services import email_locale

    url = confirm_url(tenant, email)
    with translation.override(email_locale()):
        subject = _("Bitte bestätigen Sie Ihre E-Mail — %(name)s") % {"name": tenant.name}
        body = _(
            "Hallo,\n\nIhre Aktion ist online: %(site)s\n\n"
            "Bitte bestätigen Sie Ihre E-Mail-Adresse — dann erscheinen Ihre Aktionen auch "
            "im Stadtportal:\n%(url)s\n\nIhr siteadaptor-Team"
        ) % {"site": tenant_url(tenant), "url": url}
    send_mail(subject, body, None, [email], fail_silently=True)


def confirm_tenant_email(tenant) -> bool:
    """Снять флаг и выложить активные акции. True — флаг был снят этим вызовом."""
    if not tenant.email_pending:
        return False
    tenant.email_pending = False
    tenant.save(update_fields=["email_pending", "updated_at"])
    from apps.aggregator.tasks import sync_aggregator_listing
    from apps.promotions.models import Promotion

    for pk in Promotion.objects.filter(status="active").values_list("pk", flat=True):
        sync_aggregator_listing.delay(
            dedupe_key=f"agg:{pk}:confirmed",
            tenant_schema=tenant.schema_name,
            promotion_id=str(pk),
        )
    return True


def owner_confirm_email(request, signed):
    try:
        payload = signing.loads(signed, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
    except signing.BadSignature:
        return render(request, "account/owner_confirmed.html", {"invalid": True}, status=404)
    tenant = request.tenant
    if str(payload.get("t")) != str(tenant.pk):
        return render(request, "account/owner_confirmed.html", {"invalid": True}, status=404)
    confirm_tenant_email(tenant)
    return render(request, "account/owner_confirmed.html", {})


@require_POST
def owner_confirm_resend(request):
    """Повторное письмо подтверждения (из кабинета, только владельцу под логином)."""
    from django.contrib import messages

    if not request.user.is_authenticated:
        raise Http404
    tenant = request.tenant
    next_url = safe_next(request, request.POST.get("next"))
    if not tenant.email_pending:
        return redirect(next_url)
    if ratelimit.hit("owner-confirm", connection.schema_name, limit=3, window=3600):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(next_url)
    send_confirmation(tenant, request.user.email or tenant.owner_email)
    messages.success(request, _("Bestätigungslink wurde erneut gesendet."))
    return redirect(next_url)


def pending_context(request) -> dict:
    """Плашка «E-Mail bestätigen» для экранов кабинета (Fertig, список акций)."""
    tenant = getattr(request, "tenant", None)
    if not getattr(tenant, "email_pending", False):
        return {}
    from apps.tenants import signup

    email = getattr(request.user, "email", "") or tenant.owner_email
    return {
        "email_pending": True,
        "email_pending_to": email,
        "email_pending_direct": confirm_url(tenant, email) if signup.show_direct_link() else "",
    }
