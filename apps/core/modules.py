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
    # Кому модуль ПОДХОДИТ сверх пресета (гибрид, решение владельца 2026-06-12):
    # включается без предупреждения, но не входит в стартовый набор. Оба поля
    # пустые = универсальный блок (подходит всем).
    suited_for: tuple[str, ...] = ()
    core: bool = False  # выключить нельзя, entitlement не применяется
    premium: bool = False  # требует key в Tenant.enabled_modules (тариф)
    description_de: str = ""  # «что это даёт» — пояснение на странице «Module» (D0b)
    # --- Витринный (storefront) презентационный слой (S1) ----------------------
    # «Лицо» архетипа для ПОСЕТИТЕЛЯ сайта (не кабинета). Источник правды и для
    # тизеров главной (секция «Наши разделы», S2), и для конструктора меню (S7).
    # Пусто = у модуля нет публичной «главной» → он не появляется в конструкторе
    # витрины (напр. promotions рендерятся инлайн на главной; loyalty — публичная
    # страница появится в S5).
    storefront_label: str = ""  # заголовок для клиента (DE); фолбэк — label_de
    storefront_blurb: str = ""  # короткое описание под заголовком
    storefront_landing: str = ""  # url_name публичной страницы-«главной» архетипа
    storefront_icon: str = ""  # emoji тизера/пункта меню; фолбэк — icon
    storefront_teaser: bool = True  # показывать в сетке «Наши разделы» по умолчанию


