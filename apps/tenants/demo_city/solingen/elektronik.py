"""Раздел «Elektronik & Technik» — демо-бизнесы Золингена (DCC).

Фонд CC0 почти не содержит товарной съёмки техники (пространство `ol-*` закрыто за
аутлетом) — ключи `sg-*` живут на тематическом плейсхолдере до фото-добора (план §3).
"""

from ..spec import Biz, Item, Offer, Shelf, Svc

SECTION = "elektronik-technik"

BITBRUECKE = Biz(
    key="sg_bitbruecke",
    label="PC-Werkstatt Bitbrücke",
    btype="retail",
    category="computer",
    district="mitte",
    street="Messerstraße",
    house="17",
    lat="51.1670",
    lng="7.0950",
    phone="+49 212 5551501",
    accent="#1e40af",
    hero_photo="sg-laptop",
    tagline="Laptops und PCs — verkaufen, reparieren, aufrüsten. Datenrettung im Haus.",
    about=(
        "Werkstatt mit Ladentheke in der Innenstadt: Diagnose am selben Tag, SSD-Upgrades "
        "während Sie warten, refurbished Business-Laptops mit einem Jahr Garantie."
    ),
    hours="laden",
    usp=("reparatur", "garantie", "beratung"),
    shelves=(
        Shelf(
            "Computer",
            "computer",
            "computer",
            (
                Item(
                    "Business-Laptop 14″ refurbished",
                    "449.00",
                    "Intel i5, 16 GB, 512 GB SSD — Gebrauchtware mit Garantie.",
                    "sg-laptop-refurbished",
                ),
                Item("SSD 1 TB NVMe", "79.00", "Einbau und Datenübernahme 29 € extra.", "sg-ssd"),
                Item(
                    "Monitor 27″ IPS", "219.00", "WQHD, höhenverstellbar, zwei HDMI.", "sg-monitor"
                ),
                Item(
                    "Tastatur-Maus-Set kabellos",
                    "39.00",
                    "Leise Tasten, USB-C-Ladung.",
                    "sg-tastatur",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Diagnose & Kostenvoranschlag",
            30,
            "19.00",
            "Wird bei Reparatur verrechnet.",
            "sg-pc-diagnose",
        ),
        Svc(
            "Windows neu aufsetzen",
            60,
            "69.00",
            "Inklusive Treiber, Updates und Datensicherung.",
            "sg-pc-neuinstallation",
        ),
        Svc(
            "Datenrettung (Erstcheck)",
            45,
            "49.00",
            "Festplatte oder SSD — Erstcheck, dann Festpreis.",
            "sg-datenrettung",
        ),
    ),
    offers=(
        Offer(
            "SSD-Upgrade komplett 99 €",
            "1 TB SSD inklusive Einbau und Datenübernahme — diese Woche.",
            price="99.00",
            was="108.00",
            ends="week",
            response="reserve",
            photo="sg-ssd",
            group="Diese Woche",
            item="SSD 1 TB NVMe",
            tags=("vor-ort-service",),
        ),
        Offer(
            "Refurbished-Laptops ab 449 €",
            "Geprüfte Business-Geräte, ein Jahr Garantie, Windows frisch installiert.",
            price="449.00",
            ends="none",
            response="show",
            photo="sg-laptop-refurbished",
            group="Dauerhaft",
            tags=("gebraucht",),
        ),
    ),
)

KLANGRAUM = Biz(
    key="sg_klangraum",
    label="HiFi-Studio Klangraum",
    btype="retail",
    category="tv-audio",
    district="wald",
    street="Eichenallee",
    house="18",
    lat="51.1830",
    lng="7.0550",
    phone="+49 212 5551502",
    accent="#111827",
    hero_photo="sg-lautsprecher",
    tagline="Lautsprecher, Verstärker und Plattenspieler — im Hörraum ausprobieren.",
    about=(
        "Zwei Hörräume in Wald, Termin ohne Kaufzwang. Wir stellen Anlagen zu Hause auf, "
        "richten Multiroom ein und reparieren alte Verstärker in der eigenen Werkstatt."
    ),
    hours="laden",
    usp=("beratung", "service", "reparatur"),
    shelves=(
        Shelf(
            "HiFi",
            "hifi",
            "tv-audio",
            (
                Item(
                    "Regallautsprecher Paar",
                    "599.00",
                    "Zwei-Wege, Echtholzfurnier, 8 Ohm.",
                    "sg-lautsprecher",
                ),
                Item(
                    "Streaming-Verstärker",
                    "899.00",
                    "2 × 80 W, WLAN, Phono-Eingang.",
                    "sg-verstaerker",
                ),
                Item(
                    "Plattenspieler mit Tonabnehmer",
                    "449.00",
                    "Riemenantrieb, vormontiert, justiert.",
                    "sg-plattenspieler",
                ),
                Item(
                    "Kopfhörer offen",
                    "249.00",
                    "Für zu Hause — luftig, detailreich.",
                    "sg-kopfhoerer",
                ),
                Item(
                    "Soundbar mit Subwoofer",
                    "399.00",
                    "Für Fernseher bis 65″, HDMI eARC.",
                    "sg-fernseher-soundbar",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Hörtermin im Studio",
            60,
            "0.00",
            "Ihre Musik, unsere Anlagen — unverbindlich.",
            "sg-hoerraum",
        ),
        Svc(
            "Aufstellung & Einmessung zu Hause",
            120,
            "149.00",
            "Wir bringen, stellen auf und messen ein.",
            "sg-einmessung",
        ),
    ),
    offers=(
        Offer(
            "Plattenspieler + Lautsprecher 899 €",
            "Einstiegsset mit Vorführung — statt 1.048 €.",
            price="899.00",
            was="1048.00",
            ends="14d",
            response="reserve",
            photo="sg-plattenspieler",
            group="Neu bei uns",
            item="Plattenspieler mit Tonabnehmer",
        ),
    ),
)

HAUSGERAETE_WUPPER = Biz(
    key="sg_hausgeraete_wupper",
    label="Hausgeräte-Service Wupper",
    btype="retail",
    category="haushaltsgeraete",
    district="burg-hoehscheid",
    street="Wupperufer",
    house="40",
    lat="51.1500",
    lng="7.1100",
    phone="+49 212 5551503",
    accent="#0f766e",
    hero_photo="sg-waschmaschine",
    tagline="Waschmaschine, Spülmaschine, Herd — reparieren oder neu, mit Lieferung und Anschluss.",
    about=(
        "Kundendienst für Haushaltsgroßgeräte seit 1979: Reparatur vor Ort in ganz Solingen, "
        "Ersatzteile am Lager, Neugeräte mit Anschluss und Altgerätemitnahme."
    ),
    hours="handwerk",
    usp=("service", "reparatur", "garantie"),
    shelves=(
        Shelf(
            "Hausgeräte",
            "hausgeraete",
            "haushaltsgeraete",
            (
                Item(
                    "Waschmaschine 8 kg, A",
                    "649.00",
                    "1400 U/min, leise, 10 Jahre Motorgarantie.",
                    "sg-waschmaschine",
                ),
                Item(
                    "Geschirrspüler 60 cm",
                    "579.00",
                    "Besteckschublade, 44 dB, Lieferung inklusive.",
                    "sg-geschirrspueler",
                ),
                Item(
                    "Kühl-Gefrier-Kombi 186 cm",
                    "729.00",
                    "NoFrost, 0-Grad-Zone.",
                    "sg-kuehlschrank",
                ),
                Item("Toaster Edelstahl", "49.00", "Vier Schlitze, Brötchenaufsatz.", "sg-toaster"),
            ),
        ),
    ),
    services=(
        Svc(
            "Reparatur vor Ort (Anfahrt + 30 Min)",
            30,
            "79.00",
            "In ganz Solingen, Ersatzteile extra.",
            "sg-reparatur-hausgeraet",
        ),
        Svc(
            "Lieferung mit Anschluss",
            60,
            "49.00",
            "Aufstellen, anschließen, Altgerät mitnehmen.",
            "sg-lieferung-anschluss",
        ),
    ),
    offers=(
        Offer(
            "Waschmaschine inkl. Lieferung & Anschluss",
            "Bis Monatsende: Lieferung, Anschluss und Altgerätemitnahme gratis.",
            price="649.00",
            was="698.00",
            ends="14d",
            response="reserve",
            photo="sg-waschmaschine",
            group="Saison",
            item="Waschmaschine 8 kg, A",
            tags=("vor-ort-service",),
        ),
    ),
    anfrage=("date",),
)

KABELSALAT = Biz(
    key="sg_kabelsalat",
    label="Kabelsalat Technikzubehör",
    btype="retail",
    category="technik-zubehoer",
    district="graefrath",
    street="Brunnenweg",
    house="3",
    lat="51.2000",
    lng="7.0500",
    phone="+49 212 5551504",
    accent="#7c3aed",
    hero_photo="sg-kabel",
    tagline="Kabel, Ladegeräte, Hüllen und Akkus — heute gekauft, heute benutzt.",
    about=(
        "Kleiner Laden in Gräfrath für alles, was im Alltag fehlt: das richtige Kabel, "
        "ein Ersatzakku, eine Hülle fürs neue Handy. Schutzfolie kleben wir gleich auf."
    ),
    hours="laden",
    usp=("schnell", "beratung", "zahlung"),
    shelves=(
        Shelf(
            "Zubehör",
            "zubehoer",
            "technik-zubehoer",
            (
                Item(
                    "USB-C-Ladekabel 2 m",
                    "12.90",
                    "Geflochten, 100 W, Datenübertragung.",
                    "sg-kabel",
                ),
                Item(
                    "Ladegerät 65 W GaN",
                    "39.00",
                    "Zwei USB-C, ein USB-A — Laptop und Handy.",
                    "sg-ladegeraet",
                ),
                Item(
                    "Powerbank 20.000 mAh",
                    "34.90",
                    "Zwei Geräte gleichzeitig, Schnellladen.",
                    "sg-powerbank",
                ),
                Item(
                    "Handyhülle mit Kartenfach",
                    "19.90",
                    "Für gängige Modelle, auf Lager.",
                    "sg-handyhuelle",
                ),
                Item(
                    "Schutzfolie inkl. Aufkleben",
                    "14.90",
                    "Blasenfrei aufgebracht im Laden.",
                    "sg-schutzfolie",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Kabel-Dienstag: 2 für 1",
            "Jedes zweite Ladekabel geschenkt — nur dienstags.",
            percent=50,
            ends="week",
            response="show",
            photo="sg-kabel",
            group="Diese Woche",
            item="USB-C-Ladekabel 2 m",
        ),
    ),
)

ZWEITAKKU = Biz(
    key="sg_zweitakku",
    label="Refurbished-Laden Zweitakku",
    btype="retail",
    category="smartphones",
    district="mitte",
    street="Scherenweg",
    house="8",
    lat="51.1750",
    lng="7.0780",
    phone="+49 212 5551505",
    accent="#16a34a",
    hero_photo="sg-smartphone-refurbished",
    tagline="Geprüfte gebrauchte Smartphones und Tablets — mit neuem Akku und Garantie.",
    about=(
        "Jedes Gerät bekommt bei uns 40 Prüfpunkte, einen neuen Akku und ein Jahr Garantie. "
        "Ihr altes Handy kaufen wir an oder recyceln es — Daten löschen wir vor Ihren Augen."
    ),
    hours="laden",
    usp=("garantie", "nachhaltig", "beratung"),
    shelves=(
        Shelf(
            "Refurbished",
            "refurbished",
            "smartphones",
            (
                Item(
                    "Smartphone 6,1″ refurbished, 128 GB",
                    "329.00",
                    "Zustand sehr gut, neuer Akku, 12 Monate Garantie.",
                    "sg-smartphone-refurbished",
                ),
                Item(
                    "Tablet 10,9″ refurbished, 64 GB",
                    "279.00",
                    "Zustand gut, mit Ladegerät.",
                    "sg-tablet-refurbished",
                ),
                Item(
                    "Smartwatch refurbished",
                    "149.00",
                    "Neues Armband, Akku geprüft.",
                    "sg-smartwatch",
                ),
                Item(
                    "Kabellose Ohrhörer refurbished",
                    "89.00",
                    "Neue Aufsätze, hygienisch gereinigt.",
                    "sg-ohrhoerer",
                ),
            ),
        ),
    ),
    services=(
        Svc(
            "Ankauf-Bewertung",
            15,
            "0.00",
            "Wir prüfen Ihr Gerät und machen ein Angebot.",
            "sg-ankauf",
        ),
        Svc(
            "Akkutausch Smartphone",
            45,
            "59.00",
            "Originalqualität, während Sie warten.",
            "sg-akkutausch",
        ),
    ),
    offers=(
        Offer(
            "Altes Handy abgeben: 30 € Bonus",
            "Beim Kauf eines Refurbished-Geräts — Altgerät in jedem Zustand.",
            ends="14d",
            response="show",
            photo="sg-smartphone-refurbished",
            group="Neu bei uns",
            tags=("gebraucht", "nachhaltig"),
        ),
        Offer(
            "Akkutausch 49 € statt 59 €",
            "Für alle gängigen Smartphones — diese Woche.",
            price="49.00",
            was="59.00",
            ends="week",
            response="reserve",
            photo="sg-akkutausch",
            group="Diese Woche",
        ),
    ),
)

BUSINESSES = (BITBRUECKE, KLANGRAUM, HAUSGERAETE_WUPPER, KABELSALAT, ZWEITAKKU)
