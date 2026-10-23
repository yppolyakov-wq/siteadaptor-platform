"""Роли пользователя в тенанте (M6 / master-plan §7, шов multi-user).

Единая точка определения роли и доступа к кабинету. Членство живёт в схеме
бизнеса (`django.contrib.auth` — TENANT_APP), поэтому наличие строки `Membership`
в ТЕКУЩЕЙ схеме = пользователь принадлежит этому тенанту.

Гейтинг кабинета — fail-closed: без явной `Membership` доступа к кабинету нет
(`has_cabinet_access` → False, `role_of` → ''). Легаси-владельцы без строки
Membership бэкфилятся миграцией `core/0006` (по одному Owner на схему).
"""

from .models import Membership


def _membership(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(user=user).first()


def role_of(user) -> str:
    """Роль пользователя в текущей схеме тенанта. Нет членства / аноним → ''."""
    membership = _membership(user)
    return membership.role if membership else ""


def has_cabinet_access(user) -> bool:
    """True — пользователь принадлежит текущему тенанту (есть строка Membership).

    Fail-closed: аноним или пользователь без Membership в этой схеме → False.
    Это и есть гейт кабинета поверх `@login_required` (см.
    apps.core.middleware.CabinetOwnerAccessMiddleware).
    """
    return _membership(user) is not None


def is_owner(user) -> bool:
    return role_of(user) == Membership.ROLE_OWNER


def owner_required(view):
    """KA-H11: вьюха только для владельца (выгрузки с персональными данными).

    Ставится ПОД `@login_required`. Прямые вызовы вьюх и пути с uuid посередине
    (`/dashboard/events/<pk>/roster.csv`) middleware не ловит — гейт здесь."""
    from functools import wraps

    from django.http import HttpResponseForbidden
    from django.utils.translation import gettext as _

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_owner(request.user):
            return HttpResponseForbidden(_("Nur für Inhaber."))
        return view(request, *args, **kwargs)

    return wrapper


def audit_export(request, name: str, rows: int, **context) -> None:
    """KA-H11: запись о выгрузке в журнал — кто, что, сколько строк, фильтры.
    Только счётчики и параметры фильтра, никаких персональных данных."""
    from .audit import audit_event

    audit_event(
        action=f"export.{name}",
        resource_type="export",
        resource_id=str(context.pop("resource_id", "")),
        actor=request.user,
        context={"rows": rows, **{k: str(v) for k, v in context.items() if v}},
    )
