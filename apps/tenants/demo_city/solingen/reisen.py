"""Раздел «Reisen & Übernachten» — демо-бизнесы Золингена (DCC).

Номера (`Room`) → модуль stays; категория номера в каталоге города — из раздела
(Р-3: `ferienwohnungen` у квартир, иначе `hotels`). Экскурсии — события тур-оператора.
"""

from ..spec import Biz, Ev, Offer, Room, Svc

SECTION = "reisen-uebernachten"

ALTE_SCHMIEDE = Biz(
    key="sg_alte_schmiede",
    label="Hotel Zur Alten Schmiede",
    btype="hotel",
    category="hotels",
    district="mitte",
    street="Schleifergasse",
    house="2",
    lat="51.1760",
    lng="7.0700",
    phone="+49 221 4710194",
    accent="#7c2d12",
    hero_photo="hotel-lobby",
    tagline="18 Zimmer in einer ehemaligen Schmiede — Frühstück vom Bäcker nebenan.",
    about=(
        "Stadthotel in der Innenstadt: ruhige Zimmer zum Hof, Frühstück bis 11 Uhr, "
        "Fahrradgarage, Parkplatz gegenüber. Zu Fuß fünf Minuten zum Klingenmuseum."
    ),
    hours="hotel",
    usp=("fruehstueck", "fahrrad", "wlan", "parken"),
    rooms=(
        Room(
            "Einzelzimmer Hof",
            "room",
            6,
            "79.00",
            1,
            "16 m², Dusche, Schreibtisch, Blick in den ruhigen Hof.",
            ("hotel-interior",),
        ),
        Room(
            "Doppelzimmer Schmiede",
            "room",
            10,
            "109.00",
            2,
            "22 m², Sichtmauerwerk, Regendusche.",
            ("hotel-bathroom",),
        ),
        Room(
            "Familienzimmer",
            "room",
            2,
            "149.00",
            4,
            "32 m², zwei Räume, Kinderbetten auf Wunsch.",
            ("sg-familienzimmer",),
        ),
    ),
    offers=(
        Offer(
            "Wochenende 2 Nächte −15 %",
            "Freitag bis Sonntag im Doppelzimmer, Frühstück inklusive.",
            percent=15,
            ends="14d",
            response="show",
            photo="hotel-bathroom",
            group="Saison",
            tags=("familienfreundlich",),
        ),
    ),
)

FACHWERKBLICK = Biz(
    key="sg_fachwerkblick",
    label="Ferienwohnung Fachwerkblick",
    btype="hotel",
    category="ferienwohnungen",
    district="graefrath",
    street="Am Fachwerk",
    house="12",
    lat="51.2100",
    lng="7.0650",
    phone="+49 221 4710195",
    accent="#854d0e",
    hero_photo="apartment-living",
    tagline="Zwei Ferienwohnungen im Fachwerkhaus am Gräfrather Markt — ab zwei Nächten.",
    about=(
        "Liebevoll sanierte Wohnungen über einem Altstadtladen: Küche, Waschmaschine, "
        "schnelles WLAN. Schlüsselbox für späte Anreise, Brötchenservice auf Wunsch."
    ),
    hours="hotel",
    usp=("wlan", "ruhe", "kinder"),
    rooms=(
        Room(
            "Wohnung Marktblick (2 Zimmer)",
            "apartment",
            1,
            "95.00",
            4,
            "55 m², Schlafzimmer, Wohnküche, Schlafsofa.",
            ("apartment-living", "apartment-kitchen"),
        ),
        Room(
            "Studio Dachgarten",
            "apartment",
            1,
            "75.00",
            2,
            "32 m² unterm Dach mit kleiner Terrasse.",
            ("sg-studio-dach",),
        ),
    ),
    offers=(
        Offer(
            "7 Nächte zum Preis von 6",
            "Bei Buchung einer Woche — ganzjährig.",
            ends="none",
            response="show",
            photo="apartment-kitchen",
            group="Dauerhaft",
        ),
    ),
)

KLINGENPFAD = Biz(
    key="sg_klingenpfad",
    label="Stadtführungen Klingenpfad",
    btype="tour_operator",
    category="touren",
    district="mitte",
    street="Messerstraße",
    house="8",
    lat="51.1720",
    lng="7.0860",
    phone="+49 221 4710196",
    accent="#0f766e",
    hero_photo="city-tour",
    tagline="Geführte Rundgänge durch Solingen — Klingen, Fachwerk, Wupper und Schloss Burg.",
    about=(
        "Drei zertifizierte Gästeführerinnen und -führer. Öffentliche Touren am Wochenende, "
        "private Gruppen nach Vereinbarung, Touren auch auf Englisch."
    ),
    hours="laden",
    usp=("qualitaet", "kinder", "barrierefrei"),
    events=(
        Ev(
            "Altstadtrundgang Gräfrath",
            4,
            11,
            "12.00",
            20,
            "90 Minuten Fachwerk, Kloster und Marktplatz.",
            "tour-guide-woman",
            theme="pilgern",
            duration_hours=2,
        ),
        Ev(
            "Klingenstadt: Schleifer und Schmiede",
            9,
            14,
            "14.00",
            20,
            "Vom Museum zum Kotten — zwei Stunden Industriegeschichte.",
            "tour-guide-man",
            theme="pilgern",
            duration_hours=2,
        ),
        Ev(
            "Müngstener Brücke zu Fuß",
            16,
            10,
            "15.00",
            16,
            "Wanderung zur höchsten Eisenbahnbrücke Deutschlands, 8 km.",
            "city-tour",
            theme="natur",
            duration_hours=4,
        ),
    ),
    offers=(
        Offer(
            "Private Gruppe ab 90 €",
            "Bis 15 Personen, Thema und Sprache nach Wunsch — anfragen.",
            ends="none",
            response="inquire",
            photo="tour-guide-woman",
            group="Dauerhaft",
        ),
    ),
    anfrage=("date", "guests"),
)

