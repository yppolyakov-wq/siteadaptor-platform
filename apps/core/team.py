"""W9-10 (Р-7, аудит 2026-08-05): «Team & Zugriff» — членства/роли + инвайт.

БЕЗ миграции: приглашение = одноразовый Redis-токен (TTL 7 дней, неймспейс по
схеме — паттерн magic-link CA1), принятие на публичном пути
/team/beitreten/<token>/ создаёт User+Membership и логинит.

Ролевой гейт HTTP-слоя — CabinetOwnerAccessMiddleware (owner-only префиксы:
Abo/Recht/Team): «пригласить сотрудника» не означает «отдать бизнес». Прямые
вызовы вьюх в тестах middleware обходят — реальный трафик закрыт fail-closed.
"""

import hashlib
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.audit import audit_event
from apps.core.models import Membership

INVITE_TTL = 7 * 24 * 3600  # сек; ссылка-приглашение живёт неделю
INVITE_ROLES = (Membership.ROLE_ADMIN, Membership.ROLE_STAFF)  # owner НЕ приглашается


def _token_key(token: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"team_invite:{connection.schema_name}:{digest}"


def issue_invite(email: str, role: str) -> str | None:
    """Одноразовый токен приглашения (None — некорректные входные)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or role not in INVITE_ROLES:
        return None
    token = secrets.token_urlsafe(32)
    cache.set(_token_key(token), {"email": email, "role": role}, INVITE_TTL)
    return token


def peek_invite(token: str) -> dict | None:
    """Payload без расхода (GET-форма принятия)."""
    return cache.get(_token_key(token))


def consume_invite(token: str) -> dict | None:
    """Payload с удалением ДО использования (одноразовость — как magic-link)."""
    key = _token_key(token)
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload


def owners_count() -> int:
    return Membership.objects.filter(role=Membership.ROLE_OWNER).count()


def _member_rows():
    return [
        {
            "m": m,
            "email": m.user.email or m.user.username,
            "is_last_owner": m.role == Membership.ROLE_OWNER and owners_count() <= 1,
        }
        for m in Membership.objects.select_related("user").order_by("role", "user__username")
    ]


@login_required
def team_view(request):
    """Список членств + смена роли + отзыв + инвайт. Owner-only (middleware)."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "invite":
            token = issue_invite(request.POST.get("email"), request.POST.get("role"))
            if token is None:
                messages.error(request, _("E-Mail oder Rolle ungültig."))
            else:
                link = request.build_absolute_uri(reverse("team-join", args=[token]))
                _send_invite_mail(request, link)
                audit_event(
                    action="team.invite",
                    resource_type="membership",
                    resource_id="",
                    actor=request.user,
                )
                hint = _("Einladung erstellt — Link ist 7 Tage gültig (einmalig):")
                messages.success(request, f"{hint} {link}")
        elif action in ("role", "revoke"):
            m = Membership.objects.filter(pk=request.POST.get("membership_id")).first()
            if m is None:
                messages.error(request, _("Mitglied nicht gefunden."))
            elif action == "revoke":
                _revoke(request, m)
            else:
                _change_role(request, m, request.POST.get("role", ""))
        return redirect("team")

    return render(
        request,
        "tenant/team.html",
        {
            "nav": "team",
            "rows": _member_rows(),
            "roles": Membership.ROLES,
            "invite_roles": [(r, lbl) for r, lbl in Membership.ROLES if r in INVITE_ROLES],
        },
    )


def _revoke(request, m):
    if m.role == Membership.ROLE_OWNER and owners_count() <= 1:
        messages.error(request, _("Der letzte Inhaber kann nicht entfernt werden."))
        return
    if m.user_id == request.user.pk:
        messages.error(request, _("Sich selbst entfernen ist nicht möglich."))
        return
    audit_event(
        action="team.revoke",
        resource_type="membership",
        resource_id=str(m.pk),
        actor=request.user,
    )
    m.delete()  # User остаётся (история/повторный инвайт)
    messages.success(request, _("Zugriff entzogen."))


def _change_role(request, m, role):
    valid = {r for r, _lbl in Membership.ROLES}
    if role not in valid or role == m.role:
        return
    if m.role == Membership.ROLE_OWNER and owners_count() <= 1:
        messages.error(request, _("Der letzte Inhaber kann nicht herabgestuft werden."))
        return
    m.role = role
    m.save(update_fields=["role", "updated_at"])
    audit_event(
        action="team.role",
        resource_type="membership",
        resource_id=str(m.pk),
        actor=request.user,
        changes={"role": role},
    )
    messages.success(request, _("Rolle geändert."))


def _send_invite_mail(request, link):
    """Письмо-приглашение (fail-safe: console-бэкенд/сбой не валит флоу —
    ссылка в любом случае показывается владельцу)."""
    try:
        from django.core.mail import send_mail

        tenant = getattr(request, "tenant", None)
        name = getattr(tenant, "name", "") or "SiteAdaptor"
        subject = _("Einladung ins Team")
        body = _("Sie wurden ins Team eingeladen. Zugriff einrichten:")
        send_mail(subject, f"{body}\n\n{link}\n— {name}", None, [request.POST.get("email", "")])
    except Exception:  # noqa: BLE001 — доставка письма не критична, ссылка на экране
        pass


def team_join(request, token):
    """Публичное принятие приглашения: токен → User+Membership → login.

    GET показывает форму (peek — токен НЕ расходуется), POST расходует
    (одноразовость). Существующий User с паролем НЕ перезаписывается —
    инвайт лишь добавляет членство."""
    payload = peek_invite(token)
    if payload is None:
        return render(request, "tenant/team_join.html", {"invalid": True}, status=404)
    user = get_user_model().objects.filter(username=payload["email"]).first()
    needs_password = user is None or not user.has_usable_password()
    if user is not None and Membership.objects.filter(user=user).exists():
        return render(request, "tenant/team_join.html", {"already_member": True})

    if request.method == "POST":
        pw1, pw2 = request.POST.get("password1", ""), request.POST.get("password2", "")
        if needs_password and (len(pw1) < 8 or pw1 != pw2):
            return render(
                request,
                "tenant/team_join.html",
                {"email": payload["email"], "needs_password": True, "pw_error": True},
            )
        payload = consume_invite(token)  # одноразовость — расход строго при принятии
        if payload is None:
            return render(request, "tenant/team_join.html", {"invalid": True}, status=404)
        if user is None:
            user = get_user_model().objects.create_user(
                username=payload["email"], email=payload["email"], password=pw1
            )
        elif needs_password:
            user.set_password(pw1)
            user.save(update_fields=["password"])
        Membership.objects.get_or_create(user=user, defaults={"role": payload["role"]})
        audit_event(
            action="team.join",
            resource_type="membership",
            resource_id=str(user.pk),
            actor=user,
        )
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("dashboard")

    return render(
        request,
        "tenant/team_join.html",
        {"email": payload["email"], "needs_password": needs_password},
    )
