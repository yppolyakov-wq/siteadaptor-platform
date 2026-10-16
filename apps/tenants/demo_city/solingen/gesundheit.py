"""Раздел «Gesundheit & Fitness» — демо-бизнесы Золингена (DCC).

Физиотерапия/реформхаус — без лечебных обещаний и health claims (HWG § 3, HCVO):
описываем услугу и продукт, не эффект на здоровье. Аптек нет (план §9).
"""

from ..spec import Biz, Ev, Item, Offer, Shelf, Svc

SECTION = "gesundheit-fitness"

LOTUSBLICK = Biz(
    key="sg_lotusblick",
    label="Yogaraum Lotusblick",
    btype="other",
    category="yoga",
    district="graefrath",
    street="Klosterpfad",
    house="5",
    lat="51.2020",
    lng="7.0700",
    phone="+49 212 5551801",
    accent="#7c3aed",
    hero_photo="yoga-studio",
    tagline="Hatha, Yin und Yoga für Anfänger — kleine Gruppen über den Dächern von Gräfrath.",
    about=(
        "Ein heller Raum unterm Dach, maximal zwölf Matten, drei Lehrerinnen. Probestunde "
        "kostenlos, Zehnerkarten ohne Ablauf, Matten und Decken sind da."
    ),
    hours="studio",
    usp=("probe", "ruhe", "termin"),
    services=(
        Svc("Hatha Yoga (Gruppe)", 75, "14.00", "Für alle Level, Mo und Do 18:30.", "yoga-mat"),
        Svc(
            "Yin Yoga (Gruppe)",
            75,
            "14.00",
            "Ruhig, lange gehaltene Haltungen — Mi 18:30.",
            "yoga-nature",
        ),
        Svc("Einzelstunde", 60, "65.00", "Auf Ihre Fragen zugeschnitten.", "yoga-teacher-woman"),
    ),
    events=(
        Ev(
            "Yoga-Nachmittag am Sonntag",
            10,
            14,
            "35.00",
            12,
            "Drei Stunden Praxis, Tee und Zeit — für alle Level.",
            "yoga-forest",
            theme="yoga",
            duration_hours=3,
            weekday=6,
        ),
        Ev(
            "Einführung Meditation",
            17,
            18,
            "15.00",
            12,
            "90 Minuten Atem und Stille — ohne Vorkenntnisse.",
            "meditation-breathing",
            theme="meditation",
        ),
    ),
    offers=(
        Offer(
            "Probestunde kostenlos",
            "Erste Gruppenstunde geschenkt — einfach anmelden.",
            ends="none",
            response="inquire",
            photo="yoga-training-matte",
            group="Neu bei uns",
            tags=("yoga",),
        ),
        Offer(
            "10er-Karte 119 €",
            "Zehn Gruppenstunden, kein Ablaufdatum.",
            price="119.00",
            ends="none",
            response="show",
            photo="yoga-products",
            group="Dauerhaft",
        ),
    ),
)

BEWEGUNGSRAUM = Biz(
    key="sg_bewegungsraum",
    label="Physiotherapie Bewegungsraum",
    btype="other",
    category="physiotherapie",
    district="mitte",
    street="Messerstraße",
    house="30",
    lat="51.1660",
    lng="7.0760",
    phone="+49 212 5551802",
    accent="#0369a1",
    hero_photo="sg-physiotherapie",
    tagline="Physiotherapie mit Rezept und als Selbstzahler — Termine auch am frühen Morgen.",
    about=(
        "Praxis mit vier Behandlungsräumen und Trainingsfläche in der Innenstadt. Alle "
        "Kassen, Termine ab 8 Uhr, barrierefrei im Erdgeschoss."
    ),
    hours="praxis",
    usp=("termin", "barrierefrei", "parken"),
    services=(
        Svc(
            "Krankengymnastik (Rezept)",
            20,
            "0.00",
            "Mit ärztlicher Verordnung — Zuzahlung nach Kasse.",
            "sg-physiotherapie",
        ),
        Svc(
            "Manuelle Therapie (Selbstzahler)",
            30,
            "45.00",
            "Einzeltermin ohne Rezept.",
            "sg-manuelle-therapie",
        ),
        Svc(
            "Gerätetraining (Monat)",
            60,
            "49.00",
            "Angeleitetes Training auf der Trainingsfläche.",
            "sg-geraetetraining",
        ),
    ),
    offers=(
        Offer(
            "Frühtermine 8–9 Uhr frei",
            "Diese Woche noch Plätze vor der Arbeit — anrufen oder online buchen.",
            ends="week",
            response="show",
            photo="sg-physiotherapie",
            group="Diese Woche",
            tags=("barrierefrei",),
        ),
    ),
)