BERGLAND_AUSFLUG = Biz(
    key="sg_bergland_ausflug",
    label="Ausflugsfahrten Bergland",
    btype="tour_operator",
    category="ausfluege",
    district="burg-hoehscheid",
    street="Schlossblick",
    house="9",
    lat="51.1350",
    lng="7.1550",
    phone="+49 221 4710197",
    accent="#1e40af",
    hero_photo="sg-ausflugsbus",
    tagline="Tagesfahrten im Kleinbus ab Solingen — Eifel, Mosel, Weihnachtsmärkte.",
    about=(
        "Familienbetrieb mit zwei Kleinbussen (je 16 Plätze). Abfahrt an fünf Haltepunkten in "
        "Solingen, Reiseleitung an Bord, kleine Gruppen. Keine Verkaufsveranstaltungen."
    ),
    hours="praxis",
    usp=("familie", "qualitaet", "barrierefrei"),
    events=(
        Ev(
            "Tagesfahrt Mosel mit Weinprobe",
            12,
            7,
            "69.00",
            16,
            "Cochem, Schifffahrt, Weinprobe — Rückkehr gegen 21 Uhr.",
            "sg-ausflugsbus",
            duration_hours=14,
        ),
        Ev(
            "Weihnachtsmarkt Aachen",
            40,
            9,
            "39.00",
            16,
            "Printen, Dom, Glühwein — vier Stunden Aufenthalt.",
            "sg-weihnachtsmarkt",
            duration_hours=10,
        ),
        Ev(
            "Wanderfahrt Eifel: Vulkanseen",
            19,
            8,
            "45.00",
            16,
            "Zwei Maare zu Fuß, Einkehr im Gasthof.",
            "sg-eifel-see",
            theme="natur",
            duration_hours=11,
        ),
    ),
    offers=(
        Offer(
            "Frühbucher Mosel 59 €",
            "Bei Buchung bis Sonntag — statt 69 €.",
            price="59.00",
            was="69.00",
            ends="week",
            response="show",
            photo="sg-ausflugsbus",
            group="Diese Woche",
        ),
    ),
)

WUPPERAUE = Biz(
    key="sg_wupperaue",
    label="Landgasthof Wupperaue",
    btype="hotel",
    category="hotels",
    district="ohligs-aufderhoehe-merscheid",
    street="Merscheider Weg",
    house="88",
    lat="51.1450",
    lng="7.0400",
    phone="+49 221 4710198",
    accent="#365314",
    hero_photo="sg-landgasthof",
    tagline="Gasthof mit acht Zimmern am Waldrand — Hausmannskost und Biergarten.",
    about=(
        "Landgasthof in dritter Generation: Zimmer über der Gaststube, Frühstück mit Eiern "
        "vom Nachbarhof, Biergarten unter Kastanien. Hunde willkommen, Radfahrer auch."
    ),
    hours="hotel",
    usp=("fruehstueck", "hunde", "terrasse"),
    rooms=(
        Room(
            "Doppelzimmer Waldseite",
            "room",
            5,
            "89.00",
            2,
            "20 m², Dusche, Blick ins Grüne.",
            ("sg-zimmer-wald",),
        ),
        Room(
            "Familienzimmer Scheune",
            "room",
            3,
            "129.00",
            4,
            "35 m² im Nebengebäude, zwei Schlafräume.",
            ("sg-scheune-zimmer",),
        ),
    ),
    services=(
        Svc(
            "Tisch im Biergarten (Gruppe)",
            120,
            "0.00",
            "Ab 10 Personen reservieren.",
            "sg-biergarten",
        ),
    ),
    offers=(
        Offer(
            "Wanderwochenende: 2 Nächte + Lunchpaket 169 €",
            "Pro Doppelzimmer, Frühstück und Lunchpakete inklusive.",
            price="169.00",
            was="178.00",
            ends="14d",
            response="show",
            photo="sg-zimmer-wald",
            group="Saison",
            tags=("hundefreundlich",),
        ),
    ),
)

BUSINESSES = (ALTE_SCHMIEDE, FACHWERKBLICK, KLINGENPFAD, BERGLAND_AUSFLUG, WUPPERAUE)
