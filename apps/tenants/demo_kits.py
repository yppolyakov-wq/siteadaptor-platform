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
    # Юниты размещения: (name, type, qty, price_eur, guests) ИЛИ богатый dict
    #   {name, type, qty, price, guests, min_nights, description, photos:[kw,…]}.
    stay_units: list = field(default_factory=list)
    # События: (title, in_days, capacity, price_eur) ИЛИ dict с богатой спецификацией
    #   {title, in_days, hour, duration_days|duration_hours, capacity, price,
    #    description, location, program:[...], questions:[...]}.
    events: list = field(default_factory=list)
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
    # Богатая спецификация акций всех типов (вместо авто-скидок). Список dict'ов:
    #   {title, desc, product (индекс в created_products|None), type
    #    percent|price|reservation|surprise, percent, new_price, compare_at,
    #    available_quantity, countdown(bool), recurrence(daily|weekly), group,
    #    ends_in_days}. Пусто → авто-скидки (как раньше).
    promotions_spec: list = field(default_factory=list)
    # Ваучеры/промокоды: {code, label, percent|cents, min_order(eur), max_uses}.
    vouchers: list = field(default_factory=list)
    storefront_root: str = "home"  # S4: стартовая страница (home или ключ архетипа)
    # Поддомен демо-тенанта (slug). Пусто → «<key>-demo». Pranasy → «pranasy».
    subdomain: str = ""
    # Наполнить кабинет примерами транзакций (заказы/заявки/брони/билеты) по
    # активным архетипам — чтобы демо было «как настоящее». Адреса @example.de.
    seed_records: bool = False
    # Тематические заявки/сметы (jobs) для seed_records: список dict'ов
    #   {title, name, email, phone?, description, lines:[{text,qty,unit_price}], vat_rate}.
    # Пусто → дефолтные Catering-заявки (ресторан). Werkstatt → Fahrzeug-Angebote.
    job_samples: list = field(default_factory=list)
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


# Анкета участника ретрита (LMIV/безопасность/уровень) — общая для событий.
_RETREAT_QUESTIONS = [
    "Ernährung (vegan / vegetarisch / alles)",
    "Yoga-Erfahrung (Anfänger / Mittel / Fortgeschritten)",
    "Notfallkontakt (Name & Telefon)",
]

