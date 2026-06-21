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
    # --- Конструктор витрины (S1–S8): новые возможности демо ------------------
    enable_archetypes_section: bool = False  # секция «Unsere Bereiche» (тизеры)
    # Обложки разделов (S3): key архетипа → {"intro","hero_kw","gallery_kw":[...]}.
    archetype_covers: dict = field(default_factory=dict)
    # Многоуровневое меню (S7): готовая структура menus (top/bottom) с подменю,
    # ссылками на категории (slug «demo-…») и группы акций. Пусто → легаси nav.
    menus: dict = field(default_factory=dict)
    # S6: тег группы акции = название категории её товара (Fastfood/Fertiggerichte).
    group_promos_by_category: bool = False
    storefront_root: str = "home"  # S4: стартовая страница (home или ключ архетипа)
    # Поддомен демо-тенанта (slug). Пусто → «<key>-demo». Pranasy → «pranasy».
    subdomain: str = ""
    # Наполнить кабинет примерами транзакций (заказы/заявки/брони/билеты) по
    # активным архетипам — чтобы демо было «как настоящее». Адреса @example.de.
    seed_records: bool = False
    # Скрыть тизеры этих архетипов из секции «Unsere Bereiche» (напр. пустой
    # catalog/booking у отеля). catalog — core, выключить нельзя, только скрыть.
    hide_archetypes: list = field(default_factory=list)


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

VEGAN_BURGER_MODIFIERS = [
    _mg(
        "Brötchen", [("Sesam", "0.00"), ("Vollkorn", "0.00"), ("Glutenfrei", "1.00")], min=1, max=1
    ),
    _mg("Extra Patty", [("Extra Patty", "2.50")], min=0, max=1),
    _mg(
        "Toppings",
        [
            ("Avocado", "1.50"),
            ("Vegan Bacon", "1.50"),
            ("Jalapeños", "0.80"),
            ("Röstzwiebeln", "0.80"),
            ("Vegan Cheese", "1.20"),
        ],
        min=0,
        max=0,
    ),
    _mg("Ohne", [("ohne Zwiebeln", "0.00"), ("ohne Sauce", "0.00")], min=0, max=0),
]

# Многоуровневое меню (S7): подменю Speisekarte/Aktionen + архетипы. Категории по
# slug «demo-…» (apply_kit префиксует), группы акций — по названию категории (S6).
PRANASY_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {
                "label": "Speisekarte",
                "type": "group",
                "children": [
                    {"label": "Fastfood", "type": "category", "target": "demo-fastfood"},
                    {"label": "Fertiggerichte", "type": "category", "target": "demo-fertig"},
                ],
            },
            {
                "label": "Aktionen",
                "type": "group",
                "children": [
                    {"label": "Fastfood-Aktionen", "type": "promo_group", "target": "Fastfood"},
                    {"label": "Fertig-Aktionen", "type": "promo_group", "target": "Fertiggerichte"},
                ],
            },
            {"label": "Tisch", "type": "archetype", "target": "booking"},
            {"label": "Events", "type": "archetype", "target": "events"},
            {"label": "Catering", "type": "archetype", "target": "jobs"},
            {"label": "Treue", "type": "archetype", "target": "loyalty"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Menü", "type": "archetype", "target": "catalog", "icon": "🍔"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🛒"},
            {"label": "Tisch", "type": "archetype", "target": "booking", "icon": "📅"},
            {"label": "Events", "type": "archetype", "target": "events", "icon": "🎫"},
        ],
    },
}

