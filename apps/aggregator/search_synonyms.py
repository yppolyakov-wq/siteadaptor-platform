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
    ("süßigkeiten", "süßwaren", "schokolade", "pralinen", "bonbons", "konfekt", "naschen"),
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

# Межъязыковой мост (фидбэк владельца 2026-10-23: «Сладости» на русском портале — 0 из
# 0). Объявления пишутся по-немецки, а житель ищет на своём языке. Ключ — ОСНОВА слова
# (ru/uk/en/tr, нижний регистр): слово запроса, начинающееся с неё, ищется ещё и по
# немецким терминам (и их группам синонимов). Основа короче MIN_STEM — только целым
# словом, иначе «кот» нашёл бы «котлету». Немецкие термины — головы для подстроки
# («kuchen» находит «Käsekuchen»).
CROSS_LANG_MIN_STEM = 4
CROSS_LANG: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # Lebensmittel
    (
        ("сладост", "сладк", "солодощ", "солодк", "sweets", "candy", "tatlı"),
        ("süßigkeiten", "kuchen"),
    ),
    (("шоколад", "chocolate", "çikolata"), ("schokolade",)),
    (("конфет", "цукерк", "bonbon", "şeker"), ("bonbons", "süßigkeiten")),
    (("торт", "пирож", "выпечк", "випічк", "пиріж", "cake", "cakes", "pastry", "kek"), ("kuchen",)),
    (("хлеб", "хліб", "булк", "булочк", "bread", "bakery", "ekmek", "fırın", "pekarn"), ("brot",)),
    (("пекарн", "булочн"), ("bäckerei",)),
    (
        ("мясо", "мяса", "мясом", "мясн", "м'ясо", "м'яса", "meat", "butcher", "et", "kasap"),
        ("fleisch",),
    ),
    (("колбас", "ковбас", "sausage", "sucuk"), ("wurst",)),
    (("сыр", "сир", "cheese", "peynir"), ("käse",)),
    (("фрукт", "fruit", "fruits", "meyve"), ("obst",)),
    (("овощ", "овоч", "vegetable", "vegetables", "sebze"), ("gemüse",)),
    (("напит", "напої", "drink", "drinks", "içecek"), ("getränke",)),
    (("пиво", "beer", "bira"), ("bier",)),
    (("вино", "wine", "şarap"), ("wein",)),
    (("кофе", "кава", "coffee", "kahve"), ("kaffee",)),
    (("мороженое", "морожен", "морозиво", "dondurma"), ("eis",)),
    (("пицц", "піц", "pizza"), ("pizza",)),
    (("суши", "суші", "sushi"), ("sushi",)),
    (("завтрак", "сніданок", "breakfast", "kahvaltı"), ("frühstück",)),
    (("обед", "обід", "lunch", "öğle"), ("mittagessen",)),
    (("ресторан", "restaurant", "lokanta"), ("restaurant",)),
    (("кафе", "cafe", "kafe"), ("café",)),
    (("веган", "vegan"), ("vegan",)),
    (("вегетариан", "вегетаріан", "vegetarian", "vejetaryen"), ("vegetarisch",)),
    (("продукт", "grocery", "groceries", "market"), ("lebensmittel",)),
    # Mode
    (("одежд", "одяг", "clothes", "clothing", "giyim", "kıyafet"), ("kleidung",)),
    (("обув", "взутт", "shoes", "ayakkabı"), ("schuhe",)),
    (("куртк", "пальт", "jacket", "coat", "ceket"), ("jacke",)),
    (("брюк", "штан", "джинс", "trousers", "jeans", "pantolon"), ("hose",)),
    (("плать", "сукн", "dress", "elbise"), ("kleid",)),
    (("сумк", "рюкзак", "bag", "çanta"), ("tasche",)),
    # Technik
    (("телефон", "смартфон", "phone", "telefon"), ("handy",)),
    (("ноутбук", "компьютер", "комп'ютер", "laptop", "computer", "bilgisayar"), ("laptop",)),
    (("ремонт", "repair", "tamir"), ("reparatur",)),
    (("наушник", "навушник", "headphone", "kulaklık"), ("kopfhörer",)),
    # Haus & Garten
    (("мебел", "меблі", "furniture", "mobilya"), ("möbel",)),
    (("цвет", "квіт", "flower", "flowers", "çiçek"), ("blumen",)),
    (("ламп", "светильн", "lamp", "lamba"), ("lampe",)),
    (("нож", "ножи", "ножі", "ножей", "knife", "knives", "bıçak"), ("messer",)),
    # Beauty, Gesundheit
    (("парикмах", "перукар", "стрижк", "hairdresser", "haircut", "kuaför", "berber"), ("friseur",)),
    (("косметик", "cosmetic", "kozmetik"), ("kosmetik",)),
    (("маникюр", "манікюр", "manicure", "manikür"), ("maniküre",)),
    (("массаж", "масаж", "massage", "masaj"), ("massage",)),
    (("фитнес", "фітнес", "fitness", "spor"), ("fitness",)),
    (("йога", "yoga"), ("yoga",)),
    # Freizeit, Kinder, Tiere, Reisen
    (("игрушк", "іграшк", "toy", "toys", "oyuncak"), ("spielzeug",)),
    (("детск", "дитяч", "дети", "діти", "kid", "kids", "çocuk"), ("kinder",)),
    (("собак", "пес", "dog", "dogs", "köpek"), ("hund",)),
    (("кошк", "кіш", "кот", "cat", "cats", "kedi"), ("katze",)),
    (("корм", "mama"), ("tierfutter",)),
    (("велосипед", "bicycle", "bike", "bisiklet"), ("fahrrad",)),
    (("гостиниц", "отел", "готел", "hotel", "otel"), ("hotel",)),
    (("экскурс", "екскурс", "tour", "tur"), ("tour",)),
    (("подар", "gift", "gifts", "hediye"), ("geschenk",)),
    (("курс", "workshop"), ("kurs",)),
)


