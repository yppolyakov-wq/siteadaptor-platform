"""Роли пользователя в тенанте (M6 / master-plan §7, шов multi-user).

Единая точка определения роли и доступа к кабинету. Членство живёт в схеме
бизнеса (`django.contrib.auth` — TENANT_APP), поэтому наличие строки `Membership`
в ТЕКУЩЕЙ схеме = пользователь принадлежит этому тенанту.

Гейтинг кабинета — fail-closed: без явной `Membership` доступа к кабинету нет
(`has_cabinet_access` → False, `role_of` → ''). Легаси-владельцы без строки
Membership бэкфилятся миграцией `core/0006` (по одному Owner на схему).
"""

from .models import Membership

# W9-10 / KA-H11 / KA-D7: какие пути кабинета закрыты ролью. Единственный источник —
# его читают CabinetOwnerAccessMiddleware и замки E11.2 (обход экранов сотрудником).
OWNER_ONLY_PREFIXES = (
    "/dashboard/billing/",
    "/dashboard/recht/",
    "/dashboard/settings/team/",
    # KA-12 E4.1a (решение владельца): закрыть весь бизнес на каникулы — только владелец.
    "/dashboard/settings/betriebsferien/",
    "/dashboard/stadtportal/",
    # T-8.27: импорт с сайта — согласие правообладателя даёт только владелец.
    "/imports/website/",
    # Д3 (В-7): каналы публикации пишут во ВНЕШНИЕ профили бизнеса (Google,
    # Facebook…) — подключение, ключи и синхронизация только владельцу.
    "/dashboard/channels/google/",
    "/dashboard/channels/config/",
    "/dashboard/channels/connect/",
    "/dashboard/channels/toggle/",
    # T-8.10h H-3: привязка бизнеса к общему Telegram-боту — только владельцу.
    "/dashboard/settings/notifications/telegram/",
    # T-8.29: включить модуль «свой Telegram-бот» решает владелец.
    "/dashboard/integrationen/telegram-aktivieren/",
    # Ревью T-8.31 (MEDIUM): токен своего бота подменяет бота для клиентов —
    # подключать и отключать может только владелец (экран статуса — всем).
    "/dashboard/telegram/connect/",
    "/dashboard/telegram/disconnect/",
    # KA-H9: имя/адрес/телефон бизнеса лёгкого кабинета — уходят в Impressum и
    # каталог города, менять может только владелец.
    "/dashboard/geschaeft/",
    # KA-H11: выгрузки с персональными данными — только владельцу (вьюхи
    # дополнительно под @owner_required; ростер события — только там, uuid в пути).
    "/crm/export.csv",
    # KA-12 E2.2: CSV продаж (клиенты, e-mail, телефоны).
    "/dashboard/verkaeufe/export.csv",
    "/dashboard/stays/berichte/export.csv",
    # Банковские выписки: имя плательщика, назначение, IBAN.
    "/dashboard/finance/bank/",
    # KA-12 B2-4 (решение P-1): частичный возврат денег — только владелец.
    "/dashboard/erstattung/",
)

# KA-D7: финансовые выгрузки — владельцу и admin (бухгалтер), не staff.
FINANCE_EXPORT_PREFIXES = (
    "/dashboard/finance/export.csv",
    "/dashboard/finance/datev.csv",
    "/dashboard/finance/ausgaben/datev.csv",
)

ROLE_OWNER_ONLY = "owner"
ROLE_FINANCE = "finance"


def required_role_for_path(path: str) -> str:
    """Какую роль требует путь кабинета: "owner", "finance" (owner+admin) или ""."""
    if path.startswith(OWNER_ONLY_PREFIXES):
        return ROLE_OWNER_ONLY
    if path.startswith(FINANCE_EXPORT_PREFIXES):
        return ROLE_FINANCE
    return ""


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


def can_export_finance(user) -> bool:
    """KA-D7 (решение владельца 2026-10-23): финансовые выгрузки (журнал, DATEV) —
    владельцу и роли admin (бухгалтер). Выгрузки клиентов/участников/гостей — нет."""
    return role_of(user) in (Membership.ROLE_OWNER, Membership.ROLE_ADMIN)


def finance_export_required(view):
    """KA-D7: вьюха финансовой выгрузки — owner или admin. Под `@login_required`."""
    from functools import wraps

    from django.http import HttpResponseForbidden
    from django.utils.translation import gettext as _

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not can_export_finance(request.user):
            return HttpResponseForbidden(_("Nur für Inhaber."))
        return view(request, *args, **kwargs)

    wrapper._required_role = ROLE_FINANCE  # E11.2: замок видит гейт без грепа
    return wrapper


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

    wrapper._required_role = ROLE_OWNER_ONLY  # E11.2
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