REGISTRY: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        key="dashboard",
        label_de="Übersicht",
        icon="🏠",
        nav_items=(NavItem("dashboard", _("Dashboard"), "dashboard"),),
        url_prefixes=("/dashboard/",),
        core=True,
        description_de="Überblick über Ihr Geschäft.",
    ),
    # U-D2: единая Kanban-доска входящих транзакций (заказы/брони/проживание/
    # билеты/заявки/резервы) — «одна доска дел». core: всегда доступна, пустая
    # доска показывает graceful empty-state.
    ModuleSpec(
        key="board",
        label_de="Aufgaben-Board",
        icon="🗂️",
        nav_items=(NavItem("board", _("Board"), "board"),),
        url_prefixes=("/dashboard/board/",),
        core=True,
        description_de="Alle Bestellungen, Termine, Buchungen & Anfragen als Kanban-Board.",
    ),
    ModuleSpec(
        key="catalog",
        label_de="Katalog & Import",
        icon="📦",
        # S1 (упрощение кабинета): 5 прежних пунктов каталога (Produkte/Kategorien/
        # Lager/Kombi/Import) сведены в ОДИН хаб «Sortiment» с tab-bar над контентом
        # (cabinet.HUB_TABS["catalog"] + _hub_tabs.html). Под-страницы доступны
        # табами; url_prefixes ниже сохраняют middleware-гейт всех путей.
        nav_items=(NavItem("catalog:product-list", _("Catalog"), "catalog"),),
        url_prefixes=("/catalog/", "/imports/", "/dashboard/stock/"),
        core=True,
        description_de="Produkte und Kategorien pflegen, Import aus CSV/Excel.",
        storefront_label="Sortiment",
        storefront_blurb="Stöbern Sie in unserem Angebot.",
        storefront_landing="storefront-products",
        storefront_icon="🍽️",
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
        suited_for=("hotel", "tour_operator"),
        description_de="Aktionen erstellen, Reservierungen annehmen und im Laden einlösen.",
    ),
    ModuleSpec(
        key="crm",
        label_de="Kunden (CRM)",
        icon="👥",
        nav_items=(
            NavItem("crm:customer-list", _("Customers"), "crm"),
            # B4/CM-9: купон-кампании по сегментам клиентской базы.
            NavItem("promotions:coupon-campaigns", _("Campaigns"), "campaigns"),
        ),
        url_prefixes=("/crm/", "/promotions/kampagnen/"),
        recommended_for=("hotel", "tour_operator"),
        suited_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "other",
        ),
        description_de="Kundenliste führen: Kontakte, Tags, Notizen, Buchungshistorie.",
    ),
    ModuleSpec(
        # CM-6: репутационный модуль — модерация отзывов о сущностях (reviews.Review).
        # recommended_for = ВСЕ типы: активен из коробки (урок default_disabled_for).
        key="reviews",
        label_de="Bewertungen",
        icon="⭐",
        nav_items=(NavItem("reviews:list", _("Reviews"), "reviews"),),
        url_prefixes=("/dashboard/reviews/",),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "clothing",
            "restaurant",
            "cafe",
            "retail",
            "tour_operator",
            "hotel",
            "other",
        ),
        description_de="Bewertungen Ihrer Produkte, Leistungen, Zimmer und Events: "
        "ansehen, ausblenden, beantworten.",
    ),
    ModuleSpec(
        key="orders",
        label_de="Bestellungen (Click & Collect)",
        icon="🛍️",
        # S2 (упрощение): продажные списки сведены в хаб «Verkäufe» (доска + tab-bar,
        # cabinet.HUB_TABS["board"]). Сайдбар-пункт убран, url_prefixes = гейт цел.
        nav_items=(),
        url_prefixes=("/dashboard/orders/",),
        recommended_for=("bakery", "butcher", "grocery", "retail", "clothing"),
        suited_for=("cafe", "restaurant", "other"),
        description_de="Kunden bestellen online und holen im Laden ab.",
        storefront_label="Online bestellen",
        storefront_blurb="Bestellen und im Laden abholen oder liefern lassen.",
        storefront_landing="storefront-cart",
        storefront_icon="🛍️",
    ),
    ModuleSpec(
        key="booking",
        label_de="Reservierungen nach Zeit (Booking)",
        icon="📅",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/booking/",),
        recommended_for=("cafe", "restaurant", "hotel", "tour_operator"),
        suited_for=("retail", "clothing", "other"),
        description_de="Tische, Termine oder Zimmer nach Uhrzeit reservieren lassen.",
        storefront_label="Termin buchen",
        storefront_blurb="Reservieren Sie online Ihren Tisch oder Termin.",
        storefront_landing="storefront-termin",
        storefront_icon="📅",
    ),
    ModuleSpec(
        key="stays",
        label_de="Übernachtung (nach Datum)",
        icon="🛏️",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/stays/",),
        recommended_for=("hotel",),
        suited_for=("tour_operator", "other"),
        description_de="Zimmer, Ferienwohnungen oder Stellplätze nach Nächten buchen lassen.",
        storefront_label="Übernachten",
        storefront_blurb="Verfügbarkeit prüfen und Übernachtung buchen.",
        storefront_landing="storefront-unterkunft",
        storefront_icon="🛏️",
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
        suited_for=("retail", "clothing", "other"),
        description_de="Gutscheine und Stempelkarten für Stammkunden.",
        storefront_label="Treueprogramm",
        storefront_blurb="Stempel sammeln und Prämien sichern.",
        storefront_landing="storefront-loyalty",
        storefront_icon="💝",
    ),
    ModuleSpec(
        # B1.1: продажа Geschenkgutscheine (движок G1) — для ВСЕХ архетипов.
        # Активен из коробки (non-premium, universal); страница /gutschein/
        # дополнительно требует онлайн-оплату (payments_enabled + Connect).
        key="gift",
        label_de="Geschenkgutscheine",
        icon="🎁",
        nav_items=(),
        url_prefixes=(),
        # ВСЕ типы: иначе default_disabled_for выключит gift при онбординге
        # (актив «из коробки» — суть B1; страница всё равно за гейтом оплаты).
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "clothing",
            "restaurant",
            "cafe",
            "retail",
            "tour_operator",
            "hotel",
            "other",
        ),
        description_de="Geschenkgutscheine online verkaufen: Käufer zahlt online, "
        "Beschenkte lösen den Code beim Bestellen oder Buchen ein. "
        "Voraussetzung: Online-Zahlungen (Stripe) aktiviert.",
        storefront_label="Gutschein verschenken",
        storefront_blurb="Geschenkgutschein kaufen — Betrag frei wählbar.",
        storefront_landing="storefront-gutschein",
        storefront_icon="🎁",
        storefront_teaser=False,  # ссылка в футере/меню, не «направление» в сетке
    ),
    ModuleSpec(
        key="analytics",
        label_de="Auswertung",
        icon="📊",
        nav_items=(NavItem("promotions:analytics", _("Analytics"), "analytics"),),
        url_prefixes=("/promotions/analytics/",),
        depends_on=("promotions",),
        description_de="Auswertung Ihrer Aktionen: Aufrufe, Reservierungen, Einlösungen.",
    ),
    ModuleSpec(
        key="publishing",
        label_de="Veröffentlichung (Kanäle)",
        icon="📣",
        nav_items=(
            NavItem("channels", _("Channels"), "channels"),
            # CM-2: контент-календарь — посты с отложенной отправкой.
            NavItem("publishing-posts", _("Posts"), "posts"),
        ),
        url_prefixes=("/dashboard/channels/", "/dashboard/posts/"),
        description_de="Aktionen automatisch auf Kanälen veröffentlichen (Google, Facebook, Instagram).",
    ),
    ModuleSpec(
        key="jobs",
        label_de="Aufträge & Angebote",
        icon="🧰",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/auftraege/",),
        # Выездной сервис/Handwerk — opt-in, универсальный (в business_type нет
        # ремесленных типов; включают вручную, как finance).
        description_de="Anfragen annehmen, Angebote/Kostenvoranschläge erstellen, Aufträge abrechnen.",
        storefront_label="Angebot anfragen",
        storefront_blurb="Fordern Sie online einen Kostenvoranschlag an.",
        storefront_landing="storefront-anfrage",
        storefront_icon="🧰",
    ),
    ModuleSpec(
        key="events",
        label_de="Veranstaltungen (Tickets)",
        icon="🎟️",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/events/",),
        # Билеты на мероприятия/ретриты — opt-in, универсальный (как finance/jobs);
        # подходит студиям/гидам/организаторам сверх пресета.
        suited_for=("tour_operator", "other"),
        description_de="Veranstaltungen mit bezahlten Tickets und Teilnehmerliste.",
        storefront_label="Veranstaltungen",
        storefront_blurb="Tickets für unsere Events sichern.",
        storefront_landing="storefront-events",
        storefront_icon="🎟️",
    ),
    ModuleSpec(
        key="blog",
        label_de="Blog / Neuigkeiten",
        icon="📰",
        nav_items=(NavItem("blog-list", _("Blog"), "blog"),),
        # CM-1: контент first-class для ВСЕХ архетипов (модель живёт в apps/events
        # организационно, но от событий не зависит). Гейтим и витрину /blog/ —
        # тумблер «Module» должен реально выключать. recommended_for=все типы →
        # активен из коробки везде (в default_disabled_for не попадает).
        url_prefixes=("/dashboard/blog/", "/blog/"),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "hotel",
            "tour_operator",
            "other",
        ),
        description_de="Neuigkeiten und Beiträge veröffentlichen — frischer Inhalt für Kunden und Google.",
        storefront_label="Neuigkeiten",
        storefront_blurb="Aktuelles aus unserem Betrieb.",
        storefront_landing="storefront-blog",
        storefront_icon="📰",
        storefront_teaser=False,  # контент-ссылка, не «направление» в сетке архетипов
    ),
    ModuleSpec(
        key="inbox",
        label_de="Nachrichten (Chat & Support)",
        icon="💬",
        nav_items=(NavItem("inbox:list", _("Inbox"), "inbox"),),
        url_prefixes=("/dashboard/inbox/",),
        # Коммуникация — универсальный блок, включён из коробки у всех вертикалей
        # (recommended_for=все типы → не попадает в default_disabled_for).
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "hotel",
            "tour_operator",
            "other",
        ),
        description_de="Kundennachrichten und Support-Tickets an einem Ort beantworten.",
        storefront_label="Kontakt",
        storefront_blurb="Stellen Sie uns eine Frage.",
        storefront_landing="storefront-message",
        storefront_icon="💬",
        storefront_teaser=False,  # утилитарная ссылка, не «направление» в сетке
    ),
    ModuleSpec(
        key="finance",
        label_de="Finanzen (Umsatz)",
        icon="💶",
        nav_items=(NavItem("finance:journal", _("Finance"), "finance"),),
        url_prefixes=("/dashboard/finance/",),
        # «добавь, когда дорастёшь» (ТЗ D0b) — по умолчанию выключен у всех вертикалей
        description_de="Umsatzjournal: Einnahmen aus Bestellungen, Reservierungen und manuell.",
    ),
    ModuleSpec(
        key="telegram",
        label_de="Telegram-Bot",
        icon="✈️",
        nav_items=(NavItem("telegram-settings", _("Telegram"), "telegram"),),
        url_prefixes=("/dashboard/telegram/",),
        # Универсальный opt-in (как finance/jobs) — выключен по умолчанию у всех.
        description_de="Eigener Telegram-Bot: Kunden öffnen Ihren Shop als Mini App in Telegram.",
    ),
    ModuleSpec(
        key="customer_account",
        label_de="Kundenkonto (Login für Kunden)",
        icon="👤",
        # Витринный модуль: в кабинете нет своего пункта; /konto/ гейтится во
        # вьюхах (не ModuleGatingMiddleware). Default ВКЛ у транзакционных типов
        # (recommended_for), ВЫКЛ у чистых витрин (other → default_disabled_for).
        nav_items=(),
        url_prefixes=(),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "hotel",
            "tour_operator",
        ),
        suited_for=("other",),
        description_de="Kunden melden sich per E-Mail-Link an und sehen Bestellungen, "
        "Termine, Rechnungen und Bonuskarten.",
        storefront_label="Mein Konto",
        storefront_blurb="Bestellungen, Termine und Bonuskarten einsehen.",
        storefront_landing="account-home",
        storefront_icon="👤",
        storefront_teaser=False,  # вход в ЛК, не «направление» в сетке
    ),
    ModuleSpec(
        key="settings",
        label_de="Einstellungen",
        icon="⚙️",
        # S3 (упрощение): «Website» (визуальный билдер) остаётся отдельным пунктом;
        # остальные 8 настроек сведены в ОДИН пункт-хаб «Einstellungen» с tab-bar
        # (cabinet.HUB_TABS["settings"] + «Erweitert»-ящик). url_prefixes ниже сохраняют
        # middleware-гейт всех путей — под-страницы доступны табами хаба.
        nav_items=(
            NavItem("site", _("Site"), "site"),
            NavItem("settings", _("Settings"), "settings"),
        ),
        url_prefixes=(
            "/dashboard/site/",
            "/dashboard/settings/",
            "/dashboard/recht/",
            "/dashboard/extras/",
            "/dashboard/domains/",
            "/dashboard/modules/",
            "/dashboard/help/",
        ),
        core=True,
        description_de="Einstellungen, Website-Baukasten, Domains, Module, Hilfe.",
    ),
    ModuleSpec(
        key="billing",
        label_de="Abo & Zahlung",
        icon="💳",
        nav_items=(NavItem("billing", _("Billing"), "billing"),),
        url_prefixes=("/dashboard/billing/",),
        core=True,
        description_de="Abo und Zahlung.",
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


# AB1 (анти-Битрикс): группировка меню кабинета по задачам, а не по техническим
# модулям. Порядок групп = порядок показа; внутри группы — порядок ключей. Модули
# вне карты падают в группу «sell» (бизнес-функции) как безопасный дефолт.
NAV_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("shop", "Mein Geschäft", ("dashboard",)),
    ("sell", "Verkaufen", ("board", "catalog", "orders", "booking", "stays", "events", "jobs")),
    (
        "marketing",
        "Kunden & Marketing",
        ("crm", "reviews", "promotions", "loyalty", "publishing", "inbox", "telegram"),
    ),
    (
        "settings",
        "Einstellungen",
        ("analytics", "finance", "customer_account", "settings", "billing"),
    ),
)
_GROUP_BY_KEY = {mk: gkey for gkey, _label, keys in NAV_GROUPS for mk in keys}

