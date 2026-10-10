"""T-8.13a: единые категории каталога города — справочник платформы.

План — docs/t8-13a-city-categories-plan-2026-10-10.md. Две вещи не смешиваем: своё дерево
категорий бизнеса (его сайт) и ЭТОТ справочник (один на все города и темы, ведёт платформа).
В город предложение уходит с категорией платформы; признаки (vegan, regional, yoga…) — ось
для фильтров и тематических порталов (T-8.14).

Хранение — слаги (как районы `core/districts.py`): `Promotion.city_category`/`city_tags`,
`AggregatorListing.city_category`/`city_tags`. Заявления о продукте (bio, vegan) ставит
только владелец или данные товара — подсказки их не выдумывают.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Section:
    key: str
    label: object
    icon: str


@dataclass(frozen=True)
class Category:
    key: str
    section: str
    label: object


# Разделы и подкатегории — стартовый классификатор ТЗ «Siteadaptor 2.0» §4 (2026-10-10).
# Признаки (bio, vegan…) — отдельная ось ниже, не подкатегории (ТЗ §3: свойства ≠ категории).
SECTIONS: tuple[Section, ...] = (
    Section("lebensmittel-getraenke", _("Lebensmittel & Getränke"), "🥖"),
    Section("essen-gastronomie", _("Essen & Gastronomie"), "🍽️"),
    Section("mode-accessoires", _("Mode & Accessoires"), "👗"),
    Section("elektronik-technik", _("Elektronik & Technik"), "💻"),
    Section("haus-garten", _("Haus & Garten"), "🏡"),
    Section("beauty-pflege", _("Beauty & Pflege"), "💇"),
    Section("gesundheit-fitness", _("Gesundheit & Fitness"), "🧘"),
    Section("freizeit-erlebnisse", _("Freizeit & Erlebnisse"), "🎟️"),
    Section("kinder-familie", _("Kinder & Familie"), "🧸"),
    Section("auto-mobilitaet", _("Auto & Mobilität"), "🚲"),
    Section("handwerk-reparatur", _("Handwerk & Reparatur"), "🛠️"),
    Section("dienstleistungen", _("Dienstleistungen"), "💼"),
    Section("reisen-uebernachten", _("Reisen & Übernachten"), "🛏️"),
    Section("tiere", _("Tiere & Tierbedarf"), "🐾"),
    Section("kunst-geschenke", _("Kunst & Geschenke"), "🎁"),
)

CATEGORIES: tuple[Category, ...] = (
    Category("obst-gemuese", "lebensmittel-getraenke", _("Obst & Gemüse")),
    Category("brot-backwaren", "lebensmittel-getraenke", _("Brot & Backwaren")),
    Category("fleisch-wurst", "lebensmittel-getraenke", _("Fleisch & Wurst")),
    Category("getraenke", "lebensmittel-getraenke", _("Getränke")),
    Category("feinkost", "lebensmittel-getraenke", _("Feinkost & Spezialitäten")),
    Category("lebensmittel", "lebensmittel-getraenke", _("Lebensmittel & Supermarkt")),
    Category("restaurants", "essen-gastronomie", _("Restaurants")),
    Category("cafes", "essen-gastronomie", _("Cafés")),
    Category("fruehstueck", "essen-gastronomie", _("Frühstück")),
    Category("mittagessen", "essen-gastronomie", _("Mittagessen")),
    Category("catering", "essen-gastronomie", _("Catering")),
    Category("takeaway", "essen-gastronomie", _("Takeaway")),
    Category("lieferservice", "essen-gastronomie", _("Lieferservice")),
    Category("damenmode", "mode-accessoires", _("Damenmode")),
    Category("herrenmode", "mode-accessoires", _("Herrenmode")),
    Category("kindermode", "mode-accessoires", _("Kindermode")),
    Category("schuhe", "mode-accessoires", _("Schuhe")),
    Category("taschen", "mode-accessoires", _("Taschen")),
    Category("schmuck", "mode-accessoires", _("Schmuck")),
    Category("smartphones", "elektronik-technik", _("Smartphones")),
    Category("computer", "elektronik-technik", _("Computer & Notebooks")),
    Category("tv-audio", "elektronik-technik", _("TV & Audio")),
    Category("haushaltsgeraete", "elektronik-technik", _("Haushaltsgeräte")),
    Category("technik-zubehoer", "elektronik-technik", _("Zubehör")),
    Category("moebel", "haus-garten", _("Möbel")),
    Category("dekoration", "haus-garten", _("Dekoration")),
    Category("beleuchtung", "haus-garten", _("Beleuchtung")),
    Category("kueche", "haus-garten", _("Küche")),
    Category("garten-pflanzen", "haus-garten", _("Garten & Pflanzen")),
    Category("kosmetik", "beauty-pflege", _("Kosmetik")),
    Category("friseur", "beauty-pflege", _("Friseur")),
    Category("naegel", "beauty-pflege", _("Nägel")),
    Category("massage", "beauty-pflege", _("Massage")),
    Category("pflegeprodukte", "beauty-pflege", _("Pflegeprodukte")),
    Category("fitness", "gesundheit-fitness", _("Fitness")),
    Category("yoga", "gesundheit-fitness", _("Yoga & Meditation")),
    Category("wellness", "gesundheit-fitness", _("Wellness & Retreats")),
    Category("optik", "gesundheit-fitness", _("Optik")),
    Category("gesundheitsprodukte", "gesundheit-fitness", _("Gesundheitsprodukte")),
    Category("physiotherapie", "gesundheit-fitness", _("Physiotherapie")),
    Category("events", "freizeit-erlebnisse", _("Events")),
    Category("kino", "freizeit-erlebnisse", _("Kino")),
    Category("sport", "freizeit-erlebnisse", _("Sport")),
    Category("workshops", "freizeit-erlebnisse", _("Workshops & Kurse")),
    Category("outdoor", "freizeit-erlebnisse", _("Outdoor")),
    Category("familienausfluege", "freizeit-erlebnisse", _("Familienausflüge")),
    Category("spielzeug", "kinder-familie", _("Spielzeug")),
    Category("babybedarf", "kinder-familie", _("Babybedarf")),
    Category("kinder-aktivitaeten", "kinder-familie", _("Aktivitäten für Kinder")),
    Category("autoteile", "auto-mobilitaet", _("Autoteile")),
    Category("fahrraeder", "auto-mobilitaet", _("Fahrräder")),
    Category("kfz-reparatur", "auto-mobilitaet", _("Werkstatt & Reparatur")),
    Category("vermietung", "auto-mobilitaet", _("Vermietung")),
    Category("elektriker", "handwerk-reparatur", _("Elektriker")),
    Category("sanitaer", "handwerk-reparatur", _("Sanitär")),
    Category("bau", "handwerk-reparatur", _("Bau & Renovierung")),
    Category("montage", "handwerk-reparatur", _("Montage")),
    Category("reparatur", "handwerk-reparatur", _("Reparatur")),
    Category("it", "dienstleistungen", _("IT-Service")),
    Category("beratung", "dienstleistungen", _("Beratung")),
    Category("fotografie", "dienstleistungen", _("Fotografie")),
    Category("reinigung", "dienstleistungen", _("Reinigung")),
    Category("bueroservice", "dienstleistungen", _("Büroservice")),
    Category("weitere-dienstleistungen", "dienstleistungen", _("Weitere Dienstleistungen")),
    Category("hotels", "reisen-uebernachten", _("Hotels & Pensionen")),
    Category("ferienwohnungen", "reisen-uebernachten", _("Ferienwohnungen")),
    Category("touren", "reisen-uebernachten", _("Touren")),
    Category("ausfluege", "reisen-uebernachten", _("Ausflüge")),
    Category("tierfutter", "tiere", _("Tierfutter")),
    Category("tierzubehoer", "tiere", _("Tierzubehör")),
    Category("grooming", "tiere", _("Grooming")),
    Category("tierdienstleistungen", "tiere", _("Tierdienstleistungen")),
    Category("handgemachtes", "kunst-geschenke", _("Handgemachtes")),
    Category("kunst", "kunst-geschenke", _("Kunst")),
    Category("geschenke", "kunst-geschenke", _("Geschenke")),
    Category("lokale-produkte", "kunst-geschenke", _("Lokale Produkte")),
)

# Признаки: несколько у предложения. Диеты — те же коды, что `catalog/food.py` DIETS.
TAGS: tuple[tuple[str, object], ...] = (
    ("vegan", _("vegan")),
    ("vegetarisch", _("vegetarisch")),
    ("bio", _("bio")),
    ("glutenfrei", _("glutenfrei")),
    ("laktosefrei", _("laktosefrei")),
    ("halal", _("halal")),
    ("regional", _("regional")),
    ("nachhaltig", _("nachhaltig")),
    ("familienfreundlich", _("familienfreundlich")),
    ("barrierefrei", _("barrierefrei")),
    ("hundefreundlich", _("hundefreundlich")),
    ("yoga", _("Yoga")),
    ("meditation", _("Meditation")),
    ("ayurveda", _("Ayurveda")),
)

_SECTION = {s.key: s for s in SECTIONS}
_CATEGORY = {c.key: c for c in CATEGORIES}
_TAG = dict(TAGS)

# Подсказка категории по типу бизнеса (все 16 типов; замок).
BY_BUSINESS_TYPE: dict[str, str] = {
    "bakery": "brot-backwaren",
    "butcher": "fleisch-wurst",
    "grocery": "lebensmittel",
    "clothing": "damenmode",
    "restaurant": "restaurants",
    "cafe": "cafes",
    "retail": "geschenke",
    "online_shop": "geschenke",
    "tour_operator": "touren",
    "hotel": "hotels",
    "friseur": "friseur",
    "handwerker": "reparatur",
    "werkstatt": "kfz-reparatur",
    "events": "events",
    "catering": "catering",
    "other": "weitere-dienstleistungen",
}

# Тема события (`events/taxonomy.py`) → категория; сама тема идёт и признаком, если есть.
BY_EVENT_THEME: dict[str, str] = {
    "yoga": "yoga",
    "meditation": "yoga",
    "achtsamkeit": "yoga",
    "ayurveda": "wellness",
    "fasten": "wellness",
    "klang": "workshops",
    "coaching": "workshops",
    "natur": "outdoor",
    "pilgern": "outdoor",
}


def section(key: str) -> Section | None:
    return _SECTION.get(key)


def category(key: str) -> Category | None:
    return _CATEGORY.get(key)


def label(key: str) -> str:
    """Подпись категории ИЛИ раздела по ключу ("" — неизвестный)."""
    item = _CATEGORY.get(key) or _SECTION.get(key)
    return str(item.label) if item else ""


def tag_label(key: str) -> str:
    return str(_TAG.get(key, ""))


def normalize_category(value) -> str:
    value = str(value or "").strip()
    return value if value in _CATEGORY else ""


def normalize_tags(values) -> list[str]:
    """Только известные признаки, без повторов, в порядке справочника."""
    wanted = {str(v).strip() for v in (values or []) if v}
    return [key for key, _label in TAGS if key in wanted]


def suggest_for_business_type(business_type: str) -> str:
    return BY_BUSINESS_TYPE.get(business_type or "", "weitere-dienstleistungen")


def keys_for_filter(value: str) -> list[str]:
    """`?kat=` раздела → все его категории; `?kat=` категории → она одна; иначе []."""
    if value in _CATEGORY:
        return [value]
    if value in _SECTION:
        return [c.key for c in CATEGORIES if c.section == value]
    return []


def grouped_choices() -> list[tuple[str, list[tuple[str, str]]]]:
    """Для селекта с optgroup: [(раздел, [(ключ, подпись), …]), …]."""
    return [
        (f"{s.icon} {s.label}", [(c.key, str(c.label)) for c in CATEGORIES if c.section == s.key])
        for s in SECTIONS
    ]


def tag_choices() -> list[tuple[str, str]]:
    return [(key, str(lbl)) for key, lbl in TAGS]


# T-8.13b: подсказка категории по НАЗВАНИЮ своей категории бизнеса (только предвыбор —
# владелец подтверждает). Ключ — часть слова после нормализации (умлауты → ae/oe/ue/ss):
# немецкие составные слова держат главное слово в конце (Kinderschuhe, Vollkornbrot).
# Порядок важен: первое совпадение побеждает. Короткие ключи, живущие внутри чужих слов
# (ring → Hering, spiel → Beispiel), сюда не берём.
NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("schwein", "fleisch-wurst"),  # раньше «wein»: Schweinefleisch — не напиток
    ("schuh", "schuhe"),
    ("stiefel", "schuhe"),
    ("sneaker", "schuhe"),
    ("tasche", "taschen"),
    ("rucksa", "taschen"),
    ("schmuck", "schmuck"),
    ("halskette", "schmuck"),
    ("damen", "damenmode"),
    ("frauen", "damenmode"),
    ("herren", "herrenmode"),
    ("maenner", "herrenmode"),
    ("kinderkleid", "kindermode"),
    ("kindermode", "kindermode"),
    ("baby", "babybedarf"),
    ("spielzeug", "spielzeug"),
    ("brot", "brot-backwaren"),
    ("broetchen", "brot-backwaren"),
    ("backw", "brot-backwaren"),
    ("gebaeck", "brot-backwaren"),
    ("kuchen", "brot-backwaren"),
    ("torte", "brot-backwaren"),
    ("fleisch", "fleisch-wurst"),
    ("wurst", "fleisch-wurst"),
    ("obst", "obst-gemuese"),
    ("gemuese", "obst-gemuese"),
    ("salat", "obst-gemuese"),
    ("getraenk", "getraenke"),
    ("wein", "getraenke"),
    ("bier", "getraenke"),
    ("saft", "getraenke"),
    ("kaffee", "cafes"),
    ("fruehstueck", "fruehstueck"),
    ("mittag", "mittagessen"),
    ("feinkost", "feinkost"),
    ("kaese", "feinkost"),
    ("handy", "smartphones"),
    ("smartphone", "smartphones"),
    ("computer", "computer"),
    ("notebook", "computer"),
    ("laptop", "computer"),
    ("moebel", "moebel"),
    ("deko", "dekoration"),
    ("lampe", "beleuchtung"),
    ("leuchte", "beleuchtung"),
    ("kueche", "kueche"),
    ("garten", "garten-pflanzen"),
    ("pflanze", "garten-pflanzen"),
    ("blume", "garten-pflanzen"),
    ("kosmetik", "kosmetik"),
    ("pflege", "pflegeprodukte"),
    ("haar", "friseur"),
    ("fahrrad", "fahrraeder"),
    ("hund", "tierzubehoer"),
    ("katze", "tierzubehoer"),
    ("tierfutter", "tierfutter"),
    ("futter", "tierfutter"),
    ("geschenk", "geschenke"),
    ("gutschein", "geschenke"),
    ("handgemacht", "handgemachtes"),
    ("kunst", "kunst"),
    ("buch", "geschenke"),
    ("buecher", "geschenke"),
)

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def suggest_for_name(text: str) -> str:
    """Категория справочника по названию своей категории ("" — не угадали)."""
    import re

    words = re.findall(r"[a-z]+", str(text or "").casefold().translate(_UMLAUTS))
    for prefix, key in NAME_HINTS:
        if any(prefix in w for w in words):
            return key
    return ""