# Развёрнутый «ретрит-лендинг» (Event.details) — демо. Переиспользуется ретрит-
# китом и Pranasy; «photo» у hosts — ключ для тематичного демо-фото (см. sed в
# _seed_kit_modules). Полная структура — apps/events/details.py.
_RETREAT_LANDING = {
    "promise": "Drei Tage Yoga, Stille und Natur — Auftanken, durchatmen, zu dir zurückkehren.",
    "for_whom": [
        "du dem Stadttrubel entfliehen willst",
        "du Müdigkeit und Stress spürst",
        "du Yoga und Meditation ausprobieren möchtest",
        "du einen ruhigen Ort suchst",
        "du das Wochenende in der Natur verbringen willst",
        "du allein anreist und Gleichgesinnte kennenlernen möchtest",
    ],
    "idea": "Kein Sportcamp und keine laute Party. Ein sanfter Raum zum Erholen — "
    "langsamer werden, in der Natur sein, Yoga, Atem und Meditation üben und zu sich finden.",
    "includes": [
        ("Yoga", "Sanfte Praxis morgens und abends."),
        ("Meditation", "Einfache Techniken für innere Ruhe."),
        ("Atemübungen", "Entspannung, Fokus, Regeneration."),
        ("Natur", "Spaziergänge, See, Wald, Lagerfeuer."),
        ("Verpflegung", "Vegane & vegetarische Küche."),
        ("Kreativität", "Arts, Mandalas, Musik, Tanz."),
        ("Gemeinschaft", "Kennenlern-Kreis, Abendgespräche."),
    ],
    "venue": "Seminarhaus am Waldrand, ca. 30 Min. von Köln (NRW). Mit dem Auto über die A4 "
    "(kostenlose Parkplätze) oder mit Bahn + Abholung ab Bahnhof. Großer Praxisraum, "
    "Garten, direkter Zugang zu See und Wald.",
    "accommodation": [
        "Einzelzimmer (Aufpreis)",
        "Doppelzimmer",
        "Gemeinschaftszimmer",
        "Bettwäsche & Handtücher inklusive",
        "Geteilte Bäder & Duschen",
    ],
    "food": "Drei vegane/vegetarische Mahlzeiten pro Tag aus regionalen Zutaten, plus Tee & "
    "Wasser. Allergien und Unverträglichkeiten berücksichtigen wir gern — einfach bei der "
    "Anmeldung angeben.",
    "hosts": [
        ("Mara Lind", "Retreatleitung & Yogalehrerin", "yoga,teacher,woman"),
        ("Felix Sturm", "Achtsamkeits-Coach", "meditation,man"),
    ],
    "price_includes": [
        "Unterkunft (2 Nächte)",
        "Alle Mahlzeiten",
        "Alle Praktiken & Mastery-Sessions",
        "Materialien",
    ],
    "price_excludes": ["Anreise", "persönliche Ausgaben", "Zusatzleistungen"],
    "price_note": "Frühbucher bis 30 Tage vorher 260 € · danach 290 €. Ratenzahlung auf "
    "Anfrage möglich.",
    "bring": [
        "bequeme Kleidung",
        "Yogamatte",
        "warme Decke",
        "Trinkflasche",
        "warme Sachen für abends",
        "Badesachen (See)",
        "Taschenlampe",
        "persönliche Hygieneartikel",
    ],
    "faq": [
        ("Für Anfänger geeignet?", "Ja — alle Level sind willkommen, keine Vorerfahrung nötig."),
        ("Kann ich allein kommen?", "Klar, viele reisen allein an — der Kreis verbindet schnell."),
        ("Kann ich mit Kindern kommen?", "Dieses Retreat ist für Erwachsene gedacht."),
        (
            "Was, wenn das Wetter schlecht ist?",
            "Wir haben einen großen Innenraum — es findet statt.",
        ),
        ("Wie komme ich hin?", "Auto (Parkplätze) oder Bahn + Abholung ab Bahnhof."),
        ("Kann ich in Raten zahlen?", "Ja, Ratenzahlung ist auf Anfrage möglich."),
        ("Gibt es Dusche und WC?", "Ja, geteilte Bäder und Duschen sind vorhanden."),
        ("Sind Haustiere erlaubt?", "Leider nein — aus Rücksicht auf alle Teilnehmenden."),
    ],
    "testimonials": [
        ("Johanna P.", "Köln", "Zwei Tage, die mich geerdet haben. Ich komme wieder."),
        ("Daniel R.", "Düsseldorf", "Kleine Gruppe, viel Raum, herzliche Begleitung."),
        ("Sandra K.", "Bonn", "Genau die Pause, die ich gebraucht habe."),
    ],
}
_RETREAT_PHOTOS = ["yoga,forest", "meditation,nature", "lake,forest", "campfire,night"]

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
    seed_records=True,  # наполнить кабинет (заказы/кейтеринг/брони/билеты)
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
        {
            "title": "Sommer-Retreat: Plant-Based Weekend",
            "in_days": 40,
            "hour": 16,
            "duration_days": 2,
            "capacity": 15,
            "price": "129",
            "location": "Seminarhaus am Waldrand, NRW (ca. 30 Min. von Köln)",
            "description": "Ein Wochenende voller pflanzlicher Küche, Yoga und Natur — "
            "kochen, entspannen, auftanken.",
            "program": [
                "Fr 16:00 — Ankommen & gemeinsames Abendessen",
                "Sa — Yoga · Plant-Based-Kochworkshop · Waldspaziergang · Lagerfeuer",
                "So — Morgen-Yoga · Brunch · Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["vegan,food", "yoga,forest", "campfire,night", "cooking,class"],
            "details": _RETREAT_LANDING,
        },
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
        {
            "name": "Doppelzimmer Seeblick",
            "type": "room",
            "qty": 4,
            "price": "89",
            "guests": 2,
            "description": "Helles Doppelzimmer mit direktem Blick auf den See, "
            "französischem Balkon, Queensize-Bett, Smart-TV und modernem Bad mit Regendusche. "
            "Inklusive Frühstücksbuffet.",
            "photos": ["hotel,room", "hotel,bed", "lake,view"],
        },
        {
            "name": "Einzelzimmer Komfort",
            "type": "room",
            "qty": 3,
            "price": "69",
            "guests": 1,
            "description": "Gemütliches Einzelzimmer mit Boxspringbett, Schreibtisch und "
            "schnellem WLAN — ideal für Geschäftsreisende. Inklusive Frühstück.",
            "photos": ["hotel,single,room", "hotel,bathroom"],
        },
        {
            "name": "Familienzimmer",
            "type": "room",
            "qty": 2,
            "price": "129",
            "guests": 4,
            "min_nights": 2,
            "description": "Großzügiges Familienzimmer mit Doppelbett und zwei Einzelbetten, "
            "Sitzecke und extra Stauraum. Platz für die ganze Familie.",
            "photos": ["family,hotel,room", "hotel,interior", "kids,room"],
        },
        {
            "name": "Ferienwohnung am Garten",
            "type": "apartment",
            "qty": 1,
            "price": "149",
            "guests": 4,
            "min_nights": 3,
            "description": "Komplett ausgestattete Ferienwohnung (55 m²) mit eigener Küche, "
            "Wohnzimmer, Schlafzimmer und Terrasse zum Garten. Perfekt für längere Aufenthalte.",
            "photos": ["apartment,living", "apartment,kitchen", "garden,terrace"],
        },
    ],
)

AKTIONSMARKT_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {
                "label": "Aktionen",
                "type": "group",
                "children": [
                    {"label": "Wochenangebote", "type": "promo_group", "target": "Wochenangebote"},
                    {"label": "Dauertiefpreis", "type": "promo_group", "target": "Dauertiefpreis"},
                    {"label": "Räumung", "type": "promo_group", "target": "Räumung"},
                    {
                        "label": "Anti-Food-Waste",
                        "type": "promo_group",
                        "target": "Anti-Food-Waste",
                    },
                ],
            },
            {"label": "Sortiment", "type": "archetype", "target": "catalog"},
            {"label": "Treue", "type": "archetype", "target": "loyalty"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Aktionen", "type": "anchor", "target": "aktionen", "icon": "🔥"},
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🛒"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
            {"label": "Treue", "type": "archetype", "target": "loyalty", "icon": "💝"},
        ],
    },
}

