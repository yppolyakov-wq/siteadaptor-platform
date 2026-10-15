"""Раздел «Tiere & Tierbedarf» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Ev, Item, Offer, Shelf, Svc

SECTION = "tiere"

WUSCHELKOPF = Biz(
    key="sg_wuschelkopf",
    label="Hundesalon Wuschelkopf",
    btype="other",
    category="grooming",
    district="ohligs-aufderhoehe-merscheid",
    street="Lerchenstraße",
    house="14",
    lat="51.1620",
    lng="7.0150",
    phone="+49 212 5551401",
    accent="#0f766e",
    hero_photo="sg-hundesalon",
    tagline="Baden, Schneiden, Krallenpflege — in Ruhe und ohne Fließband.",
    about=(
        "Kleiner Salon in Ohligs mit zwei Pflegeplätzen. Jeder Hund bekommt seinen Termin "
        "allein, ängstliche Tiere lernen den Salon erst beim Schnuppertermin kennen."
    ),
    hours="studio",
    usp=("termin", "ruhe", "parken"),
    services=(
        Svc(
            "Komplettpflege kleiner Hund",
            90,
            "49.00",
            "Baden, Föhnen, Schneiden, Krallen und Ohren — bis 10 kg.",
            "sg-hundesalon",
        ),
        Svc(
            "Komplettpflege großer Hund",
            150,
            "79.00",
            "Baden, Föhnen, Schneiden, Krallen und Ohren — ab 25 kg.",
            "sg-hund-gross",
        ),
        Svc("Krallen schneiden", 15, "12.00", "Auch ohne Termin, wenn ein Platz frei ist.", ""),
        Svc(
            "Schnuppertermin",
            30,
            "0.00",
            "Für ängstliche Hunde: Salon kennenlernen, ohne Pflege.",
            "",
        ),
    ),
    offers=(
        Offer(
            "Welpen-Erstpflege 29 €",
            "Erster Salonbesuch für Welpen bis 6 Monate — sanft und kurz.",
            price="29.00",
            was="49.00",
            ends="14d",
            response="show",
            photo="sg-welpe",
            group="Neu bei uns",
        ),
    ),
)

LEINENLOS = Biz(
    key="sg_leinenlos",
    label="Hundeschule Leinenlos",
    btype="other",
    category="tierdienstleistungen",
    district="burg-hoehscheid",
    street="Am Hang",
    house="30",
    lat="51.1450",
    lng="7.1300",
    phone="+49 212 5551402",
    accent="#1e3a8a",
    hero_photo="sg-hundeschule-wiese",
    tagline="Welpenkurs, Alltagstraining und Spaziergänge in Gruppe — auf eigener Wiese.",
    about=(
        "Zwei Trainerinnen, ein eingezäuntes Gelände oberhalb der Wupper und kleine Gruppen "
        "bis sechs Hunde. Wir arbeiten ohne Druck, mit Futter, Spiel und viel Geduld."
    ),
    hours="studio",
    usp=("termin", "probe", "parken"),
    services=(
        Svc(
            "Welpenstunde (Gruppe)",
            60,
            "15.00",
            "Für Welpen 9–16 Wochen, max. 6 Hunde.",
            "sg-welpenkurs",
        ),
        Svc(
            "Einzeltraining",
            60,
            "55.00",
            "Leinenführigkeit, Rückruf, Alltagsprobleme.",
            "sg-hundetraining",
        ),
        Svc(
            "Social Walk",
            90,
            "12.00",
            "Gemeinsamer Spaziergang für unsichere Hunde.",
            "sg-hund-spaziergang",
        ),
    ),
    events=(
        Ev(
            "Rückruf-Workshop am Samstag",
            12,
            10,
            "39.00",
            8,
            "Drei Stunden Praxis auf der Wiese — Hund und Mensch.",
            "sg-hund-rueckruf",
        ),
    ),
    offers=(
        Offer(
            "Schnupperstunde gratis",
            "Erste Gruppenstunde kostenlos — einfach anmelden.",
            ends="none",
            response="inquire",
            photo="sg-welpenkurs",
            group="Neu bei uns",
            tags=("hundefreundlich",),
        ),
    ),
)

NAPFGLUECK = Biz(
    key="sg_napfglueck",
    label="Futterhaus Napfglück",
    btype="retail",
    category="tierfutter",
    district="mitte",
    street="Scherenweg",
    house="19",
    lat="51.1700",
    lng="7.0700",
    phone="+49 212 5551403",
    accent="#b45309",
    hero_photo="sg-hundefutter-regal",
    tagline="Futter, Snacks und Beratung für Hund und Katze — auch getreidefrei.",
    about=(
        "Fachgeschäft in der Innenstadt mit großer Theke für Kauartikel und Probierpackungen. "
        "Wir wiegen ab, bestellen Spezialfutter und liefern Säcke ab 10 kg in Solingen."
    ),
    hours="laden",
    usp=("beratung", "lieferung", "parken"),
    shelves=(
        Shelf(
            "Hund",
            "hund",
            "tierfutter",
            (
                Item(
                    "Trockenfutter Lamm & Reis, 12 kg",
                    "49.90",
                    "Für ausgewachsene Hunde, getreidearm.",
                    "sg-hundefutter-sack",
                    unit="kg",
                    content="12",
                ),
                Item(
                    "Kauknochen Rind, 3 Stück",
                    "5.90",
                    "Luftgetrocknet, ohne Zusätze.",
                    "sg-hund-kauknochen",
                ),
                Item(
                    "Nassfutter Huhn, 6 × 400 g",
                    "11.40",
                    "70 % Fleischanteil, ohne Zucker.",
                    "sg-hundefutter-dose",
                    unit="kg",
                    content="2.4",
                ),
            ),
        ),
        Shelf(
            "Katze",
            "katze",
            "tierfutter",
            (
                Item(
                    "Katzenfutter Lachs, 2 kg",
                    "16.90",
                    "Getreidefrei, für Wohnungskatzen.",
                    "sg-katzenfutter",
                    unit="kg",
                    content="2",
                ),
                Item(
                    "Katzenstreu Klumpend, 10 l",
                    "8.90",
                    "Staubarm, aus Bentonit.",
                    "sg-katzenstreu",
                    unit="l",
                    content="10",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Großer Sack: 12 kg Trockenfutter −15 %",
            "Alle 12-kg-Säcke diese Woche günstiger.",
            percent=15,
            ends="week",
            response="show",
            photo="sg-hundefutter-sack",
            group="Diese Woche",
            item="Trockenfutter Lamm & Reis, 12 kg",
        ),
        Offer(
            "Probierpaket Katze 4,90 €",
            "Fünf Sorten Nassfutter zum Testen.",
            price="4.90",
            was="7.50",
            ends="14d",
            response="show",
            photo="sg-katze",
            group="Neu bei uns",
        ),
    ),
)

WASSERWELT = Biz(
    key="sg_wasserwelt",
    label="Aquaristik Wasserwelt",
    btype="retail",
    category="tierzubehoer",
    district="graefrath",
    street="Zinnstraße",
    house="6",
    lat="51.2100",
    lng="7.0550",
    phone="+49 212 5551404",
    accent="#0e7490",
    hero_photo="sg-aquarium",
    tagline="Aquarien, Fische und Pflanzen — mit Wasseranalyse im Laden.",
    about=(
        "Seit 2002 in Gräfrath: Süßwasserfische aus eigener Nachzucht, Pflanzen aus "
        "der Gärtnerei, Technik mit Beratung. Wasserprobe mitbringen — wir testen kostenlos."
    ),
    hours="laden",
    usp=("beratung", "qualitaet", "service"),
    shelves=(
        Shelf(
            "Aquaristik",
            "aquaristik",
            "tierzubehoer",
            (
                Item(
                    "Einsteiger-Aquarium 60 l",
                    "129.00",
                    "Becken, Filter, Heizer, LED — komplett.",
                    "sg-aquarium-set",
                ),
                Item(
                    "Außenfilter 600 l/h",
                    "79.00",
                    "Leise, für Becken bis 200 l.",
                    "sg-aquarium-filter",
                ),
                Item(
                    "Pflanzenset Vordergrund",
                    "14.90",
                    "Fünf Töpfe, in-vitro, schneckenfrei.",
                    "sg-aquarium-pflanzen",
                ),
                Item(
                    "Fischfutter Flocken, 250 ml",
                    "6.50",
                    "Hauptfutter für Zierfische.",
                    "sg-fischfutter",
                    unit="l",
                    content="0.25",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Wasseranalyse",
            20,
            "0.00",
            "pH, Nitrit, Nitrat, Härte — Probe mitbringen.",
            "sg-wassertest",
        ),
    ),
    offers=(
        Offer(
            "Starterset 60 l + Fische für 149 €",
            "Aquarium komplett mit zehn Fischen nach Beratung.",
            price="149.00",
            was="169.00",
            ends="14d",
            response="reserve",
            photo="sg-aquarium-set",
            group="Neu bei uns",
            item="Einsteiger-Aquarium 60 l",
        ),
    ),
)

PFOTENPAUSE = Biz(
    key="sg_pfotenpause",
    label="Tiersitting Pfotenpause",
    btype="other",
    category="tierdienstleistungen",
    district="wald",
    street="Fuchsweg",
    house="9",
    lat="51.1880",
    lng="7.0450",
    phone="+49 212 5551405",
    accent="#047857",
    hero_photo="sg-katze",
    tagline="Katzenbetreuung zu Hause und Gassi-Service in Wald.",
    about=(
        "Wenn Sie verreisen, kommen wir: Füttern, Spielen, Katzenklo, Post und Blumen. "
        "Hunde holen wir zum Mittagsspaziergang ab. Kennenlernbesuch immer vorher."
    ),
    hours="studio",
    usp=("service", "beratung", "hunde"),
    profile="A",
    offers=(
        Offer(
            "Katzenbesuch 30 Min 14 €",
            "Täglicher Besuch im Urlaub — Futter, Spiel, Katzenklo.",
            price="14.00",
            ends="none",
            response="inquire",
            photo="sg-katze",
            group="Dauerhaft",
            tags=("hundefreundlich",),
        ),
        Offer(
            "Gassi-Runde 45 Min 12 €",
            "Abholung zu Hause, Mittagsrunde durch den Wald.",
            price="12.00",
            ends="none",
            response="inquire",
            photo="sg-hund-spaziergang",
            group="Dauerhaft",
        ),
        Offer(
            "Herbstferien: 10 Besuche für 120 €",
            "Zehnerkarte für die Ferienwochen — spart 20 €.",
            price="120.00",
            was="140.00",
            ends="14d",
            response="inquire",
            photo="sg-katzenbesuch",
            group="Saison",
        ),
        Offer(
            "Kennenlernbesuch kostenlos",
            "Wir kommen vorbei, Sie zeigen uns alles — unverbindlich.",
            ends="none",
            response="inquire",
            photo="sg-katzenbesuch-tuer",
            group="Neu bei uns",
        ),
    ),
)

BUSINESSES = (WUSCHELKOPF, LEINENLOS, NAPFGLUECK, WASSERWELT, PFOTENPAUSE)
