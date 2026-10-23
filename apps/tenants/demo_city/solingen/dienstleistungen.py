"""Раздел «Dienstleistungen» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "dienstleistungen"

NETZKNOTEN = Biz(
    key="sg_netzknoten",
    label="IT-Service Netzknoten",
    btype="other",
    category="it",
    district="ohligs-aufderhoehe-merscheid",
    street="Bahnhofsgasse",
    house="33",
    lat="51.1665",
    lng="7.0030",
    phone="+49 221 4710135",
    accent="#1d4ed8",
    hero_photo="sg-it-service",
    tagline="Computerhilfe für Zuhause und kleine Büros — vor Ort, per Fernwartung, verständlich.",
    about=(
        "Zwei Techniker in Ohligs: WLAN einrichten, Daten retten, Drucker zum Laufen bringen, "
        "Backups für kleine Betriebe. Wir erklären, was wir tun, und schreiben es auf."
    ),
    hours="praxis",
    usp=("service", "schnell", "zahlung"),
    services=(
        Svc("Vor-Ort-Stunde", 60, "69.00", "Anfahrt in Solingen inklusive.", "sg-it-service"),
        Svc(
            "Fernwartung (30 Minuten)",
            30,
            "29.00",
            "Per Bildschirmfreigabe, sofort.",
            "sg-fernwartung",
        ),
        Svc(
            "Datenrettung Festplatte",
            120,
            "99.00",
            "Analyse und Kopie auf neuen Datenträger.",
            "sg-datenrettung",
        ),
    ),
    offers=(
        Offer(
            "WLAN-Check Zuhause 49 €",
            "Messung, Routerposition, Einstellungen — statt 69 €.",
            price="49.00",
            was="69.00",
            ends="14d",
            response="inquire",
            photo="sg-wlan-router",
            group="Saison",
            tags=("vor-ort-service",),
        ),
    ),
)

WAERMEWENDE = Biz(
    key="sg_waermewende",
    label="Energieberatung Wärmewende",
    btype="other",
    category="beratung",
    district="wald",
    street="Walder Höhe",
    house="8",
    lat="51.1880",
    lng="7.0400",
    phone="+49 221 4710136",
    accent="#15803d",
    hero_photo="sg-energieberatung",
    tagline="Unabhängige Energieberatung für Haus und Wohnung — gelistet für Förderprogramme.",
    about=(
        "Gebäudeenergieberaterin mit Sitz in Wald. Wir verkaufen keine Heizungen und keine "
        "Fenster — nur Beratung: Sanierungsfahrplan, Heizungscheck, Fördermittel."
    ),
    hours="praxis",
    usp=("beratung", "qualitaet", "termin"),
    services=(
        Svc(
            "Erstberatung (Telefon)",
            30,
            "0.00",
            "Was lohnt sich bei Ihnen? Kostenlos.",
            "sg-energieberatung",
        ),
        Svc(
            "Vor-Ort-Check Einfamilienhaus",
            120,
            "249.00",
            "Rundgang, Thermografie, Kurzbericht.",
            "sg-thermografie",
        ),
        Svc(
            "Sanierungsfahrplan",
            480,
            "1290.00",
            "Förderfähig — Zuschuss möglich.",
            "sg-sanierungsplan",
        ),
    ),
    offers=(
        Offer(
            "Heizungscheck vor der Saison 149 €",
            "Hydraulik, Einstellungen, Empfehlungen — nur im Herbst.",
            price="149.00",
            was="189.00",
            ends="14d",
            response="inquire",
            photo="sg-energieberatung",
            group="Saison",
        ),
    ),
)

BLUETENWEISS = Biz(
    key="sg_bluetenweiss",
    label="Textilreinigung Blütenweiß",
    btype="other",
    category="reinigung",
    district="mitte",
    street="Scherenweg",
    house="16",
    lat="51.1675",
    lng="7.0900",
    phone="+49 221 4710137",
    accent="#0e7490",
    hero_photo="sg-textilreinigung",
    tagline="Hemden, Anzüge, Daunen und Gardinen — gereinigt in eigener Werkstatt, nicht verschickt.",
    about=(
        "Reinigung in der Innenstadt mit eigener Maschine im Haus: Express bis 17 Uhr, "
        "Hemdenservice, Lederpflege, Teppichwäsche. Lösemittel im geschlossenen Kreislauf seit 2015."
    ),
    hours="laden",
    usp=("schnell", "nachhaltig", "zahlung"),
    services=(
        Svc("Hemd waschen & bügeln", 10, "3.90", "Auf Bügel oder gefaltet.", "sg-hemd-buegeln"),
        Svc("Anzug (2-teilig)", 15, "16.90", "Reinigung und Finish.", "sg-anzug-reinigung"),
        Svc(
            "Daunenjacke",
            15,
            "24.90",
            "Schonend gewaschen, getrocknet, aufgeschüttelt.",
            "sg-daunenjacke",
        ),
        Svc("Gardinen (je kg)", 15, "9.90", "Abnehmen und Aufhängen auf Wunsch.", "sg-gardinen"),
    ),
    offers=(
        Offer(
            "5 Hemden 17,50 €",
            "Statt 19,50 € — jede Woche.",
            price="17.50",
            was="19.50",
            ends="week",
            response="show",
            photo="sg-hemd-buegeln",
            group="Diese Woche",
        ),
        Offer(
            "Winterjacken-Wochen −15 %",
            "Daunen und Wolle bis Ende des Monats.",
            percent=15,
            ends="14d",
            response="show",
            photo="sg-daunenjacke",
            group="Saison",
        ),
    ),
)

PAPIERFLIEGER = Biz(
    key="sg_papierflieger",
    label="Copyshop Papierflieger",
    btype="retail",
    category="bueroservice",
    district="graefrath",
    street="Am Fachwerk",
    house="3",
    lat="51.2080",
    lng="7.0750",
    phone="+49 221 4710138",
    accent="#4338ca",
    hero_photo="papeterie-buero-uebersicht",
    tagline="Drucken, Kopieren, Binden, Plakate — und Büromaterial für den Notfall.",
    about=(
        "Copyshop neben der Grundschule in Gräfrath: Druck von Datei oder Stick, "
        "Abschlussarbeiten gebunden am selben Tag, Plakate bis A0, Visitenkarten. Dazu Papier, "
        "Stifte, Hefte."
    ),
    hours="laden",
    usp=("schnell", "zahlung", "service"),
    shelves=(
        Shelf(
            "Büromaterial",
            "bueromaterial",
            "bueroservice",
            (
                Item(
                    "Notizbuch Leinen A5",
                    "12.90",
                    "Punktraster, 192 Seiten.",
                    "notizbuch-leinen-a5",
                ),
                Item("Kopierpapier 500 Blatt", "6.90", "80 g/m², Recycling.", "sg-kopierpapier"),
                Item(
                    "Fineliner-Set, 6 Stück", "9.90", "0,4 mm, sechs Farben.", "fineliner-linie-set"
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Druck A4 s/w (100 Seiten)",
            15,
            "7.00",
            "Von Datei oder Stick, einseitig.",
            "sg-kopierer",
        ),
        Svc("Abschlussarbeit binden", 30, "14.90", "Hardcover, Prägung auf Wunsch.", "sg-binden"),
    ),
    offers=(
        Offer(
            "Plakat A1 nur 9 €",
            "Farbdruck auf 135 g — diese Woche statt 12 €.",
            price="9.00",
            was="12.00",
            ends="week",
            response="show",
            photo="sg-plakat-druck",
            group="Diese Woche",
        ),
    ),
)

NADELOEHR = Biz(
    key="sg_nadeloehr",
    label="Änderungsschneiderei Nadelöhr",
    btype="other",
    category="weitere-dienstleistungen",
    district="burg-hoehscheid",
    street="Mühlensteig",
    house="2",
    lat="51.1600",
    lng="7.0700",
    phone="+49 221 4710139",
    accent="#9d174d",
    hero_photo="sg-naehmaschine",
    tagline="Kürzen, Enger machen, Reißverschlüsse — Änderungen in zwei Tagen, Expresservice möglich.",
    about=(
        "Schneiderin mit Werkstatt in Höhscheid: Hosen und Röcke kürzen, Sakkos anpassen, "
        "Brautkleider ändern, Lieblingsstücke flicken. Termin nicht nötig — kommen Sie vorbei."
    ),
    hours="laden",
    usp=("schnell", "handarbeit", "zahlung"),
    services=(
        Svc("Hose kürzen", 20, "12.00", "Mit Originalsaum +4 €.", "sg-hose-kuerzen"),
        Svc("Sakko enger machen", 45, "39.00", "Seitennähte und Rücken.", "sg-sakko-anpassen"),
        Svc(
            "Reißverschluss Jacke",
            30,
            "24.00",
            "Inklusive Standard-Reißverschluss.",
            "sg-reissverschluss-jacke",
        ),
        Svc(
            "Kleid ändern", 60, "49.00", "Taille, Länge, Träger — nach Anprobe.", "sg-kleid-aendern"
        ),
    ),
    offers=(
        Offer(
            "2 Hosen kürzen 20 €",
            "Zwei Hosen zusammen abgeben — statt 24 €.",
            price="20.00",
            was="24.00",
            ends="week",
            response="show",
            photo="sg-hose-kuerzen",
            group="Diese Woche",
        ),
    ),
)

BUSINESSES = (NETZKNOTEN, WAERMEWENDE, BLUETENWEISS, PAPIERFLIEGER, NADELOEHR)