#: Слова моста, которые сравниваются только целиком, хотя и длиннее MIN_STEM
#: («кафе» как основа нашла бы «кафель»).
CROSS_LANG_EXACT = frozenset(
    {"кафе", "cafe", "kafe", "pizza", "sushi", "yoga", "tour", "hotel", "otel"}
)


def _cross_index():
    exact, stems = {}, []
    for words, german in CROSS_LANG:
        for word in words:
            if len(word) < CROSS_LANG_MIN_STEM or word in CROSS_LANG_EXACT:
                exact.setdefault(word, ())
                exact[word] = tuple(dict.fromkeys(exact[word] + german))
            else:
                stems.append((word, german))
    stems.sort(key=lambda item: -len(item[0]))  # длинная основа — точнее
    return exact, tuple(stems)


_CROSS_EXACT, _CROSS_STEMS = _cross_index()


def translate_heads(token: str) -> tuple[str, ...]:
    """Немецкие термины моста для слова — без синонимов (для поиска подстрокой)."""
    german = _CROSS_EXACT.get(token)
    if german is None:
        german = next((g for stem, g in _CROSS_STEMS if token.startswith(stem)), ())
    return german


def translate(token: str) -> tuple[str, ...]:
    """Слово запроса на ru/uk/en/tr → немецкие термины поиска (с их синонимами); пусто,
    если слова в мосте нет. Немецкие слова сюда не попадают — их ищет основная ветка."""
    german = translate_heads(token)
    out: list[str] = []
    for term in german:
        out += expand(term)
    return tuple(dict.fromkeys(out))


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
        # без generic-суффиксов zeug/spiel/studio/service/pflege (ревью: «Werkzeug» →
        # все Spielzeug/Fahrzeug, «Beispiel» → «spiel», «Fotostudio» → все студии)
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