SCHARFBLICK = Biz(
    key="sg_scharfblick",
    label="Optik Scharfblick",
    btype="retail",
    category="optik",
    district="ohligs-aufderhoehe-merscheid",
    street="Am Markt",
    house="2",
    lat="51.1670",
    lng="7.0140",
    phone="+49 212 5551803",
    accent="#1e3a8a",
    hero_photo="brille-licht",
    tagline="Brillen, Kontaktlinsen und Sehtest — Augenoptikermeister in Ohligs.",
    about=(
        "Augenoptik am Ohligser Markt: Sehtest mit moderner Messung, Fassungen von kleinen "
        "Labels, eigene Werkstatt für Gläser und Reparaturen. Kinderbrillen mit Garantie."
    ),
    hours="laden",
    usp=("meister", "beratung", "garantie"),
    shelves=(
        Shelf(
            "Brillen",
            "brillen",
            "optik",
            (
                Item(
                    "Fassung Acetat Klassik",
                    "149.00",
                    "Handpoliert, in drei Farben.",
                    "brille-licht",
                ),
                Item(
                    "Sonnenbrille Küste",
                    "119.00",
                    "Polarisiert, UV400.",
                    "mode-sonnenbrille-kueste",
                ),
                Item("Lesebrille +1,5", "29.00", "Leicht, mit Etui.", "sub-brillen"),
                Item(
                    "Kontaktlinsen Monatslinsen, 6 Stück",
                    "24.90",
                    "Silikon-Hydrogel, nach Anpassung.",
                    "sg-kontaktlinsen",
                ),
            ),
        ),
    ),
    services=(
        Svc("Sehtest", 30, "0.00", "Kostenlos beim Brillenkauf, sonst 19 €.", "sg-sehtest"),
        Svc("Kontaktlinsen-Anpassung", 45, "39.00", "Probelinsen inklusive.", "sg-kontaktlinsen"),
    ),
    offers=(
        Offer(
            "Zweitbrille −50 %",
            "Beim Kauf einer Brille die zweite Fassung zum halben Preis.",
            percent=50,
            ends="14d",
            response="show",
            photo="sub-brillen",
            group="Saison",
            item="Fassung Acetat Klassik",
        ),
    ),
)

