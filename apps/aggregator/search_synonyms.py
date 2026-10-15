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
    ("restaurant", "gaststätte"),
    ("café", "cafe", "kaffeehaus"),
    ("frühstück", "brunch"),
    ("mittagessen", "mittagstisch", "lunch"),
    ("pizza", "pizzeria"),
    ("döner", "kebab"),
    ("lieferung", "lieferservice", "liefern"),
    ("takeaway", "abholung", "mitnehmen"),
    # Mode & Accessoires
    ("kleidung", "mode", "bekleidung", "klamotten"),
    ("schuhe", "sneaker", "stiefel"),
    ("jacke", "mantel"),
    ("tasche", "rucksack", "handtasche"),
    # Elektronik & Technik
    ("handy", "smartphone", "mobiltelefon", "iphone"),
    ("laptop", "notebook", "computer", "pc"),
    ("reparatur", "reparieren", "werkstatt"),
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
    ("kinder", "kids", "familie"),
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
