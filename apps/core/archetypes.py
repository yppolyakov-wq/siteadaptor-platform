"""M20U: «главный товар» по архетипу — primary_item registry.

Единая абстракция «архетип = главный товар»: магазин → товары, ретрит → события,
отель → номера, магазин-без-товаров → акции. Поверх реестра модулей
(`apps.core.modules`), без новых моделей. Используется унифицированной главной/
каталогом, чтобы знать, что выводить первым.
"""

from django.utils.translation import gettext_lazy as _

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


# H0 («архетип = 3 сущности-страницы»): 3-я сущность — страница-ДЕТАЛЬ (товар/номер/
# событие). 1-я/2-я (главная-лендинг + список) уже даёт modules.storefront_landing /
# PRIMARY_SECTION; здесь — деталь с URL РЕАЛЬНОГО примера, чтобы редактор открыл её в
# превью и правил инлайн (инлайн-эндпоинты H1.2 уже есть для product/event/stay).
# Кортеж: (модуль, "app.Model", url_name детали, подпись, фильтр примера, order_by).
# Фильтр совпадает с публичной вьюхой (активный/опубликованный) — иначе открытая деталь
# не отрендерится. Модели резолвим лениво (apps.get_model) — иначе цикл core↔apps.
DETAIL_ENTITIES = (
    ("catalog", "catalog.Product", "storefront-product", _("Product page"),
     {"is_active": True}, ("-is_featured", "-created_at")),
    ("stays", "stays.StayUnit", "storefront-unterkunft-unit", _("Room page"),
     {"is_active": True}, ()),
    ("events", "events.Event", "storefront-event", _("Event page"),
     {"status": "published"}, ("starts_at",)),
    # UA1-2 (U-A): деталь услуги (booking.Service) на каркасе detail.html (UA1-1).
    # Группа `booking_detail` пока без пер-страничного инспектора → превью падает
    # в «правь на канве» (как `stays_detail`); реестр секций — UA4-1.
    ("booking", "booking.Service", "storefront-service-detail", _("Service page"),
     {"is_active": True}, ("-created_at",)),
)  # fmt: skip


def example_detail_pages(tenant) -> list[dict]:
    """H0/H1: пункты «деталь» для переключателя превью редактора — по одному на активный
    архетип, у которого есть опубликованный пример. Каждый — ``{"label", "url"}``.

    Покрыты архетипы с инлайн-правкой детали (H1.2): catalog→товар, stays→номер,
    events→событие. Нет примера / маршрута в текущем urlconf → пункт пропускаем.
    """
    from django.apps import apps as django_apps
    from django.urls import NoReverseMatch, reverse

    pages = []
    for module_key, model_path, url_name, label, qs_filter, order in DETAIL_ENTITIES:
        if not tenant.is_module_active(module_key):
            continue
        model = django_apps.get_model(model_path)
        qs = model.objects.filter(**qs_filter)
        if order:
            qs = qs.order_by(*order)
        obj = qs.first()
        if obj is None:
            continue
        try:
            # Part D: group = «<модуль>_detail» — билдер по ней показывает на детали
            # только блоки этой страницы (порядок секций детали и т.п.).
            pages.append(
                {
                    "label": label,
                    "url": reverse(url_name, args=[obj.pk]),
                    "group": f"{module_key}_detail",
                }
            )
        except NoReverseMatch:
            continue
    return pages


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


def aggregate_primary_sections(tenant) -> list[dict]:
    """H2 (мультиархетип): «главный» блок КАЖДОГО активного архетипа, в порядке реестра.

    Для авто-композиции главной сборного сайта (магазин+ретриты+услуги → products+events+
    services …). Возвращает по одному дескриптору на активный архетип из `_PRIORITY`,
    у которого есть секция-главного-товара (`PRIMARY_SECTION`): ``{key, module, order}``,
    отсортированный по приоритету реестра (events>stays>booking>catalog>promotions).
    Пусто, если ни один такой архетип не активен. Без запросов к БД (O(≤5)).
    """
    out = []
    for order, module in enumerate(_PRIORITY):
        section = PRIMARY_SECTION.get(module)
        if section and tenant.is_module_active(module):
            out.append({"key": section, "module": module, "order": order})
    return out
