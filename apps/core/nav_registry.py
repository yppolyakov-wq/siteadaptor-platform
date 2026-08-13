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


@dataclass(frozen=True)
class NavEntry:
    url_name: str  # reverse-имя целевой страницы
    label: str  # язык задач (lazy)
    nav_key: str  # context["nav"] целевой страницы
    hub: str  # чей таб-бар содержит запись
    module_key: str | None = None  # гейт активности (None = ядро)
    advanced: bool = False  # ящик «Erweitert»
    search: str = ""  # ключевые слова палитры (дополняют label)


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
    Anchor(
        "sellable-manage",
        _("Angebote"),
        "sellables",
        "📦",
        "angebote sortiment produkte leistungen zimmer",
        hubs=("sellables", "catalog"),
    ),
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


def _e(hub, url_name, label, nav_key, module_key=None, advanced=False, search=""):
    return NavEntry(url_name, label, nav_key, hub, module_key, advanced, search)


# --- Табы хабов (порядок внутри hub = порядок показа) -------------------------
# Содержимое = бывший литерал cabinet.HUB_TABS (W7b/W-CL) 1:1 — характеризацию
# держат test_hub_tabs/test_w7_nav; здесь добавлены только search-слова палитры.
ENTRIES: tuple[NavEntry, ...] = (
    # Sortiment (рендерится на страницах каталога; якорь — «Angebote»).
    _e("catalog", "sellable-manage", _("Angebote"), "sellables", search="übersicht alle"),
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
    # «Angebote»: main Angebote·Produkte·Kategorien, остальное — в «Erweitert».
    _e(
        "catalog",
        "stock",
        _("Lager"),
        "stock",
        "catalog",
        True,
        "bestand inventur meldebestand",
    ),
    _e(
        "catalog",
        "purchasing",
        _("Einkauf"),
        "purchasing",
        "catalog",
        True,
        "lieferanten bestellung",
    ),
    _e("catalog", "catalog:combo-list", _("Kombi"), "combos", "catalog", True),
    _e("catalog", "imports:start", _("Import"), "imports", "catalog", True, "csv excel"),
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
    _e("board", "events:list", _("Tickets"), "events", "events", search="veranstaltungen"),
    # MT-1: тур-продукт (контент + маршрут + заезды) — рядом с билетами, тот же модуль.
    _e("board", "events:tour-list", _("Reisen"), "tours", "events", search="touren reisen route"),
    _e(
        "board",
        "jobs:list",
        _("Aufträge"),
        "jobs",
        "jobs",
        search="anfragen kostenvoranschlag angebote",
    ),
    # SM-4 (решение владельца 2026-08-11): отчёты и настройки процессов — подпункты
    # раздела «Verkäufe» в сайдбаре (advanced board-хаба; сам hub_tabs "board" не
    # рендерится). Auswertungen/Finanzen ПЕРЕЕХАЛИ из settings-хаба; Berichte —
    # бывший сирота stays:reports; Abläufe — дубль-запись (таб Einstellungen жив,
    # прецедент sellables/catalog; палитра дедупит по url_name).
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
    _e("board", "ablaeufe", _("Abläufe"), "ablaeufe", None, True, "status übergänge spalten"),
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
    # Angebote-хаб (Sortiment-страницы дублем в Erweitert).
    _e("sellables", "sellable-manage", _("Angebote"), "sellables", search="übersicht alle"),
    _e("sellables", "catalog:product-list", _("Produkte"), "catalog", "catalog", True),
    _e("sellables", "catalog:category-list", _("Kategorien"), "categories", "catalog", True),
    _e("sellables", "stock", _("Lager"), "stock", "catalog", True),
    _e("sellables", "purchasing", _("Einkauf"), "purchasing", "catalog", True),
    _e("sellables", "catalog:combo-list", _("Kombi"), "combos", "catalog", True),
    _e("sellables", "imports:start", _("Import"), "imports", "catalog", True),
    _e("sellables", "collections:list", _("Kollektionen"), "collections", None, True),
    # W11-1: хаб «Kunden» удалён (Р-2) — страницы crm/inbox/telegram рендерят
    # marketing-хаб («молчаливая подмена таб-бара» умерла).
    # Einstellungen (W9-1: «базовые + по типам»; порядок = целевая структура §2.3).
    _e(
        "settings",
        "settings",
        _("Mein Geschäft"),
        "settings",
        search="kontakt öffnungszeiten firma adresse logo",
    ),
    _e("settings", "languages", _("Sprachen"), "languages", search="sprache locale übersetzung"),
    _e(
        "settings",
        "legal-docs",
        _("Recht & Steuern"),
        "legal-docs",
        search="impressum datenschutz agb widerruf steuer",
    ),
    _e(
        "settings",
        "payment-settings",
        _("Zahlung & Lieferung"),
        "payments",
        search="stripe vorkasse lieferung zonen versand",
    ),
    _e(
        "settings",
        "notifications-settings",
        _("Benachrichtigungen & Kanäle"),
        "notifications",
        search="care e-mail telegram erinnerung",
    ),
    # W9-8: настройки процессов продаж (статусы/переходы/колонки) — раньше панели
    # были разбросаны по спискам (аудит 2026-08-05).
    _e(
        "settings",
        "ablaeufe",
        _("Abläufe"),
        "ablaeufe",
        search="status übergänge spalten workflow prozesse",
    ),
    # SM-4: «Website & Domains» переехал в site-хаб (подпункт раздела Website);
    # Finanzen/Auswertungen — в board-хаб (подпункты «Verkäufe»). Настройки слимятся.
    # W9-9 (Р-3): Integrationen — вкладка настроек (был якорь сайдбара).
    _e(
        "settings",
        "integrations-home",
        _("Integrationen"),
        "integrations",
        search="integrationen stripe telegram publishing ota kanäle verbindungen",
    ),
    # GK-11: Google-рейтинг (Places API) — экран в кластере настроек.
    _e(
        "settings",
        "google-reviews-settings",
        _("Google Bewertungen"),
        "integrations",
        search="google bewertungen sterne rating place id",
    ),
    _e(
        "settings",
        "billing",
        _("Abo & Rechnung"),
        "billing",
        search="abo tarif subscription rechnung",
    ),
    # W9-10 (Р-7): членства/роли/инвайт — owner-only (middleware).
    _e(
        "settings",
        "team",
        _("Team & Zugriff"),
        "team",
        search="team mitarbeiter rollen zugriff einladen",
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


def legacy_hub_tabs() -> dict:
    """Производный реестр в форме легаси-кортежей cabinet.HUB_TABS
    (url_name, label, nav_key, module_key, advanced) — потребители/замки целы."""
    return {
        hub: tuple(
            (e.url_name, e.label, e.nav_key, e.module_key, e.advanced)
            for e in ENTRIES
            if e.hub == hub
        )
        for hub in HUBS
    }


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


def sidebar_children(anchor) -> list[NavEntry]:
    """SM-4: подпункты якоря в сайдбаре = advanced-записи его хабов (единый
    реестр W8: гейты/подсветка/палитра — те же). Дедуп по url_name (Angebote
    собирает sellables+catalog — состав одинаков). Гейты модулей применяет
    вызывающий (modules.sidebar_nav)."""
    seen, out = set(), []
    for hub in anchor.hubs:
        for e in ENTRIES:
            if e.hub == hub and e.advanced and e.url_name not in seen:
                seen.add(e.url_name)
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