AKTIONSMARKT = DemoKit(
    key="aktionsmarkt",
    label="Aktionsmarkt Sparfuchs",
    business_type="grocery",
    subdomain="aktionsmarkt",
    accent="#dc2626",  # Sale-Rot
    hero_image_kw="supermarket,sale",
    hero_title="Aktionsmarkt Sparfuchs",
    hero_text="Jede Woche neue Angebote — sparen bei allem, was Sie täglich brauchen.",
    about_title="Über den Aktionsmarkt",
    about_text="Beim Aktionsmarkt Sparfuchs dreht sich alles um gute Angebote: "
    "Wochenangebote, Dauertiefpreise, Räumungsaktionen und gerettete Lebensmittel als "
    "Überraschungstüten. Hier sehen Sie alle Aktionsarten, die unser Shop nutzen kann — "
    "von Prozent-Rabatten über Festpreise bis zu limitierten und wiederkehrenden Aktionen.",
    nav_style="classic",
    address="Marktstraße 1, 50667 Köln",
    opening_hours_text="Mo–Sa 8:00–20:00",
    opening_hours={d: ("08:00", "20:00") for d in range(6)},
    gallery_kw=["supermarket", "grocery,shelf", "vegetables", "bakery", "shopping,cart", "sale"],
    process=[
        ("Aktionen entdecken", "Stöbern Sie durch Wochenangebote, Räumung und mehr."),
        ("Code & Karte nutzen", "Gutschein-Code im Warenkorb, Stempel bei jedem Einkauf."),
        ("Sparen", "Frische Ware zum besten Preis — jede Woche neu."),
    ],
    testimonials=[
        ("Herr Wagner", "Die Überraschungstüten sind unschlagbar günstig!"),
        ("Frau Demir", "Endlich ein Markt, bei dem man jede Woche wirklich spart."),
    ],
    trust={"since": "2009", "marks": ["Anti-Food-Waste", "Regional", "Faire Preise"]},
    faq=[
        ("Rabatt in %", "Ein fester Prozent-Rabatt auf den Originalpreis — z. B. −20 % auf Äpfel."),
        (
            "Neuer Festpreis",
            "Statt Prozenten ein fixer Aktionspreis, der alte Preis wird durchgestrichen — "
            "z. B. Brot für 0,99 € statt 1,99 €.",
        ),
        (
            "Limitierte Aktion (Reservierung)",
            "Nur eine begrenzte Menge verfügbar («Nur noch X»). Online sichern, bevor sie weg ist.",
        ),
        (
            "Überraschungstüte (Anti-Food-Waste)",
            "Gerettete Lebensmittel als günstige Überraschungstüte — z. B. 5 € statt 15 €.",
        ),
        (
            "Countdown-Aktion",
            "Zeitlich stark begrenzt, mit sichtbarem Countdown bis zum Ende — schnell sein lohnt sich.",
        ),
        (
            "Wiederkehrende Aktionen",
            "Automatisch wiederkehrend, täglich oder wöchentlich — z. B. Brötchen jeden Abend −50 %.",
        ),
        (
            "Gutschein-Codes",
            "Rabatt-Codes für den Warenkorb: WILLKOMMEN10 für −10 %, SOMMER5 für 5 € ab 30 € Einkauf.",
        ),
        (
            "Stempelkarte (Treue)",
            "Bei jedem Einkauf Stempel sammeln — die volle Karte bringt ein Gratis-Brot.",
        ),
        (
            "Aktionsgruppen",
            "Wir bündeln Aktionen in Gruppen: Wochenangebote, Dauertiefpreis, Räumung und "
            "Anti-Food-Waste — filterbar unter «Aktionen».",
        ),
    ],
    cta={
        "title": "Verpassen Sie kein Angebot",
        "text": "Stöbern Sie durch alle aktuellen Aktionen.",
        "button_label": "Zu den Aktionen",
        "button_url": "/aktionen/",
    },
    enable_modules=["orders", "loyalty"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=AKTIONSMARKT_MENUS,
    loyalty={"label": "Sammelkarte", "stamps": 10, "reward": "1× Gratis-Brot"},
    vouchers=[
        {"code": "WILLKOMMEN10", "label": "−10 % für Neukunden", "percent": 10, "max_uses": 200},
        {
            "code": "SOMMER5",
            "label": "5 € Rabatt ab 30 €",
            "cents": 500,
            "min_order": 30,
            "max_uses": 200,
        },
    ],
    promotions_spec=[
        {
            "title": "Äpfel −20 %",
            "product": 0,
            "percent": 20,
            "group": "Wochenangebote",
            "ends_in_days": 7,
            "desc": "Knackige Äpfel aus der Region.",
        },
        {
            "title": "Croissant −30 % – nur heute!",
            "product": 6,
            "percent": 30,
            "countdown": True,
            "ends_in_days": 2,
            "group": "Wochenangebote",
        },
        {
            "title": "Brot zum Festpreis 0,99 €",
            "product": 4,
            "new_price": "0.99",
            "compare_at": "1.99",
            "group": "Dauertiefpreis",
        },
        {
            "title": "Cola Dauertiefpreis 0,79 €",
            "product": 9,
            "new_price": "0.79",
            "group": "Dauertiefpreis",
        },
        {
            "title": "Gemahlener Kaffee −25 % (limitiert)",
            "product": 10,
            "type": "reservation",
            "percent": 25,
            "available_quantity": 10,
            "group": "Wochenangebote",
        },
        {
            "title": "Backwaren-Überraschungstüte 5 € statt 15 €",
            "product": 14,
            "surprise": True,
            "new_price": "5.00",
            "compare_at": "15.00",
            "group": "Anti-Food-Waste",
            "desc": "Geretteten Backwaren ein zweites Leben geben.",
        },
        {
            "title": "Obst & Gemüse-Überraschungstüte 4 € statt 12 €",
            "product": 15,
            "surprise": True,
            "new_price": "4.00",
            "compare_at": "12.00",
            "group": "Anti-Food-Waste",
        },
        {
            "title": "Brötchen am Abend −50 %",
            "product": 5,
            "percent": 50,
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Anti-Food-Waste",
            "desc": "Jeden Abend ab 18 Uhr.",
        },
        {
            "title": "Mineralwasser −15 % (jede Woche)",
            "product": 8,
            "percent": 15,
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Wochenangebote",
        },
        {"title": "Waschmittel −40 % (Räumung)", "product": 13, "percent": 40, "group": "Räumung"},
        {
            "title": "Toilettenpapier −35 % – Countdown",
            "product": 12,
            "percent": 35,
            "countdown": True,
            "ends_in_days": 1,
            "group": "Räumung",
        },
        {
            "title": "Bio-Gemüsekiste −20 % – nur 5 Stück",
            "product": 3,
            "type": "reservation",
            "percent": 20,
            "available_quantity": 5,
            "group": "Wochenangebote",
        },
    ],
    categories=[
        (
            "Obst & Gemüse",
            "obst-gemuese",
            [
                _p("Äpfel 1 kg", "2.49", "Knackig und regional.", "apples"),
                _p("Bananen 1 kg", "1.79", "Fair gehandelt.", "bananas"),
                _p("Tomaten 500 g", "2.99", "Sonnengereift.", "tomatoes"),
                _p("Bio-Gemüsekiste", "24.90", "Bunte Auswahl der Saison.", "vegetable,box"),
            ],
        ),
        (
            "Backwaren",
            "backwaren",
            [
                _p(
                    "Bauernbrot 750 g",
                    "1.99",
                    "Täglich frisch gebacken.",
                    "bread",
                    allergens=["gluten"],
                ),
                _p(
                    "Brötchen 6er",
                    "0.60",
                    "Knusprig und frisch.",
                    "bread,rolls",
                    allergens=["gluten"],
                ),
                _p(
                    "Croissant",
                    "1.50",
                    "Buttrig und zart.",
                    "croissant",
                    allergens=["gluten", "milch"],
                ),
            ],
        ),
        (
            "Getränke",
            "getraenke",
            [
                _p("Orangensaft 1 L", "2.49", "100 % Direktsaft.", "orange,juice"),
                _p("Mineralwasser 1,5 L", "0.79", "Spritzig oder still.", "water,bottle"),
                _p("Cola 1,5 L", "1.49", "Eisgekühlt am besten.", "cola,bottle"),
                _p("Gemahlener Kaffee 500 g", "6.90", "Kräftige Röstung.", "coffee,ground"),
            ],
        ),
        (
            "Haushalt",
            "haushalt",
            [
                _p("Spülmittel 500 ml", "1.99", "Fettlöser-Power.", "dish,soap"),
                _p("Toilettenpapier 10er", "4.99", "Weich und ergiebig.", "toilet,paper"),
                _p("Waschmittel 2 kg", "8.99", "Für 40 Wäschen.", "laundry,detergent"),
            ],
        ),
        (
            "Überraschungstüten",
            "ueberraschungstueten",
            [
                _p("Backwaren-Tüte", "15.00", "Wert ca. 15 € — Anti-Food-Waste.", "bakery,bag"),
                _p(
                    "Obst & Gemüse-Tüte", "12.00", "Wert ca. 12 € — Anti-Food-Waste.", "grocery,bag"
                ),
            ],
        ),
    ],
)

FRISEUR_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Termin", "type": "archetype", "target": "booking"},
            {"label": "Produkte", "type": "archetype", "target": "catalog"},
            {"label": "Treue", "type": "archetype", "target": "loyalty"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Termin", "type": "archetype", "target": "booking", "icon": "✂️"},
            {"label": "Produkte", "type": "archetype", "target": "catalog", "icon": "🛍"},
            {"label": "Treue", "type": "archetype", "target": "loyalty", "icon": "💝"},
        ],
    },
}

