"""W9-10 (Р-7, аудит 2026-08-05): «Team & Zugriff» — членства/роли + инвайт.

БЕЗ миграции: приглашение = одноразовый Redis-токен (TTL 7 дней, неймспейс по
схеме — паттерн magic-link CA1), принятие на публичном пути
/team/beitreten/<token>/ создаёт User+Membership и логинит.

Ролевой гейт HTTP-слоя — CabinetOwnerAccessMiddleware (owner-only префиксы:
Abo/Recht/Team): «пригласить сотрудника» не означает «отдать бизнес». Прямые
вызовы вьюх в тестах middleware обходят — реальный трафик закрыт fail-closed.

KA-12 E6.7c-3: все записи членств — через ``apps.core.perm_grants`` (единственный
писатель): роль, отзыв, права; инвайт v2 несёт приглашающего и права и при принятии
перепроверяет их под блокировкой (приглашающий удалён/понижен → инвайт недействителен).
Каждое действие проверяет права САМО, не полагаясь только на middleware.
"""

import hashlib
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import perm_grants, perm_ui, ratelimit
from apps.core import permissions as P
from apps.core.audit import audit_event
from apps.core.models import Membership

INVITE_TTL = 7 * 24 * 3600  # сек; ссылка-приглашение живёт неделю
INVITE_ROLES = (Membership.ROLE_ADMIN, Membership.ROLE_STAFF)  # owner НЕ приглашается
INVITE_RATE = (20, 24 * 3600)  # выпусков на бизнес в сутки
JOIN_RATE = (10, 3600)  # попыток принятия с одного IP в час


