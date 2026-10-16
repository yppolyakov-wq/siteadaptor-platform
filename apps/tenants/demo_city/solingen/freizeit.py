"""Раздел «Freizeit & Erlebnisse» — демо-бизнесы Золингена (DCC).

События — на ближайшие недели (`in_days` 1..90), темы только из BY_EVENT_THEME
(natur → outdoor); без темы событие уходит в категорию `events`.
"""

from ..spec import Biz, Ev, Item, Offer, Shelf, Svc

SECTION = "freizeit-erlebnisse"

LICHTSPIEL = Biz(
    key="sg_lichtspiel",
    label="Programmkino Lichtspiel",
    btype="events",
    category="kino",
    district="wald",
    street="Walder Höhe",
    house="21",
    lat="51.1830",
    lng="7.0450",
    phone="+49 212 5551901",
    accent="#7f1d1d",
    hero_photo="sg-kino-saal",
    tagline="Ein Saal, 80 Plätze, Filme abseits des Multiplex — mit Bier vom Fass im Foyer.",
    about=(
        "Programmkino in Wald seit 1987: europäisches Kino, Dokumentarfilme, Klassiker am "
        "Sonntag und Kinderkino am Nachmittag. Karten online oder an der Kasse, Saal "
        "barrierefrei, Hörschleife vorhanden."
    ),
    hours="kultur",
    usp=("barrierefrei", "zahlung", "fahrrad"),
    events=(
        Ev(
            "Filmabend: Neuer französischer Film (OmU)",
            3,
            20,
            "9.50",
            80,
            "Original mit Untertiteln, anschließend Gespräch im Foyer.",
            "sg-kino-saal",
        ),
        Ev(
            "Kinderkino: Abenteuer im Wald (ab 6)",
            6,
            15,
            "5.00",
            80,
            "Sonntagnachmittag für Familien — Popcorn klein inklusive.",
            "sg-kino-kinder",
            weekday=6,
        ),
        Ev(
            "Klassiker am Sonntag: Stummfilm mit Live-Piano",
            13,
            19,
            "12.00",
            80,
            "Begleitet am Flügel — ein Abend wie 1925.",
            "sg-kino-piano",
            weekday=6,
        ),
        Ev(
            "Dokumentarfilm & Regiegespräch",
            27,
            19,
            "11.00",
            80,
            "Die Regisseurin ist zu Gast und beantwortet Fragen.",
            "sg-kino-gespraech",
        ),
    ),
    offers=(
        Offer(
            "Kino-Dienstag: alle Karten 7 €",
            "Jeden Dienstag alle Vorstellungen zum Einheitspreis.",
            price="7.00",
            was="9.50",
            ends="week",
            response="show",
            photo="sg-kino-saal",
            group="Diese Woche",
            tags=("barrierefrei",),
        ),
        Offer(
            "5er-Karte 40 €",
            "Fünf Vorstellungen nach Wahl, übertragbar, ein Jahr gültig.",
            price="40.00",
            ends="none",
            response="show",
            photo="sg-kino-karten",
            group="Dauerhaft",
        ),
    ),
)

STEILWAND = Biz(
    key="sg_steilwand",
    label="Kletterhalle Steilwand",
    btype="other",
    category="sport",
    district="burg-hoehscheid",
    street="Mühlensteig",
    house="10",
    lat="51.1500",
    lng="7.1050",
    phone="+49 212 5551902",
    accent="#b45309",
    hero_photo="sg-kletterhalle",
    tagline="Bouldern und Seilklettern bis 14 Meter — Einsteigerkurse jedes Wochenende.",
    about=(
        "Halle in einer alten Schleiferei: 900 m² Kletterfläche, Boulderbereich, Kinderwand, "
        "Café mit Blick auf die Wand. Leihausrüstung vor Ort, Kurse mit lizenzierten Trainerinnen und Trainern."
    ),
    hours="freizeit",
    usp=("kinder", "parken", "zahlung"),
    services=(
        Svc(
            "Tageskarte Erwachsene",
            240,
            "14.00",
            "Bouldern und Seilklettern, ganzer Tag.",
            "sg-kletterhalle",
        ),
        Svc("Tageskarte Kinder (bis 14)", 240, "9.00", "Mit Zugang zur Kinderwand.", ""),
        Svc(
            "Schnupperkurs Klettern",
            120,
            "35.00",
            "Zwei Stunden mit Trainer, Ausrüstung inklusive.",
            "sg-kletterkurs",
        ),
    ),
    events=(
        Ev(
            "Boulder-Wettkampf für alle",
            16,
            11,
            "12.00",
            60,
            "Routen für Anfänger bis Fortgeschrittene, Siegerehrung um 17 Uhr.",
            "sg-boulder",
            theme="natur",
            duration_hours=6,
        ),
    ),
    offers=(
        Offer(
            "Familien-Sonntag: 2 Erwachsene + 2 Kinder 36 €",
            "Sonntags bis 14 Uhr — statt 46 €.",
            price="36.00",
            was="46.00",
            ends="week",
            response="show",
            photo="sg-kletterhalle",
            group="Diese Woche",
            tags=("familienfreundlich",),
        ),
    ),
)

