"""Раздел «Essen & Gastronomie» — демо-бизнесы Золингена (DCC)."""

from ..spec import Biz, Item, Offer, Shelf

SECTION = "essen-gastronomie"

TRATTORIA_LUMETTO = Biz(
    key="sg_trattoria_lumetto",
    label="Trattoria Lumetto",
    btype="restaurant",
    category="restaurants",
    district="mitte",
    street="Schleifergasse",
    house="9",
    lat="51.1688",
    lng="7.0815",
    phone="+49 212 5551001",
    accent="#b91c1c",
    hero_photo="restaurant-table",
    tagline="Pasta, Risotto und Pizza aus dem Steinofen — mitten in Solingen.",
    about=(
        "Familienbetrieb seit 2009: Teig mit 48 Stunden Reife, Tomaten aus Kampanien und "
        "hausgemachte Pasta. Mittags schnell, abends gemütlich — mit Terrasse zum Lindenplatz."
    ),
    hours="gastro",
    usp=("hausgemacht", "terrasse", "familie"),
    shelves=(
        Shelf(
            "Pizza & Pasta",
            "pizza-pasta",
            "restaurants",
            (
                Item(
                    "Bruschetta al Pomodoro",
                    "7.50",
                    "Geröstetes Brot mit Tomaten, Knoblauch und Basilikum.",
                    "bruschetta",
                    diets=("vegan",),
                    allergens=("a",),
                    vat="7.00",
                ),
                Item(
                    "Pizza Verdure",
                    "11.90",
                    "Gegrilltes Gemüse, Fior di Latte, Rucola.",
                    "pizza-vegetables",
                    diets=("vegetarisch",),
                    allergens=("a", "g"),
                    vat="7.00",
                ),
                Item(
                    "Lasagne della Nonna",
                    "13.50",
                    "Schichten aus Pasta, Ragù und Béchamel — wie bei Nonna.",
                    "lasagne",
                    allergens=("a", "c", "g", "i"),
                    vat="7.00",
                ),
                Item(
                    "Gnocchi al Pesto",
                    "12.50",
                    "Hausgemachte Kartoffelgnocchi mit Basilikumpesto.",
                    "gnocchi",
                    diets=("vegetarisch",),
                    allergens=("a", "c", "g", "h"),
                    vat="7.00",
                ),
                Item(
                    "Risotto ai Funghi",
                    "14.50",
                    "Cremiger Risotto mit Waldpilzen und Parmesan.",
                    "risotto",
                    diets=("vegetarisch", "glutenfrei"),
                    allergens=("g", "l"),
                    vat="7.00",
                ),
                Item(
                    "Saltimbocca alla Romana",
                    "18.90",
                    "Kalbsschnitzel mit Parmaschinken und Salbei.",
                    "saltimbocca",
                    allergens=("a", "g", "l"),
                    vat="7.00",
                ),
                Item(
                    "Panna Cotta",
                    "6.50",
                    "Mit Waldbeeren — hausgemacht.",
                    "panna-cotta",
                    diets=("vegetarisch", "glutenfrei"),
                    allergens=("g",),
                    vat="7.00",
                ),
            ),
        ),
    ),
    offers=(
        Offer(
            "Mittagstisch: Pasta + Salat 9,90 €",
            "Mo–Fr 11:30–14:30 — ein Pastagericht nach Wahl mit kleinem Salat.",
            price="9.90",
            was="13.40",
            ends="week",
            response="show",
            photo="antipasti",
            group="Diese Woche",
            tags=("vegetarisch",),
        ),
        Offer(
            "Pizza-Abend: zweite Pizza −50 %",
            "Dienstags ab 18 Uhr — die günstigere Pizza zum halben Preis.",
            percent=50,
            ends="week",
            response="reserve",
            photo="garlic-bread",
            group="Diese Woche",
            item="Pizza Verdure",
        ),
    ),
)

BUSINESSES = (TRATTORIA_LUMETTO,)