LINDENBLUETE = Biz(
    key="sg_lindenbluete",
    label="Reformhaus Lindenblüte",
    btype="grocery",
    category="gesundheitsprodukte",
    district="burg-hoehscheid",
    street="Burgweg",
    house="4",
    lat="51.1560",
    lng="7.0950",
    phone="+49 212 5551804",
    accent="#4d7c0f",
    hero_photo="tee-feldrand-kraeuter",
    tagline="Tees, Nahrungsergänzung und Naturkosmetik — mit Beratung, ohne Versprechen.",
    about=(
        "Reformhaus seit 1968: Kräutertees, Nüsse und Trockenfrüchte, Nahrungsergänzung "
        "bekannter Hersteller, Naturkosmetik. Wir beraten zu Produkten — nicht zu Krankheiten."
    ),
    hours="laden",
    usp=("beratung", "bio", "nachhaltig"),
    shelves=(
        Shelf(
            "Reformwaren",
            "reformwaren",
            "gesundheitsprodukte",
            (
                Item(
                    "Kräutertee Feldrand",
                    "5.90",
                    "Lose, 80 g — Kamille, Fenchel, Melisse.",
                    "tee-feldrand-kraeuter",
                    diets=("vegan", "bio"),
                    ingredients="Kamille, Fenchel, Zitronenmelisse",
                    unit="100g",
                    content="0.8",
                    vat="7.00",
                ),
                Item(
                    "Honig Lindenblüte",
                    "7.90",
                    "500 g, vom Imker aus dem Bergischen.",
                    "honig-lindenbluete-glas",
                    ingredients="Honig",
                    unit="kg",
                    content="0.5",
                    vat="7.00",
                    origin="Bergisches Land",
                ),
                Item(
                    "Energy Balls Dattel-Kakao, 6 Stück",
                    "4.50",
                    "Ohne Zuckerzusatz (enthält von Natur aus Zucker), vegan.",
                    "energy-balls",
                    diets=("vegan",),
                    allergens=("h",),
                    ingredients="Datteln, Mandeln, Kakao, Kokos",
                    vat="7.00",
                ),
                Item(
                    "Ayurveda-Gewürzmischung",
                    "6.90",
                    "Für Dal und Gemüse, 60 g.",
                    "ayurveda-spices",
                    diets=("vegan", "bio"),
                    ingredients="Kurkuma, Kreuzkümmel, Koriander, Ingwer, Pfeffer",
                    unit="100g",
                    content="0.6",
                    vat="7.00",
                ),
                Item(
                    "Magnesium-Kapseln, 90 Stück",
                    "12.90",
                    "Nahrungsergänzungsmittel — kein Ersatz für ausgewogene Ernährung.",
                    "sg-kapseln-dose",
                    ingredients="Magnesiumcitrat, Kapselhülle (Cellulose)",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Tee-Woche: 2 Sorten lose −15 %",
            "Alle losen Tees beim Kauf von zwei Sorten.",
            percent=15,
            ends="week",
            response="show",
            photo="tee-blaetter-loeffel",
            group="Diese Woche",
            item="Kräutertee Feldrand",
            tags=("bio",),
        ),
    ),
)

WUPPERWELLE = Biz(
    key="sg_wupperwelle",
    label="Day-Spa Wupperwelle",
    btype="other",
    category="wellness",
    district="burg-hoehscheid",
    street="Wupperufer",
    house="55",
    lat="51.1450",
    lng="7.1400",
    phone="+49 212 5551805",
    accent="#0e7490",
    hero_photo="sg-sauna",
    tagline="Sauna, Dampfbad und Ruheraum am Fluss — drei Stunden Abstand vom Alltag.",
    about=(
        "Kleines Day-Spa direkt an der Wupper: finnische Sauna, Dampfbad, Außenbecken, "
        "Ruheraum mit Blick aufs Wasser. Maximal 20 Gäste gleichzeitig — Zeitfenster buchen."
    ),
    hours="freizeit",
    usp=("ruhe", "termin", "parken"),
    services=(
        Svc(
            "Spa-Eintritt 3 Stunden",
            180,
            "29.00",
            "Sauna, Dampfbad, Außenbecken, Ruheraum.",
            "sg-sauna",
        ),
        Svc(
            "Tageskarte",
            480,
            "45.00",
            "Von Öffnung bis Schluss, Handtuch inklusive.",
            "sg-spa-ruheraum",
        ),
        Svc(
            "Paar-Zeit (2 Personen)",
            180,
            "69.00",
            "Zwei Eintritte, Tee und Obst im Ruheraum.",
            "sg-spa-paar",
        ),
    ),
    offers=(
        Offer(
            "Mittwoch-Vormittag 22 €",
            "Mittwochs 10–15 Uhr Eintritt 22 € statt 29 € — für alle.",
            price="22.00",
            was="29.00",
            ends="week",
            response="reserve",
            photo="sg-sauna",
            group="Diese Woche",
        ),
        Offer(
            "Winterabend: Eintritt + Aufguss-Menü 35 €",
            "Freitags ab 18 Uhr mit drei Aufgüssen.",
            price="35.00",
            was="39.00",
            ends="14d",
            response="reserve",
            photo="sg-spa-ruheraum",
            group="Saison",
        ),
    ),
)

BUSINESSES = (LOTUSBLICK, BEWEGUNGSRAUM, SCHARFBLICK, LINDENBLUETE, WUPPERWELLE)