FRISEUR = DemoKit(
    key="friseur",
    label="Salon Schöngut",
    business_type="other",
    subdomain="friseur",
    accent="#9333ea",  # Violett
    hero_image_kw="hair,salon",
    hero_title="Salon Schöngut",
    hero_text="Ihr Friseur in der Altstadt — Schnitt, Farbe und Styling von Profis. "
    "Termin in 30 Sekunden online buchen.",
    about_title="Über den Salon",
    about_text="Seit 2012 verwöhnen wir Sie mit modernen Schnitten, schonenden Farben und "
    "ehrlicher Beratung. Buchen Sie Ihren Wunschtermin bequem online.",
    nav_style="centered",
    address="Altstadtgasse 7, 79098 Freiburg",
    opening_hours_text="Di–Sa 9:00–18:00",
    opening_hours={d: ("09:00", "18:00") for d in range(1, 6)},
    gallery_kw=["hairdresser", "haircut", "hair,color", "salon,interior", "barber", "hairstyle"],
    faq=[
        (
            "Wie buche ich einen Termin?",
            "Über «Termin» wählen Sie Leistung, Tag und Uhrzeit online.",
        ),
        (
            "Kann ich eine Leistung auswählen?",
            "Ja — jede Leistung hat eine feste Dauer und einen Preis.",
        ),
        ("Bekomme ich eine Erinnerung?", "Ja, vor dem Termin erhalten Sie eine Erinnerung."),
        ("Verkauft ihr Pflegeprodukte?", "Ja, hochwertige Produkte gibt es im Salon und online."),
    ],
    testimonials=[
        ("Sandra K.", "Bester Schnitt seit Jahren — und so unkompliziert zu buchen!"),
        ("Michael B.", "Tolle Beratung, faire Preise, immer pünktlich."),
    ],
    process=[
        ("Leistung wählen", "Schnitt, Farbe oder Styling — mit Dauer und Preis."),
        ("Termin buchen", "Freien Slot online sichern."),
        ("Wohlfühlen", "Entspannen und neu aussehen."),
    ],
    team=[
        ("Lea Schöngut", "Inhaberin & Stylistin", "hairstylist,woman"),
        ("Jonas Feld", "Barbier", "barber,man"),
        ("Mia Roth", "Coloristin", "hair,colorist"),
    ],
    trust={"since": "2012", "marks": ["Meisterbetrieb", "Schonende Farben", "Online-Termin"]},
    cta={
        "title": "Zeit für etwas Neues?",
        "text": "Buchen Sie jetzt Ihren Wunschtermin online.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    enable_modules=["booking", "loyalty", "orders"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=FRISEUR_MENUS,
    loyalty={"label": "Treuekarte", "stamps": 10, "reward": "1× Waschen & Föhnen gratis"},
    archetype_covers={
        "booking": {
            "intro": "Wählen Sie Ihre Leistung und buchen Sie einen freien Termin.",
            "hero_kw": "hair,salon",
            "gallery_kw": ["haircut", "hair,color", "hairstyle"],
        },
        "catalog": {
            "intro": "Pflegeprodukte für schönes Haar — auch für zuhause.",
            "hero_kw": "hair,products",
        },
    },
    services=[
        ("Haarschnitt Damen", 45, "39"),
        ("Haarschnitt Herren", 30, "25"),
        ("Waschen & Föhnen", 30, "19"),
        ("Färben", 90, "69"),
        ("Strähnen / Highlights", 120, "89"),
        ("Bart trimmen", 15, "12"),
    ],
    resources=[
        {
            "name": "Stuhl 1",
            "type": "table",
            "capacity": 1,
            "start": "09:00",
            "end": "18:00",
            "slot": 30,
            "weekdays": range(1, 6),
        },
        {
            "name": "Stuhl 2",
            "type": "table",
            "capacity": 1,
            "start": "09:00",
            "end": "18:00",
            "slot": 30,
            "weekdays": range(1, 6),
        },
    ],
    categories=[
        (
            "Pflegeprodukte",
            "pflege",
            [
                _p("Shampoo Repair 250 ml", "12.90", "Für strapaziertes Haar.", "shampoo"),
                _p("Spülung Glanz 250 ml", "12.90", "Für seidigen Glanz.", "hair,conditioner"),
                _p("Haaröl 50 ml", "16.90", "Pflege für Spitzen.", "hair,oil"),
                _p("Hitzeschutz-Spray", "14.90", "Vor dem Föhnen.", "hair,spray"),
            ],
        ),
    ],
)

WERKSTATT_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Termin", "type": "archetype", "target": "booking"},
            {"label": "Kostenvoranschlag", "type": "archetype", "target": "jobs"},
            {"label": "Teile & Zubehör", "type": "archetype", "target": "catalog"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Termin", "type": "archetype", "target": "booking", "icon": "📅"},
            {"label": "Angebot", "type": "archetype", "target": "jobs", "icon": "🧰"},
            {"label": "Teile", "type": "archetype", "target": "catalog", "icon": "🔧"},
        ],
    },
}

