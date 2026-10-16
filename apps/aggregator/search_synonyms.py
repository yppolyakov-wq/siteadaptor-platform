"""T-8.20: синонимы поиска каталога города — словарь в коде (решение владельца Р-О3).

Запрос расширяется в Python (``expand``): каждое слово ищется ИЛИ по всей своей группе.
Thesaurus Postgres не используем — он требует файлов на сервере БД. Группы двусторонние,
термины — одно слово в нижнем регистре (без дефисов: «E-Bike» → «ebike» на входе).
Замок: каждый термин ровно в одной группе (``tests/test_unified_search.py``).
"""

from __future__ import annotations

GROUPS: tuple[tuple[str, ...], ...] = (
    # Lebensmittel & Getränke
    ("brot", "brötchen", "backwaren", "semmel", "schrippe"),
    ("kuchen", "torte", "gebäck"),
    ("obst", "früchte"),
    ("gemüse", "salat"),
    ("wurst", "aufschnitt"),
    ("fleisch", "metzger", "metzgerei", "fleischerei"),
    ("getränke", "drinks"),
    ("bier", "pils"),
    ("kaffee", "espresso", "cappuccino"),
    ("feinkost", "delikatessen", "spezialitäten"),
    ("supermarkt", "lebensmittel"),
    # Essen & Gastronomie
    ("restaurant", "gaststätte", "lokal", "gasthaus"),
    ("café", "cafe", "kaffeehaus"),
    ("frühstück", "brunch"),
    ("mittagessen", "mittagstisch", "lunch", "mittag", "mittagsmenü"),
    ("vegetarisch", "vegetarische", "veggie", "vegetarian", "fleischlos"),
    ("vegan", "pflanzlich", "plantbased"),
    ("eis", "eisdiele", "gelato"),
    ("sushi", "japanisch"),
    ("burger", "hamburger"),
    ("bäcker", "bäckerei", "backstube"),
    ("wochenmarkt", "markt", "hofladen"),
    ("pizza", "pizzeria"),
    ("döner", "kebab"),
    ("lieferung", "lieferservice", "liefern"),
    ("takeaway", "abholung", "mitnehmen"),
    # Mode & Accessoires
    ("kleidung", "mode", "bekleidung", "klamotten"),
    ("schuhe", "sneaker", "stiefel"),
    ("jacke", "mantel", "parka", "anorak"),  # «winterjacke» — через split_compound
    ("hose", "jeans"),
    ("kleid", "kleider"),
    ("damen", "frauen"),
    ("herren", "männer"),
    ("tasche", "rucksack", "handtasche"),
    # Elektronik & Technik
    ("handy", "smartphone", "mobiltelefon", "iphone"),
    ("laptop", "notebook", "computer", "pc"),
    ("reparatur", "reparieren", "werkstatt"),
    ("handyreparatur", "displayreparatur"),
    ("kopfhörer", "headset"),
    # Haus & Garten
    ("möbel", "einrichtung"),
    ("garten", "pflanzen", "blumen"),
    ("lampe", "leuchte", "licht"),
    # Beauty & Pflege
    ("friseur", "frisör", "haarschnitt", "friseursalon", "barbier", "barber"),
    ("kosmetik", "beauty", "kosmetikstudio"),
    ("nägel", "maniküre", "nagelstudio"),
    ("massage", "wellness"),
    # Gesundheit & Fitness
    ("fitness", "gym", "fitnessstudio", "training"),
    ("yoga", "pilates"),
    ("physiotherapie", "physio", "krankengymnastik"),
    # Freizeit & Erlebnisse
    ("veranstaltung", "event", "konzert"),
    ("kurs", "workshop", "seminar"),
    ("kino", "film"),
    # Kinder & Familie
    ("spielzeug", "spielwaren", "spiele"),
    ("kinder", "kids", "familie", "kind", "kinderprogramm"),
    ("aktivität", "aktivitäten", "freizeit", "ausflugsziel"),
    # Auto & Mobilität
    ("fahrrad", "rad", "velo", "ebike", "pedelec"),
    ("auto", "pkw", "kfz", "wagen"),
    # Handwerk & Reparatur
    ("elektriker", "elektro", "elektroinstallation"),
    ("handwerker", "handwerk"),
    ("schlüssel", "schlüsseldienst"),
    # Dienstleistungen
    ("reinigung", "putzen", "putzservice"),
    ("versicherung", "versicherungen"),
    # Reisen & Übernachten
    ("hotel", "pension", "unterkunft", "übernachtung", "zimmer"),
    ("ferienwohnung", "apartment", "fewo"),
    ("tour", "führung", "ausflug", "stadtführung"),
    # Tiere
    ("hund", "hunde", "welpe"),
    ("katze", "katzen"),
    ("tierbedarf", "tierfutter", "futter", "zoohandlung"),
    # Kunst & Geschenke
    ("geschenk", "geschenke", "präsent", "mitbringsel"),
    ("messer", "klinge", "schneidwaren"),  # Solingen — Klingenstadt
    ("gutschein", "geschenkgutschein", "voucher"),
)