PRANASY = DemoKit(
    key="pranasy",
    label="Pranasy — Vegan Fastfood",
    business_type="restaurant",
    subdomain="pranasy",  # → pranasy.<base> (а не pranasy-demo)
    accent="#16a34a",  # frisches Grün
    hero_image_kw="vegan,burger",
    hero_title="Pranasy",
    hero_text="100 % pflanzlich. Fastfood ohne schlechtes Gewissen — frisch, schnell, lecker.",
    about_title="Über Pranasy",
    about_text="Wir machen veganes Fastfood, das schmeckt: saftige Burger, knusprige Wraps "
    "und frische Bowls — alles pflanzlich, regional und mit Liebe gemacht.",
    nav_style="centered",
    address="Mittelstraße 8, 40213 Düsseldorf",
    opening_hours_text="Mo–So 11:00–22:00",
    opening_hours={d: ("11:00", "22:00") for d in range(7)},
    gallery_kw=["vegan,burger", "vegan,bowl", "vegan,wrap", "smoothie", "vegan,food", "fries"],
    faq=[
        ("Ist alles wirklich vegan?", "Ja — 100 % pflanzlich, ohne Ausnahme."),
        (
            "Kann ich vorbestellen?",
            "Klar, online über «Online bestellen» zur Abholung oder Lieferung.",
        ),
        (
            "Macht ihr Catering?",
            "Ja! Stell über «Catering» eine Anfrage — wir melden uns mit Angebot.",
        ),
    ],
    testimonials=[
        ("Jana", "Endlich veganes Fastfood, das richtig knallt. Der Burger ist der Hammer!"),
        ("Tom & Lisa", "Schnell, frisch, lecker — unser neuer Lieblingsladen."),
    ],
    process=[
        ("Wählen", "Stell dir dein Menü zusammen — mit Extras nach Wunsch."),
        ("Bestellen", "Online zur Abholung oder Lieferung, oder direkt am Tisch."),
        ("Genießen", "Frisch zubereitet, in wenigen Minuten."),
    ],
    team=[
        ("Nour El-Amin", "Gründerin & Köchin", "chef,woman"),
        ("Ben Krause", "Küche", "cook,man"),
    ],
    trust={"since": "2021", "marks": ["100 % Vegan", "Regional", "Bio"]},
    enable_modules=["orders", "events", "jobs", "loyalty"],
    promo_count=4,
    group_promos_by_category=True,
    loyalty={"label": "Pranasy-Stempelkarte", "stamps": 10, "reward": "1 Gratis-Burger"},
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=PRANASY_MENUS,
    archetype_covers={
        "catalog": {
            "intro": "Unsere ganze Karte — Fastfood und Fertiggerichte, alles pflanzlich.",
            "hero_kw": "vegan,burger",
            "gallery_kw": ["vegan,burger", "vegan,wrap", "fries", "vegan,bowl"],
        },
        "booking": {
            "intro": "Reserviere deinen Tisch — wir halten dir einen Platz frei.",
            "hero_kw": "restaurant,table",
        },
        "events": {
            "intro": "Vegane Events, Street-Food-Festivals und Kochkurse.",
            "hero_kw": "food,festival",
            "gallery_kw": ["food,festival", "cooking,class"],
        },
        "jobs": {
            "intro": "Catering & Vorbestellung für Feiern, Büro und Events. Sag uns, was du "
            "brauchst — du bekommst ein unverbindliches Angebot.",
            "hero_kw": "catering,buffet",
        },
        "loyalty": {
            "intro": "Sammle Stempel bei jedem Besuch — der 10. Burger geht aufs Haus.",
            "hero_kw": "vegan,burger",
        },
    },
    events=[
        ("Vegan Street-Food Festival", 7, 200, "0"),
        ("Vegan Burger Battle", 14, 60, "15"),
        ("Kochkurs: Veganes Fastfood selbst machen", 21, 12, "49"),
        ("Sommer-Retreat: Plant-Based Weekend", 40, 30, "129"),
    ],
    delivery={
        "enabled": True,
        "fee_cents": 290,
        "free_cents": 2500,
        "min_cents": 1200,
        "pickup_min_cents": 0,
        "area": "Lieferung im Umkreis von 4 km um Düsseldorf-Mitte.",
        "zones": [
            {"plz": "40213", "fee_cents": 0, "free_cents": 0, "min_cents": 1200},
            {"plz": "40215", "fee_cents": 290, "free_cents": 2500, "min_cents": 1500},
        ],
    },
    cta={
        "title": "Hunger?",
        "text": "Bestell jetzt online zur Abholung oder Lieferung.",
        "button_label": "Zur Speisekarte",
        "button_url": "/sortiment/",
    },
    resources=[
        {
            "name": "Tisch",
            "type": "table",
            "capacity": 24,
            "counts_party_size": True,
            "start": "11:00",
            "end": "22:00",
            "slot": 60,
            "weekdays": range(0, 7),
        }
    ],
    categories=[
        (
            "Fastfood",
            "fastfood",
            [
                _p(
                    "Classic Vegan Burger",
                    "8.90",
                    "Saftiges Pflanzen-Patty, Salat, Tomate, hausgemachte Sauce.",
                    "vegan,burger",
                    variants=[("Single", "8.90"), ("Double", "11.90")],
                    allergens=["gluten", "soja", "senf"],
                    modifiers=VEGAN_BURGER_MODIFIERS,
                    badge="beliebt",
                ),
                _p(
                    "Crispy Chick’n Burger",
                    "9.50",
                    "Knuspriges Soja-Filet, Coleslaw, vegane Mayo.",
                    "vegan,chicken,burger",
                    allergens=["gluten", "soja"],
                    modifiers=VEGAN_BURGER_MODIFIERS,
                ),
                _p(
                    "Falafel Wrap",
                    "7.50",
                    "Falafel, Hummus, Salat, Granatapfel.",
                    "falafel,wrap",
                    allergens=["gluten", "sesam"],
                ),
                _p(
                    "Loaded Fries",
                    "6.90",
                    "Pommes mit veganem Käse, Jalapeños und Röstzwiebeln.",
                    "loaded,fries",
                    variants=[("klein", "6.90"), ("groß", "9.90")],
                    allergens=["soja"],
                ),
                _p(
                    "Vegan Hotdog",
                    "6.50",
                    "Karotten-Hotdog mit Senf, Ketchup, Gurke.",
                    "hotdog",
                    allergens=["gluten", "senf"],
                ),
                _p(
                    "Buddha Bowl",
                    "10.90",
                    "Quinoa, geröstetes Gemüse, Avocado, Tahini.",
                    "vegan,bowl",
                    allergens=["sesam"],
                    badge="neu",
                ),
                _p(
                    "Sweet Potato Fries",
                    "5.50",
                    "Süßkartoffel-Pommes mit Aioli.",
                    "sweet,potato,fries",
                ),
                _p(
                    "Mango Smoothie",
                    "4.50",
                    "Mango, Banane, Hafermilch.",
                    "mango,smoothie",
                    variants=[("0,3 L", "4.50"), ("0,5 L", "5.90")],
                ),
            ],
        ),
        (
            "Fertiggerichte",
            "fertig",
            [
                _p(
                    "Vegan Chili sin Carne",
                    "7.90",
                    "Meal-Prep-Box, 500 g — einfach aufwärmen.",
                    "vegan,chili",
                    allergens=["soja"],
                ),
                _p(
                    "Linsen-Dal mit Reis",
                    "7.50",
                    "Cremiges Dal, fertig portioniert.",
                    "lentil,dal",
                ),
                _p(
                    "Vegane Lasagne",
                    "8.90",
                    "Mit Linsen-Bolognese und Cashew-Béchamel.",
                    "vegan,lasagne",
                    allergens=["gluten", "nuss"],
                ),
                _p(
                    "Curry-Bowl to go",
                    "8.50",
                    "Gemüse-Curry mit Kokosmilch und Reis.",
                    "curry,bowl",
                ),
                _p(
                    "Pasta Pesto Box",
                    "7.90",
                    "Vollkorn-Pasta mit Basilikum-Pesto.",
                    "pasta,pesto",
                    allergens=["gluten", "nuss"],
                ),
                _p(
                    "Overnight Oats",
                    "4.90",
                    "Haferflocken, Chia, Beeren — perfekt fürs Frühstück.",
                    "overnight,oats",
                    allergens=["gluten"],
                ),
            ],
        ),
    ],
)