def _token_key(token: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"team_invite:{connection.schema_name}:{digest}"


def issue_invite(email: str, role: str, inviter=None, perms=None) -> str | None:
    """Одноразовый токен приглашения (None — некорректные входные или нет права).

    С ``inviter`` — payload v=2 (приглашающий + права, перепроверяются при принятии);
    admin приглашает только staff и только с правами из своей области выдачи.
    Без ``inviter`` — легаси-форма (только пресет роли)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or role not in INVITE_ROLES:
        return None
    payload = {"email": email, "role": role}
    if inviter is not None:
        try:
            granted = perm_grants.invite_perms(inviter, role, perms)
        except perm_grants.PermsDenied:
            return None
        member = Membership.objects.filter(user=inviter).first()
        payload.update({"v": 2, "inviter_pk": str(member.pk), "perms": sorted(granted)})
    token = secrets.token_urlsafe(32)
    cache.set(_token_key(token), payload, INVITE_TTL)
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


def _mask(email: str) -> str:
    """«a***@b.de» — e-mail коллег видит только тот, кто правит команду (B4)."""
    local, _sep, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _member_rows(can_see_emails: bool, actor=None):
    """Строки участников; с ``actor`` — формы прав (E6.7d) и флаги роль/удаление."""
    members = list(Membership.objects.select_related("user").order_by("role", "user__username"))
    owners = sum(1 for m in members if m.role == Membership.ROLE_OWNER)
    actor_eff = P.effective_from(actor.role, actor.permissions) if actor else frozenset()
    rows = []
    for m in members:
        email = m.user.email or m.user.username
        is_last_owner = m.role == Membership.ROLE_OWNER and owners <= 1
        own = actor is not None and actor.pk == m.pk
        is_owner_actor = actor is not None and actor.role == Membership.ROLE_OWNER
        rows.append(
            {
                "m": m,
                "email": email if can_see_emails else _mask(email),
                "is_last_owner": is_last_owner,
                "is_self": own,
                "can_role": is_owner_actor and not own and not is_last_owner,
                "can_revoke": not own
                and not is_last_owner
                and (
                    is_owner_actor
                    or ("team.delete" in actor_eff and m.role == Membership.ROLE_STAFF)
                ),
                "perm_form": perm_ui.perm_form(actor, m),
            }
        )
    return rows


_DENIED_TEXT = {
    "last_owner": gettext_lazy("Der letzte Inhaber kann nicht entfernt werden."),
    "self": gettext_lazy("Sich selbst entfernen ist nicht möglich."),
    "stale": gettext_lazy("Die Rechte wurden inzwischen geändert — bitte Seite neu laden."),
    "scope": gettext_lazy("Diese Änderung liegt außerhalb Ihres Bereichs."),
}


@login_required
def team_view(request):
    """Список членств + смена роли + отзыв + инвайт. Owner-only (middleware)."""
    perms = P.effective(request.user)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if "team.edit" not in perms:
            messages.error(request, _("Keine Berechtigung."))
        elif action == "invite":
            if ratelimit.hit(
                "team-invite", connection.schema_name, limit=INVITE_RATE[0], window=INVITE_RATE[1]
            ):
                messages.error(request, _("Zu viele Einladungen heute — bitte morgen erneut."))
                return redirect("team")
            role = request.POST.get("role", "")
            perms_in = None
            if role in INVITE_ROLES and request.POST.get(f"perms_present_{role}") == "1":
                perms_in = request.POST.getlist(f"perm_{role}")
            token = issue_invite(
                request.POST.get("email"), role, inviter=request.user, perms=perms_in
            )
            if token is None:
                ratelimit.refund("team-invite", connection.schema_name)
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
        elif action in ("role", "revoke", "perms"):
            _member_action(request, action)
            if action == "perms" and perm_grants._uuid(request.POST.get("membership_id")):
                anchor = perm_grants._uuid(request.POST.get("membership_id"))
                return redirect(f"{reverse('team')}#m-{anchor}")
        return redirect("team")

    actor = Membership.objects.filter(user=request.user).first()
    can_edit = "team.edit" in perms
    invite_forms = perm_ui.invite_forms(actor) if can_edit else []
    return render(
        request,
        "tenant/team.html",
        {
            "nav": "team",
            "rows": _member_rows(can_edit, actor if can_edit else None),
            "can_edit": can_edit,
            "invite_forms": invite_forms,
            "roles": Membership.ROLES,
            "invite_roles": [(f["role"], f["label"]) for f in invite_forms],
        },
    )


def _member_action(request, action):
    """Роль / отзыв / права — только через perm_grants (проверка прав и цели внутри)."""
    member_pk = request.POST.get("membership_id")
    try:
        if action == "revoke":
            perm_grants.revoke_member(request.user, member_pk)
            messages.success(request, _("Zugriff entzogen."))
        elif action == "role":
            perm_grants.set_member_role(request.user, member_pk, request.POST.get("role", ""))
            messages.success(request, _("Rolle geändert."))
        elif request.POST.get("perms_present") == "1":
            perm_grants.set_member_permissions(
                request.user,
                member_pk,
                request.POST.getlist("perm"),
                expected=request.POST.get("perms_state") or None,
            )
            messages.success(request, _("Rechte gespeichert."))
    except perm_grants.PermsDenied as exc:
        if exc.reason == "last_owner" and action == "role":
            text = _("Der letzte Inhaber kann nicht herabgestuft werden.")
        elif exc.reason in _DENIED_TEXT:
            text = _DENIED_TEXT[exc.reason]
        else:
            text = _("Mitglied nicht gefunden.")  # один ответ на чужое/мусор/нет права
        messages.error(request, text)


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
    (одноразовость). E6.7c-3 (ревью): для СУЩЕСТВУЮЩЕГО аккаунта ссылка не даёт ни
    входа, ни пароля — сначала вход этим аккаунтом (иначе держатель ссылки — в т.ч.
    сам приглашающий — входил бы в чужой аккаунт или задавал ему пароль)."""
    payload = peek_invite(token)
    if payload is None:
        return render(request, "tenant/team_join.html", {"invalid": True}, status=404)
    email = payload["email"]
    user = (
        get_user_model()
        .objects.filter(Q(username__iexact=email) | Q(email__iexact=email))
        .order_by("pk")
        .first()
    )
    if user is not None and Membership.objects.filter(user=user).exists():
        return render(request, "tenant/team_join.html", {"already_member": True})
    if user is not None and getattr(request.user, "pk", None) != user.pk:
        return render(request, "tenant/team_join.html", {"needs_login": True, "email": email})
    needs_password = user is None

    if request.method == "POST":
        if ratelimit.hit(
            "team-join", ratelimit.client_ip(request), limit=JOIN_RATE[0], window=JOIN_RATE[1]
        ):
            return render(request, "tenant/team_join.html", {"invalid": True}, status=429)
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
        try:
            with transaction.atomic():  # отказ приглашающего — без «пустого» User
                if user is None:
                    user = get_user_model().objects.create_user(
                        username=payload["email"], email=payload["email"], password=pw1
                    )
                perm_grants.join_from_invite(user, payload)
        except perm_grants.PermsDenied as exc:
            perm_grants.audit_join_denied(payload, exc.reason)
            return render(request, "tenant/team_join.html", {"invalid": True}, status=404)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("dashboard")

    return render(
        request,
        "tenant/team_join.html",
        {"email": payload["email"], "needs_password": needs_password},
    )
