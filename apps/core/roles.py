"""Роли пользователя в тенанте (M6 / master-plan §7, шов multi-user).

Единая точка определения роли и доступа к кабинету. Членство живёт в схеме
бизнеса (`django.contrib.auth` — TENANT_APP), поэтому наличие строки `Membership`
в ТЕКУЩЕЙ схеме = пользователь принадлежит этому тенанту.

Гейтинг кабинета — fail-closed: без явной `Membership` доступа к кабинету нет
(`has_cabinet_access` → False, `role_of` → ''). Легаси-владельцы без строки
Membership бэкфилятся миграцией `core/0006` (по одному Owner на схему).
"""

from .models import Membership

# KA-12 E6.7c-4: доступ к экранам задаёт реестр прав ``apps.core.view_perms`` (по имени
# маршрута). Ролевые префиксы сняты; здесь — только пол Inhaber-Vorbehalt (страховка
# middleware до разрешения маршрута): эти разделы не выдаются никому.
OWNER_FLOOR_PREFIXES = (
    "/dashboard/billing/",
    "/dashboard/recht/",
    "/dashboard/geschaeft/",
    "/imports/website/",
)


def _membership(user):
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return None  # аноним или несохранённый пользователь — fail-closed
    # KA-12 E10: строку читают middleware, сайдбар и проверки экранов — 4–5 раз за
    # запрос. Мемо на объекте user (живёт один запрос) с ключом схемы, pk и счётчика
    # изменений членства, как у `permissions.effective`; сброс — `permissions.forget`.
    from .permissions import memo_key

    key = memo_key(user)
    memo = getattr(user, "_cab_membership", None)
    if memo is not None and memo[0] == key:
        return memo[1]
    row = Membership.objects.filter(user=user).first()
    try:
        user._cab_membership = (key, row)
    except AttributeError:  # не настоящий пользователь — без мемо
        pass
    return row


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


def can_edit_policy(user) -> bool:
    """Алиас KA-12 E6.7: право «preise.edit» (правила отмены, тарифы, цены)."""
    from .permissions import has_perm

    return has_perm(user, "preise.edit")


def can_export_finance(user) -> bool:
    """Алиас KA-12 E6.7: право «finanzen.export» (журнал CSV, DATEV)."""
    from .permissions import has_perm

    return has_perm(user, "finanzen.export")


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
