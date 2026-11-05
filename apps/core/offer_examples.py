"""AIS-W W4-2: образцы для кнопки «Beispiele einfügen» шага «Angebot prüfen».

Статический реестр строк «Name — Preis» по типу бизнеса × виду ввода. Кнопка кладёт их в
textarea — в базе ничего не создаётся, владелец правит и сам жмёт «Übernehmen». Строки — ввод
владельца на немецком (не интерфейс), поэтому не переводятся. Каждая строка обязана
разбираться `offer_lines.parse_lines` без ошибок (замок)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

_BY_TYPE: dict[tuple[str, str], tuple[str, ...]] = {
    ("bakery", "waren"): (
        "Roggenbrot 750 g — 3,50 €",
        "Dinkelvollkornbrot — 4,20 €",
        "Laugenbrezel — 0,90 €",
        "Buttercroissant — 1,40 €",
        "Mohnbrötchen — 0,60 €",
        "Apfelstrudel (Stück) — 2,80 €",
        "Käsekuchen (Stück) — 3,20 €",
    ),
    ("butcher", "waren"): (
        "Rinderhüfte 100 g — 3,20 €",
        "Bratwurst (Stück) — 1,60 €",
        "Hackfleisch gemischt 500 g — 5,90 €",
        "Schinken gekocht 100 g — 2,40 €",
        "Fleischwurst 100 g — 1,50 €",
        "Frikadelle — 1,90 €",
    ),
    ("grocery", "waren"): (
        "Bio-Äpfel 1 kg — 3,49 €",
        "Vollmilch 1 l — 1,29 €",
        "Bergkäse 100 g — 2,49 €",
        "Freilandeier (10 Stück) — 3,99 €",
        "Hafermilch 1 l — 2,19 €",
        "Honig aus der Region 500 g — 7,90 €",
    ),
    ("clothing", "waren"): (
        "T-Shirt Basic — 19,90 €",
        "Jeans Straight — 79,00 €",
        "Strickpullover Merino — 89,00 €",
        "Leinenhemd — 59,00 €",
        "Wollschal — 29,00 €",
        "Ledergürtel — 39,00 €",
    ),
    ("retail", "waren"): (
        "Geschenkgutschein — 25,00 €",
        "Duftkerze — 14,90 €",
        "Notizbuch A5 — 12,50 €",
        "Keramikbecher — 18,00 €",
        "Grußkarte — 3,50 €",
        "Holzbrettchen — 24,00 €",
    ),
    ("cafe", "speisekarte"): (
        "Cappuccino — 3,40 €",
        "Latte Macchiato — 3,80 €",
        "Espresso — 2,20 €",
        "Croissant — 2,10 €",
        "Käsekuchen — 3,90 €",
        "Frühstück Klassik — 9,50 €",
    ),
    ("restaurant", "speisekarte"): (
        "Tagessuppe — 5,90 €",
        "Wiener Schnitzel mit Pommes — 18,50 €",
        "Spaghetti Bolognese — 12,90 €",
        "Gemischter Salat — 8,50 €",
        "Flammkuchen Elsässer Art — 11,50 €",
        "Apfelstrudel mit Vanilleeis — 6,90 €",
    ),
    ("catering", "speisekarte"): (
        "Fingerfood-Platte (10 Personen) — 89,00 €",
        "Antipasti-Buffet pro Person — 14,50 €",
        "Mittagsmenü pro Person — 18,00 €",
        "Dessertauswahl pro Person — 6,50 €",
        "Kaffee & Kuchen pro Person — 7,90 €",
    ),
    ("catering", "anfragen"): (
        "Hochzeitsbuffet",
        "Firmenfeier",
        "Geburtstagsfeier",
        "Grillabend",
        "Weihnachtsfeier",
    ),
    ("friseur", "termine"): (
        "Damenhaarschnitt — 45 Min — 42,00 €",
        "Herrenhaarschnitt — 30 Min — 26,00 €",
        "Färben — 90 Min — 65,00 €",
        "Strähnen — 120 Min — 85,00 €",
        "Waschen & Föhnen — 30 Min — 22,00 €",
        "Kinderhaarschnitt — 20 Min — 15,00 €",
    ),
    ("werkstatt", "termine"): (
        "Ölwechsel — 45 Min — 69,00 €",
        "Reifenwechsel — 30 Min — 29,00 €",
        "Inspektion — 2 Std — 189,00 €",
        "Klimaservice — 1 Std — 79,00 €",
        "Bremsen prüfen — 30 Min — 25,00 €",
    ),
    ("werkstatt", "anfragen"): (
        "Unfallschaden",
        "Hauptuntersuchung vorbereiten",
        "Zahnriemenwechsel",
        "Getriebe-Diagnose",
        "Lackschaden ausbessern",
    ),
    ("werkstatt", "waren"): (
        "Scheibenwischer (Paar) — 24,90 €",
        "Motoröl 5W-30 1 l — 14,90 €",
        "Frostschutz 1 l — 9,90 €",
        "Glühlampe H7 — 7,90 €",
        "Fußmatten-Set — 39,00 €",
    ),
    ("handwerker", "anfragen"): (
        "Badsanierung",
        "Fliesen verlegen",
        "Fenster einbauen",
        "Dachreparatur",
        "Malerarbeiten Innenraum",
        "Heizung warten",
    ),
    ("hotel", "zimmer"): (
        "Einzelzimmer — 1 Gast — 69,00 €",
        "Doppelzimmer Garten — 2 Gäste — 89,00 €",
        "Doppelzimmer Seeblick — 2 Gäste — 109,00 €",
        "Familienzimmer — 4 Gäste — 129,00 €",
        "Suite — 2 Gäste — 159,00 €",
    ),
    ("tour_operator", "anfragen"): (
        "Private Stadtführung",
        "Firmenausflug",
        "Schulklassen-Tour",
        "Junggesellenabschied",
        "Tour auf Englisch",
    ),
}

#: Образцы на вид, когда для типа своих нет (тип `other` и сочетания вне карты).
_BY_KIND: dict[str, tuple[str, ...]] = {
    "waren": _BY_TYPE[("retail", "waren")],
    "speisekarte": _BY_TYPE[("restaurant", "speisekarte")],
    "termine": (
        "Beratung — 60 Min — 80,00 €",
        "Erstgespräch — 30 Min — 40,00 €",
        "Workshop — 2 Std — 120,00 €",
        "Massage — 45 Min — 55,00 €",
        "Nachhilfe — 60 Min — 35,00 €",
    ),
    "zimmer": _BY_TYPE[("hotel", "zimmer")],
    "anfragen": (
        "Individuelles Angebot",
        "Beratung vor Ort",
        "Projekt nach Maß",
        "Reparatur",
        "Wartung",
    ),
}

#: Билеты: название, через сколько дней, время, цена — даты считаются от сегодня, чтобы
#: образец никогда не оказался в прошлом.
_TICKETS: dict[str, tuple[tuple[str, int, str, str], ...]] = {
    "events": (
        ("Konzert im Hof", 21, "19:30", "25,00 €"),
        ("Lesung mit Musik", 28, "19:00", "15,00 €"),
        ("Weinprobe", 35, "18:30", "39,00 €"),
        ("Kinderworkshop", 14, "15:00", "12,00 €"),
        ("Comedy-Abend", 42, "20:00", "22,00 €"),
    ),
    "tour_operator": (
        ("Altstadtführung", 7, "11:00", "15,00 €"),
        ("Abendführung mit Laterne", 10, "19:00", "18,00 €"),
        ("Radtour am Fluss", 14, "10:00", "29,00 €"),
        ("Kulinarische Tour", 21, "17:00", "49,00 €"),
        ("Brauerei-Führung", 28, "16:00", "24,00 €"),
    ),
}


def _tickets(business_type: str, today) -> tuple[str, ...]:
    rows = _TICKETS.get(business_type, _TICKETS["events"])
    return tuple(
        f"{name} — {(today + timedelta(days=days)):%d.%m.%Y} {clock} — {price}"
        for name, days, clock, price in rows
    )


def lines_for(business_type: str, kind: str, *, today=None) -> tuple[str, ...]:
    """Строки-образцы для типа × вида (пусто — образцов для вида нет)."""
    if kind == "tickets":
        return _tickets(business_type, today or timezone.localdate())
    return _BY_TYPE.get((business_type, kind)) or _BY_KIND.get(kind, ())


def examples_for(business_type: str, kind: str, *, today=None) -> str:
    """Текст для textarea (строки через перевод строки)."""
    return "\n".join(lines_for(business_type, kind, today=today))
