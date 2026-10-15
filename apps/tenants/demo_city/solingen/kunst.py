"""Раздел «Kunst & Geschenke» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Ev, Item, Offer, Shelf

SECTION = "kunst-geschenke"

WEISSWAND = Biz(
    key="sg_weisswand",
    label="Galerie Weißwand",
    btype="retail",
    category="kunst",
    district="graefrath",
    street="Klosterpfad",
    house="14",
    lat="51.2050",
    lng="7.0780",
    phone="+49 212 5552501",
    accent="#111827",
    hero_photo="sg-galerie-raum",
    tagline="Druckgrafik und Fotografie aus dem Bergischen — Originale und Editionen ab 60 €.",
    about=(
        "Kleine Galerie in Gräfrath mit wechselnden Ausstellungen regionaler Künstlerinnen "
        "und Künstler. Editionen zum Mitnehmen, Rahmung auf Wunsch, Vernissage alle acht Wochen."
    ),
    hours="laden",
    usp=("beratung", "geschenk", "regional"),
    shelves=(
        Shelf(
            "Editionen",
            "editionen",
            "kunst",
            (
                Item(
                    "Linolschnitt Schleifkotten, Ed. 30",
                    "95.00",
                    "30 × 40 cm, signiert.",
                    "sg-linolschnitt",
                ),
                Item(
                    "Fotografie Wupper im Nebel",
                    "140.00",
                    "Fine-Art-Print 40 × 60 cm.",
                    "sg-fotografie-wupper",
                ),
                Item("Risograph Altstadt, A3", "60.00", "Zweifarbig, Auflage 50.", "sg-risograph"),
                Item("Radierung Klinge", "180.00", "Handabzug, 20 × 25 cm.", "sg-radierung"),
            ),
        ),
    ),
    events=(
        Ev(
            "Vernissage: Bergische Landschaften",
            10,
            19,
            "0.00",
            40,
            "Neue Arbeiten von drei Künstlerinnen, Begrüßung 19 Uhr.",
            "sg-galerie-raum",
        ),
    ),
    offers=(
        Offer(
            "Rahmung zum Druck −20 %",
            "Beim Kauf einer Edition die Rahmung günstiger.",
            percent=20,
            ends="14d",
            response="show",
            photo="sg-bilderrahmen",
            group="Saison",
            tags=("regional",),
        ),
    ),
)

SCHLEIFCHEN = Biz(
    key="sg_schleifchen",
    label="Geschenkeladen Schleifchen",
    btype="retail",
    category="geschenke",
    district="ohligs-aufderhoehe-merscheid",
    street="Am Markt",
    house="7",
    lat="51.1680",
    lng="7.0120",
    phone="+49 212 5552502",
    accent="#be123c",
    hero_photo="geschenkpapier-bogen-drei",
    tagline="Kleine Geschenke, Karten und Papier — eingepackt, bevor Sie an der Kasse sind.",
    about=(
        "Laden am Ohligser Markt: Kerzen, Karten, Tassen, Notizbücher, Seifen und Kleinigkeiten "
        "unter 20 €. Geschenkverpackung immer gratis, Geschenkgutscheine ab 10 €."
    ),
    hours="laden",
    usp=("geschenk", "zahlung", "beratung"),
    shelves=(
        Shelf(
            "Geschenke",
            "geschenke",
            "geschenke",
            (
                Item(
                    "Duftkerze Zeder & Salz", "16.90", "Sojawachs, 40 Stunden.", "kerze-zeder-salz"
                ),
                Item(
                    "Postkarten-Set, 8 Stück",
                    "9.90",
                    "Illustrationen aus dem Bergischen.",
                    "postkarten-kueste-set",
                ),
                Item(
                    "Geschenkpapier, 3 Bögen",
                    "4.50",
                    "Recyclingpapier, 50 × 70 cm.",
                    "geschenkpapier-bogen-drei",
                ),
                Item(
                    "Tasse Solingen", "12.90", "Steingut, spülmaschinenfest.", "sg-tasse-solingen"
                ),
                Item(
                    "Geschenkgutschein",
                    "10.00",
                    "Frei aufladbar, als Karte im Umschlag.",
                    "sg-gutschein-karte",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Kerzen-Wochen: 2 für 29 €",
            "Zwei Duftkerzen nach Wahl — statt 33,80 €.",
            price="29.00",
            was="33.80",
            ends="14d",
            response="show",
            photo="kerze-zeder-salz",
            group="Saison",
            item="Duftkerze Zeder & Salz",
        ),
    ),
)

DRECHSELSPAN = Biz(
    key="sg_drechselspan",
    label="Holzkunst Drechselspan",
    btype="retail",
    category="handgemachtes",
    district="burg-hoehscheid",
    street="Am Hang",
    house="6",
    lat="51.1550",
    lng="7.0850",
    phone="+49 212 5552503",
    accent="#92400e",
    hero_photo="loeffel-drei-olivenholz",
    tagline="Gedrechselte Schalen, Löffel und Brettchen aus bergischem Holz — jedes Stück einzeln.",
    about=(
        "Drechslerei mit Laden in Höhscheid: Esche, Kirsche und Nuss aus Windbruch der Region, "
        "geölt mit Leinöl. Kurse an der Drechselbank für zwei Personen."
    ),
    hours="laden",
    usp=("handarbeit", "regional", "nachhaltig"),
    shelves=(
        Shelf(
            "Holzkunst",
            "holzkunst",
            "handgemachtes",
            (
                Item(
                    "Kochlöffel-Set, 3 Stück",
                    "24.00",
                    "Olivenholz, geölt.",
                    "loeffel-drei-olivenholz",
                ),
                Item(
                    "Schale Kirsche Ø 24 cm",
                    "68.00",
                    "Gedrechselt, Leinöl-Finish.",
                    "sg-holzschale",
                ),
                Item(
                    "Frühstücksbrett Esche",
                    "19.00",
                    "22 × 14 cm, mit Saftrille.",
                    "holz-besteck-brett",
                ),
                Item(
                    "Bürsten-Set Buche",
                    "29.00",
                    "Spül- und Gemüsebürste, Naturborste.",
                    "buersten-zubehoer-holz",
                ),
            ),
        ),
    ),
    events=(
        Ev(
            "Drechselkurs: eine Schale in vier Stunden",
            14,
            10,
            "95.00",
            2,
            "Zu zweit an der Bank, Holz und Öl inklusive.",
            "sg-drechselbank",
            theme="klang",
            duration_hours=4,
        ),
    ),
    offers=(
        Offer(
            "Weihnachtsvorrat: Brett + Löffel 39 €",
            "Frühstücksbrett und Löffel-Set zusammen — statt 43 €.",
            price="39.00",
            was="43.00",
            ends="14d",
            response="show",
            photo="holz-besteck-brett",
            group="Saison",
            tags=("handgemacht",),
        ),
    ),
)

HEIMATGUT = Biz(
    key="sg_heimatgut",
    label="Bergischer Laden Heimatgut",
    btype="retail",
    category="lokale-produkte",
    district="wald",
    street="Heidestraße",
    house="22",
    lat="51.1790",
    lng="7.0620",
    phone="+49 212 5552504",
    accent="#166534",
    hero_photo="sg-regionalladen",
    tagline="Alles aus dem Bergischen: Senf, Likör, Keramik, Bücher — Geschenkkörbe nach Wunsch.",
    about=(
        "Regionalladen in Wald mit Produkten von 40 Herstellern aus dem Umkreis von 30 km. "
        "Geschenkkörbe ab 25 €, Firmenpräsente auf Bestellung, Versand deutschlandweit."
    ),
    hours="laden",
    usp=("regional", "geschenk", "versand"),
    shelves=(
        Shelf(
            "Bergische Produkte",
            "bergisches",
            "lokale-produkte",
            (
                Item(
                    "Bergischer Senf, 200 ml",
                    "4.90",
                    "Mittelscharf, aus Wermelskirchen.",
                    "sg-senfglas",
                    unit="100ml",
                    content="2",
                    vat="7.00",
                    origin="Bergisches Land",
                ),
                Item(
                    "Bergischer Kräuterlikör, 0,5 l",
                    "19.90",
                    "32 %, 21 Kräuter.",
                    "sg-likoerflasche",
                    unit="l",
                    content="0.5",
                ),
                Item(
                    "Taschenmesser Solingen",
                    "49.00",
                    "Klinge aus Solinger Stahl, Griff Nussbaum.",
                    "sg-taschenmesser",
                ),
                Item(
                    "Bildband Bergisches Land",
                    "29.90",
                    "160 Seiten, gebunden.",
                    "sg-bildband",
                    vat="7.00",
                ),
                Item(
                    "Geschenkkorb Bergisch, klein",
                    "25.00",
                    "Senf, Likör, Keks, Karte — fertig gepackt.",
                    "sg-geschenkkorb",
                    vat="7.00",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Geschenkkorb-Woche: Großer Korb 45 €",
            "Mit Messer-Miniatur und Bildband — statt 52 €.",
            price="45.00",
            was="52.00",
            ends="week",
            response="show",
            photo="sg-geschenkkorb",
            group="Diese Woche",
            tags=("regional",),
        ),
    ),
)

FEDERKIEL = Biz(
    key="sg_federkiel",
    label="Papeterie Federkiel",
    btype="retail",
    category="geschenke",
    district="mitte",
    street="Lindenplatz",
    house="3",
    lat="51.1750",
    lng="7.0810",
    phone="+49 212 5552505",
    accent="#1e3a8a",
    hero_photo="notizbuch-taschen-a6",
    tagline="Notizbücher, Füller und Papier — für Menschen, die noch mit der Hand schreiben.",
    about=(
        "Papeterie am Lindenplatz: Notizbücher kleiner Manufakturen, Füllhalter zum "
        "Probeschreiben, Tinte in 40 Farben, Karten und Kalender. Gravur auf Füller am selben Tag."
    ),
    hours="laden",
    usp=("beratung", "geschenk", "handarbeit"),
    shelves=(
        Shelf(
            "Papeterie",
            "papeterie",
            "geschenke",
            (
                Item(
                    "Notizbuch Taschenformat A6",
                    "8.90",
                    "Fadenheftung, blanko.",
                    "notizbuch-taschen-a6",
                ),
                Item(
                    "Bleistift-Set Werkbank",
                    "12.00",
                    "Sechs Härtegrade in der Holzbox.",
                    "bleistift-werkbank-set",
                ),
                Item(
                    "Skizzenbuch A4 grau",
                    "16.90",
                    "120 g Papier, 96 Seiten.",
                    "skizzenbuch-grau-a4",
                ),
                Item(
                    "Radierer & Spitzer",
                    "5.50",
                    "Naturkautschuk, Messingspitzer.",
                    "radierer-spitzer-paar",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Schreib-Set: Notizbuch + Bleistifte 18 €",
            "Zusammen statt 20,90 €.",
            price="18.00",
            was="20.90",
            ends="week",
            response="show",
            photo="bleistift-werkbank-set",
            group="Diese Woche",
            item="Notizbuch Taschenformat A6",
        ),
    ),
)

BUSINESSES = (WEISSWAND, SCHLEIFCHEN, DRECHSELSPAN, HEIMATGUT, FEDERKIEL)
