"""Роли пользователя в тенанте (M6 / master-plan §7, шов multi-user).

Единая точка определения роли — чтобы будущий ролевой гейтинг во вьюхах
централизовать здесь, а не размазывать. Сейчас гейтинг не применяется (один
владелец); `role_of` отдаёт owner по умолчанию, поэтому легаси-тенанты без строки
Membership не требуют backfill — единственный пользователь и есть владелец.
"""

from .models import Membership


def role_of(user) -> str:
    """Роль пользователя в текущей схеме тенанта. Аноним → ''; без Membership → owner."""
    if not getattr(user, "is_authenticated", False):
        return ""
    membership = Membership.objects.filter(user=user).first()
    return membership.role if membership else Membership.ROLE_OWNER


def is_owner(user) -> bool:
    return role_of(user) == Membership.ROLE_OWNER
