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


#: Модули ступени «Aktionen»: акции, чат с клиентом (решение владельца — остаётся),
#: заявки по акции («Anfragen», T-8.2), публикация в каналы и свой Telegram-бот.
#: Отложить/купон живут в движке акций и модуль loyalty не требуют.
_LITE_MODULES = frozenset({"promotions", "inbox", "jobs", "publishing", "telegram"})

PACKAGES: dict[str, Package] = {
    AKTIONEN: Package(AKTIONEN, _("Aktionen"), True, _LITE_MODULES),
    EINTRAG: Package(EINTRAG, _("Eintrag"), True, _LITE_MODULES),
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
