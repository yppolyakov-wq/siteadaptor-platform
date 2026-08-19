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
    # --- W12-3: ось Простого режима живёт В СПЕКЕ модуля (не в параллельной карте) --
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
        label_de=_("Übersicht"),
        icon="🏠",
        nav_items=(NavItem("dashboard", _("Dashboard"), "dashboard"),),
        url_prefixes=("/dashboard/",),
        core=True,
        description_de=_("Überblick über Ihr Geschäft."),
    ),
    # U-D2: единая Kanban-доска входящих транзакций (заказы/брони/проживание/
    # билеты/заявки/резервы) — «одна доска дел». core: всегда доступна, пустая
    # доска показывает graceful empty-state.
    ModuleSpec(
        key="board",
        label_de=_("Aufgaben-Board"),
        icon="🗂️",
        nav_items=(NavItem("board", _("Board"), "board"),),
        url_prefixes=("/dashboard/board/",),
        core=True,
        description_de=_("Alle Bestellungen, Termine, Buchungen & Anfragen als Kanban-Board."),
    ),
    ModuleSpec(
        key="catalog",
        label_de=_("Katalog & Import"),
        icon="📦",
        # S1 (упрощение кабинета): 5 прежних пунктов каталога (Produkte/Kategorien/
        # Lager/Kombi/Import) сведены в ОДИН хаб «Sortiment» с tab-bar над контентом
        # (cabinet.HUB_TABS["catalog"] + _hub_tabs.html). Под-страницы доступны
        # табами; url_prefixes ниже сохраняют middleware-гейт всех путей.
        nav_items=(NavItem("catalog:product-list", _("Catalog"), "catalog"),),
        url_prefixes=("/catalog/", "/imports/", "/dashboard/stock/", "/dashboard/purchasing/"),
        core=True,
        # W12-3 (бывш. S6b-карта): товары не primary у этих архетипов — в Простом
        # хаб «Sortiment» прячется (werkstatt держит — Teile; restaurant — Speisekarte).
        description_de=_("Produkte und Kategorien pflegen, Import aus CSV/Excel."),
        storefront_label=_("Sortiment"),
        storefront_blurb=_("Stöbern Sie in unserem Angebot."),
        storefront_landing="storefront-products",
        storefront_icon="🍽️",
    ),
    ModuleSpec(
        key="promotions",
        label_de=_("Aktionen & Reservierung"),
        icon="🏷️",
        # S4a (упрощение): промо/отзывы/лояльность/публикация сведены в хаб «Marketing»
        # (tab-bar, cabinet.HUB_TABS["marketing"]). Этот якорь-пункт → страница акций;
        # остальное — вкладки хаба. url_prefixes сохраняют middleware-гейт.
        nav_items=(NavItem("promotions:promotion-list", _("Promotions"), "promotions"),),
        url_prefixes=("/promotions/",),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "online_shop",  # 2026-07-10
            "other",
            "friseur",  # S6: салон делает Aktionen
            "events",  # S6: организатор — промо-акции
            "catering",  # GK-1: акции на пакеты/сезон
        ),
        # S6: handwerker/werkstatt — suited (не вкл по умолчанию, но подходит) →
        # promotions покрывает все типы → suited_label остаётся «Für alle Geschäftstypen».
        suited_for=("hotel", "tour_operator", "handwerker", "werkstatt"),
        description_de=_("Aktionen erstellen, Reservierungen annehmen und im Laden einlösen."),
        # HF-1 (фидбэк владельца 2026-07-31, п. 7): у модуля не было витринной
        # посадочной — из-за этого пункт меню «Aktionen» нельзя было собрать
        # архетипным узлом, только сырым URL. Страница акций существовала всегда.
        storefront_label=_("Aktionen"),
        storefront_landing="storefront-aktionen",
        storefront_icon="🏷️",
        storefront_teaser=False,
    ),
    ModuleSpec(
        key="crm",
        label_de=_("Kunden (CRM)"),
        icon="👥",
        # S4a: «Kampagnen» переехали во вкладку хаба «Marketing» (гейт по модулю crm).
        # Пункт CRM остаётся якорем будущего хаба «Kunden» (S4b). url_prefix кампаний цел.
        nav_items=(NavItem("crm:customer-list", _("Customers"), "crm"),),
        url_prefixes=("/crm/", "/promotions/kampagnen/"),
        recommended_for=("hotel", "tour_operator", "catering"),  # GK-1: событийные клиенты
        suited_for=(
            "bakery",
            "butcher",
            "grocery",
            "cafe",
            "restaurant",
            "retail",
            "clothing",
            "online_shop",  # 2026-07-10
            "other",
            "friseur",  # S6
            "handwerker",  # S6
            "werkstatt",  # S6
            "events",  # S6
        ),
        description_de=_("Kundenliste führen: Kontakte, Tags, Notizen, Buchungshistorie."),
    ),
    ModuleSpec(
        # CM-6: репутационный модуль — модерация отзывов о сущностях (reviews.Review).
        # recommended_for = ВСЕ типы: активен из коробки (урок default_disabled_for).
        key="reviews",
        label_de=_("Bewertungen"),
        icon="⭐",
        # S4a: вкладка хаба «Marketing» (cabinet.HUB_TABS["marketing"]); url_prefix = гейт.
        nav_items=(),
        url_prefixes=("/dashboard/reviews/",),
        recommended_for=(
            "bakery",
            "butcher",
            "grocery",
            "clothing",
            "online_shop",  # 2026-07-10
            "restaurant",
            "cafe",
            "retail",
            "tour_operator",
            "hotel",
            "friseur",  # S6
            "handwerker",  # S6
            "werkstatt",  # S6
            "events",  # S6
            "catering",  # GK-1
            "other",
        ),
        description_de=_(
            "Bewertungen Ihrer Produkte, Leistungen, Zimmer und Events: "
            "ansehen, ausblenden, beantworten."
        ),
    ),
    ModuleSpec(
        key="orders",
        label_de=_("Bestellungen (Click & Collect)"),
        icon="🛍️",
        # S2 (упрощение): продажные списки сведены в хаб «Verkäufe» (доска + tab-bar,
        # cabinet.HUB_TABS["board"]). Сайдбар-пункт убран, url_prefixes = гейт цел.
        nav_items=(),
        url_prefixes=("/dashboard/orders/",),
        recommended_for=("bakery", "butcher", "grocery", "retail", "clothing", "online_shop"),
        # S6: friseur (Pflegeprodukte) / werkstatt (Teile) — розница как доп-канал.
        suited_for=("cafe", "restaurant", "other", "friseur", "werkstatt", "catering"),
        description_de=_("Kunden bestellen online und holen im Laden ab."),
        storefront_label=_("Online bestellen"),
        storefront_blurb=_("Bestellen und im Laden abholen oder liefern lassen."),
        storefront_landing="storefront-cart",
        storefront_icon="🛍️",
    ),
    ModuleSpec(
        key="booking",
        label_de=_("Reservierungen nach Zeit (Booking)"),
        icon="📅",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/booking/",),
        # S6: Friseur/Werkstatt — услуги по времени (Termin) primary; Handwerker — suited.
        recommended_for=("cafe", "restaurant", "hotel", "tour_operator", "friseur", "werkstatt"),
        suited_for=("retail", "clothing", "other", "handwerker", "catering"),
        description_de=_("Tische, Termine oder Zimmer nach Uhrzeit reservieren lassen."),
        storefront_label=_("Termin buchen"),
        storefront_blurb=_("Reservieren Sie online Ihren Tisch oder Termin."),
        storefront_landing="storefront-termin",
        storefront_icon="📅",
    ),
    ModuleSpec(
        key="stays",
        label_de=_("Übernachtung (nach Datum)"),
        icon="🛏️",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/stays/",),
        recommended_for=("hotel",),
        suited_for=("tour_operator", "other"),
        description_de=_("Zimmer, Ferienwohnungen oder Stellplätze nach Nächten buchen lassen."),
        storefront_label=_("Übernachten"),
        storefront_blurb=_("Verfügbarkeit prüfen und Übernachtung buchen."),
        storefront_landing="storefront-unterkunft",
        storefront_icon="🛏️",
    ),
    ModuleSpec(
        key="loyalty",
        label_de=_("Treue & Gutscheine"),
        icon="💝",
        # S4a: Gutscheine/Treuepunkte — вкладки хаба «Marketing»; url_prefixes = гейт.
        nav_items=(),
        url_prefixes=("/promotions/vouchers/", "/promotions/loyalty/"),
        depends_on=("promotions",),
        # S6: friseur — Stempelkarte для постоянных клиентов салона.
        recommended_for=("bakery", "butcher", "grocery", "cafe", "restaurant", "friseur"),
        suited_for=("retail", "clothing", "online_shop", "other"),
        description_de=_("Gutscheine und Stempelkarten für Stammkunden."),
        storefront_label=_("Treueprogramm"),
        storefront_blurb=_("Stempel sammeln und Prämien sichern."),
        storefront_landing="storefront-loyalty",
        storefront_icon="💝",
    ),
    ModuleSpec(
        # B1.1: продажа Geschenkgutscheine (движок G1) — для ВСЕХ архетипов.
        # Активен из коробки (non-premium, universal); страница /gutschein/
        # дополнительно требует онлайн-оплату (payments_enabled + Connect).
        key="gift",
        label_de=_("Geschenkgutscheine"),
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
            "online_shop",  # 2026-07-10
            "restaurant",
            "cafe",
            "retail",
            "tour_operator",
            "hotel",
            "friseur",  # S6
            "handwerker",  # S6
            "werkstatt",  # S6
            "events",  # S6
            "catering",  # GK-1
            "other",
        ),
        description_de=_(
            "Geschenkgutscheine online verkaufen: Käufer zahlt online, "
            "Beschenkte lösen den Code beim Bestellen oder Buchen ein. "
            "Voraussetzung: Online-Zahlungen (Stripe) aktiviert."
        ),
        storefront_label=_("Gutschein verschenken"),
        storefront_blurb=_("Geschenkgutschein kaufen — Betrag frei wählbar."),
        storefront_landing="storefront-gutschein",
        storefront_icon="🎁",
        storefront_teaser=False,  # ссылка в футере/меню, не «направление» в сетке
    ),
    ModuleSpec(
        key="analytics",
        label_de=_("Auswertung"),
        icon="📊",
        nav_items=(NavItem("promotions:analytics", _("Analytics"), "analytics"),),
        url_prefixes=("/promotions/analytics/",),
        depends_on=("promotions",),
        description_de=_("Auswertung Ihrer Aktionen: Aufrufe, Reservierungen, Einlösungen."),
    ),
    ModuleSpec(
        key="publishing",
        label_de=_("Veröffentlichung (Kanäle)"),
        icon="📣",
        # S4a: Kanäle/Beiträge — вкладки хаба «Marketing» (Erweitert); url_prefixes = гейт.
        nav_items=(),
        url_prefixes=("/dashboard/channels/", "/dashboard/posts/"),
        description_de=_(
            "Aktionen automatisch auf Kanälen veröffentlichen (Google, Facebook, Instagram)."
        ),
    ),
    ModuleSpec(
        key="jobs",
        label_de=_("Aufträge & Angebote"),
        icon="🧰",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/auftraege/",),
        # S6: Handwerker/Werkstatt — Angebote/Kostenvoranschläge их primary (default-ON).
        # suited_for сохраняет catering-Anfrage (Restaurant/Cafe/Retreat-демо) без
        # предупреждения; suited НЕ влияет на пресет (default_disabled читает recommended).
        # Bäckerei/Metzgerei: Partyservice (Kuchenbuffets/Platten) — классика, демо-киты
        # включают jobs (2026-07-30, запрос владельца «bakery: Partyservice»).
        recommended_for=("handwerker", "werkstatt", "catering"),  # GK-1: primary кейтеринга
        suited_for=("restaurant", "cafe", "bakery", "butcher", "other"),
        description_de=_(
            "Anfragen annehmen, Angebote/Kostenvoranschläge erstellen, Aufträge abrechnen."
        ),
        storefront_label=_("Angebot anfragen"),
        storefront_blurb=_("Fordern Sie online einen Kostenvoranschlag an."),
        storefront_landing="storefront-anfrage",
        storefront_icon="🧰",
    ),
    ModuleSpec(
        key="events",
        label_de=_("Veranstaltungen (Tickets)"),
        icon="🎟️",
        # S2: свод в хаб «Verkäufe» (tab-bar). url_prefixes сохраняют middleware-гейт.
        nav_items=(),
        url_prefixes=("/dashboard/events/",),
        # S6: архетип «Veranstalter/Events» — билеты его primary (default-ON). Сверх
        # пресета подходит гидам/студиям (tour_operator/other).
        recommended_for=("events",),
        suited_for=("tour_operator", "other", "catering"),
        description_de=_("Veranstaltungen mit bezahlten Tickets und Teilnehmerliste."),
        storefront_label=_("Veranstaltungen"),
        storefront_blurb=_("Tickets für unsere Events sichern."),
        storefront_landing="storefront-events",
        storefront_icon="🎟️",
    ),
    ModuleSpec(
        key="blog",
        label_de=_("Blog / Neuigkeiten"),
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
            "online_shop",  # 2026-07-10
            "hotel",
            "tour_operator",
            "friseur",  # S6
            "handwerker",  # S6
            "werkstatt",  # S6
            "events",  # S6
            "catering",  # GK-1 (замок test_blog: блог у всех типов)
            "other",
        ),
        description_de=_(
            "Neuigkeiten und Beiträge veröffentlichen — frischer Inhalt für Kunden und Google."
        ),
        storefront_label=_("Neuigkeiten"),
        storefront_blurb=_("Aktuelles aus unserem Betrieb."),
        storefront_landing="storefront-blog",
        storefront_icon="📰",
        storefront_teaser=False,  # контент-ссылка, не «направление» в сетке архетипов
    ),
    ModuleSpec(
        key="inbox",
        label_de=_("Nachrichten (Chat & Support)"),
        icon="💬",
        # S4b: вкладка Marketing-хаба (W11-1: Kunden влит); url_prefix = гейт.
        nav_items=(),
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
            "online_shop",  # 2026-07-10
            "hotel",
            "tour_operator",
            "friseur",  # S6
            "handwerker",  # S6
            "werkstatt",  # S6
            "events",  # S6
            "catering",  # GK-1
            "other",
        ),
        description_de=_("Kundennachrichten und Support-Tickets an einem Ort beantworten."),
        storefront_label=_("Kontakt"),
        storefront_blurb=_("Stellen Sie uns eine Frage."),
        storefront_landing="storefront-message",
        storefront_icon="💬",
        storefront_teaser=False,  # утилитарная ссылка, не «направление» в сетке
    ),
    ModuleSpec(
        key="finance",
        label_de=_("Finanzen (Umsatz)"),
        icon="💶",
        nav_items=(NavItem("finance:journal", _("Finance"), "finance"),),
        url_prefixes=("/dashboard/finance/",),
        # «добавь, когда дорастёшь» (ТЗ D0b) — по умолчанию выключен у всех вертикалей
        description_de=_("Umsatzjournal: Einnahmen aus Bestellungen, Reservierungen und manuell."),
    ),
    ModuleSpec(
        key="telegram",
        label_de=_("Telegram-Bot"),
        icon="✈️",
        # S4b: вкладка Marketing-хаба (W11-1: Kunden влит); url_prefix = гейт.
        nav_items=(),
        url_prefixes=("/dashboard/telegram/",),
        # Универсальный opt-in (как finance/jobs) — выключен по умолчанию у всех.
        description_de=_(
            "Eigener Telegram-Bot: Kunden öffnen Ihren Shop als Mini App in Telegram."
        ),
    ),
    ModuleSpec(
        key="customer_account",
        label_de=_("Kundenkonto (Login für Kunden)"),
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
            "online_shop",  # 2026-07-10
            "hotel",
            "tour_operator",
            "friseur",  # S6: Termine/Bonuskarte
            "handwerker",  # S6: Aufträge/Rechnungen
            "werkstatt",  # S6: Termine/Aufträge
            "events",  # S6: Tickets
            "catering",  # GK-1: заявки/заказы клиента
        ),
        suited_for=("other",),
        description_de=_(
            "Kunden melden sich per E-Mail-Link an und sehen Bestellungen, "
            "Termine, Rechnungen und Bonuskarten."
        ),
        storefront_label=_("Mein Konto"),
        storefront_blurb=_("Bestellungen, Termine und Bonuskarten einsehen."),
        storefront_landing="account-home",
        storefront_icon="👤",
        storefront_teaser=False,  # вход в ЛК, не «направление» в сетке
    ),
    ModuleSpec(
        key="settings",
        label_de=_("Einstellungen"),
        icon="⚙️",
        # S3 (упрощение): «Website» (визуальный билдер) остаётся отдельным пунктом;
        # остальные 8 настроек сведены в ОДИН пункт-хаб «Einstellungen» с tab-bar
        # (cabinet.HUB_TABS["settings"] + «Erweitert»-ящик). url_prefixes ниже сохраняют
        # middleware-гейт всех путей — под-страницы доступны табами хаба.
        nav_items=(
            NavItem("site-home", _("Site"), "site"),  # W11-5: url → Studio, nav_key цел
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
        description_de=_("Einstellungen, Website-Baukasten, Domains, Module, Hilfe."),
    ),
    ModuleSpec(
        key="billing",
        label_de=_("Abo & Zahlung"),
        icon="💳",
        nav_items=(NavItem("billing", _("Billing"), "billing"),),
        url_prefixes=("/dashboard/billing/",),
        core=True,
        description_de=_("Abo und Zahlung."),
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
    if key in (getattr(tenant, "disabled_modules", None) or []):
        return False
    return all(is_module_active(tenant, dep) for dep in spec.depends_on)


def active_modules(tenant) -> list[ModuleSpec]:
    return [spec for spec in REGISTRY if is_module_active(tenant, spec.key)]


# AB1 (анти-Битрикс §0.1 «меню на языке задач, не сущностей»): подпись пункта
# сайдбара в языке задач/по-немецки (nav_key → метка). Фолбэк — NavItem.label
# (англ. msgid). Отдельный реестр, а не поле NavItem: все формулировки в одном
# читаемом месте, владельцу удобно править словом. T1-b: значения в gettext_lazy —
# msgid = немецкий (DE-рендер прежний), en/tr/ru/uk из .po; тип значений — lazy-строки.
# W-CL: реестр сжат до якорей компакт-сайдбара (полный «язык задач» AB1 жил
# в снесённом классик-сайдбаре; подписи табов — литералы HUB_TABS).
NAV_TASK_LABELS: dict[str, str] = {
    "dashboard": _("Übersicht"),
    "board": _("Verkäufe"),
    "promotions": _("Marketing"),
    "settings": _("Einstellungen"),
}


# ST-4b: компактный сайдбар «хабы + Website» — плоский список якорей.
# Sortiment/Kunden/Finanzen/Auswertungen достижимы через хаб-табы и
# «Funktion hinzufügen». W-CL (2026-08-05): классик-сайдбар снесён.
def sidebar_nav(tenant) -> list[dict]:
    """Якоря компактного сайдбара — из ЕДИНОГО реестра (W8, nav_registry.ANCHORS).
    Гейты — по активным модулям; nav_key = значение `nav` целевой страницы.
    SM-4: у якоря — `children` (advanced-состав его хабов, раскрытие слайдером)."""
    from apps.core import nav_registry

    items = []
    for a in nav_registry.ANCHORS:
        if a.module_key and not is_module_active(tenant, a.module_key):
            # X0 (план cabinet-cleanup-2026-08-19): якорь с хабами виден, если жив
            # ЛЮБОЙ модуль его записей — иначе отель/werkstatt (promotions выкл по
            # умолчанию) теряли единственный вход к Nachrichten/Bewertungen/Kontakte
            # и бейдж непрочитанных (исследование 2026-08-18 §3, гейт-баг).
            if not any(is_module_active(tenant, m) for m in nav_registry.hub_module_keys(a)):
                continue
        children = [
            {
                "url_name": e.url_name,
                "nav_key": e.nav_key,
                "label": e.label,
                "search": e.search,
            }
            for e in nav_registry.sidebar_children(a)
            if (not e.module_key or is_module_active(tenant, e.module_key))
            # X4: гейт по типу бизнеса — «Kitchen Display» только гастро.
            and nav_registry.allowed_for_business(e.url_name, tenant)
        ]
        # X0: «Nachrichten» — первым подпунктом якоря Marketing со СВОИМ бейджем:
        # бейдж на якоре вёл на лендинг, где непрочитанного не видно.
        if a.badge == "inbox" and is_module_active(tenant, "inbox"):
            e = nav_registry.entry_for("marketing", "inbox:list")
            if e is not None:
                children.insert(
                    0,
                    {
                        "url_name": e.url_name,
                        "nav_key": e.nav_key,
                        "label": e.label,
                        "search": e.search,
                        "badge": "inbox",
                    },
                )
        it = {
            "url_name": a.url_name,
            "nav_key": a.nav_key,
            "icon": a.icon,
            "label": a.label,
            "search": a.search,
            "children": children,
        }
        if a.badge:
            it["badge"] = a.badge
        items.append(it)
    return items


# SM-1 (решение владельца 2026-08-10): режим Простой/Эксперт снесён ЦЕЛИКОМ —
# функционал один для всех. История: S5 (ui_mode/тумблер) → S6b (скрытие по
# архетипу) → W12 (экран «Ansicht», ось в ModuleSpec). Ключ site_config["ui_mode"]
# больше не читается и не переживает normalize (прецедент W-CL / classic_ui).


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
        return _("Für alle Geschäftstypen")
    names = [str(labels.get(bt, bt)).split("/")[-1].strip() for bt in union]
    return _("Geeignet für: %(list)s") % {"list": ", ".join(names)}


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
