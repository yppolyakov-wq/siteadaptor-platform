"""KA-12 E6.7c-2: единственный писатель прав и ролей команды.

План — docs/ka-12-e6-7c-perm-storage-plan-2026-10-25.md (+ ревью безопасности).
Все изменения — в одной транзакции под блокировкой ВСЕХ строк Membership схемы в
одном порядке (pk): так гонки «два владельца понижают друг друга» и «admin
понижен, пока выдаёт» невозможны, а порядок замков един (без взаимных блокировок).

Правила выдачи (§3, §15.3, Р-c2/Р-c3):
- owner правит всех, кроме себя; роли меняет только owner;
- admin с ``team.edit`` правит только staff: выдаёт ключи из своих прав БЕЗ
  чувствительных, отзывает в пределах своих прав; ключи вне его области не трогает;
- свои права не меняет никто; запись в журнал обязательна (без неё — откат).
"""

import hashlib
import logging
import uuid
from types import SimpleNamespace

from django.db import connection, transaction

from . import permissions as P
from .models import Membership

logger = logging.getLogger(__name__)

OWNER, ADMIN, STAFF = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF

# A.7: о выдаче этих прав не-владельцем владелец узнаёт письмом.
OWNER_ALERT_KEYS = P.SENSITIVE | frozenset(
    {"finanzen.berichte", "finanzen.journal", "finanzen.edit", "kunden.edit"}
)


