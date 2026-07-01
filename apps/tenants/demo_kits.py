"""Демо-«киты» — полноценные showcase-витрины по вертикалям (M20 demo).

Кит = курируемый набор: раскладка секций + цвет + навигация + hero-баннер с
фото + глубокий каталог (категории, товары с фото/вариантами/аллергенами) +
акции + контент-секции (CTA/отзывы/FAQ/галерея) + услуги/номера/события под тип.
Используется командой ``seed_demo_tenants`` для отдельных демо-тенантов на
субдоменах. Фото — локальный самодостаточный SVG-генератор (PR-IMG,
``apps.tenants.demo_images``): тематичные плейсхолдеры по ключевым словам,
детерминированно по ``lock``, без внешних сервисов (GDPR-чисто, грузятся везде).

Товары помечаются ``metadata={"demo": True}`` (как в apps.tenants.demo) — общая
маркировка для очистки. Категории — со слагом ``demo-…``.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import siteconfig


def demo_image(keyword: str, *, w: int = 800, h: int = 600, lock: int = 1) -> str:
    """Тематичный демо-URL картинки. PR-IMG: локальный самодостаточный SVG-генератор
    (без внешних сервисов — GDPR-чисто, грузится в любых сетях), детерминирован по
    keyword+lock. Отдаёт storefront-вьюха `demo-image` (apps.tenants.demo_images)."""
    from . import demo_images

    return demo_images.demo_image_url(keyword.strip(), w=w, h=h, lock=lock)


def _image_ref(keyword: str, lock: int, alt: str) -> dict:
    """FileRef-конверт для Product.images / галереи из внешнего фото."""
    return {
        "id": f"demo-{lock}",
        "url": demo_image(keyword, lock=lock),
        "alt": {"de": alt},
        "is_primary": True,
        "sort_order": 0,
    }


def _i18n_text(value) -> dict:
    """Привести имя/описание к i18n-дикту {"de":..,"en":..}. Строка → только de
    (одноязычно); dict → отфильтрованные непустые de/en. Для двуязычных китов."""
    if isinstance(value, dict):
        return {loc: v for loc, v in value.items() if loc in ("de", "en") and v}
    return {"de": value or ""}


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
    # A7: кейсы «Vorher / Nachher» — список (before_kw, after_kw, text). Пусто →
    # секции нет. Рендерится интерактивным слайдером (ремесло/санация/студии).
    before_after: list = field(default_factory=list)
    faq: list = field(default_factory=list)
    testimonials: list = field(default_factory=list)
    process: list = field(default_factory=list)  # (title, text) — «как мы работаем»
    team: list = field(default_factory=list)  # (name, role, photo_keyword)
    trust: dict = field(default_factory=dict)  # {"since": "1998", "marks": [...]}
    # A.3 (T-B): полоса доверия под hero — список (icon_token, label). Пусто → секции нет.
    usp: list = field(default_factory=list)
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
    # Тарифы (Rate Plans, H1): список dict {name, percent, surcharge, meal,
    #   cancellation, free_cancel_days, prepayment?, sort, description?}. На тенанта.
    rate_plans: list = field(default_factory=list)
    # Kurtaxe (H9): сбор за взрослого за ночь, € (строка/число). 0/пусто = выключено.
    kurtaxe: str = ""
    # Промокод для брони (H4a): {code, label, percent}. Пусто = нет.
    stay_promo: dict = field(default_factory=dict)
    # Hausordnung (H6): правила проживания, свободный текст. Пусто = нет страницы.
    house_rules: str = ""
    # G4: авто-скидки на проживание (StaySettings) — список правил (несколько на тип):
    #   {"kind": los|early_bird|last_minute, "threshold": int, "percent": int}.
    auto_discounts: list = field(default_factory=list)
    # События: (title, in_days, capacity, price_eur) ИЛИ dict с богатой спецификацией
    #   {title, in_days, hour, duration_days|duration_hours, capacity, price,
    #    description, location, program:[...], questions:[...]}.
    events: list = field(default_factory=list)
    # R3: преподаватели/ведущие (структурная сущность events.Teacher) — (name,
    # title, photo_kw, bio). Засеваются и линкуются ко всем событиям кита.
    teachers: list = field(default_factory=list)
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
    # M20U-2: слайдер баннеров главной. Список dict'ов
    #   {image_kw, title, text, button_label, button_url}. Пусто → одиночный hero_*.
    heroes: list = field(default_factory=list)
    # M20U-7: кастомные заголовки секций главной (key→строка); пусто → дефолты.
    section_titles: dict = field(default_factory=dict)
    # i18n (двуязычная витрина): оверлей переводов site_config, {locale: {<зеркало
    # текстовых полей>}}. Пусто → одноязычно (DE). siteconfig.localize накладывает
    # перед рендером. Пример: {"en": {"hero_title": "...", "faq": [{"q":..,"a":..}],
    # "section_titles": {...}, "heroes": [{"title":..}, ...]}}.
    i18n: dict = field(default_factory=dict)
    # M20U-7 (per-page): пресеты раскладки страниц-листингов (пусто → дефолт страницы).
    #   {"catalog","stay_index","events","related"} → пресет (list/cols2-4/gallery).
    page_layouts: dict = field(default_factory=dict)
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
    # A3/G9b: тарифы Mehrfachkarte (PassPlan) — {label, credits, price(eur),
    #   valid_days, service_index?}. Seed создаёт планы + выдаёт одну карту.
    pass_plans: list = field(default_factory=list)
    # G8/#6: отзывы клиентов (SHARED BusinessReview) — (rating, comment, email).
    # Seed создаёт PortalUser + отзыв + включает секцию «reviews» на витрине.
    reviews_seed: list = field(default_factory=list)
    # A1/A2: отзывы о ТОВАРЕ (TENANT ProductReview) — (product_index, rating, name,
    # email, comment). product_index — индекс в created_products. Seed создаёт
    # опубликованные отзывы напрямую (демо доверенный; верификация — на витрине).
    product_reviews: list = field(default_factory=list)
    # #7 универсальные Extras: (label, price_eur, scope, per_night). Seed создаёт
    # apps.core.Extra — гость отмечает при бронировании (сейчас на stays).
    extras: list = field(default_factory=list)
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
    # A9: режим Kfz-Werkstatt — Anfrage запрашивает структурные данные авто
    # (Kennzeichen/HSN/TSN) + AutoRepair-разметка. Пишется в site_config.jobs_vehicle.
    jobs_vehicle: bool = False
    # A7: зона обслуживания (Handwerker/Werkstatt) — PLZ через запятую + текст. Пусто =
    # не показываем Einzugsgebiet. Пишется в Tenant.service_area_plz/service_area_note.
    service_area_plz: str = ""
    service_area_note: str = ""
    # RT4: записи блога — (title, excerpt, body, cover_kw). Seed создаёт опубликованные
    # BlogPost (events app). Пусто = блога нет.
    blog_posts: list = field(default_factory=list)


# Товар: dict {name, price, desc, img(keyword), variants?, allergens?, modifiers?,
#   badge?, unit?, content?, stock?, gtin?, sku?}.
#   variants — список (label, price) ИЛИ dict {label, price, stock, content, gtin, sku}
#     (R1 варианты; per-variant остаток/Grundpreis/EAN).
#   unit/content — Grundpreis (R2, €/kg|l); stock — остаток (R3); gtin — EAN (A1).
def _p(
    name,
    price,
    desc,
    img,
    variants=None,
    allergens=None,
    modifiers=None,
    badge="",
    unit="",
    content=None,
    stock=None,
    gtin="",
    sku="",
    diets=None,
):
    return {
        "name": name,
        "price": price,
        "desc": desc,
        "img": img,
        "variants": variants or [],
        "allergens": allergens or [],
        "diets": diets or [],  # A4 диет-теги
        "modifiers": modifiers or [],
        "badge": badge,
        "unit": unit,
        "content": content,
        "stock": stock,
        "gtin": gtin,
        "sku": sku,
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
    # R13: отзывы с фото + рейтингом (5-кортеж: name | city | text | photo | rating).
    "testimonials": [
        (
            "Johanna P.",
            "Köln",
            "Zwei Tage, die mich geerdet haben. Ich komme wieder.",
            demo_image("portrait,woman", w=200, h=200, lock=41),
            "5",
        ),
        (
            "Daniel R.",
            "Düsseldorf",
            "Kleine Gruppe, viel Raum, herzliche Begleitung.",
            demo_image("portrait,man", w=200, h=200, lock=42),
            "5",
        ),
        ("Sandra K.", "Bonn", "Genau die Pause, die ich gebraucht habe."),
    ],
    # R13: истории «до/после» (before-URL | after-URL | text).
    "before_after": [
        (
            demo_image("stressed,office", w=400, h=300, lock=51),
            demo_image("calm,yoga", w=400, h=300, lock=52),
            "Von ausgebrannt zu erholt — nach einem Wochenende.",
        ),
    ],
    # R13: значки сертификации (Name | Aussteller | Logo-URL).
    "certifications": [
        ("RYT-500", "Yoga Alliance", demo_image("logo,seal", w=120, h=120, lock=61)),
        ("Ayurveda-Therapeutin", "VEAT e.V.", ""),
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
    usp=[
        ("shipping", "Lieferung ab 15 €"),
        ("clock", "Täglich 11–22 Uhr"),
        ("local", "Frische regionale Zutaten"),
        ("payment", "Bar & Karte"),
    ],
    reviews_seed=[  # G8/#6: отзывы на витрине (блок «reviews» включается автоматически)
        (5, "Bestes Restaurant der Stadt — wir kommen immer wieder!", "rs.schmidt@example.de"),
        (5, "Die Pizza ist ein Traum, der Service top.", "rs.laura@example.de"),
        (4, "Gemütliches Ambiente und frische Pasta — sehr zu empfehlen.", "rs.mehmet@example.de"),
    ],
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
                    diets=["vegan"],  # A4
                ),
                _p(
                    "Caprese",
                    "8.90",
                    "Tomaten, Mozzarella, Basilikum.",
                    "caprese,salad",
                    allergens=["milch"],
                    diets=["vegetarisch", "glutenfrei"],  # A4
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
                    diets=["vegan", "glutenfrei"],  # A4
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
                "label": "Restaurant",
                "type": "category",
                "target": "demo-restaurant",
            },
            {
                "label": "Shop",
                "type": "category",
                "target": "demo-shop",
            },
            {
                "label": "Catering",
                "type": "archetype",
                "target": "jobs",
                "label_i18n": {"en": "Catering"},
            },
            {
                "label": "Retreats",
                "type": "archetype",
                "target": "events",
            },
            {
                "label": "Treue & Aktionen",
                "type": "group",
                "label_i18n": {"en": "Loyalty & Offers"},
                "children": [
                    {
                        "label": "Treue",
                        "type": "archetype",
                        "target": "loyalty",
                        "label_i18n": {"en": "Loyalty"},
                    },
                    {
                        "label": "Aktionen",
                        "type": "promo_group",
                        "target": "Restaurant",
                        "label_i18n": {"en": "Offers"},
                    },
                ],
            },
            {
                "label": "Über uns",
                "type": "page",
                "target": "about",
                "label_i18n": {"en": "About us"},
            },
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Restaurant", "type": "category", "target": "demo-restaurant", "icon": "🍔"},
            {"label": "Shop", "type": "category", "target": "demo-shop", "icon": "🛒"},
            {"label": "Catering", "type": "archetype", "target": "jobs", "icon": "🎉"},
            {"label": "Retreats", "type": "archetype", "target": "events", "icon": "🧘"},
        ],
    },
}

PRANASY = DemoKit(
    key="pranasy",
    label="Pranasy — Vegan & Ayurveda",
    business_type="restaurant",
    subdomain="pranasy",  # → pranasy.<base> (а не pranasy-demo)
    accent="#16a34a",  # frisches Grün
    hero_image_kw="vegan,food",
    hero_title="Pranasy",
    hero_text="100 % pflanzlich & ayurvedisch inspiriert — frische Küche, feiner Shop, "
    "ruhige Retreats.",
    about_title="Über Pranasy",
    about_text="Pranasy steht für eine Küche, die guttut: 100 % pflanzlich, ayurvedisch "
    "inspiriert und mit echten Zutaten. Wir glauben an bewusste, ausgewogene Ernährung — "
    "leicht, lecker und im Einklang mit Körper und Natur.",
    nav_style="centered",
    address="Mittelstraße 8, 40213 Düsseldorf",
    opening_hours_text="Mo–So 11:00–22:00",
    opening_hours={d: ("11:00", "22:00") for d in range(7)},
    gallery_kw=[
        "vegan,food",
        "vegan,burger",
        "vegan,sausage",
        "vegan,cake",
        "ayurveda,spices",
        "yoga,forest",
    ],
    faq=[
        ("Ist alles wirklich vegan?", "Ja — 100 % pflanzlich, ohne Ausnahme."),
        (
            "Wann öffnet das Restaurant?",
            "Bald! Die Speisekarte ist schon online — schau dich gern um.",
        ),
        (
            "Macht ihr Catering?",
            "Ja! Stell über «Catering» eine Anfrage — wir melden uns mit Angebot.",
        ),
        (
            "Was sind eure Retreats?",
            "Ruhige Wochenenden mit veganer & ayurvedischer Küche, Yoga und Natur.",
        ),
    ],
    testimonials=[
        ("Jana", "Endlich veganes Essen, das richtig schmeckt — und so liebevoll gemacht."),
        ("Tom & Lisa", "Der Shop ist ein Traum: vegane Würstchen wie früher, nur besser."),
    ],
    process=[
        ("Wählen", "Stell dir dein Menü oder deinen Einkauf zusammen."),
        ("Bestellen", "Online zur Abholung oder Lieferung — oder Catering anfragen."),
        ("Genießen", "Frisch zubereitet, bewusst und ausgewogen."),
    ],
    team=[
        ("Nour El-Amin", "Gründerin & Köchin", "chef,woman"),
        ("Ben Krause", "Küche", "cook,man"),
    ],
    trust={"since": "2021", "marks": ["100 % Vegan", "Ayurveda", "Regional"]},
    reviews_seed=[
        (
            5,
            "Endlich veganes Essen, das richtig schmeckt — und so liebevoll gemacht.",
            "pr.jana@example.de",
        ),
        (5, "Der vegane Shop ist ein Traum. Würstchen wie früher!", "pr.tomlisa@example.de"),
        (4, "Schöne Retreats und nette Leute. Komme gerne wieder.", "pr.sven@example.de"),
    ],
    enable_modules=["orders", "events", "jobs", "loyalty"],
    promo_count=4,
    group_promos_by_category=True,
    loyalty={"label": "Pranasy-Stempelkarte", "stamps": 10, "reward": "1 Gratis-Gericht"},
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=PRANASY_MENUS,
    # M20U-2: слайдер баннеров — единая главная ведёт к ключевым действиям.
    heroes=[
        {
            "image_kw": "vegan,food",
            "title": "Bald geöffnet",
            "text": "Unser veganes Restaurant öffnet bald — die Speisekarte ist schon online.",
            "button_label": "Zur Speisekarte",
            "button_url": "/sortiment/?kategorie=demo-restaurant",
        },
        {
            "image_kw": "vegan,sausage",
            "title": "Veganer Shop",
            "text": "Würstchen, Aufschnitt und feine Konditorei — alles pflanzlich.",
            "button_label": "Zum Shop",
            "button_url": "/sortiment/?kategorie=demo-shop",
        },
        {
            "image_kw": "yoga,forest",
            "title": "Retreats & Catering",
            "text": "Ruhige Wochenenden mit veganer Küche und Yoga — oder Catering für deine Feier.",
            "button_label": "Retreats ansehen",
            "button_url": "/veranstaltung/",
        },
    ],
    section_titles={
        "products": "Speisekarte & Shop",
        "promotions": "Angebote",
        "events": "Retreats bei Pranasy",
    },
    # Меню — плотная сетка; события — карточками (а не списком).
    page_layouts={"catalog": "cols3", "events": "cols2"},
    archetype_covers={
        "catalog": {
            "intro": "Unser Restaurant öffnet bald — die Karte ist schon da. Und im veganen "
            "Shop findest du Würstchen, Aufschnitt und feine Konditorei.",
            "hero_kw": "vegan,food",
            "gallery_kw": ["vegan,burger", "vegan,sausage", "vegan,cake", "ayurveda,spices"],
        },
        "jobs": {
            "intro": "Veganes & ayurvedisches Catering für Feiern, Büro und Events. Sag uns, "
            "was du brauchst — wir kochen frisch und melden uns mit einem unverbindlichen Angebot.",
            "hero_kw": "catering,buffet",
        },
        "events": {
            "intro": "Unsere Retreats: ruhige Wochenenden mit veganer & ayurvedischer Küche, "
            "Yoga, Atem und Natur — Auftanken und zu sich zurückfinden.",
            "hero_kw": "yoga,forest",
            "gallery_kw": ["yoga,forest", "meditation,nature", "lake,forest"],
        },
        "loyalty": {
            "intro": "Sammle Stempel bei jedem Besuch — das 10. Gericht geht aufs Haus.",
            "hero_kw": "vegan,food",
        },
    },
    teachers=[
        (
            "Mara Lind",
            "Retreatleitung & Yogalehrerin",
            "yoga,teacher,woman",
            "RYT-500 Yogalehrerin, führt seit Jahren ruhige Wochenenden in der Natur.",
        ),
        (
            "Felix Sturm",
            "Achtsamkeits-Coach",
            "meditation,man",
            "Begleitet Atem- und Meditationspraxis, ruhig und nahbar.",
        ),
        (
            "Dr. Anjali Rao",
            "Ayurveda-Therapeutin",
            "ayurveda,woman",
            "Bringt ayurvedisches Wissen in Küche und Alltag — bewusst und ausgewogen.",
        ),
    ],
    events=[
        {
            "title": "Vegan & Ayurveda Retreat: Auftanken am Waldrand",
            "title_en": "Vegan & Ayurveda Retreat: Recharge by the Forest",
            "description": "Ein Wochenende mit veganer & ayurvedischer Küche, Yoga und Natur — "
            "kochen, entspannen, auftanken.",
            "description_en": "A weekend of vegan & ayurvedic cuisine, yoga and nature — "
            "cook, relax, recharge.",
            "in_days": 21,
            "hour": 16,
            "duration_days": 2,
            "capacity": 15,
            "price": "129",
            "location": "Seminarhaus am Waldrand, NRW (ca. 30 Min. von Köln)",
            "program": [
                "Fr 16:00 — Ankommen & gemeinsames Abendessen",
                "Sa — Yoga · Ayurveda-Kochworkshop · Waldspaziergang · Lagerfeuer",
                "So — Morgen-Yoga · Brunch · Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["yoga,forest", "ayurveda,spices", "lake,forest", "campfire,night"],
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Yoga & Stille: Detox-Wochenende",
            "title_en": "Yoga & Silence: Detox Weekend",
            "description": "Sanftes Yoga, Stille und leichte vegane Küche — ein Reset für Körper "
            "und Geist.",
            "description_en": "Gentle yoga, silence and light vegan food — a reset for body "
            "and mind.",
            "in_days": 35,
            "hour": 16,
            "duration_days": 2,
            "capacity": 14,
            "price": "139",
            "location": "Seminarhaus am Waldrand, NRW",
            "program": [
                "Fr — Ankommen & Stille-Abend",
                "Sa — Yoga · Atemarbeit · grüne Smoothies · Waldbaden",
                "So — Morgen-Yoga · leichter Brunch · Abschluss",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["meditation,nature", "yoga,forest", "smoothie", "lake,forest"],
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Ayurveda-Küche: Kochretreat",
            "title_en": "Ayurvedic Kitchen: Cooking Retreat",
            "description": "Lerne ayurvedisch zu kochen — Gewürze, Doshas und einfache, "
            "ausgewogene Gerichte.",
            "description_en": "Learn to cook ayurvedically — spices, doshas and simple, "
            "balanced dishes.",
            "in_days": 48,
            "hour": 15,
            "duration_days": 2,
            "capacity": 12,
            "price": "159",
            "location": "Seminarhaus am Waldrand, NRW",
            "program": [
                "Fr — Ankommen & Gewürzkunde",
                "Sa — Dosha-Basics · Kochworkshop · gemeinsames Dinner",
                "So — Frühstückskunde · Meal-Prep · Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["ayurveda,spices", "cooking,class", "vegan,food", "yoga,forest"],
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Plant-Based Weekend: Sommer-Retreat",
            "title_en": "Plant-Based Weekend: Summer Retreat",
            "description": "Ein sonniges Wochenende voller pflanzlicher Küche, Yoga und See.",
            "description_en": "A sunny weekend full of plant-based food, yoga and the lake.",
            "in_days": 62,
            "hour": 16,
            "duration_days": 2,
            "capacity": 16,
            "price": "129",
            "location": "Seminarhaus am Waldrand, NRW",
            "program": [
                "Fr — Ankommen & Lagerfeuer",
                "Sa — Yoga · Plant-Based-Kochworkshop · See & Wald",
                "So — Morgen-Yoga · Brunch · Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["vegan,food", "yoga,forest", "lake,forest", "campfire,night"],
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Achtsamkeit & Meditation: Slow Weekend",
            "title_en": "Mindfulness & Meditation: Slow Weekend",
            "description": "Langsamer werden, meditieren und bewusst essen — ein Wochenende "
            "ganz für dich.",
            "description_en": "Slow down, meditate and eat consciously — a weekend just for you.",
            "in_days": 75,
            "hour": 16,
            "duration_days": 2,
            "capacity": 14,
            "price": "139",
            "location": "Seminarhaus am Waldrand, NRW",
            "program": [
                "Fr — Ankommen & Stille-Kreis",
                "Sa — Meditation · sanftes Yoga · vegane Küche · Spaziergang",
                "So — Morgen-Meditation · Brunch · Abschluss",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["meditation,nature", "yoga,forest", "lake,forest", "campfire,night"],
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Frauen-Retreat: Balance & Ayurveda",
            "title_en": "Women's Retreat: Balance & Ayurveda",
            "description": "Ein Wochenende für Frauen — ayurvedische Küche, Yoga und Zeit zum "
            "Durchatmen.",
            "description_en": "A weekend for women — ayurvedic cuisine, yoga and time to breathe.",
            "in_days": 90,
            "hour": 16,
            "duration_days": 2,
            "capacity": 12,
            "price": "149",
            "location": "Seminarhaus am Waldrand, NRW",
            "program": [
                "Fr — Ankommen & Kennenlern-Kreis",
                "Sa — Yoga · Ayurveda-Workshop · Wald & See · Abendgespräch",
                "So — Morgen-Yoga · Brunch · Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            "photos": ["yoga,forest", "ayurveda,spices", "meditation,nature", "lake,forest"],
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
        "title": "Hunger auf Pflanzliches?",
        "text": "Schau in die Speisekarte oder stöbere im veganen Shop.",
        "button_label": "Zur Speisekarte",
        "button_url": "/sortiment/?kategorie=demo-restaurant",
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
            {"de": "Restaurant", "en": "Restaurant"},
            "restaurant",
            [
                _p(
                    {"de": "Veganer Burger", "en": "Vegan Burger"},
                    "8.90",
                    {
                        "de": "Saftiges Pflanzen-Patty, Salat, Tomate, hausgemachte Sauce.",
                        "en": "Juicy plant-based patty, lettuce, tomato, house sauce.",
                    },
                    "vegan,burger",
                    variants=[("Single", "8.90"), ("Double", "11.90")],
                    allergens=["gluten", "soja", "senf"],
                    modifiers=VEGAN_BURGER_MODIFIERS,
                    badge="beliebt",
                ),
                _p(
                    {"de": "Vegane Pizza", "en": "Vegan Pizza"},
                    "10.90",
                    {
                        "de": "Dünner Teig, Tomate, veganer Käse, frisches Gemüse.",
                        "en": "Thin crust, tomato, vegan cheese, fresh vegetables.",
                    },
                    "vegan,pizza",
                    allergens=["gluten", "soja"],
                    modifiers=PIZZA_MODIFIERS,
                ),
                _p(
                    {"de": "Vegane Pita", "en": "Vegan Pita"},
                    "7.50",
                    {
                        "de": "Warmes Pitabrot mit Falafel, Hummus und Salat.",
                        "en": "Warm pita with falafel, hummus and salad.",
                    },
                    "vegan,pita",
                    allergens=["gluten", "sesam"],
                ),
                _p(
                    {"de": "Hotdog", "en": "Hotdog"},
                    "6.50",
                    {
                        "de": "Karotten-Hotdog mit Senf, Ketchup und Gurke.",
                        "en": "Carrot hotdog with mustard, ketchup and pickle.",
                    },
                    "vegan,hotdog",
                    allergens=["gluten", "senf"],
                ),
                _p(
                    {"de": "Alaputra", "en": "Alaputra"},
                    "8.40",
                    {
                        "de": "Ayurvedisch gewürzte Kartoffeln mit Kreuzkümmel und Kurkuma.",
                        "en": "Ayurvedic spiced potatoes with cumin and turmeric.",
                    },
                    "spiced,potato",
                    allergens=[],
                    badge="ayurveda",
                ),
                _p(
                    {"de": "Kofta", "en": "Kofta"},
                    "9.20",
                    {
                        "de": "Vegane Kofta-Bällchen mit Kräutern und Tahini-Sauce.",
                        "en": "Vegan kofta balls with herbs and tahini sauce.",
                    },
                    "vegan,kofta",
                    allergens=["sesam", "gluten"],
                ),
                _p(
                    {"de": "Veganer Schaschlik", "en": "Vegan Skewers"},
                    "9.90",
                    {
                        "de": "Gegrillte Gemüse- und Tofu-Spieße mit Marinade.",
                        "en": "Grilled vegetable and tofu skewers with marinade.",
                    },
                    "vegan,skewers",
                    variants=[("1 Spieß", "9.90"), ("2 Spieße", "14.90")],
                    allergens=["soja"],
                ),
                _p(
                    {"de": "Nori-Pakora", "en": "Nori Pakora"},
                    "6.80",
                    {
                        "de": "Knusprige Nori-Pakora aus Kichererbsenmehl, frittiert.",
                        "en": "Crispy nori pakora made from chickpea flour.",
                    },
                    "pakora,fried",
                    allergens=[],
                    badge="neu",
                ),
            ],
        ),
        (
            {"de": "Shop", "en": "Shop"},
            "shop",
            [],
            [
                (
                    {"de": "Würstchen", "en": "Sausages"},
                    "wuerstchen",
                    [
                        _p(
                            {"de": "Vegane Bratwurst", "en": "Vegan Bratwurst"},
                            "4.90",
                            {
                                "de": "Pflanzliche Bratwurst, klassisch gewürzt. 2 Stück, 200 g.",
                                "en": "Plant-based bratwurst, classically spiced. 2 pcs, 200 g.",
                            },
                            "vegan,sausage",
                            allergens=["soja", "gluten"],
                            unit="kg",
                            content="0.2",
                        ),
                        _p(
                            {"de": "Vegane Wiener", "en": "Vegan Wieners"},
                            "4.50",
                            {
                                "de": "Feine vegane Wiener Würstchen. 4 Stück, 200 g.",
                                "en": "Fine vegan Vienna sausages. 4 pcs, 200 g.",
                            },
                            "vegan,sausage",
                            allergens=["soja"],
                            unit="kg",
                            content="0.2",
                        ),
                        _p(
                            {"de": "Vegane Currywurst", "en": "Vegan Currywurst"},
                            "5.40",
                            {
                                "de": "Vegane Currywurst mit hausgemachter Curry-Sauce. 250 g.",
                                "en": "Vegan currywurst with house curry sauce. 250 g.",
                            },
                            "vegan,currywurst",
                            allergens=["soja", "senf"],
                            unit="kg",
                            content="0.25",
                            badge="beliebt",
                        ),
                    ],
                ),
                (
                    {"de": "Wurst & Aufschnitt", "en": "Sausage & Cold Cuts"},
                    "aufschnitt",
                    [
                        _p(
                            {"de": "Veganer Schinken", "en": "Vegan Ham"},
                            "3.90",
                            {
                                "de": "Pflanzlicher Aufschnitt nach Schinken-Art. 100 g.",
                                "en": "Plant-based ham-style cold cut. 100 g.",
                            },
                            "vegan,coldcut",
                            allergens=["soja"],
                            unit="kg",
                            content="0.1",
                        ),
                        _p(
                            {"de": "Vegane Salami", "en": "Vegan Salami"},
                            "4.20",
                            {
                                "de": "Würzige vegane Salami, fein geschnitten. 100 g.",
                                "en": "Spicy vegan salami, thinly sliced. 100 g.",
                            },
                            "vegan,salami",
                            allergens=["soja"],
                            unit="kg",
                            content="0.1",
                        ),
                        _p(
                            {"de": "Veganer Mortadella", "en": "Vegan Mortadella"},
                            "4.40",
                            {
                                "de": "Vegane Mortadella mit Pistazien. 100 g.",
                                "en": "Vegan mortadella with pistachios. 100 g.",
                            },
                            "vegan,mortadella",
                            allergens=["soja", "nuss"],
                            unit="kg",
                            content="0.1",
                        ),
                    ],
                ),
                (
                    {"de": "Süßes & Konditorei", "en": "Sweets & Confectionery"},
                    "suesses",
                    [
                        _p(
                            {"de": "Veganer Schokokuchen", "en": "Vegan Chocolate Cake"},
                            "3.50",
                            {
                                "de": "Saftiger Schokokuchen, rein pflanzlich. Pro Stück.",
                                "en": "Moist chocolate cake, fully plant-based. Per piece.",
                            },
                            "vegan,cake",
                            allergens=["gluten", "nuss"],
                            badge="beliebt",
                        ),
                        _p(
                            {"de": "Vegane Cookies", "en": "Vegan Cookies"},
                            "2.80",
                            {
                                "de": "Knusprige Cookies mit Schokostückchen. 3 Stück.",
                                "en": "Crunchy cookies with chocolate chips. 3 pcs.",
                            },
                            "vegan,cookie",
                            allergens=["gluten", "soja"],
                        ),
                        _p(
                            {"de": "Vegane Schokolade", "en": "Vegan Chocolate"},
                            "3.20",
                            {
                                "de": "Zartbitter-Schokolade, 100 g Tafel.",
                                "en": "Dark chocolate, 100 g bar.",
                            },
                            "vegan,chocolate",
                            allergens=["soja"],
                            unit="kg",
                            content="0.1",
                        ),
                        _p(
                            {"de": "Ayurveda-Energiekugeln", "en": "Ayurveda Energy Balls"},
                            "4.50",
                            {
                                "de": "Datteln, Nüsse und Gewürze — ohne Zuckerzusatz. 6 Stück.",
                                "en": "Dates, nuts and spices — no added sugar. 6 pcs.",
                            },
                            "energy,balls",
                            allergens=["nuss"],
                            badge="ayurveda",
                        ),
                        _p(
                            {"de": "Veganer Käsekuchen", "en": "Vegan Cheesecake"},
                            "3.90",
                            {
                                "de": "Cremiger Cashew-Käsekuchen. Pro Stück.",
                                "en": "Creamy cashew cheesecake. Per piece.",
                            },
                            "vegan,cheesecake",
                            allergens=["nuss"],
                        ),
                        _p(
                            {"de": "Vegane Zimtschnecke", "en": "Vegan Cinnamon Roll"},
                            "3.30",
                            {
                                "de": "Fluffige Zimtschnecke mit Zuckerguss. Pro Stück.",
                                "en": "Fluffy cinnamon roll with icing. Per piece.",
                            },
                            "vegan,cinnamon,roll",
                            allergens=["gluten"],
                        ),
                    ],
                ),
            ],
        ),
    ],
    i18n={
        "en": {
            "hero_title": "Pranasy",
            "hero_text": "100 % plant-based & ayurveda-inspired — fresh cuisine, a fine shop, "
            "calm retreats.",
            "about_title": "About Pranasy",
            "about_text": "Pranasy stands for food that does you good: 100 % plant-based, "
            "ayurveda-inspired and made with real ingredients. We believe in conscious, "
            "balanced nutrition — light, tasty and in harmony with body and nature.",
            "section_titles": {
                "products": "Menu & Shop",
                "promotions": "Offers",
                "events": "Retreats at Pranasy",
            },
            "faq": [
                {
                    "q": "Is everything really vegan?",
                    "a": "Yes — 100 % plant-based, no exceptions.",
                },
                {
                    "q": "When does the restaurant open?",
                    "a": "Soon! The menu is already online — feel free to browse.",
                },
                {
                    "q": "Do you do catering?",
                    "a": "Yes! Send a request via «Catering» — we'll get back with an offer.",
                },
                {
                    "q": "What are your retreats?",
                    "a": "Calm weekends with vegan & ayurvedic food, yoga and nature.",
                },
            ],
            "testimonials": [
                {
                    "name": "Jana",
                    "text": "Finally vegan food that really tastes great — and made with so much love.",
                },
                {
                    "name": "Tom & Lisa",
                    "text": "The shop is a dream: vegan sausages like back in the day, only better.",
                },
            ],
            "process": [
                {"title": "Choose", "text": "Put together your menu or your shopping."},
                {
                    "title": "Order",
                    "text": "Online for pickup or delivery — or request catering.",
                },
                {"title": "Enjoy", "text": "Freshly prepared, conscious and balanced."},
            ],
            "cta": {
                "title": "Craving something plant-based?",
                "text": "Check out the menu or browse the vegan shop.",
                "button_label": "View the menu",
            },
            "heroes": [
                {
                    "title": "Opening soon",
                    "text": "Our vegan restaurant opens soon — the menu is already online.",
                    "button_label": "View the menu",
                },
                {
                    "title": "Vegan shop",
                    "text": "Sausages, cold cuts and fine confectionery — all plant-based.",
                    "button_label": "Go to the shop",
                },
                {
                    "title": "Retreats & catering",
                    "text": "Calm weekends with vegan food and yoga — or catering for your event.",
                    "button_label": "See retreats",
                },
            ],
            "trust": {"marks": ["100 % Vegan", "Ayurveda", "Regional"]},
            "archetypes": {
                "catalog": {
                    "intro": "Our restaurant opens soon — the menu is already here. And in the "
                    "vegan shop you'll find sausages, cold cuts and fine confectionery.",
                },
                "jobs": {
                    "intro": "Vegan & ayurvedic catering for parties, offices and events. Tell us "
                    "what you need — we cook fresh and send a non-binding offer.",
                },
                "events": {
                    "intro": "Our retreats: calm weekends with vegan & ayurvedic food, yoga, "
                    "breath and nature — recharge and return to yourself.",
                },
                "loyalty": {
                    "intro": "Collect a stamp on every visit — the 10th dish is on the house.",
                },
            },
        }
    },
)

# Меню отеля (ТЗ §15): «Главная/Номера/Галерея/Отзывы/Hausordnung/FAQ/Über
# uns/Контакты/Забронировать». Якоря (#galerie/#bewertungen/#faq/#kontakt/#buchen)
# созданы обёртками секций в home.html; target с «/#…» работает с любой страницы.
HOTEL_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Start", "type": "page", "target": "home"},
            {"label": "Zimmer & Preise", "type": "archetype", "target": "stays"},
            {"label": "Galerie", "type": "anchor", "target": "/#galerie"},
            {"label": "Bewertungen", "type": "anchor", "target": "/#bewertungen"},
            {"label": "Hausordnung", "type": "url", "target": "/hausordnung/"},
            {"label": "FAQ", "type": "anchor", "target": "/#faq"},
            {"label": "Über uns", "type": "page", "target": "about"},
            {"label": "Kontakt", "type": "anchor", "target": "/#kontakt"},
            {"label": "Jetzt buchen", "type": "anchor", "target": "/#buchen"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Zimmer", "type": "archetype", "target": "stays", "icon": "🛏"},
            {"label": "Galerie", "type": "anchor", "target": "/#galerie", "icon": "📷"},
            {"label": "Bewertungen", "type": "anchor", "target": "/#bewertungen", "icon": "⭐"},
            {"label": "Buchen", "type": "anchor", "target": "/#buchen", "icon": "📅"},
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
    reviews_seed=[
        (
            5,
            "Traumhafte Lage am See, herzliche Gastgeber — wir kommen wieder!",
            "hotel.bauer@example.de",
        ),
        (5, "Sauber, ruhig und das Frühstück ein Gedicht.", "hotel.julia@example.de"),
        (4, "Schöne Zimmer mit tollem Seeblick, sehr entspannt.", "hotel.klaus@example.de"),
    ],
    extras=[  # #7 доп-услуги к брони (per_night=True → за ночь)
        ("Frühstücksbuffet", "12", "stays", True),
        ("Parkplatz", "8", "stays", True),
        ("Später Check-out (bis 14 Uhr)", "20", "stays", False),
        ("Haustier", "15", "stays", False),
    ],
    enable_modules=["stays"],
    # Карточки номеров показываем напрямую (секция stay_rooms), поэтому тизер-
    # секция «Unsere Bereiche» для отеля не нужна (была бы дублем).
    enable_archetypes_section=False,
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
            "deposit": "30",  # E4: депозит за бронь (анти-no-show)
            "area": 24,  # H3
            "bed": "Queensize-Bett",
            "amenities": ["wifi", "tv", "bath", "shower", "balcony", "coffee", "nonsmoking"],
            "season": [  # A5a: Hochsaison-Tarif
                {
                    "label": "Hochsaison (Sommer)",
                    "start": "2026-07-01",
                    "end": "2026-08-31",
                    "price": "119",
                },
            ],
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
            "area": 16,  # H3
            "bed": "Einzelbett (Boxspring)",
            "amenities": ["wifi", "tv", "shower", "desk", "coffee", "hairdryer", "nonsmoking"],
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
            "area": 32,  # H3
            "bed": "Doppelbett + 2 Einzelbetten",
            "amenities": ["wifi", "tv", "bath", "shower", "coffee", "petfriendly", "nonsmoking"],
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
            "area": 55,  # H3
            "bed": "Doppelbett + Schlafsofa",
            "amenities": ["wifi", "tv", "bath", "kitchen", "balcony", "parking", "petfriendly"],
        },
    ],
    rate_plans=[  # H1: тарифы для всех номеров (гость выбирает при брони)
        {
            "name": "Basistarif",
            "description": "Flexibel & ohne Risiko buchen.",
            "cancellation": "flexible",
            "free_cancel_days": 7,
            "sort": 0,
        },
        {
            "name": "Mit Frühstück (30 % Anzahlung)",
            "description": "Inkl. Frühstücksbuffet — 30 % Anzahlung bei Buchung.",
            "surcharge": "12",
            "meal": "breakfast",
            "cancellation": "flexible",
            "free_cancel_days": 3,
            "prepayment": 30,  # G7: частичная предоплата (2-й пример рядом со 100 %)
            "sort": 1,
        },
        {
            "name": "Halbpension",
            "description": "Frühstück & Abendessen inklusive.",
            "surcharge": "28",
            "meal": "half_board",
            "cancellation": "flexible",
            "free_cancel_days": 3,
            "sort": 2,
        },
        {
            "name": "Sparpreis (nicht erstattbar)",
            "description": "Günstiger buchen — Vorkasse, keine Stornierung möglich.",
            "percent": -12,
            "cancellation": "non_refundable",
            "prepayment": 100,  # G7: полная Vorkasse для невозвратного тарифа
            "sort": 3,
        },
    ],
    kurtaxe="2.50",  # H9: Kurtaxe pro Erwachsenem/Nacht (Überlingen/Bodensee)
    # G4: по 2 правила на каждый тип авто-скидки (многоступенчато).
    auto_discounts=[
        {"kind": "los", "threshold": 7, "percent": 10},  # 7+ ночей −10 %
        {"kind": "los", "threshold": 14, "percent": 15},  # 14+ ночей −15 %
        {"kind": "early_bird", "threshold": 30, "percent": 8},  # ≥30 дней −8 %
        {"kind": "early_bird", "threshold": 60, "percent": 12},  # ≥60 дней −12 %
        {"kind": "last_minute", "threshold": 3, "percent": 12},  # ≤3 дня −12 %
        {"kind": "last_minute", "threshold": 7, "percent": 8},  # ≤7 дней −8 %
    ],
    # H4a/G4a: 2 промокода — процентный и на фикс-сумму.
    stay_promo={"code": "SOMMER10", "label": "−10 % Sommer", "percent": 10},
    vouchers=[
        {"code": "WILLKOMMEN20", "label": "20 € Willkommensrabatt", "cents": 2000, "max_uses": 200},
    ],
    house_rules=(  # H6: Hausordnung
        "Check-in: ab 15:00 Uhr · Check-out: bis 11:00 Uhr\n"
        "Ruhezeiten: 22:00–7:00 Uhr\n"
        "Haustiere: kleine Hunde auf Anfrage (15 € / Nacht)\n"
        "Rauchen: nur auf dem Balkon / der Terrasse\n"
        "Kaution: 30 € bei Anreise (bar oder Karte), Rückgabe bei Abreise\n"
        "Kinder: bis 6 Jahre kostenfrei im Bett der Eltern\n"
        "Stornierung: gemäß gewähltem Tarif (siehe Buchung)"
    ),
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
    usp=[
        ("local", "Frisch & regional"),
        ("clock", "Mo–Sa 8–20 Uhr"),
        ("payment", "Karte & bar"),
        ("quality", "Geprüfte Qualität"),
    ],
    reviews_seed=[
        (5, "Die Überraschungstüten sind unschlagbar günstig!", "am.wagner@example.de"),
        (5, "Endlich ein Markt, bei dem man jede Woche wirklich spart.", "am.demir@example.de"),
        (4, "Gute Angebote und freundliches Personal.", "am.petra@example.de"),
    ],
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
    reviews_seed=[
        (5, "Bester Schnitt seit Jahren — und so unkompliziert zu buchen!", "fr.sandra@example.de"),
        (5, "Tolle Beratung, faire Preise, immer pünktlich.", "fr.michael@example.de"),
        (4, "Sehr freundliches Team, fühle mich immer wohl.", "fr.nina@example.de"),
    ],
    cta={
        "title": "Zeit für etwas Neues?",
        "text": "Buchen Sie jetzt Ihren Wunschtermin online.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    enable_modules=["booking", "loyalty", "orders", "customer_account"],
    extras=[  # #7 доп-услуги к термину (scope booking, разово)
        ("Haarkur Intensiv", "12", "booking", False),
        ("Kopfmassage (10 Min.)", "9", "booking", False),
    ],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=FRISEUR_MENUS,
    loyalty={"label": "Treuekarte", "stamps": 10, "reward": "1× Waschen & Föhnen gratis"},
    pass_plans=[
        {
            "label": "10er-Karte Waschen & Föhnen",
            "credits": 10,
            "price": "170",
            "valid_days": 365,
            "service_index": 2,
        },
        {"label": "5er-Karte Haarschnitt", "credits": 5, "price": "180", "valid_days": 365},
    ],
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
        # A3: (name, min, price, description, image_kw) — богатая карточка услуги.
        (
            "Haarschnitt Damen",
            45,
            "39",
            "Waschen, Schnitt und Föhnen — individuell auf Sie abgestimmt.",
            "woman,haircut",
        ),
        (
            "Haarschnitt Herren",
            30,
            "25",
            "Klassischer oder moderner Schnitt inkl. Waschen.",
            "man,haircut",
        ),
        (
            "Waschen & Föhnen",
            30,
            "19",
            "Pflegende Wäsche und professionelles Styling.",
            "hair,styling",
        ),
        ("Färben", 90, "69", "Brillante Farben mit schonenden Produkten.", "hair,color"),
        (
            "Strähnen / Highlights",
            120,
            "89",
            "Natürliche Highlights für mehr Tiefe und Glanz.",
            "hair,highlights",
        ),
        ("Bart trimmen", 15, "12", "Konturen schneiden und in Form bringen.", "beard,barber"),
    ],
    resources=[
        {
            "name": "Lea",
            "type": "staff",
            "capacity": 1,
            "start": "09:00",
            "end": "18:00",
            "slot": 30,
            "weekdays": range(1, 6),
            # A3: профиль мастера
            "title": "Stylistin & Farbexpertin",
            "bio": "Seit 10 Jahren im Salon — spezialisiert auf Balayage und natürliche Farbverläufe.",
            "photo_kw": "hairdresser,woman",
        },
        {
            "name": "Jonas",
            "type": "staff",
            "capacity": 1,
            "start": "09:00",
            "end": "18:00",
            "slot": 30,
            "weekdays": range(1, 6),
            "title": "Barbier",
            "bio": "Herrenschnitte, Bart-Styling und klassische Rasur mit ruhiger Hand.",
            "photo_kw": "barber,man",
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
    jobs_vehicle=True,  # A9: Anfrage с Kennzeichen/HSN/TSN + AutoRepair-разметка
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
    usp=[
        ("meister", "Meisterbetrieb"),
        ("local", "HU/AU vor Ort"),
        ("clock", "Termin online"),
        ("quality", "Markenoffen"),
    ],
    reviews_seed=[
        (
            5,
            "Schnell, ehrlich und fairer Preis — endlich eine Werkstatt, der man vertraut.",
            "wk.berger@example.de",
        ),
        (5, "Termin online gebucht, Auto pünktlich fertig. Top Service.", "wk.yilmaz@example.de"),
        (4, "Kostenvoranschlag transparent, keine versteckten Kosten.", "wk.frank@example.de"),
    ],
    cta={
        "title": "Klappert, leuchtet oder zieht?",
        "text": "Buchen Sie einen Termin oder fordern Sie ein Angebot an.",
        "button_label": "Termin buchen",
        "button_url": "/termin/",
    },
    enable_modules=["booking", "jobs", "orders", "customer_account"],
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
            "vehicle": "VW Golf VII 1.6 TDI",
            "vehicle_plate": "DO-MV 1234",
            "vehicle_hsn": "0603",
            "vehicle_tsn": "BNV",
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
            "vehicle": "BMW 320d",
            "vehicle_plate": "DO-SK 88",
            "vehicle_hsn": "0005",
            "vehicle_tsn": "CKA",
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
        ("Ölwechsel", 30, "49", "Inkl. Öl, Filter und Entsorgung. Festpreis für gängige Modelle."),
        ("Inspektion", 120, "149", "Inspektion nach Herstellervorgabe inkl. Fehlerauslese."),
        ("Reifenwechsel", 45, "39", "Räder umstecken, Wuchten auf Wunsch, Reifendruck prüfen."),
        ("HU/AU (TÜV)", 60, "89", "Hauptuntersuchung & Abgasuntersuchung direkt vor Ort."),
        ("Bremsen-Check", 30, "0", "Kostenloser Sicherheits-Check von Belägen und Scheiben."),
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

HANDWERKER_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Angebot", "type": "archetype", "target": "jobs"},
            {"label": "Leistungen", "type": "archetype", "target": "booking"},
            {"label": "Referenzen", "type": "url", "target": "/#galerie"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Angebot", "type": "archetype", "target": "jobs", "icon": "🧰"},
            {"label": "Leistungen", "type": "archetype", "target": "booking", "icon": "🛠"},
            {"label": "Kontakt", "type": "page", "target": "contact", "icon": "📞"},
        ],
    },
}

# A7 Handwerker: generischer Meisterbetrieb (Maler · Elektro · Sanitär). Kernarchetyp
# = jobs (Anfrage → unverbindliches Angebot/Festpreis); booking liefert Leistungen mit
# Festpreisen + kostenlose Vor-Ort-Beratung. Kein Shop (keine catalog/products-Sektion).
HANDWERKER = DemoKit(
    key="handwerker",
    label="Meisterbetrieb Krause",
    business_type="other",
    subdomain="handwerker",
    accent="#ea580c",  # Handwerk-Orange
    hero_image_kw="craftsman,renovation",
    hero_title="Meisterbetrieb Krause",
    hero_text="Maler, Elektro & Sanitär aus einer Hand — kostenloses Angebot in 24 h, "
    "Festpreis-Garantie und 24/7-Notdienst für Ihre Region.",
    about_title="Über den Betrieb",
    about_text="Seit 2004 Ihr Handwerker für Renovierung, Elektrik und Bad: "
    "Meisterqualität, saubere Arbeit und faire Festpreise. Schildern Sie Ihr "
    "Vorhaben online — Sie erhalten ein unverbindliches Angebot.",
    nav_style="classic",
    address="Lindenweg 8, 50667 Köln",
    opening_hours_text="Mo–Fr 7:00–17:00 · 24h-Notdienst",
    opening_hours={d: ("07:00", "17:00") for d in range(5)},
    # A7: зона обслуживания — несколько Kölner PLZ + текстовая пометка.
    service_area_plz="50667, 50670, 50674, 50676, 50823, 51063",
    service_area_note="Köln und Umgebung (Innenstadt, Nippes, Ehrenfeld, Mülheim)",
    gallery_kw=[
        "painter,wall",
        "electrician,work",
        "bathroom,renovation",
        "tiles,bathroom",
        "painting,room",
        "heating,installation",
    ],
    before_after=[
        (
            "old,bathroom",
            "modern,bathroom",
            "Komplettsanierung Bad in Köln-Nippes — neue Fliesen, Sanitär und Beleuchtung "
            "in 8 Werktagen, zum Festpreis.",
        ),
        (
            "shabby,wall",
            "painted,wall",
            "Wohnzimmer & Flur frisch gestrichen — Wände gespachtelt, grundiert und "
            "zweifach gestrichen.",
        ),
    ],
    faq=[
        (
            "Wie bekomme ich ein Angebot?",
            "Über «Angebot anfordern» schildern Sie Ihr Vorhaben (gern mit Fotos & "
            "Adresse) — Sie erhalten ein unverbindliches Angebot, meist innerhalb von 24 h.",
        ),
        (
            "Arbeiten Sie zum Festpreis?",
            "Ja. Nach kostenloser Besichtigung erhalten Sie einen verbindlichen "
            "Festpreis — keine versteckten Kosten.",
        ),
        (
            "Welche Gewerke bieten Sie an?",
            "Maler- und Lackierarbeiten, Elektroinstallation und Sanitär/Bad — "
            "alles aus einer Hand, koordiniert vom Meister.",
        ),
        (
            "Gibt es einen Notdienst?",
            "Ja, bei Rohrbruch oder Stromausfall sind wir rund um die Uhr erreichbar.",
        ),
    ],
    testimonials=[
        (
            "Familie Becker",
            "Bad komplett saniert — pünktlich, sauber und zum vereinbarten Festpreis.",
        ),
        ("Petra L.", "Angebot online angefragt, am nächsten Tag Rückruf. Sehr professionell."),
    ],
    process=[
        ("Vorhaben schildern", "Online anfragen — gern mit Fotos und Adresse der Baustelle."),
        ("Festpreis-Angebot", "Kostenlose Besichtigung, danach verbindlicher Festpreis."),
        ("Saubere Ausführung", "Termingerechte Arbeit vom Meisterbetrieb — besenrein übergeben."),
    ],
    team=[
        ("Markus Krause", "Maler- und Lackierermeister", "craftsman,man"),
        ("Dennis Wolf", "Elektromeister", "electrician,man"),
        ("Ralf Sommer", "SHK-Meister", "plumber,man"),
    ],
    trust={"since": "2004", "marks": ["Meisterbetrieb", "Innungsmitglied", "Festpreis-Garantie"]},
    usp=[
        ("meister", "Meisterbetrieb"),
        ("clock", "24/7 Notdienst"),
        ("local", "Aus Ihrer Region"),
        ("quality", "Festpreis-Garantie"),
    ],
    reviews_seed=[
        (
            5,
            "Bad saniert zum Festpreis — alles sauber und termingerecht. Klare Empfehlung.",
            "hw.becker@example.de",
        ),
        (5, "Schnelles Angebot, faire Preise, top Handwerk. Gerne wieder.", "hw.acar@example.de"),
        (4, "Elektrik im Altbau erneuert — kompetent und zuverlässig.", "hw.peters@example.de"),
    ],
    cta={
        "title": "Brauchen Sie einen Handwerker?",
        "text": "Kostenloses Angebot in 24 Stunden — unverbindlich und zum Festpreis.",
        "button_label": "Angebot anfordern",
        "button_url": "/anfrage/",
    },
    enable_modules=["jobs", "booking", "customer_account"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=HANDWERKER_MENUS,
    hide_archetypes=["catalog"],  # kein Shop — leeren Sortiment-Teaser ausblenden
    job_samples=[
        {
            "title": "Angebot: Wohnzimmer & Flur streichen (ca. 60 m²)",
            "name": "Julia Becker",
            "email": "becker@example.de",
            "phone": "0221 9876543",
            "site_address": "Lindenweg 8, 50667 Köln",
            "description": "Wohnzimmer und Flur neu streichen, Wände vorbereiten, "
            "ein Akzentwand in Farbe. Bitte Festpreis.",
            "lines": [
                {"text": "Wände spachteln & grundieren", "qty": 60, "unit_price": "6.50"},
                {"text": "Anstrich 2-fach (weiß)", "qty": 60, "unit_price": "8.00"},
                {"text": "Akzentwand in Wunschfarbe", "qty": 1, "unit_price": "120.00"},
            ],
            "vat_rate": 19,
        },
        {
            "title": "Angebot: Bad modernisieren — Elektrik & Sanitär",
            "name": "Thomas Acar",
            "email": "acar@example.de",
            "site_address": "Rosenstraße 14, 50674 Köln",
            "description": "Gäste-WC modernisieren: neue Leuchten und Steckdosen, "
            "Waschtisch und Armatur tauschen.",
            "lines": [
                {
                    "text": "Elektro: Leuchten & Steckdosen (Material+Montage)",
                    "qty": 1,
                    "unit_price": "340.00",
                },
                {
                    "text": "Sanitär: Waschtisch + Armatur montieren",
                    "qty": 1,
                    "unit_price": "420.00",
                },
                {"text": "Demontage & Entsorgung", "qty": 1, "unit_price": "90.00"},
            ],
            "vat_rate": 19,
        },
    ],
    archetype_covers={
        "jobs": {
            "intro": "Schildern Sie Ihr Vorhaben — gern mit Fotos und Adresse. Sie erhalten "
            "ein unverbindliches Festpreis-Angebot.",
            "hero_kw": "craftsman,renovation",
            "gallery_kw": ["painter,wall", "bathroom,renovation", "electrician,work"],
        },
        "booking": {
            "intro": "Leistungen mit Festpreis oder kostenlose Vor-Ort-Beratung — Termin online wählen.",
            "hero_kw": "handyman,tools",
        },
    },
    services=[
        (
            "Vor-Ort-Beratung (kostenlos)",
            30,
            "0",
            "Wir kommen vorbei, schauen uns alles an und erstellen ein unverbindliches "
            "Festpreis-Angebot.",
            "",
            {
                # UA4-3: богатая карточка услуги + primary-CTA «Anfrage» (реш.2, A7).
                "attributes": [
                    "Kostenlos & unverbindlich",
                    "Festpreis-Angebot nach dem Termin",
                    "Meisterbetrieb, versichert",
                    "Einzugsgebiet: 25 km rund um den Betrieb",
                ],
                "faq": [
                    {
                        "q": "Was kostet die Vor-Ort-Beratung?",
                        "a": "Die Beratung vor Ort ist kostenlos und unverbindlich.",
                    },
                    {
                        "q": "Wie schnell bekomme ich einen Termin?",
                        "a": "In der Regel innerhalb von 2–3 Werktagen.",
                    },
                ],
                "primary_action": "request",
            },
        ),
        ("Maler: Zimmer streichen (bis 20 m²)", 180, "290"),
        ("Elektro: Steckdose/Schalter setzen", 45, "75"),
        ("Sanitär: Armatur tauschen", 60, "120"),
        ("Notdienst-Einsatz (Anfahrt)", 60, "89"),
    ],
    resources=[
        {
            "name": "Meister-Team",
            "type": "table",
            "capacity": 1,
            "start": "07:00",
            "end": "17:00",
            "slot": 30,
            "weekdays": range(0, 5),
        },
    ],
)

RETREAT_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Events", "type": "archetype", "target": "events"},
            {"label": "Lehrer", "type": "url", "target": "/lehrer/"},  # R3
            {"label": "Einzelsitzung", "type": "archetype", "target": "booking"},
            {"label": "Blog", "type": "url", "target": "/blog/"},  # RT4
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
    # R3: преподаватели как сущность (фильтр каталога + страницы учителей).
    teachers=[
        (
            "Mara Lind",
            "Retreatleitung & Yogalehrerin",
            "yoga,teacher,woman",
            "Mara begleitet seit 2016 Retreats am Waldrand. Ihr Hatha- und Yin-Yoga "
            "verbindet sanfte Praxis mit Achtsamkeit — herzlich und ohne Leistungsdruck.",
        ),
        (
            "Felix Sturm",
            "Achtsamkeits-Coach",
            "meditation,man",
            "Felix ist Achtsamkeits- und Meditationscoach. Er führt durch Atem- und "
            "Klangschalen-Einheiten und schafft Räume zum echten Loslassen.",
        ),
    ],
    trust={"since": "2016", "marks": ["Kleine Gruppen", "Zertifizierte Leitung", "Naturnah"]},
    reviews_seed=[
        (5, "Zwei Tage, die mich geerdet haben. Ich komme wieder.", "rt.johanna@example.de"),
        (5, "Kleine Gruppe, viel Raum, herzliche Begleitung.", "rt.daniel@example.de"),
        (4, "Genau die Pause, die ich gebraucht habe.", "rt.sandra@example.de"),
    ],
    cta={
        "title": "Zeit für dich.",
        "text": "Finde dein nächstes Retreat und sichere dir einen Platz.",
        "button_label": "Events ansehen",
        "button_url": "/veranstaltung/",
    },
    # RT4: журнал/блог ретрита — 2 опубликованные записи (новости/статьи).
    blog_posts=[
        (
            "5 Atemübungen für mehr Ruhe im Alltag",
            "Kleine Praxis, große Wirkung: so kommst du in stressigen Momenten zurück zu dir.",
            "Atem ist immer dabei — und doch nutzen wir ihn selten bewusst.\n\n"
            "1. Verlängertes Ausatmen: vier Zähler ein, sechs aus.\n"
            "2. Box-Breathing: 4–4–4–4.\n"
            "3. Bauchatmung im Liegen.\n\n"
            "Schon fünf Minuten täglich verändern, wie du auf Stress reagierst.",
            "meditation,breathing",
        ),
        (
            "Rückblick: Unser Waldwochenende im Mai",
            "Zwölf Menschen, ein Waldrand und viel Stille — ein paar Eindrücke.",
            "Das Mai-Retreat war ausgebucht — und es war wunderbar.\n\n"
            "Morgens Yoga im Tau, tagsüber Wanderungen, abends Lagerfeuer. "
            "Danke an alle, die dabei waren. Das nächste Wochenende ist schon in Planung.",
            "forest,retreat",
        ),
    ],
    enable_modules=["events", "booking", "orders", "customer_account", "stays", "jobs"],
    # R5 проживание на ретрите: типы номеров (общая/2-/1-местный) — анти-овербукинг
    # stays; weekend-retreat ниже offers_accommodation=True линкует их все.
    stay_units=[
        {
            "name": "Mehrbettzimmer (Bett)",
            "type": "bed",
            "qty": 8,
            "price": "35",
            "guests": 1,
            "description": "Bett im gemeinschaftlichen Schlafraum — günstig und gesellig.",
            "bed": "Einzelbett im Schlafsaal",
        },
        {
            "name": "Doppelzimmer",
            "type": "room",
            "qty": 4,
            "price": "70",
            "guests": 2,
            "description": "Gemütliches Zimmer für zwei — ideal zum Teilen.",
            "bed": "Doppelbett",
        },
        {
            "name": "Einzelzimmer",
            "type": "room",
            "qty": 3,
            "price": "95",
            "guests": 1,
            "description": "Ruhe und Privatsphäre im eigenen Zimmer.",
            "bed": "Einzelbett",
        },
    ],
    extras=[  # #7 доп-услуги к билету ретрита (scope events, разово)
        ("Bio-Mittagessen", "18", "events", False),
        ("Einzelzimmer-Zuschlag", "40", "events", False),
        ("Yogamatte-Verleih", "5", "events", False),
    ],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=RETREAT_MENUS,
    page_layouts={"events": "cols2"},  # RV3: грид крупных обложек на индексе ретритов
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
            # A6 ценовые тиры: ранняя цена / стандарт / шеринг-вариант
            "tiers": [
                ("Frühbucher (bis 30 Tage)", "260"),
                ("Standard", "290"),
                ("Mehrbettzimmer", "230"),
            ],
            "location": "Am Waldrand 3, Freiburg",
            "city": "Freiburg",
            "lat": "47.9650",  # R6 карта (Waldrand bei Freiburg)
            "lng": "7.8000",
            "category": "yoga",
            "level": "alle",
            "language": "de",
            "deposit_percent": 30,  # R4: бронь депозитом 30 %, остаток на месте
            "waiver_required": True,  # R8: подпись отказа (дефолтный текст)
            "offers_accommodation": True,  # R5: выбор типа номера на даты ретрита
            "description": "Zwei Tage Yoga, Meditation und Waldspaziergänge in kleiner Gruppe. "
            "Inklusive Programm, Begleitung und Tee-Pausen.",
            "program": [
                "Fr 16:00 — Ankommen & Auftakt-Meditation",
                "Sa 08:00 — Morgen-Yoga · 10:00 Achtsamkeitswanderung · 16:00 Klangschalen",
                "So 09:00 — Yin-Yoga · 12:00 Abschlusskreis",
            ],
            "questions": _RETREAT_QUESTIONS,
            # R1 структурированная анкета участника (питание/опыт/контакт/мед.).
            "registration_fields": [
                "country",
                "emergency_contact",
                "diet",
                "experience",
                "medical",
            ],
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
            "city": "Freiburg",
            "category": "achtsamkeit",
            "level": "anfaenger",
            "language": "de",
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
            "city": "Freiburg",
            "category": "klang",
            "level": "alle",
            "language": "de",
            "description": "Tiefenentspannung mit Klangschalen — ein ruhiger Abend zum Loslassen.",
        },
        {
            # RT2: онлайн/Zoom-событие — без места/карты, ссылка доступа после брони.
            "title": "Online: Morgen-Meditation per Zoom",
            "in_days": 4,
            "hour": 8,
            "duration_hours": 1,
            "capacity": 0,
            "price": "12",
            "category": "achtsamkeit",
            "level": "alle",
            "language": "de",
            "is_online": True,
            "online_url": "https://zoom.us/j/000000000?pwd=demo",
            "description": "Starte den Tag mit einer geführten Meditation — live per Zoom, "
            "ortsunabhängig. Den Zugangslink erhältst du nach der Anmeldung.",
        },
        {
            "title": "Sommer-Festival der Achtsamkeit",
            "in_days": 45,
            "hour": 11,
            "duration_hours": 8,
            "capacity": 0,  # без лимита мест
            "price": "15",
            "location": "Stadtpark Freiburg",
            "city": "Freiburg",
            "lat": "48.0100",  # R6 карта (Stadtpark)
            "lng": "7.8550",
            "category": "achtsamkeit",
            "level": "alle",
            "language": "mixed",
            "description": "Ein Tag voller Workshops, Live-Musik und Ständen rund um Achtsamkeit.",
            "program": [
                "11:00 — Eröffnung & Mitmach-Yoga",
                "13:00 — Workshops (Atem, Journaling, Klang)",
                "18:00 — Live-Musik & Ausklang",
            ],
        },
        {
            "title": "Frauen-Retreat: Kraft & Ruhe",
            "in_days": 90,
            "hour": 16,
            "duration_days": 2,
            "capacity": 12,
            "price": "320",
            # R11: per-tier вместимость (3-й столбец) — Frühbucher-/Mehrbett-контингент
            # ограничен, Standard без отдельного лимита (общий capacity).
            "tiers": [
                ("Frühbucher (bis 45 Tage)", "290", "4"),
                ("Standard", "320"),
                ("Mehrbettzimmer", "260", "6"),
            ],
            "location": "Am Waldrand 3, Freiburg",
            "city": "Freiburg",
            "lat": "47.9650",
            "lng": "7.8000",
            "category": "yoga",
            "level": "alle",
            "language": "de",
            "deposit_percent": 30,
            # R12: гибкая отмена — бесплатно до 14 дней до начала, затем без возврата.
            "cancellation": "flexible",
            "free_cancel_days": 14,
            # R10: рассрочка — депозит + равные доли до 21 дня до старта.
            "allow_installments": True,
            "installment_mode": "until_event",
            "installment_count": 4,
            "installment_min_cents": 20000,
            "installment_lead_days": 21,
            "offers_accommodation": True,
            "description": "Ein Wochenende nur für Frauen: Yoga, Kreis-Arbeit und Waldzeit "
            "in kleiner, vertrauter Runde.",
            "program": [
                "Fr 16:00 — Ankommen & Eröffnungskreis",
                "Sa 08:00 — Morgen-Yoga · 10:00 Waldzeit · 16:00 Frauenkreis",
                "So 09:00 — Yin-Yoga · 12:00 Abschluss",
            ],
            "questions": _RETREAT_QUESTIONS,
            "registration_fields": ["country", "emergency_contact", "diet", "experience"],
            "photos": _RETREAT_PHOTOS,
            "details": _RETREAT_LANDING,
        },
        {
            "title": "Ayurveda-Detox-Wochenende",
            "in_days": 160,
            "hour": 15,
            "duration_days": 3,
            "capacity": 10,
            "price": "540",
            "tiers": [
                ("Frühbucher (bis 60 Tage)", "490"),
                ("Standard", "540"),
                ("Mehrbettzimmer", "440"),
            ],
            "location": "Am Waldrand 3, Freiburg",
            "city": "Freiburg",
            "lat": "47.9650",
            "lng": "7.8000",
            "category": "ayurveda",
            "level": "alle",
            "language": "de",
            "deposit_percent": 40,
            "waiver_required": True,  # R8
            "cancellation": "non_refundable",  # R12: невозвратный тариф (демо-вариант)
            # R10: рассрочка — фикс 3 помесячные доли (дорогой ретрит, от 200 €).
            "allow_installments": True,
            "installment_mode": "fixed",
            "installment_count": 3,
            "installment_min_cents": 20000,
            "offers_accommodation": True,
            "description": "Drei Tage Ayurveda: leichte Küche, Yoga, Ölbehandlungen und "
            "Ruhe zum Auftanken.",
            "program": [
                "Fr 15:00 — Ankommen & Auftakt",
                "Sa — Yoga · Ayurveda-Küche · Behandlungen",
                "So — Abschluss bis 14:00",
            ],
            "questions": _RETREAT_QUESTIONS,
            "registration_fields": ["country", "emergency_contact", "diet", "medical"],
            "photos": _RETREAT_PHOTOS,
            "details": _RETREAT_LANDING,
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

SHOP_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog"},
            {"label": "Aktionen", "type": "archetype", "target": "promotions"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🛒"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
        ],
    },
}

# Retail-кит «Hofladen Sonnenfeld» — интернет-магазин: варианты (R1),
# Grundpreis €/kg|l (R2), остаток (R3), GTIN/EAN (A1), доставка с PLZ-зонами (A2).
SHOP = DemoKit(
    key="shop",
    label="Hofladen Sonnenfeld",
    business_type="retail",
    subdomain="shop",
    accent="#65a30d",  # Hofladen-Grün
    hero_image_kw="farm,shop",
    hero_title="Hofladen Sonnenfeld",
    hero_text="Frisch vom Hof — Obst, Gemüse und Spezialitäten aus der Region. "
    "Online bestellen, abholen oder liefern lassen.",
    about_title="Über den Hofladen",
    about_text="Seit drei Generationen bauen wir an, was bei uns im Laden liegt. "
    "Regional, saisonal und ehrlich — jetzt auch online.",
    nav_style="classic",
    address="Feldweg 1, 40221 Düsseldorf",
    opening_hours_text="Mo–Sa 8:00–18:00",
    opening_hours={d: ("08:00", "18:00") for d in range(6)},
    gallery_kw=["farm,vegetables", "market,stall", "fresh,fruit", "farm,field", "cheese", "honey"],
    faq=[
        (
            "Wie funktioniert die Lieferung?",
            "In unserem Liefergebiet bringen wir Ihre Bestellung "
            "nach Hause — die Kosten richten sich nach Ihrer PLZ.",
        ),
        (
            "Gibt es einen Mindestbestellwert?",
            "Ja, für die Lieferung; zur Abholung gibt es keinen.",
        ),
        ("Sind die Produkte bio?", "Vieles ist bio-zertifiziert — am Produkt ausgewiesen."),
        ("Kann ich auch abholen?", "Ja, Click & Collect ist kostenlos."),
    ],
    testimonials=[
        ("Familie Becker", "Endlich Hofqualität bequem nach Hause. Top!"),
        ("Renate W.", "Frischer geht's nicht — und die Lieferung ist super zuverlässig."),
    ],
    process=[
        ("Aussuchen", "Im Sortiment stöbern und in den Korb legen."),
        ("Bestellen", "Abholung oder Lieferung wählen."),
        ("Genießen", "Frische vom Hof — ganz bequem."),
    ],
    trust={"since": "1962", "marks": ["Eigener Anbau", "Bio-zertifiziert", "Regional"]},
    usp=[  # A.3: полоса доверия под hero (онлайн-магазин)
        ("shipping", "Versand ab 4,90 €"),
        ("returns", "14 Tage Widerruf"),
        ("payment", "Sichere Zahlung"),
        ("bio", "Bio-zertifiziert"),
    ],
    reviews_seed=[
        (5, "Frische Bio-Ware, schnell geliefert. Schmeckt wie früher!", "sh.koehler@example.de"),
        (5, "Super Qualität und nette Kommunikation. Sehr empfehlenswert.", "sh.anke@example.de"),
        (4, "Tolle Auswahl an regionalen Produkten.", "sh.markus@example.de"),
    ],
    # A1/A2: отзывы о товаре (на первых товарах каталога) — (idx, ★, имя, email, текст).
    product_reviews=[
        (
            0,
            5,
            "Familie Köhler",
            "sh.koehler@example.de",
            "Knackig frisch und aromatisch — kommt wieder in den Korb.",
        ),
        (0, 4, "Anke S.", "sh.anke@example.de", "Gute Qualität, etwas klein, aber lecker."),
        (
            1,
            5,
            "Markus B.",
            "sh.markus@example.de",
            "Top Ware, schnelle Lieferung. Sehr zu empfehlen!",
        ),
    ],
    cta={
        "title": "Frisch vom Feld in Ihren Korb",
        "text": "Stöbern Sie im Sortiment und lassen Sie sich beliefern.",
        "button_label": "Zum Sortiment",
        "button_url": "/sortiment/",
    },
    enable_modules=["orders", "loyalty"],
    storefront_root="home",
    seed_records=True,
    menus=SHOP_MENUS,
    loyalty={"label": "Hof-Stempelkarte", "stamps": 10, "reward": "1 kg Äpfel gratis"},
    delivery={
        "enabled": True,
        "fee_cents": 490,
        "free_cents": 4000,  # ab 40 € frei
        "min_cents": 2000,  # Mindestbestellwert Lieferung 20 €
        "pickup_min_cents": 0,
        "area": "Düsseldorf und Umgebung (PLZ 40xxx, 41xxx)",
        # PLZ-зоны (A2a): своя цена/порог/мин по префиксу; самый длинный выигрывает.
        "zones": [
            {"plz": "402", "fee_cents": 290, "free_cents": 3500, "min_cents": 1500},
            {"plz": "40", "fee_cents": 490, "free_cents": 4000, "min_cents": 2000},
            {"plz": "41", "fee_cents": 690, "free_cents": 5000, "min_cents": 3000},
        ],
    },
    categories=[
        (
            "Obst & Gemüse",
            "obst-gemuese",
            [
                # весовой товар: Grundpreis €/kg, остаток в kg, EAN
                _p(
                    "Äpfel 'Elstar'",
                    "3.90",
                    "Knackig-süß, vom eigenen Hof.",
                    "apples",
                    unit="kg",
                    content=1,
                    stock=45,
                    gtin="4012345000019",
                    badge="Bio",
                ),
                _p(
                    "Kartoffeln, 2-kg-Sack",
                    "3.20",
                    "Festkochend, regional.",
                    "potatoes",
                    unit="kg",
                    content=2,
                    stock=30,
                    gtin="4012345000026",
                ),
                _p(
                    "Bio-Tomaten, 500 g",
                    "2.80",
                    "Sonnengereift.",
                    "tomatoes",
                    unit="kg",
                    content=0.5,
                    stock=12,
                    gtin="4012345000033",
                    badge="Bio",
                ),
                _p(
                    "Karotten, 1-kg-Bund",
                    "1.90",
                    "Mit Grün, erntefrisch.",
                    "carrots",
                    unit="kg",
                    content=1,
                    stock=20,
                    gtin="4012345000040",
                ),
            ],
        ),
        (
            "Hofladen-Spezialitäten",
            "spezialitaeten",
            [
                # варианты с собственным остатком/Grundpreis/EAN (R1+R2+R3+A1)
                _p(
                    "Bio-Honig",
                    "5.90",
                    "Aus eigener Imkerei.",
                    "honey,jar",
                    unit="kg",
                    content=0.25,
                    gtin="4012345000057",
                    badge="Bio",
                    variants=[
                        {
                            "label": "250 g",
                            "price": "5.90",
                            "content": 0.25,
                            "stock": 24,
                            "gtin": "4012345000057",
                        },
                        {
                            "label": "500 g",
                            "price": "9.90",
                            "content": 0.5,
                            "stock": 8,
                            "gtin": "4012345000064",
                        },
                    ],
                ),
                _p(
                    "Naturtrüber Apfelsaft, 1 L",
                    "2.40",
                    "100 % Direktsaft.",
                    "apple,juice",
                    unit="l",
                    content=1,
                    stock=40,
                    gtin="4012345000071",
                ),
                _p(
                    "Eier vom Hof, 10er",
                    "3.50",
                    "Aus Freilandhaltung.",
                    "eggs",
                    stock=15,
                    gtin="4012345000088",
                ),
                _p(
                    "Erdbeer-Marmelade, 340 g",
                    "3.90",
                    "Hausgemacht.",
                    "jam,jar",
                    unit="kg",
                    content=0.34,
                    stock=6,
                    gtin="4012345000095",
                ),
            ],
        ),
        (
            "Käse & Wurst",
            "kaese-wurst",
            [
                _p(
                    "Bergkäse am Stück, 400 g",
                    "6.80",
                    "Würzig gereift.",
                    "cheese,wheel",
                    unit="kg",
                    content=0.4,
                    stock=10,
                    gtin="4012345000101",
                    allergens=["milk"],
                ),
                _p(
                    "Landwurst",
                    "4.50",
                    "Luftgetrocknet, nach Hausrezept.",
                    "sausage",
                    stock=14,
                    gtin="4012345000118",
                    variants=[
                        {"label": "150 g", "price": "4.50", "content": 0.15, "stock": 14},
                        {"label": "300 g", "price": "8.20", "content": 0.3, "stock": 7},
                    ],
                ),
                _p(
                    "Bauernbutter, 250 g",
                    "2.60",
                    "Frisch gebuttert.",
                    "butter",
                    unit="kg",
                    content=0.25,
                    stock=18,
                    gtin="4012345000125",
                    allergens=["milk"],
                ),
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
    HANDWERKER.key: HANDWERKER,
    RETREAT.key: RETREAT,
    SHOP.key: SHOP,
}


def _kit_sections(kit: DemoKit) -> list[dict]:
    """Раскладка секций кита: фото-hero, меню, акции, галерея, отзывы, FAQ, CTA, контакты."""
    return [
        {"key": "hero", "enabled": True},
        # A.3 (T-B): полоса доверия сразу под hero (если заданы пункты).
        {"key": "usp_bar", "enabled": bool(kit.usp)},
        # H2: поиск размещения по датам сразу под hero — для отелей/пансионов.
        {"key": "stay_search", "enabled": bool(kit.stay_units)},
        # Карточки номеров прямо на главной — для отелей/пансионов.
        {"key": "stay_rooms", "enabled": bool(kit.stay_units)},
        # A3: блок услуг «Leistungen & Preise» — если у кита есть услуги (booking).
        {"key": "services", "enabled": bool(kit.services)},
        {"key": "archetypes", "enabled": kit.enable_archetypes_section},  # S2: «Unsere Bereiche»
        # Акции/товары — только если у кита есть каталог (иначе пустые секции).
        {"key": "promotions", "enabled": bool(kit.categories)},
        {"key": "products", "enabled": bool(kit.categories)},
        {"key": "process", "enabled": bool(kit.process)},
        {"key": "team", "enabled": bool(kit.team)},
        {"key": "gallery", "enabled": bool(kit.gallery_kw)},
        # A7: «Vorher / Nachher» — кейсы санации (если заданы у кита).
        {"key": "before_after", "enabled": bool(kit.before_after)},
        {"key": "testimonials", "enabled": bool(kit.testimonials)},
        {"key": "trust", "enabled": bool(kit.trust)},
        {"key": "reviews", "enabled": bool(kit.reviews_seed)},  # G8/#6: отзывы клиентов
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

    def _make_product(item, category):
        nonlocal lock
        content = item.get("content")
        stock = item.get("stock")
        name_i18n = _i18n_text(item["name"])
        product = Product.objects.create(
            name=name_i18n,
            description=_i18n_text(item["desc"]),
            base_price=Decimal(item["price"]),
            category=category,
            images=[_image_ref(item["img"], lock, name_i18n.get("de", ""))],
            allergens=item["allergens"],
            diets=item.get("diets", []),  # A4 диет-теги
            badge=item.get("badge", ""),
            unit=item.get("unit", ""),  # R2 Grundpreis
            content_amount=Decimal(str(content)) if content is not None else None,
            stock_quantity=stock,  # R3 остаток (None = без учёта)
            gtin=item.get("gtin", ""),  # A1 EAN
            sku=item.get("sku", ""),
            is_active=True,
            is_featured=(len(created_products) < 3),
            metadata={"demo": True},
        )
        lock += 1
        for vsort, v in enumerate(item["variants"]):
            # Вариант — кортеж (label, price) ИЛИ dict с остатком/Grundpreis/EAN.
            if isinstance(v, dict):
                vc = v.get("content")
                ProductVariant.objects.create(
                    product=product,
                    label=v["label"],
                    price=Decimal(str(v["price"])),
                    content_amount=Decimal(str(vc)) if vc is not None else None,
                    stock_quantity=v.get("stock"),
                    gtin=v.get("gtin", ""),
                    sku=v.get("sku", ""),
                    sort_order=vsort,
                )
            else:
                vlabel, vprice = v
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
        return product

    def _make_category(entry, sort, parent=None):
        # entry: (name, slug, items) ИЛИ (name, slug, items, children). name —
        # строка (de) или {de,en}. children — подкатегории той же формы (1 уровень,
        # магазин→подкатегории). Первый товар категории — в category_firsts (S6).
        name, slug, items = entry[0], entry[1], entry[2]
        children = entry[3] if len(entry) > 3 else []
        category = Category.objects.create(
            name=_i18n_text(name),
            slug=f"demo-{slug}",
            sort_order=sort,
            is_active=True,
            parent=parent,
        )
        refs["categories"].append(str(category.pk))
        first_in_cat = True
        for item in items:
            product = _make_product(item, category)
            if first_in_cat:
                category_firsts.append(product)
                first_in_cat = False
        for csort, child in enumerate(children):
            _make_category(child, csort, parent=category)
        return category

    for sort, entry in enumerate(kit.categories):
        _make_category(entry, sort)

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
        from apps.loyalty.models import Voucher

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
    _seed_kit_reviews(tenant, kit)
    _seed_product_reviews(kit, created_products)
    _seed_blog_posts(tenant, kit)
    if kit.extras:  # #7 универсальные доп-услуги (Extra)
        from apps.core.models import Extra

        for sort, (label, price, scope, per_night) in enumerate(kit.extras):
            Extra.objects.create(
                label=label,
                price_cents=int(Decimal(str(price)) * 100),
                scope=scope,
                per_night=per_night,
                sort_order=sort,
                is_active=True,
            )

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
            # M20U-2: слайдер баннеров (если у кита заданы слайды).
            "heroes": [
                {
                    "image": demo_image(h.get("image_kw", ""), w=1600, h=600, lock=980 + i),
                    "title": h.get("title", ""),
                    "text": h.get("text", ""),
                    "button_label": h.get("button_label", ""),
                    "button_url": h.get("button_url", ""),
                }
                for i, h in enumerate(kit.heroes)
            ],
            "section_titles": kit.section_titles or {},
            # M20U-7 (per-page): раскладки страниц-листингов (пусто → дефолт страницы).
            "catalog_layout": {"preset": kit.page_layouts.get("catalog", "")},
            "stay_index_layout": {"preset": kit.page_layouts.get("stay_index", ""), "mobile": 1},
            "events_index_layout": {"preset": kit.page_layouts.get("events", "")},
            "detail_related_layout": {"preset": kit.page_layouts.get("related", "")},
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
            "usp_bar": [{"icon": ic, "label": lbl} for ic, lbl in kit.usp],
            "gallery": [
                {"url": demo_image(kw, lock=500 + i), "alt": {"de": kit.label}}
                for i, kw in enumerate(kit.gallery_kw)
            ],
            "gallery_video": kit.gallery_video,
            "jobs_vehicle": kit.jobs_vehicle,  # A9: Kfz-Werkstatt — структурные авто-поля
            "before_after": [
                {
                    "before": demo_image(bk, w=600, h=450, lock=560 + i),
                    "after": demo_image(ak, w=600, h=450, lock=580 + i),
                    "text": txt,
                }
                for i, (bk, ak, txt) in enumerate(kit.before_after)
            ],
            "nav": {**siteconfig.default_nav(), "style": kit.nav_style},
            "demo": refs,
            # i18n (двуязычная витрина): оверлей переводов текстов витрины (normalize
            # сохраняет поддерживаемые локали; localize накладывает перед рендером).
            "i18n": kit.i18n,
            # M20U-2 (slider) EN: переводы баннеров кладём в оверлей heroes по индексу.
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
    if kit.service_area_plz or kit.service_area_note:  # A7: зона обслуживания
        tenant.service_area_plz = kit.service_area_plz
        tenant.service_area_note = kit.service_area_note
        update_fields += ["service_area_plz", "service_area_note"]
    tenant.save(update_fields=update_fields)
    return True


def _seed_kit_reviews(tenant, kit: DemoKit) -> None:
    """G8/#6: отзывы клиентов в SHARED BusinessReview (public) + пересчёт рейтинга.

    Кросс-схемно (public): PortalUser + BusinessReview(tenant_schema). Включает
    звёзды на витрине/в агрегаторе и блок «reviews». Демо-тенант одноразовый."""
    if not kit.reviews_seed:
        return
    from django_tenants.utils import schema_context

    try:
        with schema_context("public"):
            from apps.aggregator import reviews as agg_reviews
            from apps.aggregator.models import BusinessReview, PortalUser

            for rating, comment, email in kit.reviews_seed:
                author, _ = PortalUser.objects.get_or_create(email=email)
                BusinessReview.objects.update_or_create(
                    tenant_schema=tenant.schema_name,
                    author=author,
                    defaults={
                        "rating": rating,
                        "comment": comment,
                        "status": BusinessReview.STATUS_PUBLISHED,
                    },
                )
            agg_reviews.recompute_rating(tenant.schema_name)
    except Exception:  # noqa: BLE001 — отзывы не должны рушить провижининг кита
        pass


def _seed_product_reviews(kit: DemoKit, created_products: list) -> None:
    """A1/A2: отзывы о товаре (TENANT ProductReview) на демо-товарах кита.

    Создаём опубликованные отзывы напрямую (демо доверенный — без проверки заказа,
    которая работает на витрине). Вызывается в схеме тенанта."""
    if not kit.product_reviews:
        return
    from apps.catalog.models import ProductReview

    for idx, rating, name, email, comment in kit.product_reviews:
        if not isinstance(idx, int) or idx >= len(created_products):
            continue
        ProductReview.objects.update_or_create(
            product=created_products[idx],
            email=email.lower(),
            defaults={
                "rating": rating,
                "author_name": name,
                "comment": comment,
                "is_published": True,
            },
        )


def _seed_blog_posts(tenant, kit: DemoKit) -> None:
    """RT4: опубликованные записи блога (events.BlogPost). Вызывать в схеме тенанта."""
    if not kit.blog_posts or not tenant.is_module_active("events"):
        return
    from django.utils import timezone
    from django.utils.text import slugify

    from apps.events.models import BlogPost

    now = timezone.now()
    for i, (title, excerpt, body, cover_kw) in enumerate(kit.blog_posts):
        base = slugify(title) or f"post-{i}"
        slug, n = base, 1
        while BlogPost.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        BlogPost.objects.create(
            title=title,
            slug=slug,
            excerpt=excerpt,
            body=body,
            cover={"url": demo_image(cover_kw, w=800, h=450, lock=700 + i)} if cover_kw else {},
            is_published=True,
            published_at=now - timedelta(days=7 * i),
        )


def _seed_kit_modules(tenant, kit: DemoKit, refs: dict) -> None:
    """Услуги/ресурсы/номера/события кита (под активный модуль)."""
    from datetime import time

    is_active = tenant.is_module_active
    if kit.resources and is_active("booking"):
        from apps.booking.models import AvailabilityRule, Resource

        refs["resources"] = []
        for ri, r in enumerate(kit.resources):
            sh, sm = (int(x) for x in r["start"].split(":"))
            eh, em = (int(x) for x in r["end"].split(":"))
            # A3: профиль мастера — title/bio/photo_kw (для type=staff).
            photo_kw = r.get("photo_kw", "")
            photo = (
                {"url": demo_image(photo_kw, w=400, h=400, lock=660 + ri), "alt": {"de": r["name"]}}
                if photo_kw
                else {}
            )
            resource = Resource.objects.create(
                name=r["name"],
                type=r.get("type", "table"),
                capacity=r.get("capacity", 1),
                counts_party_size=r.get("counts_party_size", False),
                title=r.get("title", ""),
                bio=r.get("bio", ""),
                photo=photo,
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
        for i, spec in enumerate(kit.services):
            # (name, minutes, price[, description[, image_kw[, rich]]]) — A3/UA4-3
            # богатая карточка. rich (dict) — attributes/faq/primary_action (UA4-3).
            name, minutes, price = spec[0], spec[1], spec[2]
            desc = spec[3] if len(spec) > 3 else ""
            image_kw = spec[4] if len(spec) > 4 else ""
            rich = spec[5] if len(spec) > 5 and isinstance(spec[5], dict) else {}
            image = (
                {"url": demo_image(image_kw, w=600, h=400, lock=620 + i), "alt": {"de": name}}
                if image_kw
                else {}
            )
            svc = Service.objects.create(
                name=name,
                description=desc,
                image=image,
                duration_minutes=minutes,
                price_cents=int(Decimal(price) * 100),
                attributes=rich.get("attributes", []),
                faq=rich.get("faq", []),
                primary_action=rich.get("primary_action", ""),
            )
            refs["services"].append(str(svc.pk))
    if kit.pass_plans and is_active("booking"):  # A3/G9b: тарифы Mehrfachkarte
        from apps.booking.models import PassPlan, Service

        svc_ids = refs.get("services", [])
        for p in kit.pass_plans:
            service = None
            si = p.get("service_index")
            if si is not None and si < len(svc_ids):
                service = Service.objects.filter(pk=svc_ids[si]).first()
            PassPlan.objects.create(
                label=p["label"],
                credits=p.get("credits", 10),
                price_cents=int(Decimal(str(p.get("price", "0"))) * 100),
                valid_days=p.get("valid_days", 0),
                service=service,
                is_active=True,
            )
    if kit.stay_units and is_active("stays"):
        from datetime import date

        from apps.stays.models import SeasonRate, StayUnit

        refs["stay_units"] = []
        for idx, spec in enumerate(kit.stay_units):
            # Краткий кортеж (name, type, qty, price, guests) ИЛИ богатый dict
            # (с описанием, фото, депозитом и сезонными тарифами номера).
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
                    deposit_cents=int(Decimal(str(spec.get("deposit", "0"))) * 100),
                    area_sqm=spec.get("area", 0),  # H3
                    bed_type=spec.get("bed", ""),  # H3
                    amenities=spec.get("amenities", []),  # H3
                    images=imgs,
                    is_active=True,
                )
                for s in spec.get("season", []):  # A5a сезонные тарифы
                    SeasonRate.objects.create(
                        unit=unit,
                        label=s.get("label", ""),
                        start_date=date.fromisoformat(s["start"]),
                        end_date=date.fromisoformat(s["end"]),
                        price_cents=int(Decimal(str(s["price"])) * 100),
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
    if (kit.kurtaxe or kit.house_rules or kit.auto_discounts) and is_active("stays"):
        from apps.stays.models import StaySettings  # H9 Kurtaxe + H6 Hausordnung + G4 авто-скидки

        settings_obj = StaySettings.load()
        if kit.kurtaxe:
            settings_obj.kurtaxe_cents = int(Decimal(str(kit.kurtaxe)) * 100)
        if kit.house_rules:
            settings_obj.house_rules = kit.house_rules
        if kit.auto_discounts:  # G4: список правил {kind, threshold, percent}
            settings_obj.auto_discount_rules = list(kit.auto_discounts)
        settings_obj.save(
            update_fields=["kurtaxe_cents", "house_rules", "auto_discount_rules", "updated_at"]
        )
    if kit.stay_promo and is_active("stays"):  # H4a промокод брони
        from apps.loyalty.models import Voucher

        Voucher.objects.get_or_create(
            code=kit.stay_promo["code"],
            defaults={
                "label": kit.stay_promo.get("label", "")[:120],
                "discount_percent": kit.stay_promo.get("percent") or None,
                "discount_cents": int(Decimal(str(kit.stay_promo["cents"])) * 100)
                if kit.stay_promo.get("cents")
                else None,
                "max_uses": 0,  # безлимит для демо
            },
        )
    if kit.rate_plans and is_active("stays"):  # H1 тарифы (на тенанта)
        from apps.stays.models import RatePlan

        for spec in kit.rate_plans:
            RatePlan.objects.create(
                name=spec["name"],
                description=spec.get("description", ""),
                percent_adjust=int(spec.get("percent", 0)),
                surcharge_cents=int(Decimal(str(spec.get("surcharge", "0"))) * 100),
                meal_plan=spec.get("meal", "none"),
                cancellation=spec.get("cancellation", "flexible"),
                free_cancel_days=int(spec.get("free_cancel_days", 0)),
                prepayment_percent=int(spec.get("prepayment", 0)),  # G7
                sort_order=int(spec.get("sort", 0)),
                is_active=True,
            )
    if kit.loyalty and is_active("loyalty"):
        from apps.loyalty.models import LoyaltyProgram

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
        # R3: преподаватели/ведущие — засеять и связать со всеми событиями.
        refs["teachers"] = []
        if kit.teachers:
            from apps.events.models import Teacher

            for tidx, t in enumerate(kit.teachers):
                name, title = t[0], (t[1] if len(t) > 1 else "")
                photo_kw = t[2] if len(t) > 2 else ""
                bio = t[3] if len(t) > 3 else ""
                teacher = Teacher.objects.create(
                    name=name,
                    title=title,
                    bio=bio,
                    photo_url=_image_ref(photo_kw, 8700 + tidx, name)["url"] if photo_kw else "",
                    sort_order=tidx,
                    is_active=True,
                )
                refs["teachers"].append(str(teacher.pk))
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
                    # i18n (PR-B): двуязычные заголовок/описание (если кит дал *_en).
                    title_i18n=_i18n_text({"de": spec["title"], "en": spec.get("title_en", "")}),
                    description_i18n=_i18n_text(
                        {"de": spec.get("description", ""), "en": spec.get("description_en", "")}
                    ),
                    location=spec.get("location", ""),
                    city=spec.get("city", ""),  # R2 таксономия
                    latitude=spec.get("lat"),  # R6 карта
                    longitude=spec.get("lng"),
                    category=spec.get("category", ""),
                    level=spec.get("level", ""),
                    language=spec.get("language", ""),
                    is_online=spec.get("is_online", False),  # RT2 онлайн/Zoom
                    online_url=spec.get("online_url", ""),
                    starts_at=starts,
                    ends_at=ends,
                    capacity=spec.get("capacity", 0),
                    price_cents=int(Decimal(str(spec.get("price", "0"))) * 100),
                    deposit_percent=spec.get("deposit_percent", 0),  # R4 онлайн-предоплата
                    waiver_required=spec.get("waiver_required", False),  # R8 отказ
                    waiver_text=spec.get("waiver_text", ""),
                    cancellation=spec.get("cancellation", Event.CANCEL_FLEXIBLE),  # R12 политика
                    free_cancel_days=spec.get("free_cancel_days", 0),
                    allow_installments=spec.get("allow_installments", False),  # R10 рассрочка
                    installment_mode=spec.get("installment_mode", Event.INSTALLMENT_UNTIL_EVENT),
                    installment_count=spec.get("installment_count", 3),
                    installment_min_cents=spec.get("installment_min_cents", 0),
                    installment_lead_days=spec.get("installment_lead_days", 14),
                    questions=list(spec.get("questions", [])),
                    program=list(spec.get("program", [])),
                    images=imgs,
                    details=_evdetails.normalize(raw_details),
                    tiers=_evdetails.normalize_tiers(spec.get("tiers", [])),  # A6 ценовые тиры
                    registration_fields=list(spec.get("registration_fields", [])),  # R1 анкета
                    offers_accommodation=spec.get("offers_accommodation", False),  # R5
                    status=Event.STATUS_PUBLISHED,
                )
                # R5: привязать все засеянные типы номеров как варианты проживания.
                if spec.get("offers_accommodation") and refs.get("stay_units"):
                    from apps.stays.models import StayUnit

                    event.accommodation_units.set(
                        StayUnit.objects.filter(pk__in=refs["stay_units"])
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
            # R3: связать всех засеянных преподавателей с событием.
            if refs.get("teachers"):
                event.teachers.set(Teacher.objects.filter(pk__in=refs["teachers"]))
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
        from apps.orders.models import Order
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
        # При активной доставке — ещё один заказ с доставкой (показать кабинет A2).
        if kit.delivery.get("enabled"):
            try:
                create_order(
                    items=[(products[0], 3)],
                    name="Sabine Lieb",
                    email="sabine@example.de",
                    phone="0151 9988776",
                    fulfillment=Order.FULFILLMENT_DELIVERY,
                    shipping_address="Beispielstraße 5, 40221 Düsseldorf",
                    shipping_cents=kit.delivery.get("fee_cents", 0),
                )
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
                    # A9: структурные данные авто (Werkstatt)
                    vehicle_plate=spec.get("vehicle_plate", ""),
                    vehicle_hsn=spec.get("vehicle_hsn", ""),
                    vehicle_tsn=spec.get("vehicle_tsn", ""),
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

    # Mehrfachkarte (A3/G9b): выдать одну карту по первому тарифу.
    if kit.pass_plans and is_active("booking"):
        from apps.booking.models import PassPlan
        from apps.booking.services import issue_pass

        plan = PassPlan.objects.order_by("price_cents").first()
        if plan is not None:
            try:
                issue_pass(
                    name="Petra Klein",
                    email="petra@example.de",
                    label=plan.label,
                    credits=plan.credits,
                    service=plan.service,
                )
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
                    # R8: подписываем waiver (на случай waiver_required события).
                    book_ticket(
                        ev,
                        name=who,
                        email=mail,
                        quantity=qty,
                        auto_confirm=True,
                        waiver_signed_name=who,
                        health_confirmed=True,
                        signed_ip="127.0.0.1",
                    )
                except Exception:
                    pass
            # R1: пара записей в лист ожидания (как будто событие популярно).
            from apps.events.models import EventWaitlistEntry

            for who, mail, qty in [
                ("Sandra Vogel", "sandra.wl@example.de", 1),
                ("Tom Berger", "tom.wl@example.de", 2),
            ]:
                try:
                    EventWaitlistEntry.objects.get_or_create(
                        event=ev, email=mail, defaults={"name": who, "party_size": qty}
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # Übernachtungen (stays)
    if is_active("stays"):
        from datetime import timedelta

        from django.utils import timezone

        from apps.stays.models import RatePlan, StayUnit
        from apps.stays.services import book_stay

        units = list(StayUnit.objects.filter(is_active=True).order_by("id"))
        if units:
            from apps.core import extras as extras_engine
            from apps.core.fsm import IllegalTransition
            from apps.core.models import Extra
            from apps.stays.models import GuestRegistration
            from apps.stays.state_machine import StayBookingSM

            today = timezone.localdate()
            rate_plans = list(RatePlan.objects.filter(is_active=True))

            def _u(i):
                return units[i % len(units)]

            multi = max(units, key=lambda u: u.quantity)  # G5: номер с quantity ≥ 2
            extra_ids = list(
                Extra.objects.filter(scope="stays", is_active=True).values_list("id", flat=True)[:2]
            )
            # Несколько демо-броней: разные номера/даты/статусы/тарифы (+промокод,
            # +Extras, +мультикомната, +прошлая бронь для отчётов, +pending, +отмена).
            # dict: unit, in_days, nights, who, mail, guests, rooms, voucher, extras, status.
            samples = [
                {
                    "unit": _u(0),
                    "in_days": 6,
                    "nights": 3,
                    "who": "Anna Berg",
                    "mail": "anna@example.de",
                    "guests": 2,
                },
                {
                    "unit": _u(1),
                    "in_days": 20,
                    "nights": 5,
                    "who": "Familie Lang",
                    "mail": "lang@example.de",
                    "guests": 4,
                },
                {
                    "unit": multi,
                    "in_days": 35,
                    "nights": 2,
                    "who": "Reisegruppe Sommer",
                    "mail": "gruppe@example.de",
                    "guests": multi.max_guests * 2,
                    "rooms": 2,
                },
                {
                    "unit": _u(2),
                    "in_days": 12,
                    "nights": 4,
                    "who": "Tom Fischer",
                    "mail": "tom@example.de",
                    "guests": 2,
                    "voucher": "SOMMER10",
                    "extras": extra_ids,
                },
                {
                    "unit": _u(0),
                    "in_days": -10,
                    "nights": 3,
                    "who": "Klaus Weber",
                    "mail": "klaus@example.de",
                    "guests": 2,
                    "status": "fulfilled",
                },
                {
                    "unit": _u(3),
                    "in_days": 3,
                    "nights": 2,
                    "who": "Lisa Wolf",
                    "mail": "lisa@example.de",
                    "guests": 2,
                    "status": "pending",
                },
                {
                    "unit": _u(1),
                    "in_days": 50,
                    "nights": 4,
                    "who": "Peter Sand",
                    "mail": "peter@example.de",
                    "guests": 2,
                    "status": "cancelled",
                },
            ]
            created_bookings = []
            for idx, s in enumerate(samples):
                unit = s["unit"]
                rooms = max(1, min(s.get("rooms", 1), unit.quantity))
                guests = max(1, min(s["guests"], unit.max_guests * rooms))
                nights = max(s["nights"], unit.min_nights)
                arrival = today + timedelta(days=s["in_days"])
                rate_plan = rate_plans[idx % len(rate_plans)] if rate_plans else None
                status = s.get("status", "confirmed")
                snap = (
                    extras_engine.snapshot(s["extras"], "stays", nights=nights)
                    if s.get("extras")
                    else None
                )
                try:
                    booking = book_stay(
                        unit,
                        arrival=arrival,
                        departure=arrival + timedelta(days=nights),
                        name=s["who"],
                        email=s["mail"],
                        guests=guests,
                        auto_confirm=status != "pending",
                        rate_plan=rate_plan,
                        rooms=rooms,
                        voucher_code=s.get("voucher", ""),
                        extras=snap,
                    )
                except Exception:
                    continue
                created_bookings.append(booking)
                # Перевести в нужный статус (прошлая бронь → fulfilled; отмена).
                if status in ("fulfilled", "cancelled"):
                    try:
                        StayBookingSM().apply(booking, status)
                    except IllegalTransition:
                        pass

            # A5/C4: Wartungs-Block (Sperrung) — показать в визуальном календаре
            # «belegt» БЕЗ брони (отличный от бронирований источник занятости).
            from apps.stays.models import UnitBlock

            try:
                UnitBlock.objects.create(
                    unit=units[0],
                    start_date=today + timedelta(days=29),
                    end_date=today + timedelta(days=30),
                )
            except Exception:
                pass

            # G6: цифровые Meldescheine (Online-Checkin) — несколько примеров, чтобы
            # кабинет /dashboard/stays/checkins/ был наполнен.
            meldungen = [
                ("Berg", "Anna", "Seeweg 3", "78464", "Konstanz", "deutsch"),
                ("Lang", "Stefan", "Bergstr. 10", "80331", "München", "deutsch"),
                ("Fischer", "Tom", "Lindenallee 7", "20095", "Hamburg", "deutsch"),
                ("Weber", "Klaus", "Rheinweg 22", "50667", "Köln", "deutsch"),
            ]
            for booking, (ln, fn, street, plz, city, nat) in zip(
                created_bookings, meldungen, strict=False
            ):
                GuestRegistration.objects.get_or_create(
                    booking=booking,
                    defaults={
                        "last_name": ln,
                        "first_name": fn,
                        "street": street,
                        "postal_code": plz,
                        "city": city,
                        "country": "Deutschland",
                        "nationality": nat,
                        "signed_name": f"{fn} {ln}",
                        "signed_at": timezone.now(),
                    },
                )

            # G11: каналы продаж (Booking/Airbnb) + импортированная бронь из канала.
            from apps.stays.models import Channel
            from apps.stays.services import import_external_booking

            for kind, label in [
                (Channel.KIND_BOOKING, "Booking.com — Hauptkonto"),
                (Channel.KIND_AIRBNB, "Airbnb"),
            ]:
                Channel.objects.get_or_create(
                    kind=kind,
                    name=label,
                    defaults={"last_status": "Bereit (iCal aktiv; API erfordert Partner-Keys)"},
                )
            # Импорт демо-брони из Booking.com (блокирует даты, идемпотентно).
            imp_unit = _u(2)
            imp_arr = today + timedelta(days=18)
            import_external_booking(
                kind=Channel.KIND_BOOKING,
                unit=imp_unit,
                arrival=imp_arr,
                departure=imp_arr + timedelta(days=max(2, imp_unit.min_nights)),
                name="Booking.com Gast",
                external_ref="BKG-DEMO-12345",
                guests=min(2, imp_unit.max_guests),
            )

    # G3: согласия на рассылку (Double-Opt-In) + примеры кампаний (newsletter).
    from apps.promotions.models import Customer, NewsletterCampaign

    # Несколько «чистых» подписчиков (без брони) — как пришедшие через форму DOI.
    for nm, em in [
        ("Sabine Vogt", "sabine@example.de"),
        ("Markus Hahn", "markus@example.de"),
        ("Nadine Roth", "nadine@example.de"),
    ]:
        Customer.objects.get_or_create(
            email=em,
            defaults={
                "name": nm,
                "created_source": Customer.SOURCE_MANUAL,
                "marketing_opt_in": True,
                "marketing_opt_in_at": timezone.now(),
            },
        )
    # + согласие гостям с броней (как будто подтвердили opt-in).
    consenting = list(Customer.objects.exclude(email="").order_by("created_at"))
    for cust in consenting:
        if not cust.marketing_opt_in:
            cust.marketing_opt_in = True
            cust.marketing_opt_in_at = timezone.now()
            cust.save(update_fields=["marketing_opt_in", "marketing_opt_in_at", "updated_at"])
    if consenting and not NewsletterCampaign.objects.exists():
        NewsletterCampaign.objects.create(
            subject="Frühlingsangebot: 3 Nächte buchen, 1 geschenkt",
            body=(
                "Liebe Gäste,\n\nder Frühling kommt — sichern Sie sich jetzt 3 Nächte und "
                "übernachten Sie die 4. Nacht gratis. Wir freuen uns auf Sie!\n\nHerzliche Grüße"
            ),
            status=NewsletterCampaign.STATUS_SENT,
            sent_at=timezone.now() - timedelta(days=14),
            recipient_count=max(1, len(consenting) - 2),
        )
        NewsletterCampaign.objects.create(
            subject="Herbst am See: Wanderwochen mit Halbpension",
            body="Goldener Herbst, klare Luft, Halbpension inklusive — jetzt die besten Termine sichern.",
            status=NewsletterCampaign.STATUS_SENT,
            sent_at=timezone.now() - timedelta(days=3),
            recipient_count=len(consenting),
        )
        NewsletterCampaign.objects.create(
            subject="Entwurf: Sommer am See — Last-Minute-Wochen",
            body="Bald verfügbar: unsere Sommer-Specials mit Frühbucher- und Last-Minute-Rabatten.",
        )