WERKSTATT = DemoKit(
    key="werkstatt",
    label="KFZ-Werkstatt Dreyer",
    business_type="other",
    subdomain="werkstatt",
    accent="#1d4ed8",  # Werkstatt-Blau
    hero_image_kw="car,workshop",
    hero_title="KFZ-Werkstatt Dreyer",
    hero_text="Ihre Meisterwerkstatt für alle Marken — Termin online buchen oder "
    "unverbindlichen Kostenvoranschlag anfordern.",
    about_title="Über die Werkstatt",
    about_text="Seit 1995 kümmern wir uns um Ihr Fahrzeug: Inspektion, Reparatur, HU/AU und "
    "mehr — schnell, fair und meisterlich. Termin und Angebot bequem online.",
    nav_style="classic",
    address="Industriestraße 22, 44137 Dortmund",
    opening_hours_text="Mo–Fr 8:00–17:00",
    opening_hours={d: ("08:00", "17:00") for d in range(5)},
    gallery_kw=["car,repair", "mechanic", "car,workshop", "car,engine", "tire,change", "garage"],
    faq=[
        ("Wie buche ich einen Termin?", "Über «Termin» Leistung und freien Slot online wählen."),
        (
            "Was ist ein Kostenvoranschlag?",
            "Über «Kostenvoranschlag» schildern Sie Ihr Anliegen — "
            "Sie erhalten ein unverbindliches Angebot mit Fahrzeugangabe.",
        ),
        ("Repariert ihr alle Marken?", "Ja, wir sind eine markenoffene Meisterwerkstatt."),
        ("Bekomme ich Ersatzteile?", "Originalteile und Zubehör führen wir im Shop."),
    ],
    testimonials=[
        ("Familie Ünal", "Schnell, ehrlich und fair — endlich eine Werkstatt zum Vertrauen."),
        ("Peter S.", "Kostenvoranschlag online angefragt, Termin gebucht, alles top."),
    ],
    process=[
        ("Anliegen schildern", "Termin buchen oder Kostenvoranschlag mit Fahrzeug anfragen."),
        ("Angebot erhalten", "Transparenter Preis, bevor wir loslegen."),
        ("Fahren", "Fertig — sicher zurück auf die Straße."),
    ],
    team=[
        ("Frank Dreyer", "Werkstattmeister", "mechanic,man"),
        ("Sven Klar", "KFZ-Techniker", "car,mechanic"),
    ],
    trust={"since": "1995", "marks": ["Meisterbetrieb", "Markenoffen", "HU/AU vor Ort"]},
    cta={
        "title": "Klappert, leuchtet oder zieht?",
        "text": "Buchen Sie einen Termin oder fordern Sie ein Angebot an.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    enable_modules=["booking", "jobs", "orders"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=WERKSTATT_MENUS,
    job_samples=[
        {
            "title": "Kostenvoranschlag: Inspektion + Bremsen vorne",
            "name": "Markus Vogel",
            "email": "vogel@example.de",
            "phone": "0231 1234567",
            "vehicle": "VW Golf VII · DO-MV 1234",
            "description": "Inspektion fällig, Bremsen vorne quietschen. Bitte Angebot.",
            "lines": [
                {"text": "Inspektion lt. Hersteller", "qty": 1, "unit_price": "149.00"},
                {"text": "Bremsbeläge vorne (Teile)", "qty": 1, "unit_price": "44.90"},
                {"text": "Arbeitslohn Bremsen (Std.)", "qty": 1.5, "unit_price": "65.00"},
            ],
            "vat_rate": 19,
        },
        {
            "title": "Kostenvoranschlag: Klimaanlage prüfen & warten",
            "name": "Sabine Koch",
            "email": "koch@example.de",
            "vehicle": "BMW 320d · DO-SK 88",
            "description": "Klima kühlt nicht mehr richtig. Bitte prüfen und warten.",
            "lines": [
                {"text": "Klima-Service inkl. Kältemittel", "qty": 1, "unit_price": "119.00"},
                {"text": "Innenraumfilter (Teile)", "qty": 1, "unit_price": "24.90"},
            ],
            "vat_rate": 19,
        },
    ],
    archetype_covers={
        "booking": {
            "intro": "Wählen Sie eine Leistung und buchen Sie einen freien Werkstatt-Termin.",
            "hero_kw": "car,workshop",
            "gallery_kw": ["car,repair", "tire,change", "car,engine"],
        },
        "jobs": {
            "intro": "Schildern Sie Ihr Anliegen mit Fahrzeug — Sie erhalten ein unverbindliches "
            "Angebot (Kostenvoranschlag).",
            "hero_kw": "mechanic",
        },
        "catalog": {
            "intro": "Ersatzteile und Zubehör — Originalqualität.",
            "hero_kw": "car,parts",
        },
    },
    services=[
        ("Ölwechsel", 30, "49"),
        ("Inspektion", 120, "149"),
        ("Reifenwechsel", 45, "39"),
        ("HU/AU (TÜV)", 60, "89"),
        ("Bremsen-Check", 30, "0"),
    ],
    resources=[
        {
            "name": "Hebebühne 1",
            "type": "table",
            "capacity": 1,
            "start": "08:00",
            "end": "17:00",
            "slot": 30,
            "weekdays": range(0, 5),
        },
        {
            "name": "Hebebühne 2",
            "type": "table",
            "capacity": 1,
            "start": "08:00",
            "end": "17:00",
            "slot": 30,
            "weekdays": range(0, 5),
        },
    ],
    categories=[
        (
            "Teile & Zubehör",
            "teile",
            [
                _p("Motoröl 5W-30 5 L", "39.90", "Vollsynthetisch.", "motor,oil"),
                _p("Wischerblätter-Set", "19.90", "Für klare Sicht.", "wiper,blade"),
                _p("Bremsbeläge vorne", "44.90", "Markenqualität.", "brake,pad"),
                _p("Luftfilter", "16.90", "Passend für viele Modelle.", "air,filter"),
                _p("Scheibenfrostschutz 3 L", "8.90", "Bis −20 °C.", "antifreeze"),
            ],
        ),
    ],
)

RETREAT_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Events", "type": "archetype", "target": "events"},
            {"label": "Einzelsitzung", "type": "archetype", "target": "booking"},
            {"label": "Shop", "type": "archetype", "target": "catalog"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Events", "type": "archetype", "target": "events", "icon": "🎫"},
            {"label": "Sitzung", "type": "archetype", "target": "booking", "icon": "🧘"},
            {"label": "Shop", "type": "archetype", "target": "catalog", "icon": "🛍"},
        ],
    },
}

