"""Демо-«киты» — полноценные showcase-витрины по вертикалям (M20 demo).

Кит = курируемый набор: раскладка секций + цвет + навигация + hero-баннер с
фото + глубокий каталог (категории, товары с фото/вариантами/аллергенами) +
акции + контент-секции (CTA/отзывы/FAQ/галерея) + услуги/номера/события под тип.
Используется командой ``seed_demo_tenants`` для отдельных демо-тенантов на
субдоменах. Фото — внешний тематичный сервис (loremflickr по ключевым словам),
детерминированно по ``lock`` (решение владельца: внешний сервис для демо).

Товары помечаются ``metadata={"demo": True}`` (как в apps.tenants.demo) — общая
маркировка для очистки. Категории — со слагом ``demo-…``.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import siteconfig


def demo_image(keyword: str, *, w: int = 800, h: int = 600, lock: int = 1) -> str:
    """Тематичный демо-URL картинки (внешний сервис, детерминирован по lock)."""
    kw = keyword.strip().replace(" ", ",")
    return f"https://loremflickr.com/{w}/{h}/{kw}?lock={lock}"


def _image_ref(keyword: str, lock: int, alt: str) -> dict:
    """FileRef-конверт для Product.images / галереи из внешнего фото."""
    return {
        "id": f"demo-{lock}",
        "url": demo_image(keyword, lock=lock),
        "alt": {"de": alt},
        "is_primary": True,
        "sort_order": 0,
    }


@dataclass
class DemoKit:
    key: str
    label: str
    business_type: str
    accent: str
    hero_image_kw: str
    hero_title: str
    hero_text: str
    # категории: (название_de, slug-суффикс, [товары])
    categories: list = field(default_factory=list)
    gallery_kw: list = field(default_factory=list)
    gallery_video: str = ""  # T1: видео в секции галереи (YouTube/Vimeo/файл)
    faq: list = field(default_factory=list)
    testimonials: list = field(default_factory=list)
    process: list = field(default_factory=list)  # (title, text) — «как мы работаем»
    team: list = field(default_factory=list)  # (name, role, photo_keyword)
    trust: dict = field(default_factory=dict)  # {"since": "1998", "marks": [...]}
    cta: dict = field(default_factory=dict)
    about_title: str = ""
    about_text: str = ""
    nav_style: str = "classic"
    promo_count: int = 3
    address: str = ""
    opening_hours_text: str = ""
    # Структурные часы для live-статуса: {weekday(0-6): ("HH:MM","HH:MM")}.
    opening_hours: dict = field(default_factory=dict)
    services: list = field(default_factory=list)  # (name, minutes, price_eur)
    stay_units: list = field(default_factory=list)  # (name, type, qty, price_eur, guests)
    events: list = field(default_factory=list)  # (title, in_days, capacity, price_eur)
    # booking-ресурсы (стол/мастер/зал) с недельным расписанием — чтобы /termin/
    # сразу показывал слоты. dict: name/type/capacity/counts_party/start/end/slot.
    resources: list = field(default_factory=list)
    # Модули, которые кит включает у демо-тенанта сверх пресета по типу (orders,
    # events, jobs … — иначе демо не покажет онлайн-заказ/события/кейтеринг).
    enable_modules: list = field(default_factory=list)
    # Конфиг доставки (Click&Collect + Lieferung) — задаётся на Tenant при apply_kit.
    delivery: dict = field(default_factory=dict)
    # Программа лояльности (штампы): {"label","stamps","reward"} — при активном loyalty.
    loyalty: dict = field(default_factory=dict)


# Товар: dict {name, price, desc, img(keyword), variants?[(label,price)],
#   allergens?[codes], modifiers?[{name,min,max,options:[(label,delta)]}]}
def _p(name, price, desc, img, variants=None, allergens=None, modifiers=None, badge=""):
    return {
        "name": name,
        "price": price,
        "desc": desc,
        "img": img,
        "variants": variants or [],
        "allergens": allergens or [],
        "modifiers": modifiers or [],
        "badge": badge,
    }


# Конструктор блюда (A4): группа модификаторов.
#   min/max — правило выбора (min>=1 обязательная; max==1 radio; max>1/0 checkbox).
def _mg(name, options, *, min=0, max=1):
    return {"name": name, "min": min, "max": max, "options": options}


# Готовые наборы модификаторов для пиццы (Teigdicke / Extra Käse / Beläge / Ohne).
PIZZA_MODIFIERS = [
    _mg(
        "Teig",
        [("Klassisch", "0.00"), ("Dünn", "0.00"), ("Dick", "1.00")],
        min=1,
        max=1,
    ),
    _mg("Extra Käse", [("Extra Käse", "1.50")], min=0, max=1),
    _mg(
        "Beläge hinzufügen",
        [
            ("Pilze", "1.00"),
            ("Schinken", "1.50"),
            ("Paprika", "1.00"),
            ("Oliven", "1.00"),
            ("Rucola", "1.00"),
        ],
        min=0,
        max=0,  # без верхнего предела
    ),
    _mg(
        "Ohne",
        [("ohne Zwiebeln", "0.00"), ("ohne Knoblauch", "0.00")],
        min=0,
        max=0,
    ),
]


RESTAURANT = DemoKit(
    key="restaurant",
    label="Restaurant «Bella Vista»",
    business_type="restaurant",
    accent="#b45309",
    hero_image_kw="restaurant,interior",
    hero_title="Bella Vista",
    hero_text="Italienische Küche mit Herz — frische Pasta, knusprige Pizza und mehr.",
    about_title="Über uns",
    about_text="Seit 1998 kochen wir mit Leidenschaft und frischen Zutaten aus der Region.",
    nav_style="centered",
    address="Hauptstraße 12, 40721 Hilden",
    opening_hours_text="Mo–So 11:00–22:00",
    opening_hours={d: ("11:00", "22:00") for d in range(7)},
    gallery_kw=[
        "restaurant,food",
        "pizza",
        "pasta",
        "wine,restaurant",
        "dessert",
        "restaurant,table",
    ],
    gallery_video="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    faq=[
        ("Kann ich einen Tisch reservieren?", "Ja, online über «Termin» oder telefonisch."),
        (
            "Habt ihr vegetarische Gerichte?",
            "Natürlich, viele Gerichte sind vegetarisch oder vegan.",
        ),
        ("Bietet ihr Lieferung an?", "Ja, im Umkreis von 5 km liefern wir frei Haus."),
    ],
    testimonials=[
        ("Familie Schmidt", "Bestes Restaurant der Stadt — wir kommen immer wieder!"),
        ("Laura K.", "Die Pizza ist ein Traum, der Service top."),
    ],
    process=[
        ("Reservieren", "Tisch online in 30 Sekunden sichern."),
        ("Genießen", "Frisch zubereitet aus regionalen Zutaten."),
        ("Wiederkommen", "Stammgäste erwartet immer etwas Besonderes."),
    ],
    team=[
        ("Maria Rossi", "Küchenchefin", "chef,woman"),
        ("Luca Bianchi", "Restaurantleiter", "waiter,man"),
        ("Sofia Conti", "Patissière", "pastry,chef"),
    ],
    trust={"since": "1998", "marks": ["Slow Food", "Regional", "Familienbetrieb"]},
    # онлайн-заказ+доставка (orders), события (events), кейтеринг-Anfrage (jobs)
    enable_modules=["orders", "events", "jobs"],
    promo_count=4,  # 4 акции — сетка кратна 2 (красивее)
    loyalty={"label": "Stempelkarte", "stamps": 10, "reward": "1 Gratis-Pizza"},
    events=[
        ("Live-Musik: Italienische Nacht", 5, 40, "0"),
        ("Sonntags-Brunch Buffet", 3, 60, "24.90"),
        ("Wein-Tasting mit Sommelier", 12, 20, "35"),
        ("Pizza-Backkurs für Anfänger", 20, 12, "49"),
    ],
    delivery={
        "enabled": True,
        "fee_cents": 290,  # 2,90 € плоско
        "free_cents": 2500,  # бесплатно от 25 €
        "min_cents": 1500,  # Mindestbestellwert 15 €
        "pickup_min_cents": 0,
        "area": "Wir liefern im Umkreis von 5 km um Hilden.",
        # PLZ-зоны (A2a): ближняя бесплатно, дальняя дороже.
        "zones": [
            {"plz": "40721", "fee_cents": 0, "free_cents": 0, "min_cents": 1500},
            {"plz": "40724", "fee_cents": 390, "free_cents": 3000, "min_cents": 2000},
        ],
    },
    cta={
        "title": "Hunger bekommen?",
        "text": "Bestellen Sie online zur Abholung oder reservieren Sie einen Tisch.",
        "button_label": "Zur Speisekarte",
        "button_url": "/sortiment/",
    },
    resources=[
        {
            "name": "Tisch",
            "type": "table",
            "capacity": 40,  # места в зале; party_size суммируется
            "counts_party_size": True,
            "start": "11:00",
            "end": "22:00",
            "slot": 60,
            "weekdays": range(0, 7),
        }
    ],
    categories=[
        (
            "Vorspeisen",
            "vorspeisen",
            [
                _p(
                    "Bruschetta",
                    "6.50",
                    "Geröstetes Brot mit Tomaten und Basilikum.",
                    "bruschetta",
                    allergens=["gluten"],
                ),
                _p(
                    "Caprese",
                    "8.90",
                    "Tomaten, Mozzarella, Basilikum.",
                    "caprese,salad",
                    allergens=["milch"],
                ),
                _p(
                    "Vitello Tonnato",
                    "11.50",
                    "Kalbfleisch mit Thunfischsauce.",
                    "vitello",
                    allergens=["fisch", "eier"],
                ),
                _p("Antipasti-Teller", "12.90", "Auswahl italienischer Vorspeisen.", "antipasti"),
                _p(
                    "Insalata Mista",
                    "6.90",
                    "Gemischter Salat — klein oder groß.",
                    "salad,bowl",
                    variants=[("klein", "6.90"), ("groß", "9.90")],
                ),
                _p(
                    "Minestrone",
                    "6.90",
                    "Klassische Gemüsesuppe.",
                    "minestrone,soup",
                    allergens=["sellerie"],
                ),
                _p(
                    "Knoblauchbrot",
                    "4.50",
                    "Mit Kräuterbutter.",
                    "garlic,bread",
                    allergens=["gluten", "milch"],
                ),
            ],
        ),
        (
            "Hauptgerichte",
            "hauptgerichte",
            [
                _p(
                    "Pizza Margherita",
                    "9.50",
                    "Tomaten, Mozzarella, Basilikum.",
                    "pizza,margherita",
                    variants=[("klein 26cm", "9.50"), ("groß 32cm", "12.50")],
                    allergens=["gluten", "milch"],
                    modifiers=PIZZA_MODIFIERS,
                ),
                _p(
                    "Pizza Salami",
                    "11.50",
                    "Mit feiner Salami.",
                    "pizza,salami",
                    variants=[("klein 26cm", "11.50"), ("groß 32cm", "14.50")],
                    allergens=["gluten", "milch"],
                    modifiers=PIZZA_MODIFIERS,
                ),
                _p(
                    "Pasta Bolognese",
                    "11.90",
                    "Mit hausgemachter Sauce.",
                    "pasta,bolognese",
                    allergens=["gluten", "sellerie"],
                ),
                _p(
                    "Spaghetti Carbonara",
                    "12.50",
                    "Mit Speck und Ei.",
                    "carbonara",
                    allergens=["gluten", "eier", "milch"],
                ),
                _p(
                    "Lasagne",
                    "12.90",
                    "Hausgemacht, im Ofen überbacken.",
                    "lasagne",
                    allergens=["gluten", "milch", "eier"],
                    badge="tagesgericht",
                ),
                _p("Risotto Funghi", "13.50", "Mit Steinpilzen.", "risotto", allergens=["milch"]),
                _p(
                    "Lasagne al Forno",
                    "11.90",
                    "Hausgemacht mit Béchamel — normale oder große Portion.",
                    "lasagne",
                    variants=[("normale Portion", "11.90"), ("große Portion", "14.90")],
                    allergens=["gluten", "milch"],
                ),
                _p(
                    "Saltimbocca",
                    "18.90",
                    "Kalbschnitzel mit Salbei und Schinken.",
                    "saltimbocca",
                    allergens=["milch"],
                ),
                _p(
                    "Rumpsteak",
                    "23.90",
                    "250 g mit Rosmarinkartoffeln.",
                    "steak",
                    allergens=[],
                    modifiers=[
                        _mg(
                            "Beilage",
                            [
                                ("Rosmarinkartoffeln", "0.00"),
                                ("Pommes", "0.00"),
                                ("Beilagensalat", "1.50"),
                            ],
                            min=1,
                            max=1,
                        ),
                        _mg(
                            "Garstufe",
                            [("Medium", "0.00"), ("Medium Well", "0.00"), ("Well Done", "0.00")],
                            min=1,
                            max=1,
                        ),
                    ],
                ),
                _p(
                    "Lachsfilet",
                    "19.50",
                    "Gebraten, mit Gemüse.",
                    "salmon,fish",
                    allergens=["fisch"],
                ),
                _p(
                    "Gnocchi Gorgonzola",
                    "12.90",
                    "In cremiger Käsesauce.",
                    "gnocchi",
                    allergens=["gluten", "milch"],
                ),
                _p(
                    "Caesar Salad",
                    "10.90",
                    "Mit Hähnchen und Parmesan.",
                    "caesar,salad",
                    allergens=["milch", "eier", "fisch"],
                ),
                _p(
                    "Pizza Vegetariana",
                    "11.90",
                    "Mit frischem Gemüse.",
                    "pizza,vegetables",
                    variants=[("klein 26cm", "11.90"), ("groß 32cm", "14.90")],
                    allergens=["gluten", "milch"],
                    modifiers=PIZZA_MODIFIERS,
                    badge="neu",
                ),
            ],
        ),
        (
            "Getränke",
            "getraenke",
            [
                _p(
                    "Hauswein rot 0,2 L",
                    "5.50",
                    "Trockener Rotwein.",
                    "red,wine",
                    allergens=["sulfit"],
                ),
                _p(
                    "Hauswein weiß 0,2 L",
                    "5.50",
                    "Frischer Weißwein.",
                    "white,wine",
                    allergens=["sulfit"],
                ),
                _p("Aperol Spritz", "7.50", "Der Klassiker.", "aperol,spritz"),
                _p("Espresso", "2.20", "Kräftig italienisch.", "espresso"),
                _p("Cappuccino", "3.20", "Mit Milchschaum.", "cappuccino", allergens=["milch"]),
                _p("Mineralwasser 0,5 L", "3.20", "Still oder sprudelnd.", "water,bottle"),
                _p("Limonata 0,33 L", "3.50", "Italienische Zitronenlimo.", "lemonade"),
                _p("Bier vom Fass 0,5 L", "4.20", "Frisch gezapft.", "beer", allergens=["gluten"]),
                _p(
                    "Cola",
                    "3.20",
                    "Eisgekühlt — 0,33 L oder 0,5 L.",
                    "cola,glass",
                    variants=[("0,33 L", "3.20"), ("0,5 L", "4.20")],
                ),
            ],
        ),
        (
            "Desserts",
            "desserts",
            [
                _p(
                    "Tiramisu",
                    "5.90",
                    "Nach Familienrezept.",
                    "tiramisu",
                    allergens=["gluten", "eier", "milch"],
                ),
                _p("Panna Cotta", "5.50", "Mit Beerensauce.", "panna,cotta", allergens=["milch"]),
                _p(
                    "Eis gemischt",
                    "5.00",
                    "Drei Kugeln nach Wahl.",
                    "ice,cream",
                    allergens=["milch"],
                ),
                _p("Affogato", "4.90", "Vanilleeis mit Espresso.", "affogato", allergens=["milch"]),
            ],
        ),
    ],
)

BAECKEREI = DemoKit(
    key="baeckerei",
    label="Bäckerei «Korn & Co.»",
    business_type="bakery",
    accent="#a16207",
    hero_image_kw="bakery,bread",
    hero_title="Korn & Co.",
    hero_text="Täglich frisch gebacken — Brot, Brötchen und Kuchen aus Meisterhand.",
    about_title="Unsere Backstube",
    about_text="Seit 1965 backen wir handwerklich mit regionalem Getreide, ohne Zusatzstoffe.",
    nav_style="classic",
    address="Marktplatz 5, 40721 Hilden",
    opening_hours_text="Mo–Fr 6:00–18:30 · Sa 6:00–13:00",
    opening_hours={
        0: ("06:00", "18:30"),
        1: ("06:00", "18:30"),
        2: ("06:00", "18:30"),
        3: ("06:00", "18:30"),
        4: ("06:00", "18:30"),
        5: ("06:00", "13:00"),
    },
    enable_modules=["orders"],
    promo_count=4,
    delivery={"enabled": True, "fee_cents": 290, "free_cents": 2500, "area": "Hilden + 5 km"},
    loyalty={"label": "Stempelkarte", "stamps": 10, "reward": "1 Gratis-Brot"},
    gallery_kw=["bread,loaf", "croissant", "cake,bakery", "bakery,counter"],
    trust={"since": "1965", "marks": ["Meisterbetrieb", "Regional", "Ohne Zusatzstoffe"]},
    faq=[
        ("Kann ich vorbestellen?", "Ja — online bestellen und im Laden abholen."),
        ("Habt ihr glutenfreies Brot?", "Freitags und samstags, am besten vorbestellen."),
    ],
    testimonials=[
        ("Maria K.", "Das beste Roggenbrot der Stadt!"),
        ("Tom B.", "Frühstück to go, immer frisch."),
    ],
    team=[("Hans Korn", "Bäckermeister", "baker,man"), ("Lena Korn", "Konditorin", "baker,woman")],
    cta={
        "title": "Vorbestellen & abholen",
        "text": "Spar dir die Warteschlange.",
        "button_label": "Zum Sortiment",
        "button_url": "/sortiment/",
    },
    categories=[
        (
            "Brot & Brötchen",
            "brot",
            [
                _p(
                    "Roggenbrot",
                    "3.80",
                    "Kräftig, saftig, lange frisch.",
                    "rye,bread",
                    variants=[("500 g", "3.80"), ("1 kg", "6.90")],
                    allergens=["gluten"],
                ),
                _p(
                    "Bauernbrot",
                    "4.20",
                    "Natursauerteig, knusprige Kruste.",
                    "sourdough,bread",
                    variants=[("500 g", "4.20"), ("1 kg", "7.50")],
                    allergens=["gluten"],
                ),
                _p("Brötchen", "0.45", "Knusprig — Stück.", "bread,roll", allergens=["gluten"]),
                _p("Laugenbrezel", "1.30", "Frisch gelaugt.", "pretzel", allergens=["gluten"]),
                _p(
                    "Vollkornbrötchen",
                    "0.55",
                    "Mit Körnern.",
                    "wholegrain,roll",
                    allergens=["gluten"],
                ),
            ],
        ),
        (
            "Kuchen & Torten",
            "kuchen",
            [
                _p(
                    "Apfelkuchen",
                    "2.90",
                    "Mit Zimt und Streuseln.",
                    "apple,cake",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Käsekuchen",
                    "3.20",
                    "Cremig, klassisch.",
                    "cheesecake",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Schwarzwälder Kirsch",
                    "3.90",
                    "Stück.",
                    "blackforest,cake",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Croissant",
                    "1.80",
                    "Buttrig, frisch.",
                    "croissant",
                    allergens=["gluten", "milch"],
                ),
            ],
        ),
        (
            "Kaffee & Snacks",
            "snacks",
            [
                _p(
                    "Kaffee",
                    "2.20",
                    "Zum Mitnehmen.",
                    "coffee,cup",
                    variants=[("klein", "2.20"), ("groß", "2.80")],
                    allergens=["milch"],
                ),
                _p(
                    "Belegtes Brötchen",
                    "3.50",
                    "Käse oder Schinken.",
                    "sandwich,roll",
                    allergens=["gluten"],
                ),
                _p(
                    "Quarktasche",
                    "2.10",
                    "Süß gefüllt.",
                    "pastry",
                    allergens=["gluten", "milch", "ei"],
                ),
            ],
        ),
    ],
)

CAFE = DemoKit(
    key="cafe",
    label="Café «Sonnentor»",
    business_type="cafe",
    accent="#0e7490",
    hero_image_kw="cafe,interior",
    hero_title="Café Sonnentor",
    hero_text="Spezialitätenkaffee, hausgemachte Kuchen und ein Platz an der Sonne.",
    about_title="Willkommen",
    about_text="Gemütliches Stadtcafé mit eigener Röstung und täglich frischem Kuchen.",
    nav_style="centered",
    address="Sonnenstraße 8, 40721 Hilden",
    opening_hours_text="Mo–So 8:00–19:00",
    opening_hours={d: ("08:00", "19:00") for d in range(7)},
    enable_modules=["orders", "booking"],
    promo_count=4,
    loyalty={"label": "Kaffeekarte", "stamps": 9, "reward": "1 Gratis-Kaffee"},
    delivery={"enabled": False},
    gallery_kw=["latte,art", "cafe,cake", "barista", "cafe,table"],
    trust={"since": "2014", "marks": ["Eigene Röstung", "Hausgemacht", "Bio-Milch"]},
    faq=[
        ("Kann ich einen Tisch reservieren?", "Ja — online über «Termin»."),
        ("Habt ihr Pflanzenmilch?", "Hafer, Soja und Mandel — ohne Aufpreis."),
    ],
    testimonials=[
        ("Nina S.", "Bester Cappuccino weit und breit."),
        ("Paul R.", "Toller Käsekuchen!"),
    ],
    team=[("Eva Sonn", "Inhaberin & Barista", "barista,woman")],
    cta={
        "title": "Tisch sichern",
        "text": "Reserviere deinen Lieblingsplatz.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    resources=[
        {
            "name": "Tisch (2 Pers.)",
            "type": "table",
            "capacity": 1,
            "start": "08:00",
            "end": "18:00",
            "slot": 30,
        },
        {
            "name": "Tisch (4 Pers.)",
            "type": "table",
            "capacity": 1,
            "start": "08:00",
            "end": "18:00",
            "slot": 30,
        },
    ],
    categories=[
        (
            "Kaffee & Getränke",
            "kaffee",
            [
                _p("Cappuccino", "3.40", "Mit Milchschaum.", "cappuccino", allergens=["milch"]),
                _p(
                    "Latte Macchiato",
                    "3.80",
                    "Geschichtet.",
                    "latte",
                    variants=[("klein", "3.20"), ("groß", "3.80")],
                    allergens=["milch"],
                ),
                _p("Filterkaffee", "2.60", "Eigene Röstung.", "filter,coffee"),
                _p("Heiße Schokolade", "3.50", "Mit Sahne.", "hot,chocolate", allergens=["milch"]),
                _p("Hausgemachte Limonade", "3.20", "Wechselnde Sorten.", "lemonade"),
            ],
        ),
        (
            "Kuchen & Frühstück",
            "kuchen",
            [
                _p(
                    "Käsekuchen",
                    "3.60",
                    "Hausgemacht.",
                    "cheesecake",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Carrot Cake",
                    "3.90",
                    "Mit Frischkäse-Topping.",
                    "carrot,cake",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Frühstücksbrett",
                    "9.80",
                    "Brot, Käse, Aufschnitt, Ei.",
                    "breakfast,plate",
                    allergens=["gluten", "milch", "ei"],
                ),
                _p(
                    "Avocado-Toast",
                    "7.50",
                    "Sauerteig, Ei, Kräuter.",
                    "avocado,toast",
                    allergens=["gluten", "ei"],
                ),
            ],
        ),
    ],
)

FRISEUR = DemoKit(
    key="friseur",
    label="Friseur «Schnittwerk»",
    business_type="other",
    accent="#9333ea",
    hero_image_kw="hair,salon",
    hero_title="Schnittwerk",
    hero_text="Dein Stil, unser Handwerk — Schnitt, Farbe und Pflege mit Termin.",
    about_title="Über uns",
    about_text="Modernes Salon-Team mit Liebe zum Detail. Online buchen in 30 Sekunden.",
    nav_style="classic",
    address="Bahnhofstraße 22, 40721 Hilden",
    opening_hours_text="Di–Fr 9:00–19:00 · Sa 9:00–14:00",
    opening_hours={
        1: ("09:00", "19:00"),
        2: ("09:00", "19:00"),
        3: ("09:00", "19:00"),
        4: ("09:00", "19:00"),
        5: ("09:00", "14:00"),
    },
    enable_modules=["booking"],
    promo_count=2,
    gallery_kw=["haircut", "hair,color", "salon,interior", "hairstyle"],
    trust={"since": "2010", "marks": ["Meisterbetrieb", "Olaplex", "Bio-Farben"]},
    faq=[
        ("Wie buche ich einen Termin?", "Online über «Termin» — Leistung wählen, Slot buchen."),
        ("Kann ich eine 10er-Karte kaufen?", "Ja, frag im Salon nach der Mehrfachkarte."),
    ],
    testimonials=[
        ("Sara L.", "Endlich ein Friseur, der zuhört!"),
        ("Mark T.", "Schneller Online-Termin, top Schnitt."),
    ],
    team=[
        ("Julia Stein", "Meisterin", "hairdresser,woman"),
        ("Ben Kraus", "Stylist", "hairdresser,man"),
    ],
    cta={
        "title": "Termin in 30 Sek.",
        "text": "Wähle Leistung und Uhrzeit.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    services=[
        ("Haarschnitt Damen", 45, "39.00"),
        ("Haarschnitt Herren", 30, "26.00"),
        ("Färben + Schnitt", 120, "89.00"),
        ("Waschen & Föhnen", 30, "22.00"),
        ("Bart trimmen", 20, "15.00"),
    ],
    resources=[
        {
            "name": "Stylistin Julia",
            "type": "staff",
            "capacity": 1,
            "start": "09:00",
            "end": "19:00",
            "slot": 30,
            "weekdays": [1, 2, 3, 4],
        },
        {
            "name": "Stylist Ben",
            "type": "staff",
            "capacity": 1,
            "start": "09:00",
            "end": "19:00",
            "slot": 30,
            "weekdays": [1, 2, 3, 4, 5],
        },
    ],
    categories=[
        (
            "Pflegeprodukte",
            "pflege",
            [
                _p("Shampoo Repair", "16.90", "Für strapaziertes Haar.", "shampoo,bottle"),
                _p("Haaröl", "19.90", "Glanz und Pflege.", "hair,oil"),
            ],
        ),
    ],
)

HOTEL = DemoKit(
    key="hotel",
    label="Hotel «Talblick»",
    business_type="hotel",
    accent="#0f766e",
    hero_image_kw="hotel,room",
    hero_title="Hotel Talblick",
    hero_text="Ruhig gelegen, herzlich geführt — Zimmer und Ferienwohnungen mit Aussicht.",
    about_title="Ihr Gastgeber",
    about_text="Familiengeführtes Haus am Stadtrand. Online buchen, Anzahlung sichert Ihr Zimmer.",
    nav_style="centered",
    address="Talweg 1, 40724 Hilden",
    opening_hours_text="Rezeption 7:00–22:00",
    opening_hours={d: ("07:00", "22:00") for d in range(7)},
    enable_modules=["stays"],
    promo_count=0,
    gallery_kw=["hotel,lobby", "hotel,bedroom", "hotel,breakfast", "hotel,view"],
    trust={"since": "1992", "marks": ["3 Sterne", "Familienbetrieb", "Kostenfreies WLAN"]},
    faq=[
        ("Wie buche ich ein Zimmer?", "Über «Übernachten» — Daten wählen, online buchen."),
        ("Ist Frühstück inklusive?", "Ja, ein reichhaltiges Frühstücksbuffet."),
    ],
    testimonials=[
        ("Familie Weber", "Tolle Aussicht, super freundlich."),
        ("Klaus M.", "Sauber, ruhig, gerne wieder."),
    ],
    team=[("Petra Tal", "Gastgeberin", "hotel,host,woman")],
    cta={
        "title": "Jetzt übernachten",
        "text": "Freie Termine online sichern.",
        "button_label": "Verfügbarkeit prüfen",
        "button_url": "/unterkunft/",
    },
    stay_units=[
        ("Einzelzimmer", "room", 3, "69.00", 1),
        ("Doppelzimmer", "room", 5, "89.00", 2),
        ("Suite", "suite", 2, "149.00", 3),
        ("Ferienwohnung", "apartment", 1, "120.00", 4),
    ],
)

KITS = {
    RESTAURANT.key: RESTAURANT,
    BAECKEREI.key: BAECKEREI,
    CAFE.key: CAFE,
    FRISEUR.key: FRISEUR,
    HOTEL.key: HOTEL,
}


def _kit_sections(kit: DemoKit) -> list[dict]:
    """Раскладка секций кита: фото-hero, меню, акции, галерея, отзывы, FAQ, CTA, контакты."""
    return [
        {"key": "hero", "enabled": True},
        {"key": "promotions", "enabled": True},
        {"key": "products", "enabled": True},
        {"key": "process", "enabled": bool(kit.process)},
        {"key": "team", "enabled": bool(kit.team)},
        {"key": "gallery", "enabled": bool(kit.gallery_kw)},
        {"key": "testimonials", "enabled": bool(kit.testimonials)},
        {"key": "trust", "enabled": bool(kit.trust)},
        {"key": "faq", "enabled": bool(kit.faq)},
        {"key": "cta", "enabled": bool(kit.cta)},
        {"key": "about", "enabled": bool(kit.about_text)},
        {"key": "contact", "enabled": True},
    ]


def apply_kit(tenant, key: str) -> bool:
    """Наполнить тенант полноценным демо-сайтом по киту. False — неизвестный кит.

    Вызывать в схеме тенанта. Создаёт каталог (категории+товары с фото/вариантами/
    аллергенами), акции, услуги/номера/события, и собирает site_config (hero-фото,
    секции, CTA/FAQ/отзывы/галерея, навигация, акцентный цвет)."""
    kit = KITS.get(key)
    if kit is None:
        return False

    from apps.catalog.models import (
        Category,
        ModifierGroup,
        ModifierOption,
        Product,
        ProductVariant,
    )

    lock = 1
    refs = {"kit": key, "categories": [], "products": [], "promotions": []}
    created_products = []
    for sort, (cat_name, slug, items) in enumerate(kit.categories):
        category = Category.objects.create(
            name={"de": cat_name}, slug=f"demo-{slug}", sort_order=sort, is_active=True
        )
        refs["categories"].append(str(category.pk))
        for item in items:
            product = Product.objects.create(
                name={"de": item["name"]},
                description={"de": item["desc"]},
                base_price=Decimal(item["price"]),
                category=category,
                images=[_image_ref(item["img"], lock, item["name"])],
                allergens=item["allergens"],
                badge=item.get("badge", ""),
                is_active=True,
                is_featured=(len(created_products) < 3),
                metadata={"demo": True},
            )
            lock += 1
            for vsort, (vlabel, vprice) in enumerate(item["variants"]):
                ProductVariant.objects.create(
                    product=product, label=vlabel, price=Decimal(vprice), sort_order=vsort
                )
            for gsort, group in enumerate(item.get("modifiers", [])):
                mg = ModifierGroup.objects.create(
                    product=product,
                    name=group["name"],
                    min_select=group.get("min", 0),
                    max_select=group.get("max", 1),
                    sort_order=gsort,
                    is_active=True,
                )
                for osort, (olabel, odelta) in enumerate(group["options"]):
                    ModifierOption.objects.create(
                        group=mg, label=olabel, price_delta=Decimal(odelta), sort_order=osort
                    )
            created_products.append(product)
            refs["products"].append(str(product.pk))

    # Акции: скидки на первые товары.
    from apps.promotions.models import Promotion

    now = timezone.now()
    discounts = [20, 15, 25, 30]
    for i, product in enumerate(created_products[: kit.promo_count]):
        d = discounts[i % len(discounts)]
        promo = Promotion.objects.create(
            title={"de": f"{product.name['de']} –{d} %"},
            description={"de": "Aktion der Woche."},
            product=product,
            promo_type=Promotion.DISCOUNT,
            discount_percent=d,
            status="active",
            starts_at=now,
            ends_at=now + timedelta(days=14),
            metadata={"demo": True},
        )
        refs["promotions"].append(str(promo.pk))

    # Включаем нужные киту модули (orders/events/jobs…) сверх пресета по типу —
    # в памяти ДО сидера (он гейтится по is_module_active) и в final save.
    if kit.enable_modules:
        tenant.disabled_modules = [
            m for m in (tenant.disabled_modules or []) if m not in kit.enable_modules
        ]

    _seed_kit_modules(tenant, kit, refs)

    # --- site_config: раскладка + hero-фото + контент-секции + навигация ---
    cfg = siteconfig.normalize(
        {
            "sections": _kit_sections(kit),
            "hero_title": kit.hero_title,
            "hero_text": kit.hero_text,
            "hero_image": demo_image(kit.hero_image_kw, w=1600, h=600, lock=999),
            "hero_style": "plain",
            "about_title": kit.about_title,
            "about_text": kit.about_text,
            "cta": kit.cta,
            "faq": [{"q": q, "a": a} for q, a in kit.faq],
            "testimonials": [{"name": n, "text": t} for n, t in kit.testimonials],
            "process": [{"title": t, "text": x} for t, x in kit.process],
            "team": [
                {"name": n, "role": r, "photo": demo_image(kw, w=600, h=600, lock=700 + i)}
                for i, (n, r, kw) in enumerate(kit.team)
            ],
            "trust": kit.trust or {"since": "", "marks": []},
            "gallery": [
                {"url": demo_image(kw, lock=500 + i), "alt": {"de": kit.label}}
                for i, kw in enumerate(kit.gallery_kw)
            ],
            "gallery_video": kit.gallery_video,
            "nav": {**siteconfig.default_nav(), "style": kit.nav_style},
            "demo": refs,
        }
    )
    tenant.site_config = cfg
    tenant.primary_color = kit.accent
    update_fields = ["site_config", "primary_color", "updated_at"]
    if kit.enable_modules:
        update_fields.append("disabled_modules")
    if kit.delivery.get("enabled"):
        d = kit.delivery
        tenant.delivery_enabled = True
        tenant.delivery_fee_cents = d.get("fee_cents", 0)
        tenant.delivery_free_cents = d.get("free_cents", 0)
        tenant.delivery_min_cents = d.get("min_cents", 0)
        tenant.delivery_area = d.get("area", "")
        tenant.delivery_zones = d.get("zones", [])
        tenant.pickup_min_cents = d.get("pickup_min_cents", 0)
        update_fields += [
            "delivery_enabled",
            "delivery_fee_cents",
            "delivery_free_cents",
            "delivery_min_cents",
            "delivery_area",
            "delivery_zones",
            "pickup_min_cents",
        ]
    if kit.address:
        tenant.address = kit.address
        update_fields.append("address")
    if kit.opening_hours_text:
        tenant.opening_hours = kit.opening_hours_text
        update_fields.append("opening_hours")
    if kit.opening_hours:
        tenant.opening_hours_structured = {str(d): list(r) for d, r in kit.opening_hours.items()}
        update_fields.append("opening_hours_structured")
    tenant.save(update_fields=update_fields)
    return True


def _seed_kit_modules(tenant, kit: DemoKit, refs: dict) -> None:
    """Услуги/ресурсы/номера/события кита (под активный модуль)."""
    from datetime import time

    is_active = tenant.is_module_active
    if kit.resources and is_active("booking"):
        from apps.booking.models import AvailabilityRule, Resource

        refs["resources"] = []
        for r in kit.resources:
            sh, sm = (int(x) for x in r["start"].split(":"))
            eh, em = (int(x) for x in r["end"].split(":"))
            resource = Resource.objects.create(
                name=r["name"],
                type=r.get("type", "table"),
                capacity=r.get("capacity", 1),
                counts_party_size=r.get("counts_party_size", False),
                is_active=True,
            )
            for wd in r.get("weekdays", range(0, 7)):
                AvailabilityRule.objects.create(
                    resource=resource,
                    weekday=wd,
                    start_time=time(sh, sm),
                    end_time=time(eh, em),
                    slot_minutes=r.get("slot", 30),
                )
            refs["resources"].append(str(resource.pk))
    if kit.services and is_active("booking"):
        from apps.booking.models import Service

        refs["services"] = []
        for name, minutes, price in kit.services:
            svc = Service.objects.create(
                name=name, duration_minutes=minutes, price_cents=int(Decimal(price) * 100)
            )
            refs["services"].append(str(svc.pk))
    if kit.stay_units and is_active("stays"):
        from apps.stays.models import StayUnit

        refs["stay_units"] = []
        for name, utype, qty, price, guests in kit.stay_units:
            unit = StayUnit.objects.create(
                name=name,
                type=utype,
                quantity=qty,
                price_cents=int(Decimal(price) * 100),
                max_guests=guests,
                is_active=True,
            )
            refs["stay_units"].append(str(unit.pk))
    if kit.loyalty and is_active("loyalty"):
        from apps.promotions.models import LoyaltyProgram

        program = LoyaltyProgram.objects.create(
            label=kit.loyalty["label"],
            stamps_required=kit.loyalty.get("stamps", 10),
            reward_label=kit.loyalty.get("reward", ""),
            is_active=True,
        )
        refs["loyalty"] = [str(program.pk)]
    if kit.events and is_active("events"):
        from apps.events.models import Event

        now = timezone.now()
        refs["events"] = []
        for title, in_days, capacity, price in kit.events:
            event = Event.objects.create(
                title=title,
                starts_at=now + timedelta(days=in_days),
                capacity=capacity,
                price_cents=int(Decimal(price) * 100),
                status=Event.STATUS_PUBLISHED,
            )
            refs["events"].append(str(event.pk))
