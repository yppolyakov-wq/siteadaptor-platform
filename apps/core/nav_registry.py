"""W8: ЕДИНЫЙ реестр навигации кабинета (план w8-nav-registry-plan-2026-08-05.md).

Один источник правды для: якорей сайдбара (`modules.sidebar_nav`), таб-баров хабов
(`cabinet.HUB_TABS` — производный, форма легаси-кортежей сохранена для замков),
карты подсветки nav_key → якорь (чинит «сайдбар не подсвечен» на ~37 экранах) и
поискового индекса палитры Ctrl+K.

Правила:
- Каждый ВИДИМЫЙ вход кабинета описан здесь ровно один раз на (hub, url_name);
  дубль-вход в двух хабах (Sortiment ↔ Angebote/Erweitert) — две записи осознанно.
- `nav_key` записи = значение context["nav"] целевой страницы. Замок
  test_w8_nav_registry сканирует литералы "nav" по apps/ — новый экран без якоря
  в карте ломает тест (класс ошибок «care»/«сирота» невозможен молча).
- Гейты видимости (модуль активен, Простой режим) применяются потребителями
  (`hub_tabs`, `sidebar_nav`) — реестр статичен и i18n-lazy.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from apps.core.archetypes import FOOD_BUSINESS_TYPES

# X4: гейт гастро-экранов (KDS/Tisch-QR) — кортеж ради frozen dataclass.
FOOD_TYPES: tuple[str, ...] = tuple(sorted(FOOD_BUSINESS_TYPES))


@dataclass(frozen=True)
class NavEntry:
    url_name: str  # reverse-имя целевой страницы
    label: str  # язык задач (lazy)
    nav_key: str  # context["nav"] целевой страницы
    hub: str  # чей таб-бар содержит запись
    module_key: str | None = None  # гейт активности (None = ядро)
    advanced: bool = False  # ящик «Erweitert»
    search: str = ""  # ключевые слова палитры (дополняют label)
    # X0 (план cabinet-cleanup-2026-08-19): owner-only экраны (мидлварь W9-10 и
    # так отдаёт сотруднику 403 — здесь СКРЫТИЕ, чтобы не показывать мёртвые табы).
    owner_only: bool = False
    # X4: «ящик Erweitert таб-бара» и «подпункты якоря в сайдбаре» были ОДНИМ
    # множеством (advanced) — склад висел в подпунктах «товаров» у парикмахера.
    # None = «как advanced» (прежнее поведение), False = остаётся в ящике, но
    # уходит из сайдбара (склад), True = подпункт сайдбара даже будучи главной
    # вкладкой (X5: «Integrationen» — вкладка ряда Verwaltung И подпункт).
    sidebar: bool | None = None
    # X4: сироты получают вход в Ctrl+K, не раздувая таб-бары/сайдбар.
    palette_only: bool = False
    # X4: доп-гейт по типу бизнеса (KDS/Tisch-QR — только гастро).
    business_types: tuple[str, ...] = ()
    # X5: ряд таб-бара («basis»/«verwaltung» у настроек). Пусто = один плоский
    # ряд, как у всех прочих хабов.
    group: str = ""
    # X5-3: query-суффикс ссылки подпункта («?from=board» у Abläufe: одна
    # страница, но заход из «Verkäufe» не должен телепортировать в настройки).
    query: str = ""


@dataclass(frozen=True)
class Anchor:
    url_name: str
    label: str  # lazy
    nav_key: str  # он же ключ подсветки якоря
    icon: str
    search: str
    module_key: str | None = None  # гейт активности якоря
    badge: str = ""  # "inbox" → бейдж непрочитанных сообщений
    hubs: tuple[str, ...] = field(default_factory=tuple)  # чьи nav_key подсвечивают якорь


# --- Якоря компакт-сайдбара (ST-4b), порядок = порядок показа -----------------
ANCHORS: tuple[Anchor, ...] = (
    Anchor(
        "dashboard",
        _("Übersicht"),
        "dashboard",
        "🏠",
        "übersicht start dashboard heute",
    ),
    Anchor(
        "verkaeufe",
        _("Verkäufe"),
        "board",
        "🗂️",
        "verkäufe bestellungen termine board kalender belegungsplan",
        hubs=("board",),
    ),
    # X4 (глоссарий §6.A4.4): раздел зовётся «Sortiment» — слово «Angebot»
    # осталось за офертой клиенту (Sofort-Angebot, смета Handwerker). URL и
    # nav_key не тронуты (мораторий X7.1 на состав якорей соблюдён).
    Anchor(
        "sellable-manage",
        _("Sortiment"),
        "sellables",
        "📦",
        "sortiment angebote produkte leistungen zimmer veranstaltungen",
        hubs=("sellables", "catalog"),
    ),
    # X0 (план cabinet-cleanup-2026-08-19): module_key — только ПРЕДПОЧТИТЕЛЬНЫЙ
    # гейт; sidebar_nav показывает якорь и при выключенном promotions, если жив
    # ЛЮБОЙ модуль его хаба (inbox/reviews/crm/…) — иначе отель терял вход к
    # сообщениям клиентов и бейдж непрочитанных (исследование 2026-08-18 §3).
    Anchor(
        "marketing-home",
        _("Marketing"),
        "promotions",
        "📣",
        "marketing aktionen kunden kampagnen nachrichten bewertungen",
        module_key="promotions",
        badge="inbox",
        hubs=("marketing",),
    ),
    # W9-9 (Р-3): «Integrationen» ушёл из якорей сайдбара — вкладка Einstellungen.
    # W11-5: якорь ведёт прямо в Studio — страница-лендинг «Site» умерла (302).
    # url_name → site-home, nav_key остаётся "site" (его эмитят 6 экранов сайта).
    # SM-4: хаб "site" — подпункты сайдбара (SEO/Domains/Medien).
    Anchor(
        "site-home",
        _("Website"),
        "site",
        "✏️",
        "website gestalten studio design",
        hubs=("site",),
    ),
    Anchor(
        "settings",
        _("Einstellungen"),
        "settings",
        "⚙️",
        "einstellungen finanzen auswertungen funktionen",
        hubs=("settings",),
    ),
)


def _e(
    hub,
    url_name,
    label,
    nav_key,
    module_key=None,
    advanced=False,
    search="",
    owner_only=False,
    sidebar=None,
    palette_only=False,
    business_types=(),
    group="",
    query="",
):
    return NavEntry(
        url_name,
        label,
        nav_key,
        hub,
        module_key,
        advanced,
        search,
        owner_only,
        sidebar,
        palette_only,
        business_types,
        group,
        query,
    )


# --- Табы хабов (порядок внутри hub = порядок показа) -------------------------
# Содержимое = бывший литерал cabinet.HUB_TABS (W7b/W-CL) 1:1 — характеризацию
# держат test_hub_tabs/test_w7_nav; здесь добавлены только search-слова палитры.
ENTRIES: tuple[NavEntry, ...] = (
    # Sortiment (рендерится на страницах каталога; якорь — «Sortiment»).
    # X4 (глоссарий §6.A4.4): подпись «Angebote» освободила слово для оферты
    # клиенту (Sofort-Angebot / смета Handwerker) — раздел товаров зовётся
    # «Sortiment» и в якоре, и в табе.
    _e("catalog", "sellable-manage", _("Sortiment"), "sellables", search="übersicht alle angebote"),
    _e(
        "catalog",
        "catalog:product-list",
        _("Produkte"),
        "catalog",
        "catalog",
        search="artikel waren sortiment",
    ),
    _e("catalog", "catalog:category-list", _("Kategorien"), "categories", "catalog"),
    # SM-4 (решение владельца): каталожные страницы — тот же компакт-бар, что на
    # «Sortiment»: main Sortiment·Produkte·Kategorien, остальное — в «Erweitert».
    # X4: складская группа осталась в ящике таб-бара, но ушла из ПОДПУНКТОВ
    # сайдбара (sidebar=False) — там место сущностям архетипа, а не учёту.
    _e(
        "catalog",
        "stock",
        _("Lager"),
        "stock",
        "catalog",
        True,
        "bestand inventur meldebestand",
        sidebar=False,
    ),
    _e(
        "catalog",
        "purchasing",
        _("Einkauf"),
        "purchasing",
        "catalog",
        True,
        "lieferanten bestellung",
        sidebar=False,
    ),
    _e("catalog", "catalog:combo-list", _("Kombi"), "combos", "catalog", True, sidebar=False),
    _e(
        "catalog",
        "imports:start",
        _("Import"),
        "imports",
        "catalog",
        True,
        "csv excel",
        sidebar=False,
    ),
    _e(
        "catalog",
        "collections:list",
        _("Kollektionen"),
        "collections",
        None,
        True,
        "podborki lookbook",
    ),
    # Verkäufe (W-CL): board/календари/список покрыты единой страницей — остаток W10.
    # Хаб как ТАБ-БАР не рендерится (W10-3): записи живут ради палитры, подсветки
    # и подпунктов сайдбара. X4: события/туры переехали в «Sortiment» (сущность),
    # здесь остались сделки и рабочие входы дня.
    _e(
        "board",
        "jobs:list",
        _("Aufträge"),
        "jobs",
        "jobs",
        search="anfragen kostenvoranschlag angebote",
    ),
    # X4 (§6.A4.2): рабочие входы дня — ПЕРВЫМИ подпунктами «Verkäufe»; отчётная
    # группа (Auswertungen/Finanzen/Berichte) осталась, но ниже.
    _e(
        "board",
        "booking:resources",
        _("Öffnungszeiten & Ressourcen"),
        "booking",
        "booking",
        True,
        "zeiten mitarbeiter tische ressourcen slots",
    ),
    _e(
        "board",
        "booking:availability",
        _("Tage blockieren"),
        "booking",
        "booking",
        True,
        "urlaub feiertag sperren verfügbarkeit",
    ),
    _e(
        "board",
        "stays:checkins",
        _("Check-ins"),
        "stays",
        "stays",
        True,
        "meldeschein anreise online-checkin",
    ),
    # X4 (§6.A4.5): KDS — гастро-экран; раньше кнопка висела у любого архетипа
    # с модулем orders (парикмахер видел «Kitchen Display»).
    _e(
        "board",
        "orders:kitchen",
        _("Kitchen Display"),
        "orders",
        "orders",
        True,
        "küche kds bon",
        business_types=FOOD_TYPES,
    ),
    # SM-4 (решение владельца 2026-08-11): отчёты и настройки процессов — подпункты
    # раздела «Verkäufe» в сайдбаре (advanced board-хаба; сам hub_tabs "board" не
    # рендерится). Auswertungen/Finanzen ПЕРЕЕХАЛИ из settings-хаба; Berichte —
    # бывший сирота stays:reports; Abläufe — дубль-запись (таб Einstellungen жив,
    # прецедент sellables/catalog; палитра дедупит по url_name).
    _e(
        "board",
        "ablaeufe",
        # VK-3 (фидбэк владельца 2026-08-20): «Abläufe» не подсказывало, что
        # именно здесь настраиваются свои статусы и колонки доски — владелец
        # искал их на самой доске. Подпись подпункта продаж говорит прямо;
        # вкладка настроек остаётся «Abläufe» (та же страница).
        _("Abläufe & Status"),
        "ablaeufe",
        None,
        True,
        # X2c: сюда переехала панель «Anfrage-Formular» — Ctrl+K обязан её
        # находить (сам приёмник POST-only и в палитру не годится).
        "status übergänge spalten anfrage-formular felder eigene status tafel",
        query="?from=board",
    ),
    # SH-15 (решение владельца «вкладка в Продажах всем» + «в меню так же вынести
    # CRM»): клиенты — подпункт раздела продаж. Ведёт на ту же вкладку страницы
    # продаж, что и ряд вкладок (один экран, одни данные); полный экран CRM с
    # компаниями/экспортом остаётся табом Marketing.
    _e(
        "board",
        "verkaeufe",
        _("Kunden"),
        "kunden",
        None,  # список клиентов есть у всех; модуль crm гейтит карточку/теги/экспорт
        True,
        "kunden kontakte crm klienten",
        query="?tab=kunden",
    ),
    # SH-14: доставка отдельным входом — заказы с доставкой одним списком
    # (фильтр вида «Liste», не новый экран).
    _e(
        "board",
        "verkaeufe",
        _("Lieferungen"),
        "lieferungen",
        "orders",
        True,
        "versand lieferung tracking sendungen",
        query="?tab=order&view=liste&versand=1",
    ),
    _e(
        "board",
        "promotions:analytics",
        _("Auswertungen"),
        "analytics",
        "analytics",
        True,
        "statistik analytics",
    ),
    _e(
        "board",
        "finance:journal",
        _("Finanzen"),
        "finance",
        "finance",
        True,
        "umsatz rechnungen datev",
    ),
    _e(
        "board",
        "stays:reports",
        _("Berichte"),
        "stays",
        "stays",
        True,
        "belegung adr revpar auslastung",
    ),
    # X4: бывшие СИРОТЫ поверхности продаж — вход через Ctrl+K (в таб-бар и
    # сайдбар не идут: palette_only). Классификация — x4-navigation-plan §4.
    _e(
        "board",
        "promotions:reservation-list",
        _("Reservierungen"),
        "reservations",
        "promotions",
        search="reservierung abholung",
        palette_only=True,
    ),
    _e(
        "board",
        "finance:invoices",
        _("Rechnungen"),
        "finance",
        "finance",
        search="rechnung invoice beleg",
        palette_only=True,
    ),
    _e(
        "board",
        "stays:channels",
        _("Channel Manager"),
        "stays",
        "stays",
        search="ota booking airbnb kanäle",
        palette_only=True,
    ),
    _e(
        "board",
        "orders:table-qr",
        _("Tisch-QR"),
        "orders",
        "orders",
        search="tisch qr code gastro",
        palette_only=True,
        business_types=FOOD_TYPES,
    ),
    # Marketing.
    _e(
        "marketing",
        "promotions:promotion-list",
        _("Aktionen"),
        "promotions",
        "promotions",
        search="rabatt deals",
    ),
    _e(
        "marketing",
        "reviews:list",
        _("Bewertungen"),
        "reviews",
        "reviews",
        search="rezension antworten",
    ),
    _e(
        "marketing",
        "promotions:coupon-campaigns",
        _("Kampagnen"),
        "campaigns",
        "crm",
        search="coupon winback",
    ),
    _e("marketing", "promotions:voucher-list", _("Gutscheine"), "vouchers", "loyalty"),
    # W11-1 (Р-2): Kunden влит в Marketing — Kontakte/Nachrichten прямыми табами
    # («Ruf & Dialog»), Telegram остаётся в Erweitert.
    _e("marketing", "crm:customer-list", _("Kontakte"), "crm", "crm", search="kunden crm"),
    _e("marketing", "inbox:list", _("Nachrichten"), "inbox", "inbox", search="chat posteingang"),
    # X4: корпоративные клиенты (CO-1) — экран был сиротой, вход через Ctrl+K.
    _e(
        "marketing",
        "crm:company-list",
        _("Firmen"),
        "crm",
        "crm",
        search="firmen unternehmen b2b konten",
        palette_only=True,
    ),
    # W10-2+решение 4а (2026-08-06): Reservierungen — вкладка Verkäufe («с первой
    # продажей»); дубль из Marketing/Erweitert убран (одна поверхность).
    _e("marketing", "promotions:redeem", _("Einlösen"), "redeem", "promotions", True, "qr scan"),
    _e(
        "marketing",
        "promotions:loyalty-list",
        _("Treuepunkte"),
        "loyalty",
        "loyalty",
        True,
        "bonus",
    ),
    _e("marketing", "telegram-settings", _("Telegram"), "telegram", "telegram", True, "bot"),
    _e(
        "marketing",
        "channels",
        _("Kanäle"),
        "channels",
        "publishing",
        True,
        "google facebook instagram",
    ),
    _e("marketing", "publishing-posts", _("Beiträge"), "posts", "publishing", True, "posting"),
    _e("marketing", "blog-list", _("Blog & News"), "blog", "blog", True),
    _e(
        "marketing",
        "promotions:newsletter",
        _("Newsletter"),
        "newsletter",
        "promotions",
        True,
        "rundschreiben e-mail",
    ),
    # Sortiment-хаб (X4: сущности архетипа — то, что бизнес ПРОДАЁТ). Порядок
    # записей = порядок подпунктов якоря «Sortiment» в сайдбаре.
    _e(
        "sellables",
        "sellable-manage",
        _("Sortiment"),
        "sellables",
        search="übersicht alle angebote",
    ),
    _e("sellables", "catalog:product-list", _("Produkte"), "catalog", "catalog", True),
    # X4: бывшие сироты — сущности НЕтоварных архетипов. У салона в подпунктах
    # «Sortiment» висел склад, а «Leistungen» не было вовсе (исследование §3).
    _e(
        "sellables",
        "booking:services",
        _("Leistungen"),
        "services",
        "booking",
        True,
        "dienstleistung termin preise dauer",
    ),
    _e(
        "sellables",
        "stays:units",
        _("Zimmer & Preise"),
        "units",
        "stays",
        True,
        "zimmer unterkunft tarife saison",
    ),
    # X4 (глоссарий): «Tickets» осталось за вкладкой СДЕЛОК в Verkäufe — сущность
    # зовётся «Veranstaltungen» (событие продаётся билетами, но это не билет).
    _e(
        "sellables",
        "events:list",
        _("Veranstaltungen"),
        "events",
        "events",
        True,
        "events tickets kurse termine",
    ),
    _e(
        "sellables",
        "events:tour-list",
        _("Reisen"),
        "tours",
        "events",
        True,
        "touren reisen route",
    ),
    _e("sellables", "catalog:category-list", _("Kategorien"), "categories", "catalog", True),
    _e("sellables", "collections:list", _("Kollektionen"), "collections", None, True),
    # Складская группа: ящик «Erweitert» таб-бара, но НЕ подпункты сайдбара.
    _e("sellables", "stock", _("Lager"), "stock", "catalog", True, sidebar=False),
    _e("sellables", "purchasing", _("Einkauf"), "purchasing", "catalog", True, sidebar=False),
    _e("sellables", "catalog:combo-list", _("Kombi"), "combos", "catalog", True, sidebar=False),
    _e("sellables", "imports:start", _("Import"), "imports", "catalog", True, sidebar=False),
    # X4: сироты-сущности — вход через Ctrl+K (x4-navigation-plan §4).
    _e(
        "sellables",
        "booking:passes",
        _("Karten & Abos"),
        "passes",
        "booking",
        search="10er-karte abo pass mitgliedschaft",
        palette_only=True,
    ),
    _e(
        "sellables",
        "events:teacher-list",
        _("Gastgeber"),
        "events",
        "events",
        search="trainer kursleiter guide gastgeber",
        palette_only=True,
    ),
    # W11-1: хаб «Kunden» удалён (Р-2) — страницы crm/inbox/telegram рендерят
    # marketing-хаб («молчаливая подмена таб-бара» умерла).
    # Einstellungen (W9-1: «базовые + по типам»; порядок = целевая структура §2.3).
    _e(
        "settings",
        "settings",
        _("Mein Geschäft"),
        "settings",
        search="kontakt öffnungszeiten firma adresse logo",
        group="basis",
    ),
    _e(
        "settings",
        "languages",
        _("Sprachen"),
        "languages",
        search="sprache locale übersetzung",
        group="basis",
    ),
    # X0: Recht/Abo/Team — owner-only (зеркалит _OWNER_ONLY мидлвари W9-10;
    # сотруднику таб не показывается вместо мёртвого 403).
    _e(
        "settings",
        "legal-docs",
        _("Recht & Steuern"),
        "legal-docs",
        search="impressum datenschutz agb widerruf steuer",
        owner_only=True,
        group="verwaltung",
    ),
    _e(
        "settings",
        "payment-settings",
        _("Zahlung & Lieferung"),
        "payments",
        search="stripe vorkasse lieferung zonen versand",
        group="basis",
    ),
    _e(
        "settings",
        "notifications-settings",
        _("Benachrichtigungen & Kanäle"),
        "notifications",
        search="care e-mail telegram erinnerung",
        group="basis",
    ),
    # W9-8: настройки процессов продаж (статусы/переходы/колонки) — раньше панели
    # были разбросаны по спискам (аудит 2026-08-05).
    _e(
        "settings",
        "ablaeufe",
        _("Abläufe"),
        "ablaeufe",
        search="status übergänge spalten workflow prozesse",
        group="verwaltung",
    ),
    # SM-4: «Website & Domains» переехал в site-хаб (подпункт раздела Website);
    # Finanzen/Auswertungen — в board-хаб (подпункты «Verkäufe»). Настройки слимятся.
    # W9-9 (Р-3): Integrationen — вкладка настроек (был якорь сайдбара).
    # X2a: advanced=True — запись становится ПОДПУНКТОМ якоря «Einstellungen»
    # (sidebar_children берёт advanced-состав хабов). Прежде единственным входом
    # с первого экрана была хаб-плитка главной, которую X2a удаляет как дубль
    # сайдбара; таб-бар настроек и палитра Ctrl+K остаются как были.
    _e(
        "settings",
        "integrations-home",
        _("Integrationen"),
        "integrations",
        None,
        # X5-1: не advanced — вкладка ряда «Verwaltung»; подпунктом якоря
        # «Einstellungen» остаётся явно (sidebar=True): вход с первого экрана
        # дал X2a, терять его нельзя.
        False,
        "integrationen stripe telegram publishing ota kanäle verbindungen",
        sidebar=True,
        group="verwaltung",
    ),
    # GK-11: Google-рейтинг (Places API) — экран в кластере настроек.
    _e(
        "settings",
        "google-reviews-settings",
        _("Google Bewertungen"),
        "integrations",
        search="google bewertungen sterne rating place id",
        palette_only=True,  # X5-2: вход — карточка Integrationen (GK-11) и Ctrl+K
    ),
    # X4: экран статуса приёма оплат (Stripe Connect) был сиротой — вход из
    # Integrationen-карточки существовал, в реестре записи не было.
    _e(
        "settings",
        "billing-payments",
        _("Zahlungen empfangen"),
        "billing",
        search="stripe connect auszahlung konto verbinden",
        owner_only=True,
        palette_only=True,
    ),
    _e(
        "settings",
        "billing",
        _("Abo & Rechnung"),
        "billing",
        search="abo tarif subscription rechnung",
        owner_only=True,
        group="verwaltung",
    ),
    # W9-10 (Р-7): членства/роли/инвайт — owner-only (middleware).
    _e(
        "settings",
        "team",
        _("Team & Zugriff"),
        "team",
        search="team mitarbeiter rollen zugriff einladen",
        owner_only=True,
        group="verwaltung",
    ),
    _e("settings", "extras", _("Zusatzleistungen"), "extras", None, True),
    _e("settings", "modules", _("Funktionen"), "modules", None, True, "module aktivieren"),
    # W12-1: режим кабинета одним экраном (Einfach/Experte + «что скрыто»).
    _e("settings", "finder-settings", _("Finder"), "finder", None, True, "fragen empfehlung"),
    _e("settings", "support:help", _("Hilfe"), "support", None, True, "anleitung hilfe"),
    # SM-4: хаб "site" — подпункты раздела Website в сайдбаре (страницы хаба нет:
    # раздел ведёт в Studio; hub_tabs "site" нигде не рендерится, как board).
    # Domains переехал из main-табов settings, Medien — из advanced settings.
    _e("site", "site-seo", _("SEO"), "seo", None, True, "meta titel beschreibung robots"),
    _e(
        "site",
        "domains",
        _("Website & Domains"),
        "domains",
        None,
        True,
        "eigene domain hinzufügen theme",
    ),
    _e("site", "media-library", _("Medien"), "media", None, True, "bilder fotos bibliothek"),
)

HUBS: tuple[str, ...] = ("catalog", "board", "marketing", "sellables", "settings", "site")

# X5-1: подписанные ряды главных вкладок (пока только хаб настроек). Порядок
# рядов = порядок показа; вкладки без группы уходят в безымянный ряд в конце.
TAB_GROUPS: tuple[tuple[str, str], ...] = (
    ("basis", _("Basis")),
    ("verwaltung", _("Verwaltung")),
)


def group_for(hub: str, url_name: str) -> str:
    """Ряд таб-бара для записи ("" — общий ряд)."""
    for e in ENTRIES:
        if e.hub == hub and e.url_name == url_name:
            return e.group
    return ""


def legacy_hub_tabs() -> dict:
    """Производный реестр в форме легаси-кортежей cabinet.HUB_TABS
    (url_name, label, nav_key, module_key, advanced) — потребители/замки целы.
    X4: palette_only-записи (бывшие сироты) в таб-бары не попадают — их вход
    только Ctrl+K."""
    return {
        hub: tuple(
            (e.url_name, e.label, e.nav_key, e.module_key, e.advanced)
            for e in ENTRIES
            if e.hub == hub and not e.palette_only
        )
        for hub in HUBS
    }


def business_types_for(url_name: str) -> tuple[str, ...]:
    """X4: гейт записи по типу бизнеса ("" — гейта нет). Потребители: hub_tabs,
    nav_palette, sidebar_nav (у всех есть tenant)."""
    for e in ENTRIES:
        if e.url_name == url_name and e.business_types:
            return e.business_types
    return ()


def allowed_for_business(url_name: str, tenant) -> bool:
    """True — запись показывается этому тенанту (гейт business_types).
    Fail-open без тенанта (тест-рендеры без запроса)."""
    types = business_types_for(url_name)
    if not types or tenant is None:
        return True
    return (getattr(tenant, "business_type", "") or "") in types


# --- Карта подсветки: nav_key страницы → nav_key якоря сайдбара ---------------
# Страницы вне хабов (легаси-поверхности продаж, лендинги, билдер) — явные записи.
_EXTRA_NAV_ANCHORS: dict[str, str] = {
    # легаси-страницы продаж (до W10) и сама единая страница
    "board": "board",
    "orders": "board",
    "booking": "board",
    "stays": "board",
    # решение 4а: список резервов — поверхность продаж (вкладка Verkäufe)
    "reservations": "board",
    # якоря-лендинги (W9-9: integrations теперь запись settings-хаба — маппится сам)
    "dashboard": "dashboard",
    "site": "site",
}


def _anchor_by_hub() -> dict[str, str]:
    out = {}
    for a in ANCHORS:
        for hub in a.hubs:
            out[hub] = a.nav_key
    return out


_HUB_ANCHOR = _anchor_by_hub()

ANCHOR_BY_NAV: dict[str, str] = {
    **{e.nav_key: _HUB_ANCHOR[e.hub] for e in ENTRIES if e.hub in _HUB_ANCHOR},
    **{a.nav_key: a.nav_key for a in ANCHORS},
    **_EXTRA_NAV_ANCHORS,
}


def anchor_for(nav_key: str) -> str:
    """nav_key якоря сайдбара для страницы с данным context["nav"] ("" — нет)."""
    return ANCHOR_BY_NAV.get(nav_key or "", "")


def owner_only_url_names() -> frozenset[str]:
    """X0: url_name'ы owner-only записей — потребители (hub_tabs/палитра) прячут
    их у сотрудников; доступ и так держит CabinetOwnerAccessMiddleware."""
    return frozenset(e.url_name for e in ENTRIES if e.owner_only)


def entry_for(hub: str, url_name: str) -> NavEntry | None:
    """Запись реестра по (hub, url_name) — для точечных потребителей
    (X0: «Nachrichten» первым подпунктом якоря Marketing)."""
    for e in ENTRIES:
        if e.hub == hub and e.url_name == url_name:
            return e
    return None


def hub_module_keys(anchor) -> set[str]:
    """X0: модульные гейты всех записей хабов якоря (для правила «якорь виден,
    если жив любой его модуль»). None-гейты (ядро) в набор не попадают."""
    return {
        e.module_key for a_hub in anchor.hubs for e in ENTRIES if e.hub == a_hub and e.module_key
    }


def sidebar_children(anchor) -> list[NavEntry]:
    """SM-4: подпункты якоря в сайдбаре = advanced-записи его хабов (единый
    реестр W8: гейты/подсветка/палитра — те же). Дедуп по url_name (Angebote
    собирает sellables+catalog — состав одинаков). Гейты модулей применяет
    вызывающий (modules.sidebar_nav)."""
    seen, out = set(), []
    for hub in anchor.hubs:
        for e in ENTRIES:
            in_sidebar = e.advanced if e.sidebar is None else e.sidebar
            if not in_sidebar or e.palette_only:
                continue  # X4: ящик «Erweitert» ≠ подпункты сайдбара (склад/сироты)
            # SH-14/15: ключ дедупа — (url_name, query): «Kunden» и «Lieferungen»
            # ведут на ОДИН экран продаж с разными вкладками/фильтрами, и по
            # голому url_name второй пункт молча исчезал бы.
            key = (e.url_name, e.query)
            if e.hub == hub and key not in seen:
                seen.add(key)
                out.append(e)
    return out


def palette_entries() -> list[dict]:
    """W8-4: индекс палитры Ctrl+K — якоря + табы (без дублей url_name).
    Гейты модулей применяет рендер (шаблон получает готовый гейтнутый список)."""
    seen, out = set(), []
    for a in ANCHORS:
        out.append(
            {
                "url_name": a.url_name,
                "label": a.label,
                "nav_key": a.nav_key,
                "module_key": a.module_key,
                "hub": "",
                "search": a.search,
            }
        )
        seen.add(a.url_name)
    for e in ENTRIES:
        # Палитра адресует экраны по url_name (без query) — записи «Kunden»/
        # «Lieferungen» (SH-14/15) ведут на уже присутствующий «Verkäufe».
        if e.url_name in seen:
            continue
        seen.add(e.url_name)
        out.append(
            {
                "url_name": e.url_name,
                "label": e.label,
                "nav_key": e.nav_key,
                "module_key": e.module_key,
                "hub": e.hub,
                "search": e.search,
            }
        )
    return out
