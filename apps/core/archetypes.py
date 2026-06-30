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
    # A3: услуги по времени (Friseur/Massage/Werkstatt-Termin) — главный товар на
    # главной = блок «Leistungen & Preise».
    "booking": "services",
}

# Приоритет выбора «главного» архетипа, если storefront_root не задан явно. booking
# выше catalog: у салона/мастерской каталог второстепенен (мерч/Teile), главный
# товар — услуга (Termin).
_PRIORITY = ["events", "stays", "booking", "catalog", "promotions"]

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


# H0 (архетипы как сущности): секция главной → модуль-архетип, который её «несёт».
# Секция БЕЗ записи — generic (применима к любому архетипу): hero, usp_bar, promotions,
# about, process, team, cta, testimonials, trust, reviews, faq, gallery, contact,
# archetypes. Источник правды гейтинга редактора (список секций) и витрины.
# ⚠️ catalog — core (всегда активен), поэтому products/categories видимы у всех; точечное
# «показывать только под primary-архетип» — отдельное решение (см. docs/archetype-entities-plan.md H0).
SECTION_ARCHETYPE_MODULE = {
    "stay_search": "stays",
    "stay_rooms": "stays",
    "services": "booking",
    "products": "catalog",
    "categories": "catalog",
    "events": "events",
    "before_after": "jobs",
}


def section_visible_for(tenant, section_key: str) -> bool:
    """H0: видна ли секция главной редактору этого тенанта.

    Generic-секция (нет в SECTION_ARCHETYPE_MODULE) — всегда; секция-архетип — только
    если её модуль активен. Так пекарня (catalog) не видит секций Stay/Events/Services/
    Handwerker, а мультиархетип — видит объединение своих архетипов.
    """
    module = SECTION_ARCHETYPE_MODULE.get(section_key)
    return module is None or tenant.is_module_active(module)


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
