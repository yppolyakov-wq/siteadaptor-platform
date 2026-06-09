"""Тарифы и маппинг тариф → функциональные модули.

Пока один платный тариф (Standard, 39 €/мес). `enabled_modules` на Tenant
определяет доступ к блокам платформы; активная подписка включает полный набор,
а suspended/trial_expired гейтятся middleware (запись off, данные не трогаем).
Расширяется добавлением Price → тариф без изменения вызывающего кода.
"""

# Полный набор функциональных модулей платформы.
ALL_MODULES = ["catalog", "promotions", "publishing", "aggregator"]

# Единственный платный тариф на сейчас.
TIER_STANDARD = "standard"

# Тариф → включаемые модули.
TIER_MODULES = {
    TIER_STANDARD: ALL_MODULES,
}


def modules_for_tier(tier: str = TIER_STANDARD) -> list[str]:
    """Модули для тарифа (по умолчанию — Standard)."""
    return list(TIER_MODULES.get(tier, ALL_MODULES))


def tier_for_price(price_id: str) -> str:
    """Stripe Price ID → внутренний тариф.

    Сейчас один Price соответствует Standard; неизвестный price тоже мапим в
    Standard (единственный платный план), чтобы оплата всегда включала доступ.
    """
    return TIER_STANDARD
