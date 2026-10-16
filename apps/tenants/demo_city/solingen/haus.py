"""Раздел «Haus & Garten» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "haus-garten"

EICHENSTUECK = Biz(
    key="sg_eichenstueck",
    label="Möbelwerkstatt Eichenstück",
    btype="retail",
    category="moebel",
    district="graefrath",
    street="Klosterpfad",
    house="14",
    lat="51.2150",
    lng="7.0900",
    phone="+49 212 5551601",
    accent="#7c2d12",
    hero_photo="set-sofaabend-decke",
    tagline="Massivholzmöbel nach Maß — Tische, Regale, Sitzbänke aus bergischer Eiche.",
    about=(
        "Schreinerei mit Ausstellung in einer alten Scheune: Esstische auf Maß, Regale für "
        "schräge Wände, Sitzbänke mit Stauraum. Holz aus dem Bergischen, Öl statt Lack."
    ),
    hours="handwerk",
    usp=("handarbeit", "regional", "beratung"),
    shelves=(
        Shelf(
            "Möbel",
            "moebel",
            "moebel",
            (
                Item(
                    "Esstisch Eiche 200 × 90",
                    "1890.00",
                    "Massiv, geölt, Tischbeine nach Wahl.",
                    "set-schreibtisch-oben",
                ),
                Item(
                    "Sofadecke Wolle",
                    "129.00",
                    "Reine Schurwolle, 140 × 200 cm.",
                    "decken-kissen-sofa",
                ),
                Item(
                    "Kissen Grasnarbe Leinen",
                    "39.00",
                    "Leinenbezug, Federfüllung, 50 × 50.",
                    "kissen-grasnarbe-leinen",
                ),
                Item(
                    "Wandregal Eiche 120 cm",
                    "249.00",
                    "Unsichtbare Halterung, 25 cm tief.",
                    "sg-regal-eiche",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Aufmaß vor Ort",
            60,
            "0.00",
            "Wir messen aus und zeichnen — unverbindlich in Solingen.",
            "sg-aufmass",
        ),
    ),
    offers=(
        Offer(
            "Tisch nach Maß: Sitzbank −20 % dazu",
            "Bei Bestellung eines Esstisches bis Monatsende.",
            percent=20,
            ends="14d",
            response="inquire",
            photo="set-tafel-gedeckt",
            group="Saison",
            tags=("handgemacht", "regional"),
        ),
    ),
    anfrage=("date",),
)

GLUEHFADEN = Biz(
    key="sg_gluehfaden",
    label="Leuchtenhaus Glühfaden",
    btype="retail",
    category="beleuchtung",
    district="mitte",
    street="Lindenplatz",
    house="12",
    lat="51.1725",
    lng="7.0870",
    phone="+49 212 5551602",
    accent="#ca8a04",
    hero_photo="licht-duft-kerzen",
    tagline="Leuchten für Wohnung, Büro und Garten — mit Lichtplanung und Montage.",
    about=(
        "Leuchtengeschäft am Lindenplatz: Pendel-, Tisch- und Stehleuchten, Leuchtmittel "
        "für alte Fassungen, Lichtplanung für Umbau und Neubau. Montage durch eigenen Elektriker."
    ),
    hours="laden",
    usp=("beratung", "service", "qualitaet"),
    shelves=(
        Shelf(
            "Leuchten",
            "leuchten",
            "beleuchtung",
            (
                Item(
                    "Tischleuchte Knick Stahl",
                    "149.00",
                    "Schwenkbar, dimmbar, E27.",
                    "tischleuchte-knick-stahl",
                ),
                Item(
                    "Campinglampe Docht Laterne",
                    "59.00",
                    "Petroleum, für Terrasse und Balkon.",
                    "campinglampe-docht-laterne",
                ),
                Item(
                    "Pendelleuchte Glas 30 cm",
                    "189.00",
                    "Mundgeblasen, Textilkabel 2 m.",
                    "sg-pendelleuchte",
                ),
                Item(
                    "LED-Leuchtmittel E27 warmweiß, 3er",
                    "14.90",
                    "2700 K, dimmbar, 9 W.",
                    "sg-leuchtmittel",
                ),
                Item(
                    "Stehleuchte Leseleuchte",
                    "229.00",
                    "Mit Leseleuchte und Fußdimmer.",
                    "sg-stehleuchte",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Lichtplanung zu Hause",
            90,
            "89.00",
            "Wird beim Kauf ab 500 € verrechnet.",
            "sg-lichtplanung",
        ),
    ),
    offers=(
        Offer(
            "Leuchtmittel-Woche: 3er-Pack 9,90 €",
            "LED E27 warmweiß — statt 14,90 €.",
            price="9.90",
            was="14.90",
            ends="week",
            response="show",
            photo="candles",
            group="Diese Woche",
            item="LED-Leuchtmittel E27 warmweiß, 3er",
        ),
    ),
)

PFANNENWERK = Biz(
    key="sg_pfannenwerk",
    label="Küchenladen Pfannenwerk",
    btype="retail",
    category="kueche",
    district="ohligs-aufderhoehe-merscheid",
    street="Am Markt",
    house="11",
    lat="51.1690",
    lng="7.0120",
    phone="+49 212 5551603",
    accent="#374151",
    hero_photo="kueche-tafel-uebersicht",
    tagline="Pfannen, Messer und Geschirr — aus Solingen und von kleinen Manufakturen.",
    about=(
        "Küchenfachgeschäft am Ohligser Markt: Gusseisen, Emaille, Solinger Messer und "
        "Steinzeug aus der Eifel. Messer schleifen wir, Pfannen brennen wir für Sie ein."
    ),
    hours="laden",
    usp=("qualitaet", "beratung", "geschenk"),
    shelves=(
        Shelf(
            "Küche",
            "kueche",
            "kueche",
            (
                Item(
                    "Pfanne Feuer Gusseisen 28 cm",
                    "89.00",
                    "Eingebrannt, für Herd, Ofen und Grill.",
                    "pfanne-feuer-gusseisen",
                ),
                Item(
                    "Bräter Sonntag Emaille",
                    "129.00",
                    "6 l, für Braten und Brot.",
                    "braeter-sonntag-emaille",
                ),
                Item(
                    "Besteck Gerade Edelstahl, 24-tlg.",
                    "149.00",
                    "Matt gebürstet, spülmaschinenfest.",
                    "besteck-gerade-edelstahl",
                ),
                Item(
                    "Teekanne Bauch Steinzeug",
                    "49.00",
                    "1,2 l, mit Sieb.",
                    "teekanne-bauch-steinzeug",
                ),
                Item(
                    "Schneidebrett Eiche",
                    "59.00",
                    "Stirnholz, 40 × 30 cm, geölt.",
                    "brett-scheibe-eiche",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Messer schleifen", 15, "7.00", "Pro Messer, meist am selben Tag.", "messer-kante-koch"
        ),
    ),
    offers=(
        Offer(
            "Pfanne + Bräter 199 €",
            "Gusseisen und Emaille im Set — spart 19 €.",
            price="199.00",
            was="218.00",
            ends="14d",
            response="show",
            photo="kochen-braten-pfanne",
            group="Saison",
            item="Pfanne Feuer Gusseisen 28 cm",
        ),
    ),
)

GRUENSPROSS = Biz(
    key="sg_gruenspross",
    label="Gärtnerei Grünspross",
    btype="retail",
    category="garten-pflanzen",
    district="wald",
    street="Am Weiher",
    house="30",
    lat="51.1930",
    lng="7.0200",
    phone="+49 212 5551604",
    accent="#15803d",
    hero_photo="garden-terrace",
    tagline="Stauden, Kräuter und Gemüsejungpflanzen aus eigener Anzucht.",
    about=(
        "Gärtnerei mit Gewächshäusern in Wald: Stauden für den bergischen Boden, "
        "Kräuter ungespritzt, im Frühjahr Tomaten- und Paprikajungpflanzen. Beratung am Beet."
    ),
    hours="lebensmittel",
    usp=("regional", "bio", "beratung"),
    shelves=(
        Shelf(
            "Pflanzen",
            "pflanzen",
            "garten-pflanzen",
            (
                Item(
                    "Lavendel im 12-cm-Topf",
                    "4.90",
                    "Winterhart, für Sonne.",
                    "sg-lavendel-pflanze",
                    vat="7.00",
                ),
                Item(
                    "Kräuterset 6 Töpfe",
                    "14.90",
                    "Basilikum, Schnittlauch, Petersilie, Thymian, Minze, Rosmarin.",
                    "sg-kraeuter-pflanze",
                    vat="7.00",
                ),
                Item(
                    "Tomatenjungpflanze",
                    "2.90",
                    "Sorte nach Saison, veredelt.",
                    "sg-tomaten-pflanze",
                    vat="7.00",
                ),
                Item(
                    "Staude Sonnenhut",
                    "6.50",
                    "Echinacea, 1-l-Topf.",
                    "sg-staude-pflanze",
                    vat="7.00",
                ),
                Item(
                    "Blumenerde torffrei, 40 l",
                    "9.90",
                    "Für Beet und Kübel.",
                    "sg-blumenerde-sack",
                    unit="l",
                    content="40",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Staudenwochen: 5 kaufen, 1 geschenkt",
            "Alle Stauden im 1-l-Topf — bis Ende Oktober pflanzen.",
            ends="14d",
            response="show",
            photo="sg-staude-beet",
            group="Saison",
            tags=("regional",),
        ),
        Offer(
            "Heute: Kräutersets 9,90 €",
            "Sechs Töpfe Küchenkräuter — nur heute.",
            price="9.90",
            was="14.90",
            ends="today",
            response="show",
            photo="sg-kraeuter-pflanze",
            group="Heute",
            item="Kräuterset 6 Töpfe",
        ),
    ),
)

VERGISSMEINNICHT = Biz(
    key="sg_vergissmeinnicht",
    label="Blumen Vergissmeinnicht",
    btype="retail",
    category="garten-pflanzen",
    district="graefrath",
    street="Am Fachwerk",
    house="9",
    lat="51.2090",
    lng="7.0820",
    phone="+49 212 5551605",
    accent="#db2777",
    hero_photo="sg-blumenstrauss",
    tagline="Sträuße, Trauerfloristik und Pflanzen — täglich frisch vom Großmarkt.",
    about=(
        "Blumenladen am Gräfrather Markt seit 2011: Sträuße nach Wunsch, Hochzeits- und "
        "Trauerfloristik, Zimmerpflanzen. Lieferung in Solingen am selben Tag."
    ),
    hours="laden",
    usp=("lieferung", "hausgemacht", "geschenk"),
    profile="A",
    offers=(
        Offer(
            "Strauß der Woche 12 €",
            "Saisonblumen, gebunden am Morgen — jede Woche anders.",
            price="12.00",
            was="15.00",
            ends="week",
            response="reserve",
            photo="sg-blumenstrauss",
            group="Diese Woche",
            tags=("regional",),
        ),
        Offer(
            "Zimmerpflanzen −20 %",
            "Alle Grünpflanzen bis Sonntag.",
            percent=20,
            ends="week",
            response="show",
            photo="sg-zimmerpflanze",
            group="Diese Woche",
        ),
        Offer(
            "Tulpen 10 Stück 5 €",
            "Nur heute — solange der Vorrat reicht.",
            price="5.00",
            was="7.90",
            ends="today",
            response="show",
            photo="sg-tulpen",
            group="Heute",
        ),
        Offer(
            "Hochzeitsfloristik: Beratung kostenlos",
            "Brautstrauß, Tischschmuck, Auto — Termin im Laden.",
            ends="none",
            response="inquire",
            photo="sg-hochzeitsstrauss",
            group="Auf Bestellung",
        ),
        Offer(
            "Lieferung in Solingen 4,90 €",
            "Bestellung bis 12 Uhr — Zustellung am selben Tag.",
            price="4.90",
            ends="none",
            response="show",
            photo="sg-blumen-lieferung",
            group="Dauerhaft",
        ),
    ),
)

BUSINESSES = (EICHENSTUECK, GLUEHFADEN, PFANNENWERK, GRUENSPROSS, VERGISSMEINNICHT)