HOTEL_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Zimmer", "type": "archetype", "target": "stays"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Zimmer", "type": "archetype", "target": "stays", "icon": "🛏"},
            {"label": "Über uns", "type": "page", "target": "about", "icon": "ℹ️"},
        ],
    },
}

HOTEL = DemoKit(
    key="hotel",
    label="Pension Seeblick",
    business_type="hotel",
    subdomain="hotel",  # → hotel.<base>
    accent="#0e7490",  # cyan/See
    hero_image_kw="hotel,room",
    hero_title="Pension Seeblick",
    hero_text="Ihr gemütliches Zuhause am See — komfortable Zimmer, herzlicher Service "
    "und ein reichhaltiges Frühstück.",
    about_title="Über uns",
    about_text="Seit 1985 begrüßen wir Gäste aus aller Welt in unserer familiengeführten "
    "Pension direkt am See. Ruhe, Natur und persönliche Betreuung — dafür stehen wir.",
    nav_style="centered",
    address="Seestraße 5, 88662 Überlingen",
    opening_hours_text="Rezeption täglich 7:00–21:00",
    opening_hours={d: ("07:00", "21:00") for d in range(7)},
    gallery_kw=["hotel,room", "hotel,lobby", "breakfast", "lake,view", "hotel,bathroom", "terrace"],
    faq=[
        ("Wann ist Check-in / Check-out?", "Check-in ab 15:00, Check-out bis 11:00."),
        ("Ist Frühstück inklusive?", "Ja, ein reichhaltiges Frühstücksbuffet ist inklusive."),
        ("Gibt es Parkplätze?", "Kostenlose Parkplätze sind direkt am Haus verfügbar."),
        ("Sind Haustiere erlaubt?", "Hunde sind auf Anfrage herzlich willkommen."),
    ],
    testimonials=[
        ("Herr & Frau Bauer", "Traumhafte Lage am See, herzliche Gastgeber — wir kommen wieder!"),
        ("Julia M.", "Sauber, ruhig und das Frühstück ein Gedicht."),
    ],
    process=[
        ("Anfragen", "Verfügbarkeit online prüfen — in 30 Sekunden."),
        ("Buchen", "Zimmer mit wenigen Klicks sichern."),
        ("Wohlfühlen", "Ankommen, durchatmen, genießen."),
    ],
    team=[
        ("Familie Keller", "Ihre Gastgeber", "hotel,owner"),
        ("Petra Lang", "Rezeption", "receptionist,woman"),
    ],
    trust={"since": "1985", "marks": ["Familienbetrieb", "Direkt am See", "Frühstück inklusive"]},
    enable_modules=["stays"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=HOTEL_MENUS,
    hide_archetypes=["catalog", "booking"],  # пустые у отеля — скрыть из «Bereiche»
    archetype_covers={
        "stays": {
            "intro": "Unsere Zimmer und Ferienwohnungen — alle mit Seeblick oder Gartenblick.",
            "hero_kw": "hotel,room",
            "gallery_kw": ["hotel,room", "lake,view", "breakfast", "hotel,bathroom"],
        },
    },
    cta={
        "title": "Bereit für eine Auszeit?",
        "text": "Prüfen Sie jetzt die Verfügbarkeit und buchen Sie Ihr Zimmer.",
        "button_label": "Zimmer ansehen",
        "button_url": "/unterkunft/",
    },
    stay_units=[
        ("Doppelzimmer Seeblick", "room", 4, "89", 2),
        ("Einzelzimmer", "room", 3, "69", 1),
        ("Familienzimmer", "room", 2, "129", 4),
        ("Ferienwohnung am Garten", "apartment", 1, "149", 4),
    ],
)

KITS = {RESTAURANT.key: RESTAURANT, PRANASY.key: PRANASY, HOTEL.key: HOTEL}


def _kit_sections(kit: DemoKit) -> list[dict]:
    """Раскладка секций кита: фото-hero, меню, акции, галерея, отзывы, FAQ, CTA, контакты."""
    return [
        {"key": "hero", "enabled": True},
        {"key": "archetypes", "enabled": kit.enable_archetypes_section},  # S2: «Unsere Bereiche»
        # Акции/товары — только если у кита есть каталог (иначе пустые секции).
        {"key": "promotions", "enabled": bool(kit.categories)},
        {"key": "products", "enabled": bool(kit.categories)},
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
    category_firsts = []  # первый товар каждой категории — для акций по группам (S6)
    for sort, (cat_name, slug, items) in enumerate(kit.categories):
        category = Category.objects.create(
            name={"de": cat_name}, slug=f"demo-{slug}", sort_order=sort, is_active=True
        )
        refs["categories"].append(str(category.pk))
        first_in_cat = True
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
            if first_in_cat:
                category_firsts.append(product)
                first_in_cat = False

    # Акции: скидки на первые товары.
    from apps.promotions.models import Promotion

    now = timezone.now()
    discounts = [20, 15, 25, 30]
    # S6: при group_promos_by_category берём по первому товару каждой категории
    # (каждая группа представлена), добираем остальными до promo_count.
    if kit.group_promos_by_category:
        rest = [p for p in created_products if p not in category_firsts]
        promo_products = (category_firsts + rest)[: max(kit.promo_count, len(category_firsts))]
    else:
        promo_products = created_products[: kit.promo_count]
    for i, product in enumerate(promo_products):
        d = discounts[i % len(discounts)]
        # Группа акции = название категории товара (S6) — для /aktionen/ и меню.
        group = ""
        if kit.group_promos_by_category and product.category:
            group = (product.category.name or {}).get("de", "")
        promo = Promotion.objects.create(
            title={"de": f"{product.name['de']} –{d} %"},
            description={"de": "Aktion der Woche."},
            product=product,
            promo_type=Promotion.DISCOUNT,
            discount_percent=d,
            status="active",
            starts_at=now,
            ends_at=now + timedelta(days=14),
            group=group,
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
    _seed_kit_records(tenant, kit, refs, created_products)

    # S3: обложки разделов — интро + hero-фото + галерея на архетип.
    archetypes_cfg = {}
    for cov_i, (akey, cov) in enumerate(kit.archetype_covers.items()):
        archetypes_cfg[akey] = {
            "intro": cov.get("intro", ""),
            "hero_image": (
                demo_image(cov["hero_kw"], w=1600, h=600, lock=800 + cov_i)
                if cov.get("hero_kw")
                else ""
            ),
            "gallery": [
                {"url": demo_image(kw, lock=820 + cov_i * 10 + j), "id": f"cov-{akey}-{j}"}
                for j, kw in enumerate(cov.get("gallery_kw", []))
            ],
        }
    # Скрыть пустые архетипы из секции «Unsere Bereiche» (catalog/booking у отеля).
    for hk in kit.hide_archetypes:
        cur = dict(archetypes_cfg.get(hk) or {})
        cur["hidden"] = True
        archetypes_cfg[hk] = cur

    # --- site_config: раскладка + hero-фото + контент-секции + навигация ---
    cfg = siteconfig.normalize(
        {
            "sections": _kit_sections(kit),
            "archetypes": archetypes_cfg,  # S3 обложки разделов
            "menus": kit.menus or None,  # S7 меню (пусто → выводится из nav, без регрессии)
            "storefront_root": kit.storefront_root,  # S4 стартовая страница
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


def _seed_kit_records(tenant, kit: DemoKit, refs: dict, products: list) -> None:
    """Примеры транзакций по активным архетипам (заказы/заявки/брони/билеты) —
    чтобы кабинет демо был наполнен «как настоящий». Демо-тенант одноразовый
    (схема дропается), спец-маркировка не нужна. Адреса @example.de (RFC 2606) —
    реальным людям письма не уходят. Каждый блок изолирован (сбой не рушит сид)."""
    if not kit.seed_records:
        return
    is_active = tenant.is_module_active

    # Bestellungen (Click & Collect)
    if is_active("orders") and products:
        from apps.orders.services import create_order

        samples = [
            ("Max Mustermann", "max@example.de", [(products[0], 2)]),
            ("Lena Vogt", "lena@example.de", [(products[1 % len(products)], 1), (products[0], 1)]),
            ("Tom Berg", "tom@example.de", [(products[2 % len(products)], 3)]),
        ]
        for name, email, items in samples:
            try:
                create_order(items=items, name=name, email=email, phone="0151 2345678")
            except Exception:
                pass

    # Aufträge & Angebote (Catering / Vorbestellung)
    if is_active("jobs"):
        from apps.jobs.services import create_job, set_lines

        try:
            j1 = create_job(
                title="Catering Firmenfeier (25 Personen)",
                name="Eventbüro Schmidt",
                email="events@example.de",
                phone="0211 1234567",
                description="Veganes Fingerfood-Buffet für 25 Gäste, inkl. Lieferung & Aufbau.",
            )
            set_lines(
                j1,
                [
                    {
                        "text": "Veganes Fingerfood-Buffet (25 Pers.)",
                        "qty": 1,
                        "unit_price": "375.00",
                    },
                    {"text": "Lieferung & Aufbau", "qty": 1, "unit_price": "60.00"},
                ],
                vat_rate=19,
            )
        except Exception:
            pass
        try:
            j2 = create_job(
                title="Vorbestellung: 50 Falafel-Wraps",
                name="Kanzlei Wolf",
                email="office@example.de",
                description="50 Falafel-Wraps zur Abholung am Freitag, 12 Uhr.",
            )
            set_lines(
                j2,
                [{"text": "Falafel-Wrap (vorbestellt)", "qty": 50, "unit_price": "6.50"}],
                vat_rate=7,
            )
        except Exception:
            pass

    # Tischreservierungen
    if is_active("booking") and refs.get("resources"):
        from datetime import datetime, time, timedelta

        from django.utils import timezone

        from apps.booking.models import Resource
        from apps.booking.services import book

        try:
            res = Resource.objects.get(pk=refs["resources"][0])
            day = timezone.localdate() + timedelta(days=1)
            for hh, who, mail, party in [
                (12, "Familie Klein", "klein@example.de", 4),
                (19, "Sara Hoff", "sara@example.de", 2),
            ]:
                start = timezone.make_aware(datetime.combine(day, time(hh, 0)))
                try:
                    book(
                        res,
                        start=start,
                        end=start + timedelta(hours=1),
                        name=who,
                        email=mail,
                        party_size=party,
                        auto_confirm=True,
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # Event-Tickets
    if is_active("events") and refs.get("events"):
        from apps.events.models import Event
        from apps.events.services import book_ticket

        try:
            ev = Event.objects.get(pk=refs["events"][0])
            for who, mail, qty in [
                ("Nina Roth", "nina@example.de", 2),
                ("Paul Adam", "paul@example.de", 1),
            ]:
                try:
                    book_ticket(ev, name=who, email=mail, quantity=qty, auto_confirm=True)
                except Exception:
                    pass
        except Exception:
            pass

    # Übernachtungen (stays)
    if is_active("stays"):
        from datetime import timedelta

        from django.utils import timezone

        from apps.stays.models import StayUnit
        from apps.stays.services import book_stay

        units = list(StayUnit.objects.filter(is_active=True).order_by("id"))
        if units:
            today = timezone.localdate()
            samples = [
                (units[0], 5, 3, "Anna Berg", "anna@example.de", 2),
                (units[min(1, len(units) - 1)], 20, 5, "Familie Lang", "lang@example.de", 4),
            ]
            for unit, in_days, nights, who, mail, guests in samples:
                arrival = today + timedelta(days=in_days)
                try:
                    book_stay(
                        unit,
                        arrival=arrival,
                        departure=arrival + timedelta(days=nights),
                        name=who,
                        email=mail,
                        guests=guests,
                        auto_confirm=True,
                    )
                except Exception:
                    pass
