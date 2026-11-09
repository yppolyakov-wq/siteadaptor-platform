"""FB-26: «Was verkaufen Sie?» при регистрации — направления обязательны, ниша — нет.

Решения владельца 2026-11-08 (`docs/fb26-simple-site-creation-plan-2026-11-07.md` §4):
1. Первый вопрос — направления (мультивыбор), второй — ниша, необязательно.
2. Направления выбрать ОБЯЗАТЕЛЬНО: без них не понять, отель это или магазин.
3. У ниши остаётся «Demo ansehen».

Направления регистрации — шесть чипов поверх реестра `apps.core.directions`
(«Speisen & Getränke» = Speisekarte + Tisch). Ниша — данные (тексты, образцы, вид);
модули включают направления. Пустая ниша выводится из направлений только там, где
вывод однозначен (гастро → ресторан, только номера → отель, только билеты → события),
иначе `other`.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.utils.translation import gettext_lazy as _

#: (ключ, иконка, подпись, подсказка, примеры типов) — порядок чипов на странице.
#: Фидбэк владельца 2026-11-08: «продаю» — это ЛЮБЫЕ товары (не только еда), с примерами.
#: SHP (2026-11-09, фидбэк «два пункта одинаковы»): «в лавке/самовывоз» и «онлайн с
#: доставкой» — ОДИН пункт «Waren»: это не разные направления, а способы получения товара;
#: при регистрации их не спрашиваем — выбор в мастере «Verkauf öffnen», настройка —
#: «Versandarten». Прежний чип «online» понимается у старых заявок (LEGACY_KEYS).
CHOICES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "waren",
        "🛍️",
        _("Waren verkaufen"),
        _(
            "Alles, was Sie verkaufen: Lebensmittel, Drogerie, Spielzeug, Mode, Technik … "
            "Abholung, Lieferung oder Versand legen Sie danach fest."
        ),
        _("z. B. Bäckerei, Hofladen, Drogerie, Boutique, Online-Shop"),
    ),
    (
        "termine",
        "📅",
        _("Termine & Dienstleistungen"),
        _("Kunden buchen eine Uhrzeit."),
        _("z. B. Friseur, Kosmetik, Werkstatt, Massage"),
    ),
    (
        "zimmer",
        "🛏️",
        _("Zimmer & Übernachtung"),
        _("Gäste buchen Nächte."),
        _("z. B. Hotel, Pension, Ferienwohnung"),
    ),
    (
        "tickets",
        "🎟️",
        _("Tickets & Touren"),
        _("Plätze für Termine mit Datum."),
        _("z. B. Kurse, Stadtführungen, Konzerte"),
    ),
    (
        "anfragen",
        "📝",
        _("Anfragen & Aufträge"),
        _("Kunden fragen an, Sie schicken ein Angebot."),
        _("z. B. Handwerk, Catering, Reparatur"),
    ),
    (
        "gastro",
        "🍽️",
        _("Speisen & Getränke"),
        _("Speisekarte und Tischreservierung."),
        _("z. B. Café, Restaurant, Imbiss"),
    ),
)
KEYS: tuple[str, ...] = tuple(c[0] for c in CHOICES)
#: чипы прежних версий формы — понимаются у неподтверждённых заявок (SignupRequest)
LEGACY_KEYS: tuple[str, ...] = ("online",)

#: Чип регистрации → направления реестра.
_EXPAND = {"gastro": ("speisekarte", "tisch"), "online": ("waren",)}

#: Ниша по единственному направлению, когда её не выбрали (однозначные случаи).
_INFER = {"zimmer": "hotel", "tickets": "events", "online": "online_shop"}

#: Направления, чьи модули выключаются, если их НЕ отметили. «Waren» не трогаем:
#: онлайн-продажу открывает шаг «Verkauf öffnen», каталог — базовый.
_SWITCHABLE = ("termine", "tisch", "zimmer", "tickets", "anfragen")


def clean(keys) -> list[str]:
    """Только известные чипы, без дублей, в порядке страницы (прежние — в конце)."""
    picked = {k for k in keys or () if isinstance(k, str)}
    return [k for k in (*KEYS, *LEGACY_KEYS) if k in picked]


def resolve_type(niche: str, chips) -> str:
    """Тип бизнеса: выбранная ниша, иначе вывод из направлений, иначе `other`."""
    if niche and niche != "other":
        return niche
    chips = clean(chips)
    if "gastro" in chips:
        return "restaurant"
    if len(chips) == 1 and chips[0] in _INFER:
        return _INFER[chips[0]]
    return niche or "other"


def directions_for(business_type: str, chips) -> list[str]:
    """Ключи реестра для типа: «gastro» раскрыт, неуместные типу отброшены (Tisch у кафе)."""
    from apps.core import directions

    allowed = {d.key for d in directions.choices_for(SimpleNamespace(business_type=business_type))}
    out: list[str] = []
    for chip in clean(chips):
        for key in _EXPAND.get(chip, (chip,)):
            if key in allowed and key not in out:
                out.append(key)
    return out


def disabled_modules(business_type: str, chosen: list[str], *, online: bool = False) -> list[str]:
    """Стартовый `disabled_modules`: дефолт типа, модули отмеченных направлений включены,
    неотмеченных — выключены (общий модуль держит отмеченное направление).

    `online` (чип «Online-Shop») сразу включает заказы: владелец сказал, что продаёт
    онлайн. Без него «Waren» онлайн-продажу не включает — её открывает «Verkauf öffnen»."""
    from apps.core import directions, modules

    disabled = set(modules.default_disabled_for(business_type))
    keep = {"orders"} if online else set()
    for key in chosen:
        d = directions.get(key)
        if d and key != "waren":
            keep.update(d.modules)
    for key in _SWITCHABLE:
        d = directions.get(key)
        if d and key not in chosen:
            disabled.update(m for m in d.modules if m not in keep)
    disabled -= keep
    return sorted(disabled)


def initial_for(business_type: str) -> list[str]:
    """Предвыбор чипов по нише (пришли с Branchen-страницы `?type=`)."""
    from apps.core import directions

    out = ["waren"] if business_type == "online_shop" else []
    for key in directions.defaults_for(business_type):
        chip = "gastro" if key in ("speisekarte", "tisch") else key
        if chip not in out:
            out.append(chip)
    return [k for k in clean(out) if k in KEYS]


def niche_chips(business_type: str) -> str:
    """Чипы, которые подходят нише, — пробелами (атрибут карточки для фильтра на странице)."""
    return " ".join(initial_for(business_type))


#: FB-26b: слова, по которым владелец ищет свою нишу (ищут по своему названию бизнеса,
#: а не по нашему). Немецкий — язык рынка; без перевода: это ключи поиска, не текст.
SEARCH_TERMS: dict[str, str] = {
    "bakery": "Bäcker Konditorei Brot Kuchen Torten",
    "butcher": "Fleischerei Wurst Partyservice",
    "grocery": "Bioladen Supermarkt Hofladen Feinkost Kiosk Getränke Unverpackt",
    "clothing": "Mode Boutique Schuhe Textil Kleidung",
    "restaurant": "Gaststätte Imbiss Pizzeria Bistro Lieferdienst",
    "cafe": "Kaffee Eisdiele Bar Teestube",
    "retail": "Laden Geschäft Drogerie Spielwaren Spielzeug Haushalt Geschenke Blumen "
    "Buchhandlung Elektro Möbel Deko Schmuck Optiker Fahrrad Zoo",
    "online_shop": "Versand Webshop E-Commerce Manufaktur",
    "tour_operator": "Reisen Touren Stadtführung Reiseveranstalter",
    "hotel": "Pension Ferienwohnung Gästehaus Hostel Übernachtung Camping",
    "friseur": "Kosmetik Nagelstudio Barbier Massage Beauty Tattoo Physio",
    "handwerker": "Maler Elektriker Sanitär Tischler Schreiner Dachdecker Gärtner Reinigung",
    "werkstatt": "Autowerkstatt KFZ Reparatur Reifen Fahrradwerkstatt",
    "events": "Kurse Workshops Konzerte Yoga Tanzschule Seminar",
    "catering": "Partyservice Buffet Hochzeit Events Essen",
}


def search_terms(business_type: str) -> str:
    return SEARCH_TERMS.get(business_type, "")
