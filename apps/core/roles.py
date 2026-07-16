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