# AB1 (анти-Битрикс §0.1 «меню на языке задач, не сущностей»): подпись пункта
# сайдбара в языке задач/по-немецки (nav_key → метка). Фолбэк — NavItem.label
# (англ. msgid). Отдельный реестр, а не поле NavItem: все формулировки в одном
# читаемом месте, владельцу удобно править словом. Хром кабинета пока без de.po
# (T-1 отложен), поэтому эти немецкие литералы заодно убирают английские техтермины.
NAV_TASK_LABELS: dict[str, str] = {
    "dashboard": "Übersicht",
    # S2: пункт-хаб «Verkäufe» (доска + продажные списки/календари под tab-bar).
    "board": "Verkäufe",
    "catalog": "Sortiment",
    "stock": "Lager",
    "categories": "Kategorien",
    "combos": "Kombi-Angebote",
    "imports": "Import",
    "orders": "Bestellungen",
    "booking": "Termine",
    "stays": "Übernachtungen",
    "events": "Veranstaltungen",
    "jobs": "Aufträge",
    "crm": "Kunden",
    "campaigns": "Kampagnen",
    "reviews": "Bewertungen",
    "promotions": "Aktionen",
    "reservations": "Reservierungen",
    "redeem": "Einlösen",
    "vouchers": "Gutscheine",
    "loyalty": "Treuepunkte",
    "channels": "Kanäle",
    "posts": "Beiträge",
    "blog": "Blog & News",
    "inbox": "Nachrichten",
    "telegram": "Telegram",
    "analytics": "Auswertungen",
    "finance": "Finanzen",
    "site": "Website gestalten",
    "settings": "Einstellungen",
    "notifications": "Benachrichtigungen",
    "languages": "Sprachen",
    "legal-docs": "Rechtstexte",
    "extras": "Zusatzleistungen",
    "media": "Medien",
    "domains": "Domains",
    "modules": "Funktionen",
    "support": "Hilfe",
    "billing": "Abrechnung",
}


