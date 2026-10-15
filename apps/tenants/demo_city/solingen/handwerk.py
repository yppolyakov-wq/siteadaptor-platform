"""Раздел «Handwerk & Reparatur» — демо-бизнесы Золингена (DCC).

Handwerker-киты продают через заявку (`anfrage` → модуль jobs); услуги с ценой «ab»
описывают типовые работы, точная цена — в смете.
"""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "handwerk-reparatur"

WASSERLAUF = Biz(
    key="sg_wasserlauf",
    label="Sanitärtechnik Wasserlauf",
    btype="handwerker",
    category="sanitaer",
    district="wald",
    street="Eichenallee",
    house="27",
    lat="51.1850",
    lng="7.0550",
    phone="+49 212 5552201",
    accent="#0369a1",
    hero_photo="plumber-man",
    tagline="Bad, Heizung, Notdienst — Meisterbetrieb aus Wald, Anfahrt in Solingen inklusive.",
    about=(
        "Sanitär- und Heizungsbetrieb mit sechs Monteuren. Badsanierung aus einer Hand, "
        "Wartung von Gasthermen, Notdienst bei Rohrbruch rund um die Uhr. Kostenvoranschlag "
        "nach Besichtigung, Festpreis für Standardarbeiten."
    ),
    hours="handwerk",
    usp=("meister", "garantie", "service"),
    services=(
        Svc(
            "Badsanierung (Beratung vor Ort)",
            60,
            "0.00",
            "Besichtigung, Aufmaß, Angebot — kostenlos in Solingen.",
            "bathroom-renovation",
        ),
        Svc(
            "Wartung Gastherme",
            60,
            "119.00",
            "Reinigung, Abgasmessung, Protokoll.",
            "heating-installation",
        ),
        Svc(
            "Armatur tauschen",
            60,
            "89.00",
            "Arbeitszeit für Waschtisch oder Spüle, Armatur nach Wahl.",
            "modern-bathroom",
        ),
    ),
    offers=(
        Offer(
            "Thermenwartung vor dem Winter 99 €",
            "Bis Ende des Monats — statt 119 €.",
            price="99.00",
            was="119.00",
            ends="14d",
            response="inquire",
            photo="heating-installation",
            group="Saison",
            tags=("vor-ort-service",),
        ),
    ),
    anfrage=("date",),
)

FARBENFROH = Biz(
    key="sg_farbenfroh",
    label="Malerbetrieb Farbenfroh",
    btype="handwerker",
    category="bau",
    district="ohligs-aufderhoehe-merscheid",
    street="Höhenblick",
    house="12",
    lat="51.1500",
    lng="7.0300",
    phone="+49 212 5552202",
    accent="#c2410c",
    hero_photo="painter-wall",
    tagline="Streichen, Tapezieren, Fassade — sauber abgeklebt, termingerecht fertig.",
    about=(
        "Malermeisterbetrieb in Aufderhöhe: Innenanstrich, Tapeten, Spachteltechnik, "
        "Fassadenanstrich mit Gerüst. Wir arbeiten mit emissionsarmen Farben und räumen "
        "jeden Abend auf."
    ),
    hours="handwerk",
    usp=("meister", "nachhaltig", "garantie"),
    services=(
        Svc(
            "Zimmer streichen (bis 20 m²)",
            240,
            "349.00",
            "Decke und Wände, zwei Anstriche, Farbe inklusive.",
            "painting-room",
        ),
        Svc(
            "Tapezieren (je m²)",
            30,
            "18.00",
            "Vliestapete, ohne Material.",
            "painted-wall",
        ),
        Svc(
            "Fassaden-Beratung vor Ort",
            60,
            "0.00",
            "Zustand prüfen, Angebot erstellen — kostenlos.",
            "shabby-wall",
        ),
    ),
    offers=(
        Offer(
            "Winterpreis: Innenanstrich −10 %",
            "Für alle Aufträge mit Ausführung bis Ende Februar.",
            percent=10,
            ends="14d",
            response="inquire",
            photo="painting-room",
            group="Saison",
        ),
    ),
    anfrage=("date",),
)

SCHRAUBGUT = Biz(
    key="sg_schraubgut",
    label="Montageservice Schraubgut",
    btype="handwerker",
    category="montage",
    district="mitte",
    street="Am Klingenhof",
    house="21",
    lat="51.1690",
    lng="7.0980",
    phone="+49 212 5552203",
    accent="#374151",
    hero_photo="handyman-tools",
    tagline="Möbel aufbauen, Lampen und Regale montieren, Küche anschließen — stundenweise.",
    about=(
        "Zwei Monteure, ein Transporter, alles Werkzeug an Bord. Wir bauen auf, was Sie "
        "gekauft haben, hängen auf, was hängen soll, und nehmen die Verpackung mit."
    ),
    hours="handwerk",
    usp=("schnell", "service", "zahlung"),
    services=(
        Svc(
            "Montagestunde",
            60,
            "49.00",
            "Pro Monteur, Anfahrt in Solingen inklusive.",
            "handyman-tools",
        ),
        Svc(
            "Kleiderschrank aufbauen",
            180,
            "139.00",
            "Bis 250 cm Breite, inklusive Wandbefestigung.",
            "craftsman-man",
        ),
        Svc(
            "Küche anschließen",
            240,
            "249.00",
            "Spüle, Geschirrspüler, Herd (ohne Elektroanschluss durch Fachbetrieb).",
            "craftsman-renovation",
        ),
    ),
    offers=(
        Offer(
            "Samstagsmontage ohne Aufschlag",
            "Diesen Monat samstags zum Wochentagspreis.",
            ends="14d",
            response="inquire",
            photo="handyman-tools",
            group="Saison",
            tags=("vor-ort-service",),
        ),
    ),
    anfrage=("date",),
)

