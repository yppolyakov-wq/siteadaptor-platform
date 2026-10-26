"""T-8.32a: пакет бизнеса по направлению — одна точка истины «что ему доступно».

План docs/t8-32ab-package-gate-plan-2026-10-23.md (решения KA-3 §2–§4).

Пакет пока ВЫВОДИТСЯ из профиля витрины (`site_config["profile"]`, T-8.1/T-8.27d):
«Nur Aktionen» → aktionen, «Nur Eintrag» → eintrag, иначе laden. Свой ключ
`site_config["package"]` появится вместе с переключением пакетов (T-8.32d).

Профиль прятал только входы в каталог, а модули не ограничивал: быстрый старт включает
пресет вертикали, и лёгкий бизнес получал блог («Neuigkeiten»), ЛК клиента, CRM.
Потолок модулей пакета действует внутри `modules.is_module_active` — значит гаснут сразу
меню, адреса (404 через ModuleGatingMiddleware), секции, плитки и фоновые задачи.

Дубль «Angebote» в шапке лёгкой витрины (легаси-пункт → главная) гасит
`menu.resolve_menu`, если меню выведено из легаси-nav.

Читает только `site_config`, без БД: функция зовётся сотни раз за запрос. Любая ошибка —
пакет laden (fail-open: полный бизнес не теряет доступ к своему кабинету)."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

AKTIONEN = "aktionen"
EINTRAG = "eintrag"
LADEN = "laden"


@dataclass(frozen=True)
class Package:
    key: str
    label: str
    lite: bool
    #: Потолок НЕобязательных модулей; None — без потолка. Core-модули не ограничиваются.
    modules: frozenset[str] | None
    #: T-8.32b: экраны кабинета, открытые пакету (view_name или префикс «…*»);
    #: None — весь кабинет. Остальное — страница «In Ihrem Paket nicht enthalten».
    cabinet_allow: frozenset[str] | None = None


#: Модули ступени «Aktionen»: акции, чат с клиентом (решение владельца — остаётся),
#: заявки по акции («Anfragen», T-8.2), публикация в каналы и свой Telegram-бот.
#: Отложить/купон живут в движке акций и модуль loyalty не требуют.
_LITE_MODULES = frozenset({"promotions", "inbox", "jobs", "publishing", "telegram"})

#: T-8.32b (KA-3 §3.1): экраны «Aktionen». Товар правится только из акции (Angebot —
#: с Eintrag, В-1); заявки — карточка и новая (список/доска — T-8.32c); касса — отложенное и
#: погашение кода. Ваучеры loyalty/gift, рассылки, кампании, типы, аналитика — вне пакета.
_AKTIONEN_VIEWS = frozenset(
    {
        # Start / Geschäft / Teilen / Sichtbar + служебное
        "dashboard",
        "lite-business",
        "lite-share",
        "lite-visibility",
        "lite-requests",
        "betriebsferien",  # KA-12 О-8: каникулы — и в лёгком пакете
        "legal-docs",
        "owner-confirm-resend",
        "set-cabinet-lang",
        "account_logout",
        "tg-start",
        "tg-lite-info",
        "palette-search",
        # Sichtbar: уведомления, общий и свой Telegram-бот, Google-профиль
        "notifications-settings",
        "platform-bot-connect",
        "platform-bot-disconnect",
        "integrations-telegram-activate",
        "telegram-settings",
        "telegram-connect",
        "telegram-disconnect",
        "gbp-sync",
        "gbp-hours",
        "gbp-location",
        "channels",
        "channel-toggle",
        "channel-config",
        "channel-oauth-start",
        # Aktionen
        "promotions:promotion-list",
        "promotions:promotion-quick",
        "promotions:promotion-quick-done",
        "promotions:promotion-preview",
        "promotions:promotion-flyer",
        "promotions:promotion-transition",
        "promotions:promotion-create",
        "promotions:promotion-edit",
        "promotions:promotion-share",
        "promotions:promotion-feature",  # ★ платное продвижение в каталоге города
        "promotions:promotion-feature-checkout",
        "portal-stats",  # «Besuche aus dem Stadtportal» (владельцу)
        "promotions:promotion-image-delete",
        "promotions:promotion-image-primary",
        "promotions:promotion-text-check",
        "promotions:promotion-text-check-ai",
        "promotions:promotion-text-check-ai-result",
        "promotions:promotion-quick-ai",
        "promotions:promotion-quick-ai-result",
        "promotions:today-dismiss",
        "promotions:shop-poster",
        "promotions:reservation-list",
        "promotions:reservation-action",
        "promotions:redeem",
        "promotions:redeem-detail",
        "promotions:redeem-action",
        # товар — только правка из акции
        "catalog:product-edit",
        "catalog:product-image-delete",
        "catalog:product-image-primary",
        "catalog:variant-*",
        "catalog:modifier-*",
        # Kunden & Nachrichten (без Sofort-Angebot: он создаёт заказ — продажа вне пакета)
        "inbox:list",
        "inbox:thread",
        "inbox:thread-poll",
        "inbox:thread-typing",
        "inbox:unread-count",
        "inbox:reply-draft",
        "inbox:reply-draft-result",
        # заявки по акции
        "jobs:detail",
        "jobs:new",
        "jobs:pdf",
        "jobs:protocol-pdf",
        "jobs:invoice-pdf",
        "jobs:delete",
    }
)
_EINTRAG_VIEWS = _AKTIONEN_VIEWS | {
    "sellable-manage",
    "sellable-visibility",
    "sellable-sold-out",  # KA-12 E3.4
    "sortiment-view",
    "catalog:product-create",
    "catalog:product-delete",
    "imports:website",
    "imports:website-*",
}

PACKAGES: dict[str, Package] = {
    AKTIONEN: Package(AKTIONEN, _("Aktionen"), True, _LITE_MODULES, _AKTIONEN_VIEWS),
    EINTRAG: Package(EINTRAG, _("Eintrag"), True, _LITE_MODULES, _EINTRAG_VIEWS),
    LADEN: Package(LADEN, _("Laden"), False, None),
}


def _config(tenant) -> dict:
    cfg = getattr(tenant, "site_config", None)
    return cfg if isinstance(cfg, dict) else {}


def package_of(tenant) -> Package:
    """Пакет бизнеса. Без тенанта и при мусоре — laden."""
    if tenant is None:
        return PACKAGES[LADEN]
    try:
        profile = _config(tenant).get("profile") or ""
    except Exception:  # noqa: BLE001 — пакет не должен ронять запрос
        return PACKAGES[LADEN]
    return PACKAGES[profile] if profile in (AKTIONEN, EINTRAG) else PACKAGES[LADEN]


def module_allowed(tenant, key: str) -> bool:
    """Разрешает ли пакет модуль. Core-модули проверяет вызывающий (is_module_active)."""
    ceiling = package_of(tenant).modules
    return ceiling is None or key in ceiling


def view_allowed(tenant, view_name: str) -> bool:
    """Открыт ли экран кабинета пакету. «префикс-*» — только с разделителем «-»
    (`catalog:variant-*`), без голых строковых префиксов. Безымянный экран у лёгкого
    пакета закрыт (сегодня таких под кабинетом нет — замок)."""
    allow = package_of(tenant).cabinet_allow
    if allow is None:
        return True
    if not view_name:
        return False
    if view_name in allow:
        return True
    return any(p.endswith("-*") and view_name.startswith(p[:-1]) for p in allow)
