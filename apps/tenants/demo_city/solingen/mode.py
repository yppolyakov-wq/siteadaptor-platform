"""Раздел «Mode & Accessoires» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "mode-accessoires"

NADELSTREIF = Biz(
    key="sg_nadelstreif",
    label="Herrenausstatter Nadelstreif",
    btype="clothing",
    category="herrenmode",
    district="mitte",
    street="Lindenplatz",
    house="3",
    lat="51.1710",
    lng="7.0850",
    phone="+49 212 5551301",
    accent="#1f2937",
    hero_photo="mode-oxfordhemd-kontor",
    tagline="Hemden, Hosen und Strick für Herren — mit Änderungsschneiderei im Haus.",
    about=(
        "Herrenmode am Lindenplatz seit 1987: Hemden in Slim und Regular, Chinos, Strick aus "
        "Merino. Säumen und Enger-Nähen machen wir im Haus, meist bis zum nächsten Tag."
    ),
    hours="laden",
    usp=("beratung", "qualitaet", "service"),
    shelves=(
        Shelf(
            "Herren",
            "herren",
            "herrenmode",
            (
                Item(
                    "Oxfordhemd Kontor",
                    "69.00",
                    "Baumwolle, Button-down, blau oder weiß.",
                    "mode-oxfordhemd-kontor",
                ),
                Item(
                    "Chino Deich",
                    "79.00",
                    "Schmal geschnitten, Stretch-Baumwolle.",
                    "mode-chino-deich",
                ),
                Item(
                    "Merinopullover Herren",
                    "99.00",
                    "Feinstrick, Rundhals, extrafeine Merinowolle.",
                    "mode-merinopullover-herren",
                ),
                Item(
                    "Flanellhemd Werft",
                    "74.00",
                    "Gebürstete Baumwolle, kariert.",
                    "mode-flanellhemd-werft",
                ),
                Item(
                    "Ledergürtel Werft",
                    "49.00",
                    "Vollrindleder, 3,5 cm, gefertigt in Deutschland.",
                    "mode-lederguertel-werft",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Hose kürzen", 15, "12.00", "Saum nach Maß — fertig am nächsten Tag.", "sg-naehmaschine"
        ),
    ),
    offers=(
        Offer(
            "Zwei Hemden 119 €",
            "Alle Oxford- und Flanellhemden — zwei zum Paketpreis.",
            price="119.00",
            was="138.00",
            ends="week",
            response="show",
            photo="mode-oxfordhemd-kontor-blau",
            group="Diese Woche",
            item="Oxfordhemd Kontor",
        ),
    ),
)

PUENKTCHEN = Biz(
    key="sg_puenktchen",
    label="Pünktchen Kindermode",
    btype="clothing",
    category="kindermode",
    district="graefrath",
    street="Tuchmacherweg",
    house="11",
    lat="51.2120",
    lng="7.0700",
    phone="+49 212 5551302",
    accent="#f59e0b",
    hero_photo="mode-kat-kinder",
    tagline="Kindermode von 50 bis 164 — robust, bunt und zum Mitwachsen.",
    about=(
        "Kleiner Laden in Gräfrath für Babys und Kinder: Bio-Baumwolle, Regenjacken, die "
        "etwas aushalten, und eine Second-Hand-Ecke für Getragenes in gutem Zustand."
    ),
    hours="laden",
    usp=("kinder", "nachhaltig", "beratung"),
    shelves=(
        Shelf(
            "Kinder",
            "kinder",
            "kindermode",
            (
                Item(
                    "Kinderregenjacke Pfütze",
                    "44.90",
                    "Wasserdicht, verschweißte Nähte, Gr. 92–140.",
                    "mode-kinderregenjacke-pfuetze",
                ),
                Item(
                    "Kinderpullover Nordstern",
                    "34.90",
                    "Bio-Baumwolle, Gr. 98–152.",
                    "mode-kinderpullover-nordstern",
                ),
                Item(
                    "Latzhose Krabbe",
                    "39.90",
                    "Cord, verstellbare Träger, Gr. 80–116.",
                    "mode-latzhose-krabbe",
                ),
                Item(
                    "Kindermütze Sternchen",
                    "14.90",
                    "Gefüttert, mit Ohrenklappen.",
                    "mode-kindermuetze-sternchen",
                ),
                Item(
                    "Mädchenkleid Sommerwiese",
                    "29.90",
                    "Jersey, Gr. 98–140.",
                    "mode-maedchenkleid-sommerwiese",
                ),
            ),
        ),
        Shelf(
            "Baby",
            "baby",
            "kindermode",
            (
                Item(
                    "Babybody Muschel, 3er-Pack",
                    "19.90",
                    "Bio-Baumwolle, Gr. 50–86.",
                    "mode-babybody-muschel",
                ),
                Item(
                    "Babystrickjacke Wolke",
                    "29.90",
                    "Merino-Baumwolle, Gr. 56–86.",
                    "mode-babystrickjacke-wolke",
                ),
                Item(
                    "Strampler Seestern",
                    "24.90",
                    "Mit Druckknöpfen, Gr. 50–80.",
                    "mode-strampler-seestern",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Regenjacken −20 % zum Herbst",
            "Alle Kinderregenjacken bis Ende des Monats.",
            percent=20,
            ends="14d",
            response="show",
            photo="mode-kinderregenjacke-pfuetze-tuerkis",
            group="Saison",
            item="Kinderregenjacke Pfütze",
            tags=("nachhaltig",),
        ),
    ),
)

FUNKENFLUG = Biz(
    key="sg_funkenflug",
    label="Goldschmiede Funkenflug",
    btype="retail",
    category="schmuck",
    district="wald",
    street="Walder Höhe",
    house="22",
    lat="51.1900",
    lng="7.0250",
    phone="+49 212 5551303",
    accent="#a16207",
    hero_photo="ring-firn",
    tagline="Schmuck aus der eigenen Werkstatt — Trauringe, Umarbeitungen, Reparaturen.",
    about=(
        "Werkstatt und Laden in einem: Silber und Gold aus recyceltem Material, Steine mit "
        "Herkunftsnachweis. Trauringe entwerfen wir gemeinsam, Altgold arbeiten wir um."
    ),
    hours="laden",
    usp=("handarbeit", "nachhaltig", "beratung"),
    shelves=(
        Shelf(
            "Schmuck",
            "schmuck",
            "schmuck",
            (
                Item("Ring Firn", "189.00", "925er Silber, matt, handgeschmiedet.", "ring-firn"),
                Item("Kette Kiesel", "149.00", "Silber mit Flussstein-Anhänger.", "kette-kiesel"),
                Item("Armband Ufer", "119.00", "Gliederarmband, Silber, 19 cm.", "armband-ufer"),
                Item("Armreif Moos", "229.00", "Silber, grün patiniert.", "armreif-moos"),
                Item("Ohrhänger Farn", "99.00", "Silber, vergoldet.", "ohrhaenger-farn"),
            ),
        ),
    ),
    services=(
        Svc(
            "Beratung Trauringe",
            60,
            "0.00",
            "Entwurf, Materialwahl, Anprobe — unverbindlich.",
            "sg-trauringe",
        ),
        Svc(
            "Ringgröße ändern",
            30,
            "35.00",
            "Silber und Gold, meist am selben Tag.",
            "sg-ringgroesse",
        ),
    ),
    offers=(
        Offer(
            "Altgold-Wochen: Umarbeitung −20 %",
            "Aus Omas Kette wird Ihr Ring — Werkstattpreis im Oktober.",
            percent=20,
            ends="14d",
            response="inquire",
            photo="armband-gischt",
            group="Saison",
            tags=("handgemacht", "nachhaltig"),
        ),
    ),
)

RIEMENWERK = Biz(
    key="sg_riemenwerk",
    label="Lederwerkstatt Riemenwerk",
    btype="retail",
    category="taschen",
    district="burg-hoehscheid",
    street="Schlossblick",
    house="2",
    lat="51.1420",
    lng="7.1550",
    phone="+49 212 5551304",
    accent="#78350f",
    hero_photo="bags-collection",
    tagline="Taschen, Gürtel und Etuis aus pflanzlich gegerbtem Leder — genäht in Burg.",
    about=(
        "Kleine Manufaktur in Unterburg: jede Tasche wird hier zugeschnitten und von Hand "
        "gesattelt. Reparaturen auch für fremde Stücke — Reißverschluss, Naht, Schnalle."
    ),
    hours="laden",
    usp=("handarbeit", "garantie", "reparatur"),
    shelves=(
        Shelf(
            "Leder",
            "leder",
            "taschen",
            (
                Item(
                    "Canvas-Tasche mit Lederboden",
                    "149.00",
                    "Wachsleinen, Leder, Messing.",
                    "canvas-bag",
                ),
                Item(
                    "Rucksack Office", "219.00", "Für 15-Zoll-Laptop, Vollleder.", "backpack-office"
                ),
                Item(
                    "Ledergürtel Tau", "69.00", "4 cm, Messingschnalle, auf Länge.", "guertel-tau"
                ),
                Item(
                    "Schlüsseletui", "39.00", "Für sechs Schlüssel, zwei Farben.", "keycase-leather"
                ),
                Item(
                    "Shopper Leder", "189.00", "Großes Fach, Innentasche, Magnet.", "tote-leather"
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Reparatur Tasche",
            30,
            "25.00",
            "Naht, Reißverschluss, Schnalle — Kostenvoranschlag im Laden.",
            "sg-lederreparatur",
        ),
    ),
    offers=(
        Offer(
            "Gürtel nach Maß 59 €",
            "Länge und Schnalle nach Wunsch — fertig in drei Tagen.",
            price="59.00",
            was="69.00",
            ends="none",
            response="inquire",
            photo="leather-belt",
            group="Dauerhaft",
            tags=("handgemacht",),
        ),
    ),
)

KLEIDERKREISEL = Biz(
    key="sg_kleiderkreisel",
    label="Second-Hand Kleiderkreisel",
    btype="clothing",
    category="damenmode",
    district="ohligs-aufderhoehe-merscheid",
    street="Am Markt",
    house="5",
    lat="51.1680",
    lng="7.0100",
    phone="+49 212 5551305",
    accent="#be185d",
    hero_photo="fashion",
    tagline="Gebrauchte Damenmode in gutem Zustand — gesichtet, gewaschen, gebügelt.",
    about=(
        "Second-Hand-Boutique am Ohligser Markt: wir nehmen auf Kommission, was wir selbst "
        "tragen würden. Alles hängt sortiert nach Größe, Umkleide mit Tageslicht."
    ),
    hours="laden",
    usp=("nachhaltig", "beratung", "zahlung"),
    shelves=(
        Shelf(
            "Damen Second-Hand",
            "damen-secondhand",
            "damenmode",
            (
                Item(
                    "Wollmantel, Gr. 38",
                    "59.00",
                    "Kamelhaarfarben, kaum getragen.",
                    "mode-wollmantel-winterhafen",
                ),
                Item(
                    "Seidenbluse, Gr. 36",
                    "29.00",
                    "Bordeaux, gereinigt.",
                    "mode-seidenbluse-aurora",
                ),
                Item(
                    "Jeans Elbe, Gr. 40",
                    "19.00",
                    "Anthrazit, gerade geschnitten.",
                    "mode-jeans-elbe-anthrazit",
                ),
                Item(
                    "Strickkleid, Gr. 38",
                    "34.00",
                    "Creme, Wollmix, neuwertig.",
                    "mode-strickkleid-winterlicht",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Kommission: 50 % für Sie",
            "Bringen Sie gereinigte Kleidung — die Hälfte des Verkaufspreises gehört Ihnen.",
            ends="none",
            response="inquire",
            photo="hosen-kleider-buegel",
            group="Dauerhaft",
            tags=("gebraucht", "nachhaltig"),
        ),
        Offer(
            "Mäntel-Woche: alle Mäntel −30 %",
            "Winter kommt — Mäntel und Jacken diese Woche günstiger.",
            percent=30,
            ends="week",
            response="show",
            photo="jacken-westen-garderobe",
            group="Diese Woche",
            item="Wollmantel, Gr. 38",
        ),
    ),
)

BUSINESSES = (NADELSTREIF, PUENKTCHEN, FUNKENFLUG, RIEMENWERK, KLEIDERKREISEL)