_INDEX: dict[str, tuple[str, ...]] = {}
for _group in GROUPS:
    for _term in _group:
        _INDEX[_term] = _group


def expand(token: str) -> tuple[str, ...]:
    """Слово → вся его группа синонимов (вкл. само слово); вне словаря — само слово."""
    return _INDEX.get(token, (token,))


# T-8.26 п.5b (Р-6): составные немецкие слова — ЗАКРЫТЫЙ словарь «голов» и модификаторов.
# «Winterjacke» → ещё и «jacke», «Kinderaktivitäten» → «kinder» + «aktivitäten». Авто-
# разрезания нет: без словаря «Nachtisch» дал бы «Tisch». Внутри слова — ИЛИ, между
# словами — И; ранг держит точное первым (вес A у заголовка).
HEADS: frozenset[str] = frozenset(
    {
        "jacke",
        "hose",
        "schuhe",
        "kleid",
        "hemd",
        "mantel",
        "tasche",
        "schal",
        "mütze",
        "kurs",
        "kurse",
        "workshop",
        "brot",
        "kuchen",
        "torte",
        "salat",
        "suppe",
        "pizza",
        "menü",
        "reparatur",
        "schnitt",
        "massage",
        "führung",
        "tour",
        "touren",
        "aktivität",
        "aktivitäten",
        "spiel",
        "spiele",
        "zeug",
        "rad",
        "lampe",
        "möbel",
        "wein",
        "bier",
        "käse",
        "wurst",
        "fleisch",
        "gemüse",
        "obst",
        "pflege",
        "studio",
        "service",
        "verleih",
        "vermietung",
        "beratung",
        "training",
        "unterricht",
    }
)
MODIFIERS: frozenset[str] = frozenset(
    {
        "kinder",
        "damen",
        "herren",
        "winter",
        "sommer",
        "herbst",
        "frühjahr",
        "bio",
        "vegan",
        "familien",
        "baby",
        "hand",
        "vollkorn",
        "weihnachts",
        "oster",
        "regen",
        "wander",
        "sport",
        "outdoor",
        "hochzeits",
        "geburtstags",
    }
)
# ложные головы — в HEADS их нет ПО ПОСТРОЕНИЮ; замок держит список
HEAD_STOPLIST: frozenset[str] = frozenset(
    {"tisch", "haus", "stadt", "land", "zeit", "platz", "markt"}
)
COMPOUND_MIN = 8  # букв в слове, с которого ищем голову/модификатор
PART_MIN = 3  # минимальный остаток, чтобы разрез считался осмысленным


def split_compound(token: str) -> tuple[str, ...]:
    """Части составного слова по словарю: (модификатор?, голова?) или ()."""
    token = (token or "").lower()
    if len(token) < COMPOUND_MIN or token in _INDEX:
        return ()
    parts: list[str] = []
    for mod in sorted(MODIFIERS, key=len, reverse=True):
        if token.startswith(mod) and len(token) - len(mod) >= PART_MIN:
            parts.append(mod)
            break
    for head in sorted(HEADS, key=len, reverse=True):
        if len(head) >= 4 and token.endswith(head) and len(token) - len(head) >= PART_MIN:
            if head not in HEAD_STOPLIST:
                parts.append(head)
            break
    return tuple(parts)
