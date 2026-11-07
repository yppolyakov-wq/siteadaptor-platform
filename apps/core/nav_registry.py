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
# VF-5 (вопрос владельца 2026-08-24: «Küchenanzeige у продуктового?»): набор
# пищевой МАРКИРОВКИ (bakery/butcher/grocery/…) — не то же, что «есть кухня».
# KDS — тем, кто ГОТОВИТ под заказ; Tisch-QR — заведениям со столами.
KITCHEN_TYPES: tuple[str, ...] = ("cafe", "catering", "restaurant")
# AIS-M M-0: «стол, а не мастер» — один источник с направлениями.
from apps.core.directions import TABLE_TYPES  # noqa: E402


@dataclass(frozen=True)
class NavEntry:
    url_name: str  # reverse-имя целевой страницы
    label: str  # язык задач (lazy)
    nav_key: str  # context["nav"] целевой страницы
    hub: str  # чей таб-бар содержит запись
    module_key: str | None = None  # гейт активности (None = ядро)
    advanced: bool = False  # ящик «Erweitert»
    search: str = ""  # ключевые слова палитры (дополняют label)
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
    # KA-12 E8.4: группа подменю (подзаголовок, SUBMENU_GROUPS[hub]). Пусто = блок без
    # ряд, как у всех прочих хабов.
    group: str = ""
    # X5-3: query-суффикс ссылки подпункта («?from=board» у Abläufe: одна
    # страница, но заход из «Verkäufe» не должен телепортировать в настройки).
    query: str = ""
    # KA-12 E8.1/E8.12: у КАЖДОЙ записи есть гейт — модуль, «любой из модулей»,
    # направление, тип бизнеса — либо она в UNIVERSAL с причиной («экран для всех»).
    modules_any: tuple[str, ...] = ()
    direction: str = ""  # "waren" | "gastro" — см. direction_active()


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
    # KA-12 E8.3: условный якорь — виден, если активен ЛЮБОЙ из модулей; иначе его
    # подпункты уходят в якорь `fallback` группой `fallback_group`.
    modules_any: tuple[str, ...] = ()
    fallback: str = ""
    fallback_group: str = ""
    # Цели клика по разделу: первый видимый экран (иначе url_name).
    targets: tuple[str, ...] = ()


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
        hubs=("sellables",),
    ),
    # X0 (план cabinet-cleanup-2026-08-19): module_key — только ПРЕДПОЧТИТЕЛЬНЫЙ
    # гейт; sidebar_nav показывает якорь и при выключенном promotions, если жив
    # ЛЮБОЙ модуль его хаба (inbox/reviews/crm/…) — иначе отель терял вход к
    # сообщениям клиентов и бейдж непрочитанных (исследование 2026-08-18 §3).
    Anchor(
        "marketing-home",
        _("Marketing & Kunden"),
        "promotions",
        "📣",
        "marketing aktionen kunden kampagnen nachrichten bewertungen",
        module_key="promotions",
        badge="inbox",
        hubs=("marketing",),
        # KA-12 E8.6: лендинг убран (302) — раздел ведёт на первый активный экран.
        targets=("inbox:list", "promotions:promotion-list", "reviews:list", "crm:customer-list"),
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
    # KA-12 E8.3 (решение владельца KA-4 В-1…В-6): седьмой якорь «Finanzen» — только при
    # модуле finance или analytics; мораторий X7 снят ровно для него. Без них его
    # подпункты живут группой «Zahlen & Finanzen» в Einstellungen.
    Anchor(
        "finance:journal",
        _("Finanzen"),
        "finance",
        "💶",
        "finanzen journal rechnungen datev auswertungen zahlungen",
        hubs=("finance",),
        modules_any=("finance", "analytics"),
        fallback="settings",
        fallback_group="finanzen",
        targets=("finance:journal", "promotions:analytics", "payments-page"),
    ),
    # SR-5 (вариант Б, прецедент W11-5): якорь ведёт на страницу-обзор
    # /dashboard/einstellungen/ — url_name → einstellungen-home, nav_key
    # остаётся "settings" (его эмитят все страницы настроек). Обзор становится
    # первым подпунктом подменю автоматически (modules.sidebar_nav).
    Anchor(
        "einstellungen-home",
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
    sidebar=None,
    palette_only=False,
    business_types=(),
    group="",
    query="",
    modules_any=(),
    direction="",
):
    return NavEntry(
        url_name,
        label,
        nav_key,
        hub,
        module_key,
        advanced,
        search,
        sidebar,
        palette_only,
        business_types,
        group,
        query,
        modules_any,
        direction,
    )


# --- Табы хабов (порядок внутри hub = порядок показа) -------------------------
# Содержимое = бывший литерал cabinet.HUB_TABS (W7b/W-CL) 1:1 — характеризацию
# держат test_hub_tabs/test_w7_nav; здесь добавлены только search-слова палитры.
ENTRIES: tuple[NavEntry, ...] = (
    # KA-12 E8.1: хаб "catalog" (дубль "sellables" со времён SM-4) снят — каталожные
    # экраны живут одной строкой в "sellables"; их nav_key подсвечивают якорь Sortiment.
    # Verkäufe (W-CL): board/календари/список покрыты единой страницей — остаток W10.
    # Хаб как ТАБ-БАР не рендерится (W10-3): записи живут ради палитры, подсветки
    # и подпунктов сайдбара. X4: события/туры переехали в «Sortiment» (сущность),
    # здесь остались сделки и рабочие входы дня.
    # VF-10 (фидбэк 2026-08-25 «Заявки не нажимается»): пункт вёл на jobs:list →
    # 302 → verkaeufe?tab=job — у архетипов с одним направлением (catering) это
    # ТА ЖЕ страница, что «Verkäufe», и подсветка не переходила: клик выглядел
    # мёртвым. Прямая ссылка с query даёт видимый отклик (подсветка переезжает).
    _e(
        "board",
        "verkaeufe",
        _("Aufträge"),
        "jobs",
        "jobs",
        search="anfragen kostenvoranschlag angebote",
        query="?tab=job",
    ),
    # X4 (§6.A4.2): рабочие входы дня — ПЕРВЫМИ подпунктами «Verkäufe»; отчётная
    # группа (Auswertungen/Finanzen/Berichte) осталась, но ниже.
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
        _("Küche"),
        "orders",
        "orders",
        True,
        "küche kds bon",
        business_types=KITCHEN_TYPES,
    ),
    # KA-12 WR-7: «Produktion» — Σ штук под выдачи дня (пекарня/мясная/кафе/кейтеринг).
    _e(
        "board",
        "orders:production",
        _("Produktion"),
        "production",
        "orders",
        True,
        "produktion backliste zerlegeliste vorbestellung heute menge",
        business_types=FOOD_TYPES,
    ),
    # KA-12 GA-6: «Tischplan» — столы по зонам на момент времени (зал ресторана/кафе).
    _e(
        "board",
        "booking:tischplan",
        _("Tischplan"),
        "tischplan",
        "booking",
        True,
        "tisch tische zuweisen walk-in saal plan belegung",
        business_types=TABLE_TYPES,
    ),
    # SM-4: отчёты — подпункты раздела «Verkäufe» (Auswertungen/Finanzen ПЕРЕЕХАЛИ из
    # settings-хаба; Berichte — бывший сирота stays:reports). KA-12 E8.2: дубль
    # «Abläufe & Status» и пункт «Kunden» сняты — настройка процессов живёт в
    # Einstellungen (кнопка «⚙️» тулбара Verkäufe ведёт туда же), клиенты — вкладкой
    # страницы продаж и разделом Marketing.
    # SH-14 → R7-3 (фидбэк владельца 2026-08-24 «доставку нужно вынести в
    # отдельную страницу, там могут формироваться отгрузочные накладные»):
    # доставка стала СВОИМ экраном (адрес/трек-номер/Lieferschein), а не
    # фильтром списка.
    _e(
        "board",
        "orders:deliveries",
        _("Lieferungen"),
        "deliveries",
        "orders",
        True,
        "versand lieferung tracking sendungen lieferschein",
    ),
    # X4: бывшие СИРОТЫ поверхности продаж — вход через Ctrl+K (в таб-бар и
    # сайдбар не идут: palette_only). Классификация — x4-navigation-plan §4.
    # KA-12 E8.1: резервы — вкладка страницы продаж; палитра ведёт туда, а не на
    # легаси-список (тот остаётся экраном лёгкого кабинета и Mini App).
    _e(
        "board",
        "verkaeufe",
        _("Reservierungen"),
        "reservations",
        "promotions",
        search="reservierung abholung zurückgelegt",
        palette_only=True,
        query="?tab=reservation",
        direction="reservations",
    ),
    # MX-2c: сводные доп-продажи — вход из тулбара Verkäufe + палитра.
    _e(
        "board",
        "verkaeufe-zusatz",
        _("Zusatzverkäufe"),
        "board",
        search="zusatz extras frühstück optionen verkauft",
        palette_only=True,
        modules_any=("booking", "stays", "events"),
    ),
    _e(
        "board",
        "orders:table-qr",
        _("Tisch-QR"),
        "orders",
        "orders",
        search="tisch qr code gastro",
        palette_only=True,
        business_types=TABLE_TYPES,
    ),
    # Marketing & Kunden (KA-12 E8.4): Kunden · Aktionen · Reichweite.
    _e(
        "marketing",
        "inbox:list",
        _("Nachrichten"),
        "inbox",
        "inbox",
        search="chat posteingang",
        group="kunden",
    ),
    _e(
        "marketing",
        "crm:customer-list",
        _("Kunden"),
        "crm",
        "crm",
        search="kunden crm",
        group="kunden",
    ),
    _e(
        "marketing",
        "promotions:promotion-list",
        _("Aktionen"),
        "promotions",
        "promotions",
        search="rabatt deals",
        group="aktionen",
    ),
    # VF-20b (решение владельца 2026-08-25 «поставить рядом, но не объединять»):
    # Кампании — сразу за Акциями (одна группа задач: «предложить и разослать»),
    # каждая остаётся своим экраном со своим модульным гейтом.
    _e(
        "marketing",
        "promotions:coupon-campaigns",
        _("Kampagnen"),
        "campaigns",
        "crm",
        search="coupon winback",
        group="aktionen",
    ),
    # PT-5: «Aktionstypen» — ось типов акции и их вывод (шаблон · раскладка ·
    # сетка/лента · форма карточки). Стоит ПОСЛЕ Кампаний: правило VF-20b
    # («Kampagnen сразу за Aktionen») — решение владельца, его замок держит.
    _e(
        "marketing",
        "promotions:promo-type-list",
        _("Aktionstypen"),
        "promo-types",
        "promotions",
        True,
        search="gruppen rubriken typen mystery vorbestellung",
        group="aktionen",
    ),
    # T-8.4: ассистент «Schnell-Aktion» — вход из палитры (основной вход — «＋»
    # в списке акций и мобильная плавающая кнопка).
    _e(
        "marketing",
        "promotions:promotion-quick",
        _("Neue Aktion"),
        "promotions",
        "promotions",
        search="schnell handy foto neu wiederholen",
        palette_only=True,
        group="aktionen",
    ),
    _e(
        "marketing",
        "reviews:list",
        _("Bewertungen"),
        "reviews",
        "reviews",
        search="rezension antworten",
        group="kunden",
    ),
    # В5 V5-3: «Stadtportal» — учёт результатов каталога города. Модуль None: каталог
    # города есть у всех типов; пустые состояния экрана объясняют, почему цифр нет.
    _e(
        "marketing",
        "portal-stats",
        _("Stadtportal"),
        "portal-stats",
        search="stadtportal besuche klicks statistik portal aufrufe",
        group="reichweite",
    ),
    _e(
        "marketing",
        "promotions:voucher-list",
        _("Gutscheine"),
        "vouchers",
        "loyalty",
        group="aktionen",
    ),
    # W11-1 (Р-2): Kunden влит в Marketing — Kontakte/Nachrichten прямыми табами
    # («Ruf & Dialog»), Telegram остаётся в Erweitert.
    # X4: корпоративные клиенты (CO-1) — экран был сиротой, вход через Ctrl+K.
    _e(
        "marketing",
        "crm:company-list",
        _("Firmen"),
        "crm",
        "crm",
        search="firmen unternehmen b2b konten",
        palette_only=True,
        group="kunden",
    ),
    # W10-2+решение 4а (2026-08-06): Reservierungen — вкладка Verkäufe («с первой
    # продажей»); дубль из Marketing/Erweitert убран (одна поверхность).
    _e(
        "marketing",
        "promotions:redeem",
        _("Einlösen"),
        "redeem",
        "promotions",
        True,
        "qr scan",
        group="aktionen",
    ),
    _e(
        "marketing",
        "promotions:loyalty-list",
        _("Treuepunkte"),
        "loyalty",
        "loyalty",
        True,
        "bonus",
        group="aktionen",
    ),
    _e(
        "marketing",
        "channels",
        _("Kanäle"),
        "channels",
        "publishing",
        True,
        "google facebook instagram",
        group="reichweite",
    ),
    # Д3: Google-Profil (Standort, Öffnungszeiten, Angebote) — вход с «Kanäle» и палитры.
    _e(
        "marketing",
        "gbp-sync",
        _("Google-Profil"),
        "channels",
        "publishing",
        search="google profil öffnungszeiten standort sync",
        palette_only=True,
        group="reichweite",
    ),
    # M23b.2: фид товаров для Google Merchant Center — вход с «Google-Profil» и «Kanäle».
    _e(
        "marketing",
        "gbp-merchant",
        _("Google Merchant Center"),
        "channels",
        "publishing",
        search="google merchant produktfeed shopping feed produkte",
        palette_only=True,
        group="reichweite",
    ),
    _e(
        "marketing",
        "publishing-posts",
        _("Beiträge"),
        "posts",
        "publishing",
        True,
        "posting",
        group="reichweite",
    ),
    _e("marketing", "blog-list", _("Blog"), "blog", "blog", True, group="reichweite"),
    _e(
        "marketing",
        "promotions:newsletter",
        _("Newsletter"),
        "newsletter",
        "promotions",
        True,
        "rundschreiben e-mail",
        group="reichweite",
    ),
    # Sortiment-хаб (X4: сущности архетипа — то, что бизнес ПРОДАЁТ). Порядок
    # записей = порядок подпунктов якоря «Sortiment» в сайдбаре.
    _e(
        "sellables",
        "sellable-manage",
        _("Sortiment"),
        "sellables",
        search="übersicht alle angebote artikel waren produkte",
    ),
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
    # KA-12 Z-3 (О-9): цены и ограничения по дням — подпункт «Sortiment» у отеля.
    _e(
        "sellables",
        "stays:price-calendar",
        _("Preise & Verfügbarkeit"),
        "price-calendar",
        "stays",
        True,
        "preise kalender verfügbarkeit stopp mindestaufenthalt tagespreis",
    ),
    # UX-D D4.1: тарифы — свой экран (раньше карточка во вкладке списка номеров).
    _e(
        "sellables",
        "stays:rate-plans",
        _("Tarife"),
        "rate-plans",
        "stays",
        True,
        "tarife frühstück halbpension nicht erstattbar rate plan",
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
    _e(
        "sellables",
        "catalog:category-list",
        _("Kategorien"),
        "categories",
        "catalog",
        True,
        direction="waren",
    ),
    # FB-16: page templates live only under Website (Seitenvorlagen).
    _e("sellables", "collections:list", _("Kollektionen"), "collections", None, True, "lookbook"),
    # R2 (редизайн B, утверждённая структура): складская группа — подпункты
    # сайдбара «Sortiment» (ящик «Erweitert» на страницах больше не рендерится,
    # каждая страница живёт ровно в одном месте; X4-решение пересмотрено).
    # KA-12 E8.1: учёт товаров — направлению «Waren» (тип, модуль заказов или хотя бы
    # один активный товар); парикмахер без товаров их не видит.
    _e(
        "sellables",
        "stock",
        _("Lager"),
        "stock",
        "catalog",
        True,
        "bestand inventur meldebestand",
        direction="waren",
    ),
    _e(
        "sellables",
        "purchasing",
        _("Einkauf"),
        "purchasing",
        "catalog",
        True,
        "lieferanten bestellung",
        direction="waren",
    ),
    _e(
        "sellables",
        "catalog:combo-list",
        _("Kombi"),
        "combos",
        "catalog",
        True,
        "menü set paket",
        direction="waren|gastro",
    ),
    _e(
        "sellables",
        "imports:start",
        _("Import"),
        "imports",
        "catalog",
        True,
        "csv excel",
        # Импорт — путь к первым товарам: и для гастро (меню из Excel).
        direction="waren|gastro",
    ),
    _e(
        "sellables",
        "imports:website",
        _("Von der Website importieren"),
        "imports",
        "catalog",
        True,
        search="website import übernehmen shop seite",
        # Вход — со страницы «Import» и из Ctrl+K; состав подменю «Sortiment» не трогаем.
        palette_only=True,
    ),
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
    # KA-12 E8.3: хаб «Finanzen» — Überblick (оплаты, отчёты) · Buchhaltung (журнал,
    # счета, расходы, результат, открытые позиции, банк). Был разбросан по «Verkäufe»
    # и палитре; без finance/analytics — группа «Zahlen & Finanzen» в Einstellungen.
    _e(
        "finance",
        "payments-page",
        _("Zahlungen"),
        "zahlungen",  # свой ключ: "payments" занят страницей «Zahlarten & Lieferung»
        None,  # деньги есть у любого продающего модуля; finance не требуется
        True,
        "zahlungen bezahlt offen stripe vorkasse geld",
        group="ueberblick",
    ),
    _e(
        "finance",
        "promotions:analytics",
        _("Auswertungen"),
        "analytics",
        "analytics",
        True,
        "statistik analytics",
        group="ueberblick",
    ),
    _e(
        "finance",
        "stays:reports",
        _("Berichte"),
        "stays-reports",
        "stays",
        True,
        "belegung adr revpar auslastung",
        group="ueberblick",
    ),
    _e(
        "finance",
        "stays:kurtaxe",
        _("Kurtaxe-Meldung"),
        "stays-kurtaxe",
        "stays",
        True,
        "kurtaxe tourismusabgabe gemeinde meldeschein",
        group="ueberblick",
    ),
    _e(
        "finance",
        "finance:journal",
        _("Journal"),
        "finance",
        "finance",
        True,
        "umsatz rechnungen datev",
        group="buchhaltung",
    ),
    _e(
        "finance",
        "finance:invoices",
        _("Rechnungen"),
        "finance",
        "finance",
        True,
        "rechnung invoice beleg",
        group="buchhaltung",
    ),
    _e(
        "finance",
        "finance:expenses",
        _("Ausgaben"),
        "finance",
        "finance",
        True,
        "ausgaben kosten einkauf spesen",
        group="buchhaltung",
    ),
    _e(
        "finance",
        "finance:ergebnis",
        _("Ergebnis"),
        "finance",
        "finance",
        True,
        "ergebnis gewinn marge saldo",
        group="buchhaltung",
    ),
    _e(
        "finance",
        "finance:offene",
        _("Offene Posten"),
        "finance",
        "finance",
        True,
        "offene posten schulden unbezahlt mahnung",
        group="buchhaltung",
    ),
    _e(
        "finance",
        "finance:bank",
        _("Bankabgleich"),
        "finance",
        "finance",
        True,
        "bank kontoauszug abgleich umsatz vorkasse",
        group="buchhaltung",
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
        group="geschaeft",
    ),
    _e(
        "settings",
        "languages",
        _("Sprachen"),
        "languages",
        search="sprache locale übersetzung",
        group="geschaeft",
    ),
    # KA-12 E4.1a: закрытие всего бизнеса (запись, самовывоз, «Jetzt geöffnet», баннер).
    _e(
        "settings",
        "betriebsferien",
        _("Betriebsferien"),
        "betriebsferien",
        search="urlaub ferien geschlossen feiertag pause",
        group="geschaeft",
    ),
    # X0: Recht/Abo/Team — owner-only (зеркалит _OWNER_ONLY мидлвари W9-10;
    # сотруднику таб не показывается вместо мёртвого 403).
    _e(
        "settings",
        "legal-docs",
        _("Recht & Steuern"),
        "legal-docs",
        search="impressum datenschutz agb widerruf steuer",
        group="geschaeft",
    ),
    # UX-D D6.2b: настройки склада (Meldebestand, Chargen/MHD, Standorte) — раньше
    # формы на рабочей странице склада над таблицей.
    _e(
        "settings",
        "stock-settings",
        _("Lager"),
        "stock-settings",
        "catalog",
        True,
        "meldebestand chargen mhd standorte lager",
        group="verkauf",
        direction="waren",
    ),
    # AIS W4-5a: «Verkauf öffnen» — короткие вопросы (доставка, Vorkasse …) по направлению
    _e(
        "settings",
        "verkauf-oeffnen",
        _("Verkauf öffnen"),
        "settings",
        search="verkauf öffnen liefern vorkasse stornierung fragen",
        group="verkauf",
        modules_any=("orders", "booking", "stays", "events", "jobs"),
    ),
    _e(
        "settings",
        "payment-settings",
        _("Zahlarten & Lieferung"),
        "payments",
        search="stripe vorkasse lieferung zonen versand",
        group="verkauf",
    ),
    _e(
        "settings",
        "notifications-settings",
        _("Kanäle & Benachrichtigungen"),
        "notifications",
        search="care e-mail telegram erinnerung",
        group="kanaele",
    ),
    # W9-8: настройки процессов продаж (статусы/переходы/колонки) — раньше панели
    # были разбросаны по спискам (аудит 2026-08-05).
    _e(
        "settings",
        "ablaeufe",
        _("Abläufe"),
        "ablaeufe",
        # X2c: панель «Anfrage-Formular» живёт здесь — Ctrl+K её находит.
        search="status übergänge spalten workflow prozesse anfrage-formular felder eigene status",
        group="verkauf",
    ),
    # SM-4: «Website & Domains» переехал в site-хаб (подпункт раздела Website);
    # Finanzen/Auswertungen — в board-хаб (подпункты «Verkäufe»). Настройки слимятся.
    # KA-12 E8.4: свой Telegram-бот — канал, не маркетинг (был в Marketing/Erweitert).
    _e(
        "settings",
        "telegram-settings",
        _("Telegram-Bot"),
        "telegram",
        "telegram",
        True,
        "bot telegram eigener",
        group="kanaele",
    ),
    # UX-D D8.2: авто-рассылки (Win-back, Geburtstagsgruß) — были раскрыты формами
    # на рабочем экране кампаний.
    _e(
        "settings",
        "promotions:campaign-automation",
        _("Automatische Mailings"),
        "campaign-automation",
        "crm",
        True,
        "win-back winback geburtstag automatisch gutschein mailing",
        group="kanaele",
    ),
    # GK-11: Google-рейтинг (Places API) — экран в кластере настроек.
    _e(
        "settings",
        "google-reviews-settings",
        _("Google Bewertungen"),
        "integrations",
        search="google bewertungen sterne rating place id",
        palette_only=True,  # X5-2: вход — карточка Integrationen (GK-11) и Ctrl+K
        group="kanaele",
    ),
    # X4: экран статуса приёма оплат (Stripe Connect) был сиротой — вход из
    # Integrationen-карточки существовал, в реестре записи не было.
    _e(
        "settings",
        "billing-payments",
        _("Zahlungen empfangen"),
        "billing",
        search="stripe connect auszahlung konto verbinden",
        palette_only=True,
        group="system",
    ),
    _e(
        "settings",
        "billing",
        _("Abo & Rechnung"),
        "billing",
        search="abo tarif subscription rechnung",
        group="system",
    ),
    # W9-10 (Р-7): членства/роли/инвайт — owner-only (middleware).
    _e(
        "settings",
        "team",
        _("Team & Zugriff"),
        "team",
        search="team mitarbeiter rollen zugriff einladen",
        group="geschaeft",
    ),
    _e(
        "settings",
        "extras",
        _("Zusatzleistungen"),
        "extras",
        None,
        True,
        modules_any=("booking", "stays", "events"),
        group="verkauf",
    ),
    # KA-12 E8.2: настройки записи и каналов отеля — в Einstellungen (были
    # подпунктами «Verkäufe» рядом с рабочими экранами дня).
    _e(
        "settings",
        "booking:resources",
        _("Öffnungszeiten & Ressourcen"),
        "booking-resources",
        "booking",
        True,
        "zeiten mitarbeiter tische ressourcen slots",
        group="termine",
    ),
    # UX-D D2.1: правила записи для всех услуг (правило неявок, сроки отмены) — были
    # свёрнутым блоком над списком услуг.
    _e(
        "settings",
        "booking:booking-rules",
        _("Buchungsregeln"),
        "booking-rules",
        "booking",
        True,
        "nichterscheinen anzahlung storno stornofrist no-show regeln",
        group="termine",
    ),
    _e(
        "settings",
        "booking:availability",
        _("Tage blockieren"),
        "booking-availability",
        "booking",
        True,
        "urlaub feiertag sperren verfügbarkeit",
        group="termine",
    ),
    # UX-D D4.2: правила цены и продаж номеров — из вкладки списка номеров (П4).
    _e(
        "settings",
        "stays:price-rules",
        _("Preise & Regeln"),
        "price-rules",
        "stays",
        True,
        "rabatt frühbucher last minute dynamisch lücken mindestaufenthalt anreise",
        group="zimmer",
    ),
    # UX-D D4.3: Kurtaxe, Hausordnung, часы заезда/выезда, удобства на карточке номера.
    _e(
        "settings",
        "stays:stay-settings",
        _("Unterkunft"),
        "stay-settings",
        "stays",
        True,
        "kurtaxe hausordnung check-in check-out anreise abreise ausstattung",
        group="zimmer",
    ),
    _e(
        "settings",
        "stays:channels",
        _("Kanal-Manager"),
        "channel-manager",
        "stays",
        True,
        "ota booking airbnb kanäle",
        group="zimmer",
    ),
    _e(
        "settings",
        "modules",
        _("Richtungen & Funktionen"),
        "modules",
        None,
        True,
        "module aktivieren funktionen richtung verkaufen wie",
        group="system",
    ),
    # W12-1: режим кабинета одним экраном (Einfach/Experte + «что скрыто»).
    _e(
        "settings",
        "finder-settings",
        _("Finder"),
        "finder",
        None,
        True,
        "fragen empfehlung",
        group="system",
    ),
    _e(
        "settings",
        "support:help",
        _("Hilfe"),
        "support",
        None,
        True,
        "anleitung hilfe",
        group="system",
    ),
    # SM-4: хаб "site" — подпункты раздела Website в сайдбаре (страницы хаба нет:
    # раздел ведёт в Studio; hub_tabs "site" нигде не рендерится, как board).
    # Domains переехал из main-табов settings, Medien — из advanced settings.
    # DL-7b: переключатель шаблонов (сборки + Look'и) — первым подпунктом Website.
    _e("site", "design", _("Design"), "design", None, False, "vorlage look theme farben schrift"),
    # STU-19d: every page of the site in one place (Studio keeps block order/texts).
    _e(
        "site",
        "page-templates-website",
        _("Seitenvorlagen"),
        "seitenvorlagen",
        None,
        True,
        "vorlage layout raster kartenform startseite blog textseiten",
    ),
    _e("site", "site-seo", _("SEO"), "seo", None, True, "meta titel beschreibung robots"),
    # M21.1: старые адреса после переезда с другой платформы (301/410).
    _e(
        "site",
        "site-redirects",
        _("Weiterleitungen"),
        "redirects",
        None,
        True,
        "umzug alte adressen 301 410 redirect",
    ),
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

HUBS: tuple[str, ...] = ("board", "marketing", "sellables", "finance", "settings", "site")

# KA-12 E8.4/E8.12: подзаголовки подменю по хабам (порядок = порядок показа). Запись без
# группы стоит в конце безымянного блока. Размер подменю считается по группе (≤ 7).
SUBMENU_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "marketing": (
        ("kunden", _("Kunden")),
        ("aktionen", _("Aktionen")),
        ("reichweite", _("Reichweite")),
    ),
    "finance": (
        ("ueberblick", _("Überblick")),
        ("buchhaltung", _("Buchhaltung")),
    ),
    "settings": (
        ("geschaeft", _("Geschäft")),
        ("verkauf", _("Verkauf")),
        ("termine", _("Termine")),
        ("zimmer", _("Zimmer")),
        ("kanaele", _("Kanäle & Benachrichtigungen")),
        ("finanzen", _("Zahlen & Finanzen")),
        ("system", _("System")),
    ),
}


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


# KA-12 E8.1 → AIS-M M-0: «waren» вычисляет apps.core.directions (единственный источник
# ответа «как продаёт бизнес»); здесь — гейты навигации поверх него.
def direction_active(tenant, direction: str) -> bool:
    """Активно ли направление у тенанта. Fail-open: без тенанта или при ошибке — да."""
    if not direction or tenant is None:
        return True
    if "|" in direction:  # «waren|gastro» — любое из направлений
        return any(direction_active(tenant, d) for d in direction.split("|"))
    btype = getattr(tenant, "business_type", "") or ""
    if direction == "gastro":
        return btype in FOOD_TYPES
    if direction == "reservations":
        # Вкладка «Reservierungen» продаж живёт только при записях (sales_page) —
        # без них вход вёл бы на чужую вкладку.
        cached = getattr(tenant, "_nav_has_reservations", None)
        if cached is None:
            from apps.core import sales_page

            cached = sales_page._has_reservations()
            try:
                tenant._nav_has_reservations = cached
            except Exception:  # noqa: BLE001
                pass
        return cached
    if direction != "waren":
        return True
    from apps.core import directions

    return directions.is_active(tenant, "waren")


# KA-12 E8.12: экраны «для всех» — без гейта модуля/направления, с причиной. Запись
# без гейта и без строки здесь краснит CI (test_ka_w2_nav_locks).
UNIVERSAL: dict[str, str] = {
    "settings": "данные бизнеса — у каждого",
    "languages": "языки витрины — у каждого",
    "betriebsferien": "закрытие бизнеса на отпуск/праздники — у каждого бизнеса (только владелец)",
    "legal-docs": "правовые тексты — у каждого",
    "team": "команда и доступ — у каждого",
    "billing": "подписка — у каждого",
    "billing-payments": "приём оплаты — у каждого",
    "payment-settings": "способы оплаты и доставки — у каждого",
    "payments-page": "журнал оплат — у каждого",
    "notifications-settings": "уведомления и каналы — у каждого",
    "modules": "включение функций — у каждого",
    "support:help": "помощь — у каждого",
    "design": "дизайн сайта — у каждого",
    "site-seo": "SEO сайта — у каждого",
    # STU-19d: the screens show only the page types whose module is on.
    "page-templates-website": "шаблоны всех страниц сайта — у каждого",
    "site-redirects": "переадресации старых адресов — у каждого",
    "domains": "домены — у каждого",
    "media-library": "медиатека — у каждого",
    "sellable-manage": "обзор ассортимента — у каждого",
    "ablaeufe": "статусы и переходы — у каждого",
    "portal-stats": "статистика каталога города — у каждого",
    "finder-settings": "опция «Finder» — у каждого",
    "google-reviews-settings": "рейтинг Google — у каждого",
    # UB3-2: подборки собирают товары, услуги и номера — не только у магазинов.
    "collections:list": "подборки товаров, услуг и номеров — у каждого",
}


def entry_gate(entry: NavEntry) -> str:
    """Чем гейтится запись (для замков): модуль, направление, тип или причина."""
    if entry.module_key:
        return f"module:{entry.module_key}"
    if entry.modules_any:
        return "modules:" + ",".join(entry.modules_any)
    if entry.direction:
        return f"direction:{entry.direction}"
    if business_types_for(entry.url_name):
        return "business_types"
    return UNIVERSAL.get(entry.url_name, "")


#: AIS-M M-1d (§5.3/§5.7): типы, у которых акции включены базово, но пункты меню
#: «Aktionen» появляются только с первой акцией (вход — карточка на «Richtungen &
#: Funktionen» и «Neue Aktion» в палитре).
LATE_PROMO_TYPES = frozenset({"hotel", "tour_operator", "handwerker", "werkstatt"})


def has_promotions(tenant) -> bool:
    """Есть ли у бизнеса хоть одна акция (мемо на объекте тенанта, fail-open)."""
    memo = getattr(tenant, "_m1d_has_promos", None)
    if memo is not None:
        return memo
    from django.db import connection, transaction

    from apps.core import lite_cabinet

    memo = True
    try:
        if not lite_cabinet.is_lite(tenant) and connection.schema_name == getattr(
            tenant, "schema_name", None
        ):
            from apps.promotions.models import Promotion

            with transaction.atomic():
                memo = Promotion.objects.exists()
    except Exception:  # noqa: BLE001 — хром меню не падает, пункт остаётся видимым
        memo = True
    try:
        tenant._m1d_has_promos = memo
    except Exception:  # noqa: BLE001
        pass
    return memo


def late_promo_hidden(entry: NavEntry, tenant) -> bool:
    if entry.module_key != "promotions" or entry.group != "aktionen" or entry.palette_only:
        return False
    if getattr(tenant, "business_type", "") not in LATE_PROMO_TYPES:
        return False
    return not has_promotions(tenant)


def entry_visible(entry: NavEntry, tenant, owner_hidden=frozenset(), *, menu: bool = False) -> bool:
    """Единый гейт показа записи — сайдбар, палитра, обзор настроек и замки.

    ``menu=True`` — показ в меню/палитре: дополнительно прячет «поздние» акции
    (M-1d). Ссылки и счётчики (assistant, day_home) этот гейт не трогает."""
    from apps.core.modules import is_module_active

    if entry.module_key and not is_module_active(tenant, entry.module_key):
        return False
    if entry.modules_any and not any(is_module_active(tenant, m) for m in entry.modules_any):
        return False
    if entry.direction and not direction_active(tenant, entry.direction):
        return False
    if not allowed_for_business(entry.url_name, tenant):
        return False
    if menu and late_promo_hidden(entry, tenant):
        return False
    return entry.url_name not in owner_hidden and (entry.url_name + entry.query) not in owner_hidden


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
    # SR-1: записи «Produkte» умерли вместе со страницей, но формы товара
    # по-прежнему эмитят nav="catalog" — подсвечивают якорь Sortiment.
    "catalog": "sellables",
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


def hidden_for(user) -> frozenset[str]:
    """E6.7e: адреса реестра, которые пользователь НЕ вправе открыть — ``url_name`` и
    ``url_name+query`` (вкладки со своим правом). Источник один — ``view_perms``: меню
    прячет ровно то, что middleware отдал бы 403. Аноним/None — пусто (fail-open
    хрома: доступ держит middleware)."""
    from apps.core import permissions, view_perms

    if user is None or not permissions.is_member(user):
        return frozenset()  # не член команды — кабинет его и так не пустит
    key = (permissions._schema(), user.pk)
    memo = getattr(user, "_cab_nav_hidden", None)
    if memo is not None and memo[0] == key and memo[1] is permissions.effective(user):
        return memo[2]
    out = set()
    for name in {e.url_name for e in ENTRIES} | {a.url_name for a in ANCHORS}:
        if not view_perms.allowed_quiet(user, name, "GET"):
            out.add(name)
    for (name, query), _key in view_perms.QUERY_RULES.items():
        if not view_perms.query_allowed(user, name, query):
            out.add(name + query)
    hidden = frozenset(out)
    try:  # мемо на запрос; сверка по объекту прав — перезапись прав его сбрасывает
        user._cab_nav_hidden = (key, permissions.effective(user), hidden)
    except AttributeError:
        pass
    return hidden


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
    """Подпункты якоря в сайдбаре = ВЕСЬ состав его хабов (единый реестр W8:
    гейты/подсветка/палитра — те же).

    R7-1 (фидбэк владельца 2026-08-24 «при нажатии на Продажи или Ассортимент
    должно открываться подменю, и в нём уже всё, а не сразу страница»): раньше
    в подменю шли только advanced-записи (SM-4), а main-состав жил таб-баром
    НА странице — то есть одни и те же ссылки показывались дважды («дубль
    меню»). Теперь меню одно: раздел раскрывается подменю с полным составом,
    таб-бары со страниц сняты. `sidebar=False` (явный) и `palette_only`
    по-прежнему исключают запись. Дедуп по (url_name, query); гейты модулей
    применяет вызывающий (modules.sidebar_nav)."""
    seen, out = set(), []
    for hub in anchor.hubs:
        for e in ENTRIES:
            in_sidebar = True if e.sidebar is None else e.sidebar
            if not in_sidebar or e.palette_only:
                continue  # sidebar=False — осознанно вне меню (сироты/дубли)
            # SH-14/15: ключ дедупа — (url_name, query): «Kunden» и «Lieferungen»
            # ведут на ОДИН экран продаж с разными вкладками/фильтрами, и по
            # голому url_name второй пункт молча исчезал бы.
            key = (e.url_name, e.query)
            if e.hub == hub and key not in seen:
                seen.add(key)
                out.append(e)
    return out


def palette_entries() -> list[dict]:
    """W8-4: индекс палитры Ctrl+K — якоря + табы (без дублей ЭКРАНА).
    Гейты модулей применяет рендер (шаблон получает готовый гейтнутый список).

    VF-10: запись с query — самостоятельный адрес («Aufträge» →
    verkaeufe?tab=job, «Kunden» → ?tab=kunden): иначе вкладки схлопывались в
    якорь «Verkäufe» и их поисковые термины пропадали из палитры. Инвариант
    «один экран — одна карточка» цел: query-запись помечает url_name занятым,
    так дубль-записи без query (settings-«Abläufe») по-прежнему схлопываются."""
    seen, seen_q, out = set(), set(), []

    def _rec(url_name, label, nav_key, module_key, hub, search, query="", entry=None, anchor=None):
        return {
            "entry": entry,
            "anchor": anchor,  # KA-12 E8.1: полный гейт записи (entry_visible) в рендере
            "url_name": url_name,
            "label": label,
            "nav_key": nav_key,
            "module_key": module_key,
            "hub": hub,
            "search": search,
            "query": query,
        }

    for a in ANCHORS:
        if a.targets:
            continue  # KA-12 E8.3: раздел с целями ведёт на свой подпункт — карточку даёт он
        out.append(_rec(a.url_name, a.label, a.nav_key, a.module_key, "", a.search, anchor=a))
        seen.add(a.url_name)
    for e in ENTRIES:
        if e.query:
            key = (e.url_name, e.query)
            if key in seen_q:
                continue
            seen_q.add(key)
            seen.add(e.url_name)
        else:
            if e.url_name in seen:
                continue
            seen.add(e.url_name)
        out.append(_rec(e.url_name, e.label, e.nav_key, e.module_key, e.hub, e.search, e.query, e))
    return out


# --- KA-12 E8.3/E8.4: условные якоря и группы подменю --------------------------


def palette_entries_for(request) -> list[dict]:
    """W8-4: гейтнутый индекс палитры Ctrl+K для этого запроса (модули, права, тип бизнеса,
    пакет). Одна точка для палитры и помощника (AIS-A A-0 «Wo stelle ich das ein?»).
    haystack = label+search в нижнем регистре (клиентский фильтр)."""
    from apps.core import modules, packages

    tenant = getattr(request, "tenant", None) if request is not None else None
    area_by_hub = {hub: a.label for a in ANCHORS for hub in a.hubs}
    owner_hidden = modules.owner_hidden_for(getattr(request, "user", None))
    entries = []
    for e in palette_entries():
        anchor = e.get("anchor")
        if anchor is not None and tenant is not None and not anchor_visible(anchor, tenant):
            continue  # KA-12 E8.3: скрытый условный якорь — без карточки
        mod = e["module_key"]
        if mod is not None and tenant is not None and not modules.is_module_active(tenant, mod):
            continue
        if e["url_name"] in owner_hidden or e["url_name"] + e.get("query", "") in owner_hidden:
            continue  # E6.7e: экраны без права пользователя не показываем
        if not allowed_for_business(e["url_name"], tenant):
            continue  # X4: гейт по типу бизнеса (гастро-экраны)
        entry = e.get("entry")
        if entry is not None and tenant is not None and not entry_visible(entry, tenant, menu=True):
            continue  # KA-12 E8.1: «любой из модулей» и направления — как в сайдбаре
        if tenant is not None and not packages.view_allowed(tenant, e["url_name"]):
            continue  # T-8.32b: экраны вне пакета в палитре не показываем
        entries.append(
            {
                "url_name": e["url_name"],
                # VF-10: вкладки-адреса («Aufträge» ?tab=job) — прыжок с query
                "query": e.get("query", ""),
                "label": e["label"],
                "area": area_by_hub.get(e["hub"], ""),
                "haystack": f"{e['label']} {e['search']}".lower(),
            }
        )
    return entries


def anchor_visible(anchor, tenant) -> bool:
    """Виден ли якорь тенанту. Условный (modules_any) — если активен любой из модулей;
    иначе прежнее правило: свой модуль или любой модуль его хабов (X0)."""
    from apps.core.modules import is_module_active

    if tenant is None:
        return not anchor.modules_any
    if anchor.modules_any:
        return any(is_module_active(tenant, m) for m in anchor.modules_any)
    if anchor.module_key and not is_module_active(tenant, anchor.module_key):
        return any(is_module_active(tenant, m) for m in hub_module_keys(anchor))
    return True


def _entry_in_hubs(anchor, url_name):
    for hub in anchor.hubs:
        e = entry_for(hub, url_name)
        if e is not None:
            return e
    return None


def anchor_target(anchor, tenant, owner_hidden=frozenset()) -> str:
    """Куда ведёт раздел: первый видимый ЭТОМУ пользователю экран из `targets`."""
    for url_name in anchor.targets:
        e = _entry_in_hubs(anchor, url_name)
        if e is not None and entry_visible(e, tenant, owner_hidden):
            return url_name
    if anchor.targets:
        # Ни одной цели нет (модули выключены/роль) — первый видимый подпункт без query;
        # сам якорь у разделов с целями — редирект-заглушка (иначе петля 302).
        for e, _group in visible_children(anchor, tenant, owner_hidden):
            if not e.query and e.url_name != anchor.url_name:
                return e.url_name
        return "dashboard"
    if anchor.url_name in owner_hidden:
        # E6.7e: обзор раздела закрыт правами — ведём на первый разрешённый подпункт.
        for e, _group in visible_children(anchor, tenant, owner_hidden):
            if not e.query:
                return e.url_name
        return "dashboard"
    return anchor.url_name


def anchor_for_tenant(nav_key: str, tenant) -> str:
    """Якорь подсветки с учётом скрытых условных якорей: страницы «Finanzen» без
    модулей finance/analytics подсвечивают «Einstellungen» (там живут их пункты)."""
    key = anchor_for(nav_key)
    for a in ANCHORS:
        if a.nav_key == key and a.fallback and not anchor_visible(a, tenant):
            return a.fallback
    return key


def _group_order(hub: str) -> dict[str, int]:
    return {key: i for i, (key, _label) in enumerate(SUBMENU_GROUPS.get(hub, ()))}


def group_label(hub: str, key: str) -> str:
    for k, label in SUBMENU_GROUPS.get(hub, ()):
        if k == key:
            return label
    return ""


def visible_children(anchor, tenant, owner_hidden=frozenset()) -> list[tuple]:
    """Подпункты якоря `(запись, группа)` под едиными гейтами — сайдбар и обзор настроек.
    К якорю-фолбэку добавляются подпункты скрытых условных якорей (их группой).
    Порядок — по группам SUBMENU_GROUPS (стабильно внутри группы); без группы — в конце."""
    out = [
        (e, e.group)
        for e in sidebar_children(anchor)
        if entry_visible(e, tenant, owner_hidden, menu=True)
    ]
    seen = {(e.url_name, e.query) for e, _g in out}
    for other in ANCHORS:
        if other.fallback != anchor.nav_key or anchor_visible(other, tenant):
            continue
        for e in sidebar_children(other):
            key = (e.url_name, e.query)
            if key in seen or not entry_visible(e, tenant, owner_hidden, menu=True):
                continue
            seen.add(key)
            out.append((e, other.fallback_group))
    hub = anchor.hubs[0] if anchor.hubs else ""
    order = _group_order(hub)
    tail = len(order)
    return sorted(out, key=lambda pair: order.get(pair[1], tail))