DREHSCHEIBE = Biz(
    key="sg_drehscheibe",
    label="Töpferwerkstatt Drehscheibe",
    btype="events",
    category="workshops",
    district="graefrath",
    street="Zinnstraße",
    house="6",
    lat="51.2010",
    lng="7.0850",
    phone="+49 212 5551903",
    accent="#9a3412",
    hero_photo="sg-toepferscheibe",
    tagline="Kurse an der Töpferscheibe und Keramik aus eigener Werkstatt — in Gräfrath.",
    about=(
        "Werkstatt mit sechs Scheiben und Brennofen im Hinterhof. Kurse für Anfänger, "
        "offene Werkstatt am Freitag, dazu ein kleines Regal mit Becher und Schalen."
    ),
    hours="studio",
    usp=("handarbeit", "kinder", "geschenk"),
    shelves=(
        Shelf(
            "Keramik aus der Werkstatt",
            "keramik",
            "handgemachtes",
            (
                Item(
                    "Becher gedreht, Steinzeug",
                    "22.00",
                    "Jeder ein Unikat, spülmaschinenfest.",
                    "sg-toepfer-becher",
                ),
                Item("Schale Mulde", "28.00", "Ø 18 cm, matte Glasur.", "sg-toepfer-schale"),
                Item("Vase Krug", "39.00", "Handgedreht, 24 cm hoch.", "sg-toepfer-vase"),
            ),
        ),
    ),
    events=(
        Ev(
            "Anfängerkurs Drehscheibe (4 Abende)",
            8,
            17,
            "149.00",
            6,
            "Vier Dienstagabende, Ton und Brand inklusive.",
            "sg-toepferscheibe",
            theme="klang",
            duration_hours=3,
            weekday=1,
        ),
        Ev(
            "Töpfern für Kinder (ab 7)",
            12,
            15,
            "25.00",
            8,
            "Zwei Stunden Aufbaukeramik — Werke werden gebrannt und abgeholt.",
            "sg-toepfer-kinder",
            theme="klang",
        ),
        Ev(
            "Offene Werkstatt am Freitag",
            5,
            17,
            "18.00",
            6,
            "Scheibe und Material für drei Stunden, Hilfe bei Bedarf.",
            "sg-toepfer-werkstatt",
            theme="klang",
            duration_hours=3,
            weekday=4,
        ),
    ),
    offers=(
        Offer(
            "Gutschein Anfängerkurs 139 €",
            "Zum Verschenken — Termin frei wählbar, ein Jahr gültig.",
            price="139.00",
            ends="none",
            response="show",
            photo="sg-toepfer-becher",
            group="Dauerhaft",
        ),
    ),
)

WUPPERPFAD = Biz(
    key="sg_wupperpfad",
    label="Outdoor-Schule Wupperpfad",
    btype="events",
    category="outdoor",
    district="burg-hoehscheid",
    street="Wupperufer",
    house="80",
    lat="51.1400",
    lng="7.1500",
    phone="+49 212 5551904",
    accent="#166534",
    hero_photo="forest-path",
    tagline="Wandern, Feuer machen, Orientierung — Kurse im Wald an der Wupper.",
    about=(
        "Zwei Wildnispädagogen, ein Stück Pachtwald bei Burg. Tagesworkshops für Erwachsene, "
        "Familientage und Schulklassen. Wir gehen bei jedem Wetter, außer bei Sturm."
    ),
    hours="freizeit",
    usp=("kinder", "hunde", "nachhaltig"),
    events=(
        Ev(
            "Feuer & Messer: Grundkurs Draußen",
            9,
            10,
            "59.00",
            10,
            "Feuer ohne Streichholz, Schnitzen, sicher mit dem Messer — Mittagessen am Feuer.",
            "campfire-night",
            theme="natur",
            duration_hours=6,
        ),
        Ev(
            "Familien-Wandertag Wupper",
            15,
            10,
            "15.00",
            16,
            "12 km mit Pausen, Spiele unterwegs — Kinder ab 6 Jahren.",
            "forest-path",
            theme="natur",
            duration_hours=5,
        ),
        Ev(
            "Nachtwanderung mit Laterne",
            22,
            19,
            "12.00",
            16,
            "Zwei Stunden durch den dunklen Wald, Tee am Ende.",
            "lantern-night",
            theme="natur",
        ),
    ),
    offers=(
        Offer(
            "Frühbucher Feuer & Messer 49 €",
            "Bei Anmeldung bis Sonntag — statt 59 €.",
            price="49.00",
            was="59.00",
            ends="week",
            response="show",
            photo="campfire-night",
            group="Diese Woche",
            tags=("familienfreundlich",),
        ),
    ),
)