ABSATZ = Biz(
    key="sg_absatz",
    label="Schuh- & Schlüsseldienst Absatz",
    btype="other",
    category="reparatur",
    district="burg-hoehscheid",
    street="Burgweg",
    house="18",
    lat="51.1580",
    lng="7.0900",
    phone="+49 212 5552204",
    accent="#78350f",
    hero_photo="sg-schuhreparatur",
    tagline="Absätze, Sohlen, Reißverschlüsse und Schlüssel — meist noch am selben Tag.",
    about=(
        "Werkstatt in Höhscheid seit 1979: Schuhreparatur aller Art, Lederpflege, "
        "Schlüssel nachmachen, Gravuren. Keine Türöffnung in der Nacht — dafür faire Preise am Tag."
    ),
    hours="laden",
    usp=("schnell", "reparatur", "zahlung"),
    services=(
        Svc(
            "Absätze erneuern (Paar)",
            20,
            "14.00",
            "Gummi oder Leder, während Sie warten.",
            "sg-schuhreparatur",
        ),
        Svc(
            "Sohle neu (Paar)", 60, "49.00", "Halbsohle Leder oder Gummi, ein Tag.", "sg-schuhsohle"
        ),
        Svc(
            "Reißverschluss Stiefel",
            60,
            "29.00",
            "Austausch inklusive Material.",
            "sg-reissverschluss",
        ),
        Svc(
            "Schlüssel nachmachen",
            10,
            "4.50",
            "Haus- und Briefkastenschlüssel sofort.",
            "sg-schluessel",
        ),
    ),
    offers=(
        Offer(
            "Winterstiefel fit: Sohle + Pflege 55 €",
            "Neue Halbsohle und Imprägnierung zusammen — statt 63 €.",
            price="55.00",
            was="63.00",
            ends="14d",
            response="show",
            photo="sg-schuhsohle",
            group="Saison",
        ),
    ),
)

ZEITWERK = Biz(
    key="sg_zeitwerk",
    label="Uhrmacher Zeitwerk",
    btype="retail",
    category="reparatur",
    district="mitte",
    street="Lindenplatz",
    house="11",
    lat="51.1730",
    lng="7.0830",
    phone="+49 212 5552205",
    accent="#1e293b",
    hero_photo="sg-uhrmacher-werkbank",
    tagline="Uhrenreparatur, Batteriewechsel und Revisionen — Werkstatt mit Blick auf den Platz.",
    about=(
        "Uhrmachermeisterin mit eigener Werkstatt: Batteriewechsel sofort, Armbänder, "
        "Revisionen mechanischer Uhren mit Garantie. Kleine Auswahl an Uhren und Bändern."
    ),
    hours="laden",
    usp=("meister", "garantie", "reparatur"),
    shelves=(
        Shelf(
            "Uhren & Bänder",
            "uhren",
            "schmuck",
            (
                Item(
                    "Armbanduhr Quarz, Lederband",
                    "129.00",
                    "Schlichtes Zifferblatt, 38 mm.",
                    "sg-armbanduhr",
                ),
                Item(
                    "Lederband 20 mm",
                    "24.00",
                    "Pflanzlich gegerbt, in drei Farben.",
                    "sg-uhrenband-leder",
                ),
                Item(
                    "Wecker mechanisch", "39.00", "Zum Aufziehen, lautes Glockenwerk.", "sg-wecker"
                ),
            ),
        ),
    ),
    services=(
        Svc("Batteriewechsel", 10, "9.00", "Inklusive Dichtungsprüfung.", "sg-armbanduhr"),
        Svc(
            "Revision mechanische Uhr",
            60,
            "189.00",
            "Zerlegen, Reinigen, Ölen, Regulieren — 2 Jahre Garantie.",
            "sg-uhrmacher-werkbank",
        ),
    ),
    offers=(
        Offer(
            "Batteriewechsel 7 €",
            "Diese Woche für alle Quarzuhren — statt 9 €.",
            price="7.00",
            was="9.00",
            ends="week",
            response="show",
            photo="sg-armbanduhr",
            group="Diese Woche",
        ),
    ),
)

BUSINESSES = (WASSERLAUF, FARBENFROH, SCHRAUBGUT, ABSATZ, ZEITWERK)