def nav_task_label(nav_key: str) -> str:
    """AB1: подпись пункта сайдбара в языке задач по nav_key ("" → фолбэк на label)."""
    return NAV_TASK_LABELS.get(nav_key, "")


def grouped_active_modules(tenant) -> list[dict]:
    """AB1: активные модули, сгруппированные по задачам (для сайдбара кабинета).

    → [{"key", "label", "modules": [ModuleSpec, …]}] в порядке NAV_GROUPS; пустые
    группы опускаются. Модуль без явной группы попадает в «sell» (бизнес-функции)."""
    buckets: dict[str, list[ModuleSpec]] = {gkey: [] for gkey, _l, _k in NAV_GROUPS}
    order = {mk: i for _g, _l, keys in NAV_GROUPS for i, mk in enumerate(keys)}
    for spec in active_modules(tenant):
        buckets[_GROUP_BY_KEY.get(spec.key, "sell")].append(spec)
    groups = []
    for gkey, label, _keys in NAV_GROUPS:
        mods = sorted(buckets[gkey], key=lambda s: order.get(s.key, 99))
        if mods:
            groups.append({"key": gkey, "label": label, "modules": mods})
    return groups


def optional_modules() -> list[ModuleSpec]:
    """Выключаемые модули (для тумблеров страницы «Module»)."""
    return [spec for spec in REGISTRY if not spec.core]