class PermsDenied(Exception):
    """Отказ. ``reason`` — машинный код; текст для человека — общий (без оракула)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _uuid(raw):
    try:
        return uuid.UUID(str(raw or "").strip())
    except ValueError:
        return None


def _lock_all() -> dict:
    """Все строки Membership схемы под блокировкой, одним запросом в порядке pk."""
    return {
        m.pk: m
        for m in Membership.objects.select_for_update(of=("self",))
        .select_related("user")
        .order_by("pk")
    }


def _rows_for(actor_user, member_pk):
    """(actor_row, target_row) под блокировкой или PermsDenied."""
    target_pk = _uuid(member_pk)
    if target_pk is None or getattr(actor_user, "pk", None) is None:
        raise PermsDenied("not_found")
    rows = _lock_all()
    actor = next((m for m in rows.values() if m.user_id == actor_user.pk), None)
    target = rows.get(target_pk)
    if actor is None or target is None:
        raise PermsDenied("not_found")
    if actor.pk == target.pk:
        raise PermsDenied("self")
    return actor, target, rows


def _scopes(actor, target):
    """(grant_scope, revoke_scope) актора для цели — права актора из ЗАБЛОКИРОВАННОЙ строки."""
    if target.role == OWNER:
        raise PermsDenied("target_owner")
    if actor.role == OWNER:
        everything = frozenset(P.PERMS)
        return everything, everything
    if actor.role == ADMIN:
        eff = P.effective_from(actor.role, actor.permissions)
        if "team.edit" not in eff:
            raise PermsDenied("no_team_edit")
        if target.role != STAFF:
            raise PermsDenied("target_not_staff")
        return eff - P.SENSITIVE, eff
    raise PermsDenied("actor_role")


def _with_requires(keys) -> set:
    """Отметка «edit» тянет «view» (вверх по requires)."""
    out, stack = set(), [k for k in keys if k in P.PERMS]
    while stack:
        key = stack.pop()
        if key in out:
            continue
        out.add(key)
        stack.extend(P.PERMS[key].requires)
    return out


def _audit(action, target, actor_user, changes):
    from apps.audit.services import audit_event

    with transaction.atomic():  # свой savepoint; ошибка журнала откатывает всю выдачу
        audit_event(
            action=action,
            resource_type="membership",
            resource_id=str(target.pk),
            actor=actor_user,
            changes=changes,
            strict=True,
        )


def _audit_denied(member_pk, actor_user, reason):
    """Отказ — в журнал ВНЕ откатываемой транзакции выдачи (иначе запись исчезнет)."""
    from apps.audit.services import audit_event

    if reason == "not_found":
        logger.info("perm_grants: denied (not_found)")
        return  # мусорный pk — не шум в журнале
    try:
        with transaction.atomic():
            audit_event(
                action="team.perms_denied",
                resource_type="membership",
                resource_id=str(_uuid(member_pk) or ""),
                actor=actor_user,
                changes={"reason": reason},
            )
    except Exception:  # noqa: BLE001 — отказ остаётся отказом, а не ошибкой БД
        logger.exception("perm_grants: denial audit not written (%s)", reason)


def _audited(fn):
    """Обёртка: PermsDenied, брошенный внутри транзакции, журналируется после отката."""

    def wrapper(actor_user, member_pk, *args, **kwargs):
        try:
            return fn(actor_user, member_pk, *args, **kwargs)
        except PermsDenied as exc:
            _audit_denied(member_pk, actor_user, exc.reason)
            raise

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def state_token(eff) -> str:
    """Отпечаток набора прав — форма шлёт его, чтобы не затереть чужую правку (lost update)."""
    return hashlib.sha256(",".join(sorted(eff)).encode()).hexdigest()[:16]


# E6.7f заполнит реестр шаблонов; неизвестное имя не хранится (не подписать staff чужим шаблоном).
TEMPLATE_KEYS: frozenset = frozenset()


@_audited
def set_member_permissions(
    actor_user, member_pk, requested_keys, template: str = "", expected: str | None = None
) -> frozenset:
    """Записать права участника. Возвращает его новые эффективные права.
    ``expected`` — ``state_token`` прав цели на момент открытия формы (иначе отказ "stale")."""
    with transaction.atomic():
        actor, target, _rows = _rows_for(actor_user, member_pk)
        grant_scope, revoke_scope = _scopes(actor, target)
        role = target.role
        old = P.effective_from(role, target.permissions)
        if expected is not None and expected != state_token(old):
            raise PermsDenied("stale")
        requested = _with_requires(requested_keys or ())
        # Запрошенное сверх текущего обязано быть в области выдачи — иначе отказ,
        # а не тихое выбрасывание ключа (актор должен видеть, что не выдал).
        if ((requested - old) & P.ROLE_LIMIT[role]) - grant_scope:
            raise PermsDenied("scope")
        new = P._closure(((old - revoke_scope) | (requested & revoke_scope)) & P.ROLE_LIMIT[role])
        added = new - old
        # Замыкание после отзыва может уронить ключ вне области актора (X требует R,
        # R снят) — это тоже «тронуть чужое», отказ.
        if added - grant_scope or (old - new) - revoke_scope:
            raise PermsDenied("scope")
        if template not in TEMPLATE_KEYS:
            template = ""
        preset = P.PRESETS[role]
        delta = P.normalize_permissions(
            role,
            {"add": sorted(new - preset), "remove": sorted(preset - new), "template": template},
        )
        if delta == target.permissions:  # сырое сравнение: повреждённое хранение чинится записью
            return new
        target.permissions = delta
        target.save(update_fields=["permissions", "updated_at"])
        _audit(
            "team.perms",
            target,
            actor_user,
            {
                "before": sorted(old),
                "after": sorted(new),
                "added": sorted(added),
                "removed": sorted(old - new),
                "template": delta.get("template", ""),
                "actor_role": actor.role,
            },
        )
        if actor.role != OWNER and added & OWNER_ALERT_KEYS:
            transaction.on_commit(
                lambda: _alert_owner(actor_user, target, added & OWNER_ALERT_KEYS, new)
            )
    P.forget(actor_user)
    P.forget(target.user)
    return new


@_audited
def set_member_role(actor_user, member_pk, role: str) -> None:
    """Сменить роль участника — только владелец; последний владелец защищён."""
    if role not in (OWNER, ADMIN, STAFF):
        raise PermsDenied("bad_role")
    with transaction.atomic():
        actor, target, rows = _rows_for(actor_user, member_pk)
        if actor.role != OWNER:
            raise PermsDenied("actor_role")
        if role == target.role:
            return
        owners = sum(1 for m in rows.values() if m.role == OWNER)
        if target.role == OWNER and owners <= 1:
            raise PermsDenied("last_owner")
        before = target.role
        target.role = role
        # Дельта переносится на новую роль (лишнее для роли вырезается normalize).
        old_eff = P.effective_from(before, target.permissions)
        # Понижение владельца — ровно пресет новой роли (иначе «admin» = совладелец).
        keep = before != OWNER and role != OWNER
        target.permissions = _delta_for(role, old_eff) if keep else {}
        target.save(update_fields=["role", "permissions", "updated_at"])
        _audit("team.role", target, actor_user, {"role": role, "before": before})
    P.forget(target.user)


def _delta_for(role, eff) -> dict:
    """Дельта, при которой у роли ``role`` остаются права ``eff`` (в пределах её лимита).
    Понижение admin → staff: всё, чего у staff не бывает, отпадает само."""
    if role not in P.PRESETS:
        return {}
    preset = P.PRESETS[role]
    eff = frozenset(eff) & P.ROLE_LIMIT[role]
    return P.normalize_permissions(
        role, {"add": sorted(eff - preset), "remove": sorted(preset - eff)}
    )


@_audited
def revoke_member(actor_user, member_pk) -> None:
    """Отозвать доступ. Owner — любого, кроме последнего владельца; admin с
    ``team.delete`` — только staff. Себя — никто."""
    with transaction.atomic():
        actor, target, rows = _rows_for(actor_user, member_pk)
        if actor.role == OWNER:
            owners = sum(1 for m in rows.values() if m.role == OWNER)
            if target.role == OWNER and owners <= 1:
                raise PermsDenied("last_owner")
        elif actor.role == ADMIN:
            eff = P.effective_from(actor.role, actor.permissions)
            if "team.delete" not in eff or target.role != STAFF:
                raise PermsDenied("revoke_scope")
        else:
            raise PermsDenied("actor_role")
        _audit("team.revoke", target, actor_user, {"role": target.role})
        target_user = target.user
        target.delete()  # User остаётся (история/повторный инвайт)
    P.forget(target_user)


def _alert_owner(actor_user, target, keys, new) -> None:
    """Письмо владельцу: не-владелец выдал чувствительные права (A.7). Без данных
    клиентов и без e-mail участника; дедуп по состоянию (повтор того же набора — без письма)."""
    try:
        from django.utils import translation
        from django.utils.translation import gettext as _

        from apps.notifications.services import email_locale, notify

        tenant = getattr(connection, "tenant", None)
        recipient = (getattr(tenant, "owner_email", "") or "").strip()
        if not recipient:
            owner = (
                Membership.objects.filter(role=OWNER, user__is_active=True)
                .exclude(user__email="")
                .select_related("user")
                .order_by("pk")
                .first()
            )
            recipient = owner.user.email if owner else ""
        if not recipient:
            logger.error("perm_grants: no recipient for the owner alert")
            return
        state = hashlib.sha256(",".join(sorted(new)).encode()).hexdigest()[:12]
        who = getattr(actor_user, "get_full_name", lambda: "")() or actor_user.get_username()
        whom = target.user.get_full_name() or target.user.get_username().split("@")[0]
        with translation.override(email_locale()):
            subject = _("Neue Rechte im Team vergeben")
            body = _(
                "%(who)s hat %(whom)s neue Rechte gegeben: %(keys)s. "
                "Sie können das unter „Team & Zugriff“ prüfen und ändern."
            ) % {"who": who, "whom": whom, "keys": ", ".join(sorted(keys))}
        notify(
            dedupe_key=f"perms:{connection.schema_name}:{target.pk}:{state}",
            type="team_perms_owner",
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception:  # noqa: BLE001 — письмо не должно ронять выдачу
        logger.error("perm_grants: owner alert not sent", exc_info=True)


# --- E6.7c-3: инвайт v2 ---------------------------------------------------------------------


def _invite_compute(inviter, role, requested_keys):
    """(новые права, срезанные ключи) нового участника роли ``role`` от ``inviter``.
    Тот же расчёт, что у правки: база — пресет роли, выдать — только из области выдачи."""
    if role not in (ADMIN, STAFF):
        raise PermsDenied("bad_role")
    grant_scope, revoke_scope = _scopes(inviter, SimpleNamespace(role=role))
    old = P.for_role(role)
    if requested_keys is None:
        return old, frozenset()
    limit = P.ROLE_LIMIT[role]
    requested = _with_requires(requested_keys) & limit
    new = P._closure(((old - revoke_scope) | (requested & revoke_scope)) & limit)
    out = (new - old) - grant_scope
    if out:
        new = P._closure(new - out)
    return new, frozenset(requested - new)


def check_invite(inviter_user, role, requested_keys=None) -> None:
    """Проверка при выпуске: приглашающий вправе выдать роль и ВСЕ запрошенные ключи."""
    inviter = (
        Membership.objects.filter(user_id=getattr(inviter_user, "pk", None)).first()
        if getattr(inviter_user, "pk", None)
        else None
    )
    if inviter is None:
        raise PermsDenied("not_found")
    _new, stripped = _invite_compute(inviter, role, requested_keys)
    if stripped:
        raise PermsDenied("scope")


def join_from_invite(user, payload) -> tuple[Membership, dict]:
    """Членство по инвайту под блокировкой: приглашающий перечитывается, лишнее срезается.

    v=2: приглашающего нет/он больше не вправе → PermsDenied("inviter") (членство не
    создаётся). Легаси (без ``v``): только пресет роли (Р-c5). Возвращает (членство, аудит).
    """
    role = payload.get("role")
    if role not in (ADMIN, STAFF):
        raise PermsDenied("bad_role")
    info = {"role": role, "legacy": False, "stripped": []}
    with transaction.atomic():
        rows = _lock_all()
        if any(m.user_id == user.pk for m in rows.values()):
            raise PermsDenied("already_member")
        if payload.get("v") == 2:
            inviter = rows.get(_uuid(payload.get("inviter_pk")))
            if inviter is None:
                raise PermsDenied("inviter")
            try:
                eff, stripped = _invite_compute(inviter, role, payload.get("perms"))
            except PermsDenied as exc:
                raise PermsDenied("inviter") from exc
            info["stripped"] = sorted(stripped)
            info["inviter"] = str(inviter.pk)
            delta = _delta_for(role, eff)
        else:
            info["legacy"] = True
            delta = {}
        member = Membership.objects.create(user=user, role=role, permissions=delta)
        _audit("team.join", member, user, info)
    return member, info