FUNKENSCHLAG = Biz(
    key="sg_funkenschlag",
    label="Kulturkeller Funkenschlag",
    btype="events",
    category="events",
    district="mitte",
    street="Scherenweg",
    house="3",
    lat="51.1700",
    lng="7.0850",
    phone="+49 212 5551905",
    accent="#581c87",
    hero_photo="sg-buehne-keller",
    tagline="Kleinkunst, Konzerte und Lesungen im Gewölbekeller — 90 Plätze, keine Säule.",
    about=(
        "Gewölbekeller unter einem Fabrikantenhaus: Kabarett am Freitag, Konzerte am "
        "Samstag, Lesungen unter der Woche. Getränke zu fairen Preisen, Einlass eine Stunde "
        "vor Beginn."
    ),
    hours="kultur",
    usp=("zahlung", "fahrrad", "barrierefrei"),
    events=(
        Ev(
            "Kabarett: Bergisch für Fortgeschrittene",
            4,
            20,
            "18.00",
            90,
            "Ein Abend über Regen, Nachbarn und Schleifer — ausverkauft im Frühjahr.",
            "sg-buehne-keller",
        ),
        Ev(
            "Konzert: Jazz-Trio Wupperklang",
            11,
            20,
            "15.00",
            90,
            "Standards und Eigenes, zwei Sets.",
            "sg-konzert-jazz",
        ),
        Ev(
            "Lesung: Krimi aus der Klingenstadt",
            18,
            19,
            "10.00",
            90,
            "Die Autorin liest aus ihrem neuen Roman, danach Signierstunde.",
            "sg-lesung",
        ),
        Ev(
            "Offene Bühne",
            25,
            20,
            "5.00",
            90,
            "Zehn Minuten für alle, die sich trauen — Anmeldung am Abend.",
            "sg-buehne-mikro",
        ),
    ),
    offers=(
        Offer(
            "Kulturabo: 4 Abende 50 €",
            "Vier Veranstaltungen nach Wahl in dieser Saison.",
            price="50.00",
            ends="none",
            response="show",
            photo="sg-buehne-keller",
            group="Dauerhaft",
        ),
    ),
)

ABENTEUERWIESE = Biz(
    key="sg_abenteuerwiese",
    label="Familienhof Abenteuerwiese",
    btype="events",
    category="familienausfluege",
    district="ohligs-aufderhoehe-merscheid",
    street="Höhenblick",
    house="40",
    lat="51.1400",
    lng="6.9950",
    phone="+49 212 5551906",
    accent="#ca8a04",
    hero_photo="bbq-family",
    tagline="Ponys, Traktor, Hofcafé — Familiennachmittage und Kindergeburtstage auf dem Hof.",
    about=(
        "Bauernhof am Stadtrand von Ohligs: Streichelgehege, Strohscheune, Grillplatz. "
        "Sonntags offener Hoftag, unter der Woche Geburtstage und Gruppen nach Anmeldung."
    ),
    hours="freizeit",
    usp=("kinder", "parken", "hunde"),
    events=(
        Ev(
            "Offener Hoftag am Sonntag",
            7,
            11,
            "6.00",
            60,
            "Tiere füttern, Traktor fahren, Waffeln — Kinder bis 3 frei.",
            "bbq-family",
            duration_hours=6,
            weekday=6,
        ),
        Ev(
            "Laternenabend auf dem Hof",
            21,
            17,
            "4.00",
            80,
            "Laternen basteln, Umzug über die Wiese, Punsch am Feuer.",
            "sg-laternen-hof",
            duration_hours=3,
        ),
        Ev(
            "Brot backen im Holzofen (Familien)",
            28,
            14,
            "12.00",
            20,
            "Teig kneten, Ofen anheizen, eigenes Brot mitnehmen.",
            "sg-holzofen-brot",
            duration_hours=3,
        ),
    ),
    offers=(
        Offer(
            "Kindergeburtstag ab 89 €",
            "Zwei Stunden Hofprogramm für bis zu 8 Kinder — Termin anfragen.",
            ends="none",
            response="inquire",
            photo="sg-kindergeburtstag-hof",
            group="Dauerhaft",
            tags=("familienfreundlich",),
        ),
    ),
    anfrage=("date", "guests"),
)

BUSINESSES = (LICHTSPIEL, STEILWAND, DREHSCHEIBE, WUPPERPFAD, FUNKENSCHLAG, ABENTEUERWIESE)