def is_suited_for(spec: ModuleSpec, business_type: str) -> bool:
    """Подходит ли модуль вертикали (гибрид, решение владельца 2026-06-12).

    Подходит = recommended_for (пресет) ∪ suited_for. Оба пустые —
    универсальный блок (Analytics/Channels), подходит всем. Неподходящий
    включить можно, но UI предупреждает (осознанный выбор, не запрет).
    """
    if not spec.recommended_for and not spec.suited_for:
        return True
    return business_type in spec.recommended_for or business_type in spec.suited_for


def suited_label(spec: ModuleSpec) -> str:
    """«Geeignet für: Bäckerei, Metzgerei…» / «Für alle Geschäftstypen»."""
    from apps.tenants.models import Tenant

    labels = dict(Tenant.BUSINESS_TYPES)
    union = dict.fromkeys((*spec.recommended_for, *spec.suited_for))  # порядок без дублей
    if not union or len(union) >= len(labels):
        return "Für alle Geschäftstypen"
    names = [str(labels.get(bt, bt)).split("/")[-1].strip() for bt in union]
    return "Geeignet für: " + ", ".join(names)


def default_disabled_for(business_type: str) -> list[str]:
    """Стартовый disabled_modules при онбординге (D0b): опциональные −
    рекомендованные-для-вертикали (recommended_for). Лёгкий старт — лишние
    блоки владелец добавляет позже на /dashboard/modules/."""
    return [
        spec.key for spec in REGISTRY if not spec.core and business_type not in spec.recommended_for
    ]


@dataclass(frozen=True)
class StorefrontArchetype:
    """Витринное «лицо» активного архетипа (S1) — данные для тизера/пункта меню.

    url_name НЕ резолвим здесь: шаблон делает {% url %}, чтобы не падать на
    маршруте, недоступном в текущем urlconf (портал/агрегатор используют свой).
    """

    key: str
    label: str
    blurb: str
    icon: str
    url_name: str
    teaser: bool


def storefront_archetypes(tenant) -> list[StorefrontArchetype]:
    """Витринные «лица» активных архетипов для конструктора витрины.

    Источник правды для тизеров главной («Наши разделы», S2) и конструктора
    меню (S7). Берём только активные модули с публичной страницей
    (``storefront_landing`` задан); порядок — как в реестре. Новый архетип
    подключается к конструктору одной декларацией здесь, без правок витрины.
    """
    out = []
    for spec in REGISTRY:
        if not spec.storefront_landing or not is_module_active(tenant, spec.key):
            continue
        out.append(
            StorefrontArchetype(
                key=spec.key,
                label=spec.storefront_label or spec.label_de,
                blurb=spec.storefront_blurb,
                icon=spec.storefront_icon or spec.icon,
                url_name=spec.storefront_landing,
                teaser=spec.storefront_teaser,
            )
        )
    return out


def archetype_by_landing(url_name: str) -> str | None:
    """Ключ архетипа по url_name его публичной «главной» (S3 — обложки)."""
    if not url_name:
        return None
    for spec in REGISTRY:
        if spec.storefront_landing and spec.storefront_landing == url_name:
            return spec.key
    return None


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
