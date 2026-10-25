"""KA-12 E6.7c-4: ЗАМОРОЖЕННЫЙ эталон ролевых гейтов до перехода на права.

Префиксы и декораторы сняты из кода (доступ задаёт ``apps.core.view_perms``); здесь —
их последний вид, чтобы паритет «пустые права = вчерашний доступ» проверялся и дальше.
Не править: новый экран регистрируется в view_perms, а не здесь.
"""

# W9-10 / KA-H11 / KA-D7: какие пути кабинета закрыты ролью. Единственный источник —
# его читают CabinetOwnerAccessMiddleware и замки E11.2 (обход экранов сотрудником).
LEGACY_OWNER_ONLY_PREFIXES = (
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
LEGACY_FINANCE_EXPORT_PREFIXES = (
    "/dashboard/finance/export.csv",
    "/dashboard/finance/datev.csv",
    "/dashboard/finance/ausgaben/datev.csv",
)

ROLE_OWNER_ONLY = "owner"
ROLE_FINANCE = "finance"


def legacy_role_for_path(path: str) -> str:
    """Какую роль требует путь кабинета: "owner", "finance" (owner+admin) или ""."""
    if path.startswith(LEGACY_OWNER_ONLY_PREFIXES):
        return ROLE_OWNER_ONLY
    if path.startswith(LEGACY_FINANCE_EXPORT_PREFIXES):
        return ROLE_FINANCE
    return ""


# Вьюхи под @owner_required / @finance_export_required до E6.7c-4 (имя маршрута → роль).
LEGACY_DECORATED = {
    "crm:customer-export": ROLE_OWNER_ONLY,
    "crm:customer-dsgvo": ROLE_OWNER_ONLY,
    "crm:customer-dsgvo-export": ROLE_OWNER_ONLY,
    "crm:customer-dsgvo-erase": ROLE_OWNER_ONLY,
    "finance:bank": ROLE_OWNER_ONLY,
    "finance:expenses-datev": ROLE_FINANCE,
    "finance:export-csv": ROLE_FINANCE,
    "finance:export-datev": ROLE_FINANCE,
    "stays:reports-export": ROLE_OWNER_ONLY,
    "stays:meldescheine-export": ROLE_OWNER_ONLY,  # KA-12 Z-6: персональные данные
    "events:roster-csv": ROLE_OWNER_ONLY,
    "lite-business": ROLE_OWNER_ONLY,
    "legal-docs": ROLE_OWNER_ONLY,
    "verkaeufe-export": ROLE_OWNER_ONLY,
    "betriebsferien": ROLE_OWNER_ONLY,
}
