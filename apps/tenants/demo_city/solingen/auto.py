"""Раздел «Auto & Mobilität» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "auto-mobilitaet"

KOLBENRING = Biz(
    key="sg_kolbenring",
    label="Kfz-Meisterbetrieb Kolbenring",
    btype="werkstatt",
    category="kfz-reparatur",
    district="ohligs-aufderhoehe-merscheid",
    street="Lerchenstraße",
    house="30",
    lat="51.1580",
    lng="7.0200",
    phone="+49 212 5552101",
    accent="#1f2937",
    hero_photo="car-workshop",
    tagline="Inspektion, HU-Vorbereitung und Reparatur aller Marken — Festpreise vorab.",
    about=(
        "Freie Werkstatt mit drei Hebebühnen in Ohligs. Kostenvoranschlag vor jeder Arbeit, "
        "Ersatzwagen auf Anfrage, HU durch Prüforganisation im Haus dienstags und freitags."
    ),
    hours="handwerk",
    usp=("meister", "garantie", "termin"),
    services=(
        Svc(
            "Inspektion nach Herstellervorgabe",
            120,
            "149.00",
            "Inkl. Ölwechsel bis 5 l, Filter nach Aufwand.",
            "car-repair",
        ),
        Svc(
            "HU/AU-Vorbereitung",
            60,
            "49.00",
            "Durchsicht und Mängelliste vor der Prüfung.",
            "car-mechanic",
        ),
        Svc("Bremsen vorne (Beläge)", 90, "189.00", "Teile und Arbeit, Kleinwagen.", "brake-pad"),
        Svc("Fehlerdiagnose", 30, "39.00", "Auslesen und Einschätzung.", "car-engine"),
    ),
    offers=(
        Offer(
            "Winter-Check 19 €",
            "Batterie, Licht, Reifen, Frostschutz — diese Woche.",
            price="19.00",
            was="29.00",
            ends="week",
            response="show",
            photo="car-workshop",
            group="Diese Woche",
        ),
        Offer(
            "Kostenvoranschlag per Anfrage",
            "Fahrzeug, Kilometerstand und Problem schildern — wir melden uns am selben Tag.",
            ends="none",
            response="inquire",
            photo="mechanic-man",
            group="Dauerhaft",
        ),
    ),
    anfrage=("date",),
)

VENTIL = Biz(
    key="sg_ventil",
    label="Autoteile Ventil",
    btype="retail",
    category="autoteile",
    district="wald",
    street="Fuchsweg",
    house="9",
    lat="51.1760",
    lng="7.0200",
    phone="+49 212 5552102",
    accent="#b91c1c",
    hero_photo="car-parts",
    tagline="Verschleißteile, Öle und Zubehör — heute bestellt, morgen am Tresen.",
    about=(
        "Teilehandel für Werkstätten und Selbermacher in Wald: Bremsen, Filter, Batterien, "
        "Öle. Teilesuche nach Fahrzeugschein, Rücknahme von Altöl und Batterien."
    ),
    hours="handwerk",
    usp=("beratung", "abholung", "parken"),
    shelves=(
        Shelf(
            "Autoteile & Pflege",
            "autoteile",
            "autoteile",
            (
                Item(
                    "Motoröl 5W-30, 5 l",
                    "34.90",
                    "Longlife, für Benziner und Diesel.",
                    "motor-oil",
                    unit="l",
                    content="5",
                ),
                Item(
                    "Bremsbeläge vorne", "39.90", "Satz, passend nach Fahrzeugschein.", "brake-pad"
                ),
                Item("Luftfilter", "12.90", "Für gängige Kleinwagen.", "air-filter"),
                Item(
                    "Frostschutz Kühler, 1,5 l",
                    "9.90",
                    "Konzentrat, bis −40 °C.",
                    "antifreeze",
                    unit="l",
                    content="1.5",
                ),
                Item("Scheibenwischer 60/45 cm", "19.90", "Flachbalken, Paar.", "wiper-blade"),
            ),
        ),
    ),
    offers=(
        Offer(
            "Ölwechsel-Paket: Öl + Filter −10 %",
            "Motoröl und Ölfilter zusammen gekauft.",
            percent=10,
            ends="week",
            response="show",
            photo="motor-oil",
            group="Diese Woche",
            item="Motoröl 5W-30, 5 l",
        ),
    ),
)

PROFIL = Biz(
    key="sg_profil",
    label="Reifenservice Profil",
    btype="werkstatt",
    category="kfz-reparatur",
    district="graefrath",
    street="Brunnenweg",
    house="15",
    lat="51.1950",
    lng="7.0500",
    phone="+49 212 5552103",
    accent="#0f172a",
    hero_photo="tire-change",
    tagline="Reifenwechsel, Einlagerung und Auswuchten — Termin online, 30 Minuten vor Ort.",
    about=(
        "Reifenfachbetrieb in Gräfrath: Wechsel mit Auswuchten, Einlagerung im Hochregal, "
        "Reifenwäsche, Reparatur von Stichverletzungen. Neue Reifen auf Bestellung."
    ),
    hours="handwerk",
    usp=("termin", "schnell", "zahlung"),
    services=(
        Svc(
            "Räderwechsel mit Auswuchten",
            30,
            "39.00",
            "Vier Räder, inklusive Luftdruck.",
            "tire-change",
        ),
        Svc(
            "Einlagerung je Saison",
            15,
            "35.00",
            "Trocken, gewaschen, mit Reifenbild.",
            "sg-reifenlager",
        ),
        Svc(
            "Reifenreparatur",
            30,
            "25.00",
            "Stichverletzung in der Lauffläche.",
            "sg-reifen-reparatur",
        ),
    ),
    offers=(
        Offer(
            "Wechsel + Einlagerung 69 €",
            "Beides zusammen — statt 74 €. Termine vor dem Saisonstart noch frei.",
            price="69.00",
            was="74.00",
            ends="14d",
            response="show",
            photo="tire-change",
            group="Saison",
        ),
    ),
)

WUPPERSCHLEIFE = Biz(
    key="sg_wupperschleife",
    label="Radverleih Wupperschleife",
    btype="other",
    category="vermietung",
    district="burg-hoehscheid",
    street="Wupperufer",
    house="12",
    lat="51.1480",
    lng="7.1200",
    phone="+49 212 5552104",
    accent="#047857",
    hero_photo="bike-tour",
    tagline="E-Bikes, Trekkingräder und Kinderanhänger — direkt am Wupperradweg.",
    about=(
        "Verleih in einer alten Schleifkotten-Garage an der Wupper. Räder in allen Größen, "
        "Helme und Schlösser inklusive, Routenvorschläge nach Müngsten und Burg."
    ),
    hours="freizeit",
    usp=("fahrrad", "kinder", "parken"),
    services=(
        Svc("E-Bike Tagesmiete", 480, "39.00", "Akku für 80 km, Helm und Schloss.", "bike-tour"),
        Svc(
            "Trekkingrad Tagesmiete", 480, "19.00", "7 Gänge, Gepäckträger.", "sg-fahrrad-trekking"
        ),
        Svc(
            "Kinderanhänger Tagesmiete",
            480,
            "12.00",
            "Für zwei Kinder, mit Regenverdeck.",
            "sg-fahrradanhaenger",
        ),
    ),
    offers=(
        Offer(
            "Familienpaket: 2 E-Bikes + Anhänger 79 €",
            "Samstag und Sonntag — statt 90 €.",
            price="79.00",
            was="90.00",
            ends="week",
            response="reserve",
            photo="bike-tour",
            group="Diese Woche",
        ),
    ),
)

KLINGENMOBIL = Biz(
    key="sg_klingenmobil",
    label="Mietwagen Klingenmobil",
    btype="other",
    category="vermietung",
    district="mitte",
    street="Messerstraße",
    house="52",
    lat="51.1620",
    lng="7.0650",
    phone="+49 212 5552105",
    accent="#1e40af",
    hero_photo="sg-mietwagen",
    tagline="Transporter, Kombi und Kleinwagen — stundenweise oder für den Umzug am Wochenende.",
    about=(
        "Lokale Autovermietung ohne Flughafenzuschlag: 12 Fahrzeuge, Abholung am Stadtrand, "
        "Kilometer inklusive innerhalb von 200 km. Anhängerkupplung und Anhänger auf Wunsch."
    ),
    hours="laden",
    usp=("termin", "zahlung", "parken"),
    services=(
        Svc(
            "Transporter 3,5 t (Tag)",
            480,
            "89.00",
            "Kastenwagen, 11 m³, 200 km inklusive.",
            "sg-transporter",
        ),
        Svc("Kombi (Tag)", 480, "59.00", "Fünf Sitze, großer Kofferraum.", "sg-mietwagen"),
        Svc("Kleinwagen (3 Stunden)", 180, "19.00", "Für die Fahrt in die Stadt.", "sg-kleinwagen"),
    ),
    offers=(
        Offer(
            "Umzugs-Wochenende: Transporter Fr–Mo 199 €",
            "Freitag 14 Uhr bis Montag 10 Uhr — statt 267 €.",
            price="199.00",
            was="267.00",
            ends="14d",
            response="reserve",
            photo="sg-transporter",
            group="Saison",
        ),
    ),
)

BUSINESSES = (KOLBENRING, VENTIL, PROFIL, WUPPERSCHLEIFE, KLINGENMOBIL)
