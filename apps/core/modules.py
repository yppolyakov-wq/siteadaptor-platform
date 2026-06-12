"""Реестр модулей кабинета (Track D / D0a) — только код, без таблиц.

Каждый функциональный блок кабинета — ModuleSpec: пункты навигации, URL-префиксы
(гейтинг), зависимости и рекомендации по вертикали (D0b). Приложения остаются в
TENANT_APPS — тумблер переключает видимость/доступ, а не загружает код (решение
владельца 2026-06-11: реестр + feature-flags, не рантайм-плагины).

Два смысла включённости, разведены:
- ``Tenant.enabled_modules`` — entitlement (что разрешает тариф), пишет биллинг;
- ``Tenant.disabled_modules`` — выбор владельца (что он сам выключил). Храним
  «выключенное», а не «включённое»: новый модуль появляется у всех сразу.

Активно = (entitlement ∩ реестр) − disabled, с двумя уточнениями к ТЗ:
- core-модули активны всегда (выключить нельзя);
- entitlement применяется только к ``premium``-модулям. Существующие тенанты
  созданы с enabled_modules=["catalog","promotions","publishing"] — строгое
  пересечение молча выключило бы им loyalty/analytics/crm. Пока premium-модулей
  нет, формула совпадает с ТЗ; когда биллинг начнёт продавать модули — помечаем
  их premium=True, и enabled_modules заработает как настоящий entitlement.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class NavItem:
    url_name: str
    label: str  # lazy-строка (msgid совпадает с прежним хардкодом nav)
    nav_key: str  # подсветка активного пункта ({{ nav }} в шаблонах кабинета)


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    label_de: str  # человеческое имя блока (страница «Module», D0b)
    icon: str
    nav_items: tuple[NavItem, ...]
    # Префиксы путей кабинета, принадлежащие модулю. Гейтинг матчит по самому
    # длинному совпавшему префиксу среди ВСЕХ модулей — поэтому loyalty/analytics
    # могут жить внутри /promotions/ со своими более длинными префиксами.
    url_prefixes: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    recommended_for: tuple[str, ...] = ()  # business_type → стартовый набор (D0b)
    core: bool = False  # выключить нельзя, entitlement не применяется
    premium: bool = False  # требует key в Tenant.enabled_modules (тариф)


REGISTRY: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        key="dashboard",
        label_de="Übersicht",
        icon="🏠",
        nav_items=(NavItem("dashboard", _("Dashboard"), "dashboard"),),
        url_prefixes=("/dashboard/",),
        core=True,
    ),
    ModuleSpec(
        key="catalog",
        label_de="Katalog & Import",
        icon="📦",
        nav_items=(
            NavItem("catalog:product-list", _("Catalog"), "catalog"),
            NavItem("catalog:category-list", _("Categories"), "categories"),
            NavItem("imports:start", _("Imports"), "imports"),
        ),
        url_prefixes=("/catalog/", "/imports/"),
        core=True,
    ),
    ModuleSpec(
        key="promotions",
        label_de="Aktionen & Reservierung",
        icon="🏷️",
        nav_items=(
            NavItem("promotions:promotion-list", _("Promotions"), "promotions"),
            NavItem("promotions:reservation-list", _("Reservations"), "reservations"),
            NavItem("promotions:redeem", _("Redeem"), "redeem"),
        ),
        url_prefixes=("/promotions/",),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "other",
        ),
    ),
    ModuleSpec(
        key="crm",
        label_de="Kunden (CRM)",
        icon="👥",
        nav_items=(NavItem("crm:customer-list", _("Customers"), "crm"),),
        url_prefixes=("/crm/",),
        recommended_for=("hotel", "tour_operator"),
    ),
    ModuleSpec(
        key="loyalty",
        label_de="Treue & Gutscheine",
        icon="💝",
        nav_items=(
            NavItem("promotions:voucher-list", _("Vouchers"), "vouchers"),
            NavItem("promotions:loyalty-list", _("Loyalty"), "loyalty"),
        ),
        url_prefixes=("/promotions/vouchers/", "/promotions/loyalty/"),
        depends_on=("promotions",),
        recommended_for=("bakery", "butcher", "grocery", "cafe", "restaurant"),
    ),
    ModuleSpec(
        key="analytics",
        label_de="Auswertung",
        icon="📊",
        nav_items=(NavItem("promotions:analytics", _("Analytics"), "analytics"),),
        url_prefixes=("/promotions/analytics/",),
        depends_on=("promotions",),
    ),
    ModuleSpec(
        key="publishing",
        label_de="Veröffentlichung (Kanäle)",
        icon="📣",
        nav_items=(NavItem("channels", _("Channels"), "channels"),),
        url_prefixes=("/dashboard/channels/",),
    ),
    ModuleSpec(
        key="settings",
        label_de="Einstellungen",
        icon="⚙️",
        nav_items=(
            NavItem("site", _("Site"), "site"),
            NavItem("settings", _("Settings"), "settings"),
            NavItem("domains", _("Domains"), "domains"),
        ),
        url_prefixes=("/dashboard/site/", "/dashboard/settings/", "/dashboard/domains/"),
        core=True,
    ),
    ModuleSpec(
        key="billing",
        label_de="Abo & Zahlung",
        icon="💳",
        nav_items=(NavItem("billing", _("Billing"), "billing"),),
        url_prefixes=("/dashboard/billing/",),
        core=True,
    ),
)

_BY_KEY = {spec.key: spec for spec in REGISTRY}


def get_module(key: str) -> ModuleSpec | None:
    return _BY_KEY.get(key)


def is_entitled(tenant, spec: ModuleSpec) -> bool:
    """Разрешает ли тариф модуль (core и не-premium — всегда)."""
    if spec.core or not spec.premium:
        return True
    return spec.key in (tenant.enabled_modules or [])


def is_module_active(tenant, key: str) -> bool:
    """Активно = (entitlement ∩ реестр) − disabled; core — всегда; deps — рекурсивно."""
    spec = _BY_KEY.get(key)
    if spec is None:
        return False
    if spec.core:
        return True
    if not is_entitled(tenant, spec):
        return False
    if key in (tenant.disabled_modules or []):
        return False
    return all(is_module_active(tenant, dep) for dep in spec.depends_on)


def active_modules(tenant) -> list[ModuleSpec]:
    return [spec for spec in REGISTRY if is_module_active(tenant, spec.key)]


def module_for_path(path: str) -> ModuleSpec | None:
    """Модуль-владелец пути кабинета: самый длинный совпавший префикс.

    Витрина/аккаунты/health ни одному модулю не принадлежат → None (гейтинг
    их не трогает).
    """
    best: ModuleSpec | None = None
    best_len = 0
    for spec in REGISTRY:
        for prefix in spec.url_prefixes:
            if path.startswith(prefix) and len(prefix) > best_len:
                best, best_len = spec, len(prefix)
    return best
