"""Раздел «Kinder & Familie» — демо-бизнесы Золингена (DCC).

Фото `mode-kinder*` заняты китом sg_puenktchen (раздел Mode) — здесь `mode-baby*`
и тематические плейсхолдеры `sg-*`.
"""

from ..spec import Biz, Ev, Item, Offer, Shelf, Svc

SECTION = "kinder-familie"

WOLKE7 = Biz(
    key="sg_wolke7",
    label="Babyladen Wolke 7",
    btype="retail",
    category="babybedarf",
    district="ohligs-aufderhoehe-merscheid",
    street="Merscheider Weg",
    house="11",
    lat="51.1710",
    lng="7.0280",
    phone="+49 212 5552001",
    accent="#be185d",
    hero_photo="mode-kat-baby",
    tagline="Erstausstattung, Tragen und Kinderwagen — mit Beratung ohne Zeitdruck.",
    about=(
        "Fachgeschäft in Merscheid: Bodys und Strampler aus Bio-Baumwolle, Tragehilfen zum "
        "Probieren, Kinderwagen von zwei Herstellern, Stillkissen und Wickelzubehör. "
        "Wickeltisch und Stillecke im Laden."
    ),
    hours="laden",
    usp=("beratung", "bio", "parken"),
    shelves=(
        Shelf(
            "Babybedarf",
            "babybedarf",
            "babybedarf",
            (
                Item(
                    "Babybody Wölkchen, 3er-Pack",
                    "24.90",
                    "Bio-Baumwolle, Gr. 56–80.",
                    "sg-babybody",
                ),
                Item(
                    "Strickjäckchen Himmelblau",
                    "34.90",
                    "Merinowolle, Gr. 62–86.",
                    "sg-babyjacke-strick",
                ),
                Item(
                    "Babymütze Sturmhaube",
                    "14.90",
                    "Wolle-Seide, für kalte Tage.",
                    "mode-babymuetze-sturmhaube",
                ),
                Item(
                    "Tragehilfe ab Geburt",
                    "129.00",
                    "Mitwachsend bis 20 kg — im Laden anprobieren.",
                    "sg-tragehilfe",
                ),
                Item(
                    "Kinderwagen Stadt & Land",
                    "549.00",
                    "Luftbereifung, Wanne und Sportsitz.",
                    "sg-kinderwagen",
                    stock=2,
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Erstausstattungs-Set −15 %",
            "Bodys, Strampler, Mützchen und Decke zusammen gekauft.",
            percent=15,
            ends="14d",
            response="show",
            photo="mode-set-erstausstattung",
            group="Saison",
            item="Babybody Wölkchen, 3er-Pack",
            tags=("nachhaltig",),
        ),
        Offer(
            "Trageberatung kostenlos",
            "30 Minuten mit Trageberaterin — Termin per Anfrage.",
            ends="none",
            response="inquire",
            photo="sg-tragehilfe",
            group="Dauerhaft",
        ),
    ),
)

PURZELBAUM = Biz(
    key="sg_purzelbaum",
    label="Kinderturnen Purzelbaum",
    btype="other",
    category="kinder-aktivitaeten",
    district="wald",
    street="Am Weiher",
    house="4",
    lat="51.1900",
    lng="7.0300",
    phone="+49 212 5552002",
    accent="#ea580c",
    hero_photo="sg-kinderturnen",
    tagline="Eltern-Kind-Turnen, Bewegungskurse ab 3 und Kinderyoga — in kleiner Halle in Wald.",
    about=(
        "Eigene Turnhalle mit Mattenlandschaft, Kletterwand und Trampolin. Kurse nach "
        "Alter, maximal zehn Kinder, Probestunde kostenlos. Eltern dürfen zuschauen."
    ),
    hours="studio",
    usp=("probe", "kinder", "parken"),
    services=(
        Svc(
            "Eltern-Kind-Turnen (1–3 Jahre)",
            45,
            "8.00",
            "Krabbeln, klettern, rutschen — Mi 10:00.",
            "sg-kinderturnen",
        ),
        Svc(
            "Bewegungskurs (3–6 Jahre)",
            45,
            "9.00",
            "Laufen, Springen, Balancieren — Do 16:00.",
            "sg-kinder-bewegung",
        ),
        Svc(
            "Kinderyoga (5–9 Jahre)",
            45,
            "9.00",
            "Spielerische Haltungen und Entspannung — Fr 15:30.",
            "sg-kinderyoga",
        ),
    ),
    events=(
        Ev(
            "Tobe-Nachmittag in der Halle",
            6,
            15,
            "6.00",
            20,
            "Zwei Stunden freies Toben für 3–8 Jahre, Eltern bleiben dabei.",
            "sg-kinderturnen",
            duration_hours=2,
        ),
    ),
    offers=(
        Offer(
            "10er-Karte Kinderkurs 79 €",
            "Zehn Stunden, für Geschwister übertragbar.",
            price="79.00",
            ends="none",
            response="show",
            photo="sg-kinder-bewegung",
            group="Dauerhaft",
            tags=("familienfreundlich",),
        ),
    ),
)

KREISEL = Biz(
    key="sg_kreisel",
    label="Spielwaren Kreisel",
    btype="retail",
    category="spielzeug",
    district="mitte",
    street="Lindenplatz",
    house="6",
    lat="51.1745",
    lng="7.0880",
    phone="+49 212 5552003",
    accent="#1d4ed8",
    hero_photo="sg-spielzeugladen",
    tagline="Holzspielzeug, Brettspiele und Bastelbedarf — mit Spieletisch zum Ausprobieren.",
    about=(
        "Spielwarenladen am Lindenplatz: Holzspielzeug europäischer Hersteller, Brettspiele "
        "für jedes Alter, Puzzle, Bastelmaterial. Jeden Samstagvormittag Spielerunde."
    ),
    hours="laden",
    usp=("beratung", "geschenk", "zahlung"),
    shelves=(
        Shelf(
            "Spielzeug",
            "spielzeug",
            "spielzeug",
            (
                Item(
                    "Bauklötze Buche, 50 Teile",
                    "34.90",
                    "Unbehandeltes Holz, im Baumwollbeutel.",
                    "sg-bauklotz",
                ),
                Item(
                    "Kugelbahn Holz",
                    "59.00",
                    "Erweiterbar, ab 3 Jahren.",
                    "sg-kugelbahn",
                ),
                Item(
                    "Familien-Brettspiel Bergische Burgen",
                    "29.90",
                    "2–5 Spieler, ab 8 Jahren, 45 Minuten.",
                    "sg-brettspiel",
                ),
                Item("Puzzle 500 Teile", "14.90", "Motiv Schloss Burg.", "sg-puzzle"),
                Item(
                    "Puppe Stoff, 35 cm",
                    "39.00",
                    "Handgenäht, waschbar.",
                    "sg-puppe",
                ),
            ),
        ),
    ),
    events=(
        Ev(
            "Spielerunde für Familien",
            4,
            10,
            "0.00",
            16,
            "Neue Brettspiele erklärt und ausprobiert — kostenlos.",
            "sg-brettspiel",
            duration_hours=3,
            weekday=5,
        ),
    ),
    offers=(
        Offer(
            "Brettspiel der Woche −20 %",
            "Jede Woche ein Spiel vom Spieletisch günstiger.",
            percent=20,
            ends="week",
            response="show",
            photo="sg-brettspiel",
            group="Diese Woche",
            item="Familien-Brettspiel Bergische Burgen",
        ),
    ),
)

LESERATTE = Biz(
    key="sg_leseratte",
    label="Kinderbuchladen Leseratte",
    btype="retail",
    category="kinder-aktivitaeten",
    district="burg-hoehscheid",
    street="Schlossblick",
    house="4",
    lat="51.1390",
    lng="7.1480",
    phone="+49 212 5552004",
    accent="#0f766e",
    hero_photo="sg-kinderbuch-regal",
    tagline="Bilderbücher, Erstleser, Jugendbuch — und jeden Mittwoch die Vorlesestunde.",
    about=(
        "Kleine Buchhandlung unterhalb von Schloss Burg: nur Kinder- und Jugendbuch, "
        "Leseecke mit Kissen, Bestellung bis zum nächsten Tag. Vorlesestunde mittwochs 16 Uhr."
    ),
    hours="laden",
    usp=("beratung", "kinder", "geschenk"),
    shelves=(
        Shelf(
            "Kinderbücher",
            "kinderbuecher",
            "spielzeug",
            (
                Item(
                    "Bilderbuch Der kleine Schleifer",
                    "14.00",
                    "Ab 3 Jahren, gebunden.",
                    "sg-kinderbuch-bilder",
                    vat="7.00",
                ),
                Item(
                    "Erstleser Burg-Abenteuer",
                    "9.00",
                    "Ab 6 Jahren, große Schrift.",
                    "sg-kinderbuch-erstleser",
                    vat="7.00",
                ),
                Item(
                    "Jugendroman Wupperlicht",
                    "16.00",
                    "Ab 12 Jahren, Taschenbuch.",
                    "sg-jugendbuch",
                    vat="7.00",
                ),
                Item(
                    "Lesetagebuch",
                    "8.90",
                    "Für die ersten 20 Bücher — mit Stickern.",
                    "journal-book",
                ),
            ),
        ),
    ),
    events=(
        Ev(
            "Vorlesestunde (ab 4)",
            2,
            16,
            "0.00",
            12,
            "Jeden Mittwoch — 45 Minuten Geschichten, kostenlos.",
            "sg-kinderbuch-bilder",
            duration_hours=1,
            weekday=2,
        ),
        Ev(
            "Autorenlesung für Kinder",
            19,
            16,
            "4.00",
            30,
            "Die Autorin des Burg-Abenteuers liest und zeichnet.",
            "sg-kinderbuch-erstleser",
            duration_hours=1,
        ),
    ),
    offers=(
        Offer(
            "Schulanfang: Lesetagebuch geschenkt",
            "Ab drei Erstlesebüchern gibt es das Lesetagebuch mit Stickern dazu.",
            ends="14d",
            response="show",
            photo="sg-kinderbuch-erstleser",
            group="Saison",
            item="Erstleser Burg-Abenteuer",
        ),
    ),
)

KINDERKISTE = Biz(
    key="sg_kinderkiste",
    label="Kinder-Secondhand Kinderkiste",
    btype="retail",
    category="babybedarf",
    district="mitte",
    street="Schleifergasse",
    house="14",
    lat="51.1715",
    lng="7.0790",
    phone="+49 212 5552005",
    accent="#65a30d",
    hero_photo="sg-secondhand-kinder",
    tagline="Gebrauchte Kinderkleidung, Spielzeug und Kinderwagen — geprüft, gewaschen, günstig.",
    about=(
        "Secondhand für Kinder von 0 bis 10: Kleidung nach Größe sortiert, Spielzeug "
        "vollständig und sauber, Kinderwagen und Autositze mit Prüfdatum. Wir kaufen an — "
        "dienstags und donnerstags."
    ),
    hours="laden",
    usp=("nachhaltig", "kinder", "zahlung"),
    shelves=(
        Shelf(
            "Secondhand für Kinder",
            "secondhand",
            "babybedarf",
            (
                Item(
                    "Kleiderpaket Gr. 74, 10 Teile",
                    "19.00",
                    "Bodys, Hosen, Shirts — zusammengestellt.",
                    "sg-kleiderpaket-kinder",
                ),
                Item(
                    "Holz-Laufrad, gebraucht",
                    "35.00",
                    "Geprüft, neue Griffe.",
                    "sg-laufrad",
                    stock=1,
                ),
                Item(
                    "Kinderwagen Buggy, gebraucht",
                    "79.00",
                    "Gereinigt, Bremsen geprüft, 2 Jahre alt.",
                    "sg-kinderwagen-gebraucht",
                    stock=1,
                ),
                Item(
                    "Bilderbuch-Paket, 5 Bücher",
                    "9.00",
                    "Gut erhalten, ab 2 Jahren.",
                    "sg-kinderbuch-paket",
                    vat="7.00",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Wintersachen jetzt −30 %",
            "Alle Jacken, Schneehosen und Stiefel bis Ende des Monats.",
            percent=30,
            ends="14d",
            response="show",
            photo="sg-kleiderpaket-kinder",
            group="Saison",
            tags=("gebraucht", "nachhaltig"),
        ),
        Offer(
            "Ankauf-Dienstag: 10 % mehr Gutschrift",
            "Wer dienstags abgibt, bekommt 10 % mehr auf den Ladengutschein.",
            ends="week",
            response="show",
            photo="sg-secondhand-kinder",
            group="Diese Woche",
            tags=("gebraucht",),
        ),
    ),
)

BUSINESSES = (WOLKE7, PURZELBAUM, KREISEL, LESERATTE, KINDERKISTE)