RETREAT = DemoKit(
    key="retreat",
    label="Waldlicht Retreat",
    business_type="other",
    subdomain="retreat",
    accent="#15803d",  # Wald-Grün
    hero_image_kw="yoga,forest",
    hero_title="Waldlicht Retreat",
    hero_text="Achtsamkeit, Yoga und Natur — Wochenend-Retreats, Tagesworkshops und "
    "Abende, die guttun. Sichern Sie sich Ihren Platz online.",
    about_title="Über uns",
    about_text="Seit 2016 schaffen wir Räume zum Durchatmen — am Waldrand bei Freiburg. "
    "Kleine Gruppen, erfahrene Begleitung, ehrliche Achtsamkeit ohne Esoterik-Kitsch.",
    nav_style="centered",
    address="Am Waldrand 3, 79117 Freiburg",
    opening_hours_text="Büro: Mo–Fr 10:00–16:00",
    opening_hours={d: ("10:00", "16:00") for d in range(5)},
    gallery_kw=[
        "yoga,nature",
        "meditation",
        "forest,path",
        "retreat,group",
        "candles",
        "tea,ceremony",
    ],
    faq=[
        (
            "Wie buche ich einen Platz?",
            "Über «Events» wählen Sie ein Datum und buchen direkt online.",
        ),
        (
            "Was ist im Preis enthalten?",
            "Programm, Begleitung und Materialien; Verpflegung je nach Event.",
        ),
        ("Brauche ich Vorerfahrung?", "Nein — unsere Events sind für alle Levels geeignet."),
        (
            "Kann ich eine Einzelsitzung buchen?",
            "Ja, über «Einzelsitzung» buchen Sie einen 1:1-Termin.",
        ),
    ],
    testimonials=[
        ("Johanna P.", "Zwei Tage, die mich geerdet haben. Ich komme wieder."),
        ("Daniel R.", "Kleine Gruppe, viel Raum, herzliche Begleitung. Sehr empfehlenswert."),
    ],
    process=[
        ("Event wählen", "Wochenend-Retreat, Tagesworkshop oder Abend — mit Programm und Preis."),
        ("Platz buchen", "Online buchen, kurze Anmelde-Anfrage ausfüllen."),
        ("Ankommen", "Loslassen, auftanken, sich selbst begegnen."),
    ],
    team=[
        ("Mara Lind", "Retreatleitung & Yogalehrerin", "yoga,teacher,woman"),
        ("Felix Sturm", "Achtsamkeits-Coach", "meditation,man"),
    ],
    trust={"since": "2016", "marks": ["Kleine Gruppen", "Zertifizierte Leitung", "Naturnah"]},
    cta={
        "title": "Zeit für dich.",
        "text": "Finde dein nächstes Retreat und sichere dir einen Platz.",
        "button_label": "Events ansehen",
        "button_url": "/veranstaltung/",
    },
    enable_modules=["events", "booking", "orders"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=RETREAT_MENUS,
    archetype_covers={
        "events": {
            "intro": "Wochenend-Retreats, Tagesworkshops und Achtsamkeits-Abende — mit Programm.",
            "hero_kw": "yoga,forest",
            "gallery_kw": ["meditation", "retreat,group", "forest,path"],
        },
        "booking": {
            "intro": "Lieber 1:1? Buchen Sie eine Einzelsitzung mit fester Dauer und Preis.",
            "hero_kw": "yoga,studio",
        },
        "catalog": {
            "intro": "Kleines Sortiment für deine Praxis zuhause.",
            "hero_kw": "yoga,products",
        },
    },
    events=[
        {
            "title": "Waldlicht Wochenend-Retreat",
            "in_days": 21,
            "hour": 16,
            "duration_days": 2,
            "capacity": 18,
            "price": "290",
            "location": "Am Waldrand 3, Freiburg",
            "description": "Zwei Tage Yoga, Meditation und Waldspaziergänge in kleiner Gruppe. "
            "Inklusive Programm, Begleitung und Tee-Pausen.",
            "program": [
                "Fr 16:00 — Ankommen & Auftakt-Meditation",
                "Sa 08:00 — Morgen-Yoga · 10:00 Achtsamkeitswanderung · 16:00 Klangschalen",
                "So 09:00 — Yin-Yoga · 12:00 Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": _RETREAT_PHOTOS,
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Yoga & Achtsamkeit — Tagesworkshop",
            "in_days": 10,
            "hour": 10,
            "duration_hours": 6,
            "capacity": 25,
            "price": "89",
            "description": "Ein Tag zum Auftanken: Yoga, Atemübungen und Achtsamkeit für alle Levels.",
            "program": [
                "10:00 — Hatha-Yoga",
                "12:30 — Pause & veganer Imbiss",
                "14:00 — Atem & Meditation · 16:00 Ausklang",
            ],
            "questions": _RETREAT_QUESTIONS,
        },
        {
            "title": "Klangschalen-Meditation am Abend",
            "in_days": 7,
            "hour": 19,
            "duration_hours": 2,
            "capacity": 30,
            "price": "25",
            "description": "Tiefenentspannung mit Klangschalen — ein ruhiger Abend zum Loslassen.",
        },
        {
            "title": "Sommer-Festival der Achtsamkeit",
            "in_days": 45,
            "hour": 11,
            "duration_hours": 8,
            "capacity": 0,  # без лимита мест
            "price": "15",
            "location": "Stadtpark Freiburg",
            "description": "Ein Tag voller Workshops, Live-Musik und Ständen rund um Achtsamkeit.",
            "program": [
                "11:00 — Eröffnung & Mitmach-Yoga",
                "13:00 — Workshops (Atem, Journaling, Klang)",
                "18:00 — Live-Musik & Ausklang",
            ],
        },
    ],
    services=[
        ("Einzel-Yogastunde (1:1)", 60, "55"),
        ("Achtsamkeits-Coaching", 60, "75"),
        ("Schnupperstunde", 30, "0"),
    ],
    resources=[
        {
            "name": "Studio",
            "type": "table",
            "capacity": 1,
            "start": "10:00",
            "end": "18:00",
            "slot": 30,
            "weekdays": range(0, 5),
        },
    ],
    categories=[
        (
            "Shop",
            "shop",
            [
                _p(
                    "Yogamatte Natur",
                    "49.00",
                    "Rutschfest, aus Naturkautschuk.",
                    "yoga,mat",
                    variants=[("Standard", "49.00"), ("Extra dick", "59.00")],
                ),
                _p("Bio-Kräutertee 100 g", "9.90", "Beruhigende Mischung.", "herbal,tea"),
                _p("Räucherstäbchen-Set", "12.90", "Für die Praxis zuhause.", "incense"),
                _p("Achtsamkeits-Journal", "16.90", "Geführtes Tagebuch.", "journal,book"),
            ],
        ),
    ],
)

KITS = {
    RESTAURANT.key: RESTAURANT,
    PRANASY.key: PRANASY,
    HOTEL.key: HOTEL,
    AKTIONSMARKT.key: AKTIONSMARKT,
    FRISEUR.key: FRISEUR,
    WERKSTATT.key: WERKSTATT,
    RETREAT.key: RETREAT,
}


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

    # Акции.
    from apps.promotions.models import Promotion

    now = timezone.now()
    if kit.promotions_spec:
        # Богатая спецификация — все типы/виды акций (showcase).
        for spec in kit.promotions_spec:
            idx = spec.get("product")
            product = (
                created_products[idx]
                if isinstance(idx, int) and idx < len(created_products)
                else None
            )
            fields = {
                "title": {"de": spec["title"]},
                "description": {"de": spec.get("desc", "")},
                "product": product,
                "promo_type": Promotion.RESERVATION
                if spec.get("type") == "reservation"
                else Promotion.DISCOUNT,
                "status": "active",
                "starts_at": now,
                "ends_at": now + timedelta(days=spec.get("ends_in_days", 14)),
                "group": spec.get("group", ""),
                "show_countdown": bool(spec.get("countdown")),
                "is_surprise": bool(spec.get("surprise")),
                "recurrence": spec.get("recurrence", ""),
                "metadata": {"demo": True},
            }
            if spec.get("percent"):
                fields["discount_percent"] = spec["percent"]
            if spec.get("new_price"):
                fields["price_override"] = Decimal(str(spec["new_price"]))
            if spec.get("compare_at"):
                fields["compare_at_price"] = Decimal(str(spec["compare_at"]))
            if spec.get("type") == "reservation":
                fields["available_quantity"] = spec.get("available_quantity", 10)
            if spec.get("image"):
                lock += 1
                fields["images"] = [_image_ref(spec["image"], lock, spec["title"])]
            promo = Promotion.objects.create(**fields)
            refs["promotions"].append(str(promo.pk))
    else:
        # Авто-скидки на первые товары (как раньше).
        discounts = [20, 15, 25, 30]
        if kit.group_promos_by_category:
            rest = [p for p in created_products if p not in category_firsts]
            promo_products = (category_firsts + rest)[: max(kit.promo_count, len(category_firsts))]
        else:
            promo_products = created_products[: kit.promo_count]
        for i, product in enumerate(promo_products):
            d = discounts[i % len(discounts)]
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

    # Ваучеры/промокоды (фикс-коды, чтобы описание ссылалось на них).
    if kit.vouchers:
        from apps.promotions.models import Voucher

        for v in kit.vouchers:
            Voucher.objects.get_or_create(
                code=v["code"],
                defaults={
                    "label": v.get("label", ""),
                    "discount_percent": v.get("percent"),
                    "discount_cents": v.get("cents"),
                    "min_order_cents": int(Decimal(str(v.get("min_order", 0))) * 100),
                    "max_uses": v.get("max_uses", 100),
                    "is_active": True,
                },
            )

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
        for idx, spec in enumerate(kit.stay_units):
            # Краткий кортеж (name, type, qty, price, guests) ИЛИ богатый dict
            # (с описанием и фото номера).
            if isinstance(spec, dict):
                imgs = [
                    _image_ref(kw, 8400 + idx * 10 + j, spec["name"])
                    for j, kw in enumerate(spec.get("photos", []))
                ]
                for j, ref in enumerate(imgs):
                    ref["is_primary"] = j == 0
                    ref["sort_order"] = j
                unit = StayUnit.objects.create(
                    name=spec["name"],
                    type=spec.get("type", "room"),
                    description=spec.get("description", ""),
                    quantity=spec.get("qty", 1),
                    price_cents=int(Decimal(str(spec.get("price", "0"))) * 100),
                    min_nights=spec.get("min_nights", 1),
                    max_guests=spec.get("guests", 2),
                    images=imgs,
                    is_active=True,
                )
            else:
                name, utype, qty, price, guests = spec
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
        for idx, spec in enumerate(kit.events):
            # Поддерживаем и краткий кортеж (title, in_days, capacity, price), и
            # богатый dict (с Programm/анкетой/описанием/длительностью).
            if isinstance(spec, dict):
                in_days = spec.get("in_days", 7)
                hour = spec.get("hour", 10)
                starts = (now + timedelta(days=in_days)).replace(
                    hour=hour, minute=0, second=0, microsecond=0
                )
                duration_days = spec.get("duration_days")
                duration_hours = spec.get("duration_hours")
                ends = None
                if duration_days:
                    ends = starts + timedelta(days=duration_days)
                elif duration_hours:
                    ends = starts + timedelta(hours=duration_hours)
                imgs = [
                    _image_ref(kw, 9200 + idx * 10 + j, spec["title"])
                    for j, kw in enumerate(spec.get("photos", []))
                ]
                for j, ref in enumerate(imgs):
                    ref["is_primary"] = j == 0
                    ref["sort_order"] = j
                # «Ретрит-лендинг»: hosts.photo как тематичное демо-фото по ключу.
                from apps.events import details as _evdetails

                raw_details = dict(spec.get("details") or {})
                hosts = []
                for h in raw_details.get("hosts", []):
                    if isinstance(h, (list, tuple)):
                        name, role, photo = (list(h) + ["", "", ""])[:3]
                    else:
                        name, role, photo = h.get("name"), h.get("role"), h.get("photo")
                    if photo and not str(photo).startswith("http"):
                        photo = demo_image(photo, w=200, h=200, lock=9300 + len(hosts))
                    hosts.append({"name": name or "", "role": role or "", "photo": photo or ""})
                if hosts:
                    raw_details["hosts"] = hosts
                event = Event.objects.create(
                    title=spec["title"],
                    description=spec.get("description", ""),
                    location=spec.get("location", ""),
                    starts_at=starts,
                    ends_at=ends,
                    capacity=spec.get("capacity", 0),
                    price_cents=int(Decimal(str(spec.get("price", "0"))) * 100),
                    questions=list(spec.get("questions", [])),
                    program=list(spec.get("program", [])),
                    images=imgs,
                    details=_evdetails.normalize(raw_details),
                    status=Event.STATUS_PUBLISHED,
                )
            else:
                title, in_days, capacity, price = spec
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

    # Aufträge & Angebote (Catering / Vorbestellung по умолчанию; kit.job_samples
    # переопределяет тематически — напр. Fahrzeug-Angebote у Werkstatt).
    if is_active("jobs"):
        from apps.jobs.services import create_job, set_lines

        jobs = kit.job_samples or [
            {
                "title": "Catering Firmenfeier (25 Personen)",
                "name": "Eventbüro Schmidt",
                "email": "events@example.de",
                "phone": "0211 1234567",
                "description": "Veganes Fingerfood-Buffet für 25 Gäste, inkl. Lieferung & Aufbau.",
                "lines": [
                    {
                        "text": "Veganes Fingerfood-Buffet (25 Pers.)",
                        "qty": 1,
                        "unit_price": "375.00",
                    },
                    {"text": "Lieferung & Aufbau", "qty": 1, "unit_price": "60.00"},
                ],
                "vat_rate": 19,
            },
            {
                "title": "Vorbestellung: 50 Falafel-Wraps",
                "name": "Kanzlei Wolf",
                "email": "office@example.de",
                "description": "50 Falafel-Wraps zur Abholung am Freitag, 12 Uhr.",
                "lines": [{"text": "Falafel-Wrap (vorbestellt)", "qty": 50, "unit_price": "6.50"}],
                "vat_rate": 7,
            },
        ]
        for spec in jobs:
            try:
                job = create_job(
                    title=spec["title"],
                    name=spec["name"],
                    email=spec["email"],
                    phone=spec.get("phone", ""),
                    description=spec.get("description", ""),
                    vehicle=spec.get("vehicle", ""),
                    site_address=spec.get("site_address", ""),
                )
                set_lines(job, spec.get("lines", []), vat_rate=spec.get("vat_rate", 19))
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
