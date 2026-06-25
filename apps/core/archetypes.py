"""M20U: «главный товар» по архетипу — primary_item registry.

Единая абстракция «архетип = главный товар»: магазин → товары, ретрит → события,
отель → номера, магазин-без-товаров → акции. Поверх реестра модулей
(`apps.core.modules`), без новых моделей. Используется унифицированной главной/
каталогом, чтобы знать, что выводить первым.
"""

from apps.core import modules

# Ключ модуля-архетипа → секция главной с его «главным товаром».
PRIMARY_SECTION = {
    "catalog": "products",
    "events": "events",
    "stays": "stay_rooms",
    "promotions": "promotions",
}

# Приоритет выбора «главного» архетипа, если storefront_root не задан явно.
_PRIORITY = ["events", "stays", "catalog", "promotions"]

# M20U-5: способ покупки по архетипу — определяет виджет на детальной/листинге.
#   cart    — добавить в корзину (товары → /warenkorb/);
#   booking — бронь/оформление (билеты события, номера: даты → бронь);
#   reserve — резерв акции (промо-бронь);
#   request — заявка/запрос предложения (под заказ).
PURCHASE_MODE = {
    "catalog": "cart",
    "events": "booking",
    "stays": "booking",
    "promotions": "reserve",
    "jobs": "request",
    "booking": "booking",  # услуги по времени (Termin)
}


def purchase_mode(module: str) -> str:
    """Способ покупки для модуля-архетипа (cart|booking|reserve|request); по
    умолчанию `request` (под запрос) — безопасный фолбэк без онлайн-оплаты."""
    return PURCHASE_MODE.get(module, "request")


# M20U-5: подпись основного действия по режиму покупки (DE, как storefront_label).
# Для CTA на карточках/детальной: «купить» vs «забронировать» vs «запросить».
PURCHASE_LABELS = {
    "cart": "In den Warenkorb",
    "booking": "Jetzt buchen",
    "reserve": "Reservieren",
    "request": "Anfrage senden",
}


def purchase_label(module: str) -> str:
    """Немецкая подпись действия покупки для модуля-архетипа (фолбэк — «Anfrage senden»)."""
    return PURCHASE_LABELS.get(purchase_mode(module), PURCHASE_LABELS["request"])


def primary_module(tenant) -> str | None:
    """Ключ модуля «главного товара» тенанта.

    `site_config.storefront_root` (если это архетип из PRIMARY_SECTION и он активен)
    → иначе первый активный архетип по приоритету `_PRIORITY` → иначе None.
    """
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    root = cfg.get("storefront_root")
    if root in PRIMARY_SECTION and tenant.is_module_active(root):
        return root
    for key in _PRIORITY:
        if tenant.is_module_active(key):
            return key
    return None


def primary_section(tenant) -> str | None:
    """Секция главной для «главного товара» тенанта (или None)."""
    module = primary_module(tenant)
    return PRIMARY_SECTION.get(module) if module else None


def primary_item(tenant) -> dict | None:
    """Дескриптор главного товара: {module, section, landing, label} или None."""
    module = primary_module(tenant)
    if not module:
        return None
    spec = modules.get_module(module)
    return {
        "module": module,
        "section": PRIMARY_SECTION[module],
        "landing": getattr(spec, "storefront_landing", "") if spec else "",
        "label": getattr(spec, "storefront_label", "") if spec else "",
        "mode": purchase_mode(module),
    }
