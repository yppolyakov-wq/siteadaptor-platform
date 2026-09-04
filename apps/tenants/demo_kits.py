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

from django.conf import settings
from django.utils import timezone

from apps.core import card_forms

from . import siteconfig


def demo_image(keyword: str, *, w: int = 800, h: int = 600, lock: int = 1, cap: str = "") -> str:
    """Тематичный демо-URL картинки. PR-IMG: локальный самодостаточный SVG-генератор
    (без внешних сервисов — GDPR-чисто, грузится в любых сетях), детерминирован по
    keyword+lock. Отдаёт storefront-вьюха `demo-image` (apps.tenants.demo_images)."""
    from . import demo_images

    return demo_images.demo_image_url(keyword.strip(), w=w, h=h, lock=lock, cap=cap)


def _product_images(img, lock: int, alt: str) -> list[dict]:
    """DL-16.4: `img` — ключ фото или СПИСОК ключей (первое главное; lock смещается,
    чтобы кадры отличались)."""
    keys = list(img) if isinstance(img, (list, tuple)) else [img]
    out = []
    for i, kw in enumerate(keys):
        ref = _image_ref(kw, lock + i, alt)
        ref["is_primary"] = i == 0
        ref["sort_order"] = i
        out.append(ref)
    return out


def _image_ref(keyword: str, lock: int, alt: str) -> dict:
    """FileRef-конверт для Product.images / галереи из внешнего фото."""
    return {
        "id": f"demo-{lock}",
        # O-7: подпись плейсхолдера = alt (имя позиции), а не технический ключ
        # («Ol-w-blazer» на витрине читался как сломанная картинка).
        "url": demo_image(keyword, lock=lock, cap=alt),
        "alt": {"de": alt},
        "is_primary": True,
        "sort_order": 0,
    }


def _i18n_text(value) -> dict:
    """Привести имя/описание к i18n-дикту. Строка → только de (одноязычно);
    dict → непустые значения ЛЮБЫХ локалей (L3d: новая локаль реестра
    сеется без правки хелпера)."""
    if isinstance(value, dict):
        return {loc: v for loc, v in value.items() if v}
    return {"de": value or ""}


def _split_i18n(value) -> tuple[str, dict]:
    """L3d: (база_de, оверлей_без_de) для overlay-моделей (Service/StayUnit/
    Combo): база — в плоское поле, переводы — в *_i18n. Строка → (строка, {})."""
    if isinstance(value, dict):
        base = value.get("de") or next((v for v in value.values() if v), "")
        return base, {loc: v for loc, v in value.items() if loc != "de" and v}
    return value or "", {}


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
    # L3d.3: комбо-наборы (Kombo-тизер A4): [{"name": str|i18n-dict, "description",
    # "price", "groups": [{"label", "products": [имена]}]}]. Пусто → не сеются.
    # MEN-6: + поля «набора меню» — photos/category(slug)/per_person/min_persons/
    # event_types/free_pool; у группы — included/min/max; элемент products может
    # быть кортежем ("Имя", "надбавка").
    combos: list = field(default_factory=list)
    # MEN-6: тип подачи (Gang) блюдам — {"Имя товара": "hauptgang"}; питает
    # «свободную сборку» меню и группировку PDF-Speisekarte.
    product_courses: dict = field(default_factory=dict)
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
    # DS-4b: город тенанта (сидер по умолчанию ставит Hilden — киты с другим
    # адресом переопределяют; город виден в eyebrow split-hero и SEO).
    city: str = ""
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
    # PMS-D: occupancy-правила цены — {"occupancy": 1..100, "percent": −50..+50}.
    occupancy_pricing: list = field(default_factory=list)
    # События: (title, in_days, capacity, price_eur) ИЛИ dict с богатой спецификацией
    #   {title, in_days, hour, duration_days|duration_hours, capacity, price,
    #    description, location, program:[...], questions:[...]}.
    events: list = field(default_factory=list)
    # MT-1: тур-продукты (events.Tour) — контент+маршрут, даты живут в заездах.
    #   {title, summary, description, region, difficulty, duration_days, distance_km,
    #    photos:[kw,…], details:{...}, itinerary:[{day,time_from,…,visibility}],
    #    teachers:[индексы в kit.teachers], published}. Событие привязывается к туру
    #   ключом "tour": <индекс в kit.tours>.
    tours: list = field(default_factory=list)
    # MT-3/4/6: наполнение ПЕРВОГО заезда — лента группы, закупки, чек-лист.
    #   {posts:[текст], supplier_bookings:[{kind,supplier,day,stop,cost,…}], tasks:[{title,in_days,done}]}
    tour_operations: dict = field(default_factory=dict)
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
    # GK-15: сетка категорий каталога НА ГЛАВНОЙ (фото-плитки, как у референса
    # catering: 6 направлений сразу под первым экраном). Опт-ин на кит.
    enable_categories_section: bool = False
    # Обложки разделов (S3): key архетипа → {"intro","hero_kw","gallery_kw":[...]}.
    archetype_covers: dict = field(default_factory=dict)
    # M20U-2: слайдер баннеров главной. Список dict'ов
    #   {image_kw, title, text, button_label, button_url}. Пусто → одиночный hero_*.
    heroes: list = field(default_factory=list)
    # M20U-7: кастомные заголовки секций главной (key→строка); пусто → дефолты.
    section_titles: dict = field(default_factory=dict)
    # H1/MT-F3: вводный текст под заголовком секции (key→строка); пусто → нет.
    section_intros: dict = field(default_factory=dict)
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
    # P6 «ценовой слой»: + service/stay_unit (индекс в refs["services"]/["stay_units"];
    #   такие акции создаются после _seed_kit_modules), rules (target_rules:
    #   weekdays/hour_from/hour_to/resource_id | stay_from/stay_to), limit
    #   (available_quantity = лимит кампании обычной акции).
    promotions_spec: list = field(default_factory=list)
    # Ваучеры/промокоды: {code, label, percent|cents, min_order(eur), max_uses}.
    vouchers: list = field(default_factory=list)
    # A3/G9b: тарифы Mehrfachkarte (PassPlan) — {label, credits, price(eur),
    #   valid_days, service_index?}. Seed создаёт планы + выдаёт одну карту.
    pass_plans: list = field(default_factory=list)
    # G8/#6: отзывы клиентов (SHARED BusinessReview) — (rating, comment, email).
    # Seed создаёт PortalUser + отзыв + включает секцию «reviews» на витрине.
    reviews_seed: list = field(default_factory=list)
    # A1/A2: отзывы о ТОВАРЕ (generic reviews.Review, entity_kind='product') —
    # (product_index, rating, name, email, comment). product_index — индекс в
    # created_products. Seed создаёт опубликованные отзывы напрямую (демо доверенный;
    # верификация — на витрине).
    product_reviews: list = field(default_factory=list)
    # UB3-2: подборки (Collection) — [(name, {"services": [idx…], "stay_units": [idx…],
    # "products": [idx…], "photos": ["kw"…]})]; индексы — позиции в refs (порядок
    # создания сидером). На витрине — чипы-фасет листинга (?kollektion=<slug>);
    # M4-B: с "photos" подборка становится «луком» со страницей /lookbook/<slug>/.
    collections: list = field(default_factory=list)
    # UA4-4b: отзывы об УСЛУГЕ/НОМЕРЕ/СОБЫТИИ (generic reviews.Review) — (index, rating,
    # name, email, comment). index — позиция в refs["services"]/["stay_units"]/["events"]
    # (порядок создания сидером). Делает секцию отзывов UA4-4b видимой в демо.
    service_reviews: list = field(default_factory=list)
    stay_reviews: list = field(default_factory=list)
    event_reviews: list = field(default_factory=list)
    # MEN-21: отзывы о НАБОРЕ МЕНЮ (kind="combo") — индекс в refs["combos"].
    combo_reviews: list = field(default_factory=list)
    # #7 универсальные Extras: (label, price_eur, scope, per_night). Seed создаёт
    # apps.core.Extra — гость отмечает при бронировании (сейчас на stays).
    extras: list = field(default_factory=list)
    storefront_root: str = "home"  # S4: стартовая страница (home или ключ архетипа)
    # Явный «главный товар» (hero-CTA/buybar); пусто = эвристика _PRIORITY. Нужен китам,
    # где дополнение-архетип приоритетнее по эвристике (Bäckerei/Metzgerei: jobs on,
    # но primary — Sortiment).
    primary_module: str = ""
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
    # AF-1: событийные поля формы /anfrage/ (Catering/Partyservice) —
    # {"fields": ["date","guests","event_type"], "event_types": [...]}.
    # Пусто = форма прежняя. Пишется в site_config.anfrage (presence-minimal).
    anfrage_form: dict = field(default_factory=dict)
    # A7: зона обслуживания (Handwerker/Werkstatt) — PLZ через запятую + текст. Пусто =
    # не показываем Einzugsgebiet. Пишется в Tenant.service_area_plz/service_area_note.
    service_area_plz: str = ""
    service_area_note: str = ""
    # RT4: записи блога — (title, excerpt, body, cover_kw). Seed создаёт опубликованные
    # BlogPost (events app). Пусто = блога нет.
    blog_posts: list = field(default_factory=list)
    # FB-3 Вариант B: демо кастом-статусы {kind: [{code,label,role,stage,blocks_capacity,
    #   revenue_recognized?}]} + рёбра {kind: [{src,dst}]}. Показывают фичу «Eigene Status»
    #   в демо-тенанте (роль определяет ёмкость/деньги). Пусто = нет кастом-статусов.
    status_defs: dict = field(default_factory=dict)
    status_edges: dict = field(default_factory=dict)
    # Склад-2 E1.5: учёт партий/MHD (Chargen) — тумблер `lots_enabled` + демо-партии
    # с реалистичным сроком годности (еда: bakery/butcher). Пусто = чистый счётчик.
    enable_lots: bool = False
    # FD-1: включить Finder «вопросы → 3 предложения» (/finder/) в демо кита.
    enable_finder: bool = False
    # --- Демо «по новой идеологии» (2026-07-19): носители новых фич ---
    # ST-1: Look-семейство ("" = как было; klar|warm|nacht) — ВИЗУАЛЬНЫЙ оверлей
    # (font/typography/site_defaults/nav.style/hero_style/theme/акцент); секции
    # и тексты кита НЕ трогаются (полный apply_look переписал бы раскладку).
    look: str = ""
    # ST-7c: форма карточек витрины ("" | overlay | compact | etikett) → site_defaults.
    card_style: str = ""
    # DL-16.4: форма карточки акции ("" | preis) и листание фото на карточке товара ("" | "on").
    promo_card: str = ""
    card_slider: str = ""
    # O-2: дефолтный вид выбора вариантов магазина ("" = выпадающий список).
    variant_style: str = ""
    # E4 «задача-первым»: primary-виджет ВНУТРИ hero ("" | stays | services |
    # gastro) → site_defaults.hero_widget. При "stays" секция stay_search гасится
    # (hero несёт); "gastro" = плитки Reservieren/Speisekarte/Angebot des Tages.
    hero_widget: str = ""
    # LS-1/LS-2: WhatsApp-номер бизнеса (гейт видео-CTA и presence-пилюли) +
    # явный режим присутствия ("" = auto по часам; "on"/"off").
    whatsapp_number: str = ""
    presence_mode: str = ""
    # ST-5b: представление раздела заказов в кабинете ("" = архетип-дефолт).
    # ST-2c/ST-7b: стили секций {section_key: style} (валидные SECTION_STYLES).
    section_styles: dict = field(default_factory=dict)
    # MEN-24c: кап строк прайс-вида {section_key: N} (пока только products).
    section_rows: dict = field(default_factory=dict)
    # Фидбэк 2026-08-27: раскладка секции-сетки {section_key: {"preset": "cols3",
    # …}} — то же поле layout, что правит владелец в конструкторе (normalize
    # клампит). Пусто → дефолт секции (GRID_SECTION_DEFAULTS).
    section_layouts: dict = field(default_factory=dict)
    # ST-2: пресеты страниц page_presets [(host, preset_id), …] — info/cart.
    page_presets: list = field(default_factory=list)
    # Фидбэк 2026-08-26: C-блоки КОНКРЕТНОЙ страницы — {host: [(key, data), …]}.
    # Хост — фикс-страница (PAGE_BLOCK_HOSTS) или категория «catalog:<slug>»;
    # key — обычный C-блок или ссылочная секция (PAGE_REF_BLOCKS: gallery_ref…),
    # тогда data пустой (контент общий, из конструктора главной).
    page_blocks: dict = field(default_factory=dict)
    # M2 Boutique: Größentabellen per категория {slug: text} (строки «S | 86–90»).
    size_tables: dict = field(default_factory=dict)
    # M3 Boutique: Click&Reserve «In der Anprobe» (site_config["anprobe"]).
    enable_anprobe: bool = False
    # ST-7a: демо-spacer'ы [{"after": "<section_key>", "height": "sm|lg|xl"}].
    spacers: list = field(default_factory=list)
    # GK-15: C-блоки главной в раскладке кита — [{"after": "<section_key>",
    # "key": "stats|image_text|newsletter|…" (REPEATABLE_BLOCKS), "data": {...},
    # "visual": {...}}]. Вставка по образцу spacers; данные санитайзит normalize
    # (_clean_cblock_data). Любой кит наполняет индивидуально.
    home_blocks: list = field(default_factory=list)
    # GK-15: соцпрофили футера (GK-9) — {"instagram"|"facebook"|"linkedin"|
    # "tiktok"|"youtube": "url|handle"}. Для демо ТОЛЬКО корневые URL соцсетей
    # (фиктивный handle мог бы указать на ЧУЖОЙ реальный аккаунт).
    socials: dict = field(default_factory=dict)
    # GK-15: демо-кэш Google-рейтинга (GK-11) — {"rating": "4.9", "count": 41}.
    # Фикция как и отзывы демо; place_id НЕ задаётся → beat/API не трогаются.
    google_rating: dict = field(default_factory=dict)
    # DS-4 (Fokus): секция anfrage на главной (реестр DS-3b; гейт jobs в партиале).
    enable_anfrage_section: bool = False
    # DS-9: сборка Fokus (реестр sitetemplates.BUNDLES) — один источник правды
    # композиции: демо получает ровно то, что владелец жмёт кнопкой «Startpaket».
    bundle: str = ""
    # DS-4b: принудительно ВЫКЛЮЧИТЬ секции главной (контент кита остаётся —
    # страницы /galerie/ /team/ живы; главная = курированный макет).
    sections_off: list = field(default_factory=list)
    # DS-4b: per-секционный visual ({key: {"background": "#hex", ...}}) —
    # тонированные полосы макета (ось SE-3d, normalize валидирует).
    section_visuals: dict = field(default_factory=dict)
    # DS-4: точечные top-level оси конфига (hero_style/nav/catalog_layout…) —
    # shallow-merge ПОСЛЕ look-оверлея (dict-значения мержатся по ключам).
    config_patch: dict = field(default_factory=dict)
    # LS-3/4/6: демо-треды «Прямой линии» (вопрос + staff-ответ + открытое
    # Sofort-Angebot; second — high-тред «Etwas stimmt nicht?»). Без писем.
    seed_inbox: bool = False
    # B4/LS-5: активная auto-win-back кампания {"inactive_days", "percent",
    # "subject"} — видна в Kampagnen и в обзоре напоминаний Marketing-центра.
    winback: dict = field(default_factory=dict)
    # DL-1/DL-3: языки витрины демо-кита — включают переключатель языка (скрытый блок
    # в шапке) и определяют, какие локали видны. Дефолт — все 5 языков реестра/кабинета
    # (немецкий контент = база + оверлеи en/ru/uk/tr из demo_i18n). Первый =
    # default_locale. Пусто → только DE. Невалидные коды отбрасываются в apply_kit.
    enabled_locales: list = field(default_factory=lambda: ["de", "en", "ru", "uk", "tr"])


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
    material="",
    care="",
    variant_style="",
    card_style="",
    vat="",
    ingredients="",
    condition="",
    note="",
    brand="",
    uvp="",
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
        # SH-4: ставка НДС позиции (пусто = 19 %). В демо гастро-китов еда идёт
        # 7 %, напитки 19 % — владелец видит СМЕШАННЫЙ чек, как в жизни.
        "vat": vat or "19.00",
        "unit": unit,
        "content": content,
        "stock": stock,
        "gtin": gtin,
        "sku": sku,
        "material": material,  # M1: Textilkennzeichnung (Boutique)
        "care": care,
        "variant_style": variant_style,  # O-2: per-товарный вид выбора
        # DL-19: per-товарная ФОРМА карточки ("" = форма сайта; своя побеждает)
        "card_style": card_style,
        # Ф2/LMIV: «Zutaten» товара (переводится оверлеем ingredients_i18n —
        # demo_i18n заполняет локали из словарей).
        "ingredients": ingredients,
        # O-1 (Outlet): состояние B-Ware + описание следа использования, марка,
        # UVP (Streichpreis). Пусто = новый товар без UVP — как у всех прежних китов.
        "condition": condition,
        "condition_note": note,
        "brand": brand,
        "uvp": uvp,
    }


# Конструктор блюда (A4): группа модификаторов.
#   min/max — правило выбора (min>=1 обязательная; max==1 radio; max>1/0 checkbox).
def _mg(name, options, *, min=0, max=1, style=""):
    """O-2: `style` — вид выбора группы на витрине ("" = как раньше)."""
    return {"name": name, "min": min, "max": max, "options": options, "style": style}


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
        style="chips",  # O-2: их много — компактные пилюли читаются лучше списка
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

# Аудит 2026-08-06: у ресторана НЕ БЫЛО своего меню — шапка выводилась из
# легаси-`nav` (плоский список активных модулей), поэтому ни галереи, ни отзывов,
# ни команды в навигации не было, хотя контент у кита есть.
RESTAURANT_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Speisekarte", "type": "archetype", "target": "catalog"},
            # MEN-13: комбо-наборы ресторана тоже были недостижимы из шапки.
            {"label": "Menüs", "type": "page", "target": "combos"},
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Veranstaltungen", "type": "archetype", "target": "events"},
            {"label": "Catering", "type": "archetype", "target": "jobs"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
            {"label": "Kontakt", "type": "anchor", "target": "/#kontakt"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Speisekarte", "type": "archetype", "target": "catalog", "icon": "🍝"},
            {"label": "Angebote", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Veranstaltungen", "type": "archetype", "target": "events", "icon": "🎫"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
        ],
    },
}

RESTAURANT = DemoKit(
    menus=RESTAURANT_MENUS,
    promotions_spec=[
        # Angebot des Tages: recurrence="daily" → плитка hero «Angebot des Tages»
        # (тег deal_of_day ставит daily первой). Фикс-цена + festpreis + лимит порций.
        {
            "title": "Mittagstisch: Lasagne für 8,90 €",
            "desc": "Jeden Mittag bis 15 Uhr: hausgemachte Lasagne mit kleinem Salat.",
            "product": 11,  # Lasagne 12,90 € (badge «tagesgericht»)
            "new_price": "8.90",
            "compare_at": "12.90",
            "discount_style": "festpreis",
            "recurrence": "daily",
            "ends_in_days": 1,
            "limit": 25,  # лимит кампании → «Nur noch N» на карточке/детали
            "new": True,
            "group": "Mittagstisch",
            "image": "lasagne",
        },
        # Классическая процент-скидка (Happy Hour). Окно часов — В ТЕКСТЕ: target_rules
        # движок проверяет только для service/stay, товарная акция действует всегда.
        {
            "title": "Happy Hour: Aperol Spritz −30 %",
            "desc": "Montag bis Freitag von 17 bis 19 Uhr an der Bar und auf der Terrasse.",
            "product": 22,  # Aperol Spritz 7,50 € → 5,25 €
            "percent": 30,
            "discount_style": "percent",
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Happy Hour",
            "image": "aperol,spritz",
        },
        # Комбо-меню БЕЗ цели-товара («свободная» акция): чекаут /p/<uuid>/kaufen/ =
        # обычный Order через custom_lines (модуль orders у кита включён).
        {
            "title": "Weinabend-Kombi: Pasta & Hauswein für 14,90 €",
            "desc": "Pasta Bolognese und ein Glas Hauswein — freitags zum Weinabend.",
            "new_price": "14.90",
            "compare_at": "17.40",  # 11,90 € Pasta + 5,50 € Hauswein
            "discount_style": "strikethrough",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Kombi-Menüs",
            "image": "wine,restaurant",
        },
        # Стиль «ab»: у пиццы есть варианты klein/groß → «ab 7,50 €» честнее фикс-цены.
        {
            "title": "Familien-Sonntag: Pizza Margherita ab 7,50 €",
            "desc": "Jeden Sonntag für die ganze Familie — auch zum Mitnehmen.",
            "product": 7,  # Pizza Margherita 9,50 € (klein/groß)
            "new_price": "7.50",
            "compare_at": "9.50",
            "discount_style": "ab",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Familien-Sonntag",
            "image": "pizza,margherita",
        },
        # Резервируемая акция (anti-oversell) + countdown-стиль: ограниченные порции.
        {
            "title": "Trüffelwochen: Risotto Funghi −20 % — nur 12 Portionen",
            "desc": "Mit frischem Trüffel aus dem Piemont, solange der Vorrat reicht.",
            "product": 12,  # Risotto Funghi 13,50 € → 10,80 €
            "type": "reservation",
            "percent": 20,
            "available_quantity": 12,
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 5,
            "group": "Limitierte Angebote",
            "image": "risotto",
        },
        # Сюрприз-блюдо (surprise) + галерея миниатюр + остаток порций.
        {
            "title": "Feierabend-Überraschung: Antipasti-Teller 6,90 € statt 12,90 €",
            "desc": "Ab 21 Uhr: unser Antipasti-Teller mit der Auswahl des Abends.",
            "surprise": True,
            "product": 3,  # Antipasti-Teller 12,90 €
            "new_price": "6.90",
            "compare_at": "12.90",
            "discount_style": "surprise",
            "limit": 8,
            "ends_in_days": 3,
            "group": "Limitierte Angebote",
            "images": ["antipasti", "restaurant,table", "restaurant,food"],
        },
    ],
    key="restaurant",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "events": {"preset": "cols2"}},
    # DS-5c: Speisekarte как в печатных меню — «классическая карта» на главной
    # и на странице /sortiment/ (config_patch).
    # DS-8 (Fokus для ресторана): сплит-баннер с плитками задач, печатная карта,
    # компакт-доверие, CTA «Tisch reservieren» в шапке.
    look="klar",
    section_styles={
        "contact": "map_first",
        "reviews": "quotes",
        "about": "accent",
        "products": "preisliste_karte",
        "trust": "compact",
    },  # ST-2c/7b
    config_patch={
        # MEN-16: на главной — «печатная карта» тизером, на полной Speisekarte
        # разворот книги с листанием (демо показывает оба вида семейства).
        "menu_labels": True,  # MEN-24a: маркировка (диеты/аллергены) в прайсе
        "catalog_layout": {"preset": "preisliste_buch"},
        "hero_style": "split",
        "nav": {"cta": True},
        # DS-8: CTA шапки/hero — бронь стола (эвристика _PRIORITY ставила events).
        "primary_module": "booking",
    },
    sections_off=["archetypes", "usp_bar", "team", "gallery", "reviews", "testimonials"],
    label="Restaurant «Bella Vista»",
    # 2026-07-30: слайдер над гастро-плитками (первый экран).
    heroes=[
        {
            "image_kw": "restaurant,interior",
            "title": "Bella Vista",
            "text": "Italienische Küche mit Herz — frische Pasta und knusprige Pizza.",
            "button_label": "Tisch reservieren",
            "button_url": "/termin/",
        },
        {
            "image_kw": "pasta,food",
            "title": "Pasta wie in Bologna",
            "text": "Jeden Morgen frisch gemacht — mit Zutaten aus der Region.",
            "button_label": "Speisekarte ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "wine,restaurant",
            "title": "Mittagstisch & Weinabende",
            "text": "Wechselnde Gerichte unter der Woche, Weinproben am Freitag.",
            "button_label": "Zu den Aktionen",
            "button_url": "/aktionen/",
        },
    ],
    business_type="restaurant",
    accent="#b45309",
    hero_image_kw="restaurant,interior",
    hero_title="Bella Vista",
    hero_text="Italienische Küche mit Herz — frische Pasta, knusprige Pizza und mehr.",
    about_title="Über uns",
    about_text="Seit 1998 kochen wir mit Leidenschaft und frischen Zutaten aus der Region.",
    nav_style="classic",  # DS-8 (Fokus): шапка одной строкой
    hero_widget="",  # DS-8 (Fokus): одно действие — CTA шапки + кнопка hero
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
    # L3d.3: Kombo-тизер A4 — демо-наборы с EN-оверлеем.
    combos=[
        {
            "name": {"de": "Mittags-Kombo", "en": "Lunch combo"},
            "description": {
                "de": "Vorspeise nach Wahl + Hauptgericht — der schnelle Mittag.",
                "en": "Starter of your choice + main dish — the quick lunch.",
            },
            "price": "16.90",
            "groups": [
                {"label": "Vorspeise", "products": ["Bruschetta", "Caprese"]},
            ],
        },
        {
            "name": {"de": "Familien-Paket", "en": "Family bundle"},
            "description": {
                "de": "Zwei Vorspeisen zum Teilen — ideal für den Tisch.",
                "en": "Two starters to share — perfect for the table.",
            },
            "price": "24.90",
            "groups": [
                {"label": "Zum Teilen", "products": ["Bruschetta", "Caprese", "Vitello Tonnato"]},
            ],
        },
    ],
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
    # AF-1: кейтеринг-Anfrage с событийными полями (Wunschdatum/Personen/Art).
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": ["Firmenfeier", "Hochzeit", "Geburtstag", "Familienfeier", "Sonstiges"],
    },
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
                            style="list",  # O-2: строка с местом под фото
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
                "target": "restaurant",
            },
            {
                "label": "Shop",
                "type": "category",
                "target": "shop",
            },
            # Catering-Welle 2026-08-25: das Catering ist jetzt ein eigener Bereich
            # (Speisekarte + Menü-Pakete + Anfrage) — deshalb Gruppe statt
            # Einzelpunkt auf die Anfrage-Seite.
            {
                # Подписи — msgid'ы хрома меню (_MENU_LABELS): переводятся на все
                # пять локалей витрины из каталогов, свой label_i18n не нужен.
                #
                # Фидбэк владельца 2026-08-26: «убери пункт меню — меню и пакеты;
                # оставить меню картинками по наборам и категориям, отправить
                # запрос, наша работа». Поэтому тип `categories` (подменю плитками
                # с фото) + `with_combos` — в тех же плитках стоят наборы меню.
                "label": "Catering",
                "type": "categories",
                "target": "catering",
                "with_combos": True,
                "children": [
                    {"label": "Anfrage", "type": "archetype", "target": "jobs"},
                    {"label": "Unsere Arbeit", "type": "page", "target": "gallery"},
                ],
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
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
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
            {"label": "Restaurant", "type": "category", "target": "restaurant", "icon": "🍔"},
            {"label": "Shop", "type": "category", "target": "shop", "icon": "🛒"},
            # Фидбэк 2026-08-26: нижнее меню вело сразу на форму запроса —
            # теперь на саму страницу кейтеринга (запрос доступен с неё).
            {"label": "Catering", "type": "category", "target": "catering", "icon": "🎉"},
            {"label": "Retreats", "type": "archetype", "target": "events", "icon": "🧘"},
        ],
    },
}

PRANASY = DemoKit(
    promotions_spec=[
        # Angebot des Tages (daily → плитка hero) + стиль «ab»: у бургера есть
        # варианты Single/Double. Лимит кампании даёт «Nur noch N».
        {
            "title": "Mittagsangebot: Veganer Burger ab 6,90 €",
            "desc": "Montag bis Freitag bis 15 Uhr — mit hausgemachter Sauce und Salat.",
            "product": 0,  # Veganer Burger 8,90 € (Single/Double)
            "new_price": "6.90",
            "compare_at": "8.90",
            "discount_style": "ab",
            "recurrence": "daily",
            "ends_in_days": 1,
            "limit": 20,
            "new": True,
            "group": "Restaurant",  # ⚠️ группу «Restaurant» требует пункт меню promo_group
            "image": "vegan,burger",
        },
        # Процент-скидка с недельным ритмом (8,40 € → 6,30 €).
        {
            "title": "Ayurveda-Dienstag: Alaputra −25 %",
            "desc": "Jeden Dienstag: ayurvedisch gewürzte Kartoffeln mit Kreuzkümmel und Kurkuma.",
            "product": 4,  # Alaputra 8,40 €
            "percent": 25,
            "discount_style": "percent",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Restaurant",
            "image": "spiced,potato",
        },
        # Комбо-теллер БЕЗ цели-товара («свободная» акция) → обычный заказ custom_lines.
        {
            "title": "Kombi-Teller: Vegane Pita & Nori-Pakora für 12,90 €",
            "desc": "Warme Pita mit Falafel und Hummus plus knusprige Nori-Pakora.",
            "new_price": "12.90",
            "compare_at": "14.30",  # 7,50 € Pita + 6,80 € Pakora
            "discount_style": "strikethrough",
            "ends_in_days": 10,
            "group": "Restaurant",
            "image": "vegan,pita",
        },
        # Shop: резервируемый набор с отсчётом (anti-oversell, 15 пакетов).
        {
            "title": "Grillpaket: Bratwurst, Wiener & Currywurst für 12,90 €",
            "desc": "Drei Sorten vegane Wurst im Paket — vorbestellen und abholen.",
            "product": 8,  # Vegane Bratwurst 4,90 € (якорь набора)
            "type": "reservation",
            "new_price": "12.90",
            "compare_at": "14.80",  # 4,90 + 4,50 + 5,40 €
            "available_quantity": 15,
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 5,
            "group": "Shop",
            "image": "vegan,currywurst",
        },
        # Anti-Food-Waste: Überraschungstüte (surprise) с галереей и остатком.
        {
            "title": "Konditorei-Überraschungstüte 4,90 € statt 12,00 €",
            "desc": "Was vom Tag übrig bleibt: Kuchen, Cookies und Zimtschnecken.",
            "surprise": True,
            "new_price": "4.90",
            "compare_at": "12.00",
            "discount_style": "surprise",
            "limit": 8,
            "ends_in_days": 3,
            "group": "Shop",
            "images": ["vegan,cake", "vegan,cookie", "vegan,cinnamon,roll"],
        },
        # Mystery: цена скрыта до клика-раскрытия (единственный стиль с этим эффектом).
        {
            "title": "Mystery-Dessert der Woche",
            "desc": "Jede Woche ein anderes Dessert aus unserer Konditorei — "
            "Preis erst beim Aufdecken.",
            "product": 18,  # Veganer Käsekuchen 3,90 €
            "new_price": "2.50",
            "compare_at": "3.90",
            "discount_style": "mystery",
            "ends_in_days": 7,
            "new": True,
            "group": "Shop",
            "image": "vegan,cheesecake",
        },
    ],
    key="pranasy",
    label="Pranasy — Vegan & Ayurveda",
    business_type="restaurant",
    subdomain="pranasy",  # → pranasy.<base> (а не pranasy-demo)
    look="natur",  # DS-2: organic-дизайн (Nunito на песке, листовой акцент)
    hero_widget="gastro",  # 2026-07-30: плитки Reservieren/Speisekarte/Angebot des Tages
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
        # Catering-Welle 2026-08-25: Restaurant und Shop sind rein pflanzlich, die
        # Catering-Karte des Betreibers bringt ayurvedische Klassiker mit Sahne,
        # Paneer oder Joghurt mit — die Antwort sagt das, statt «ohne Ausnahme».
        (
            "Ist alles wirklich vegan?",
            "Restaurant und Shop sind 100 % pflanzlich. Beim Catering stehen daneben "
            "ayurvedische Klassiker mit Sahne, Paneer oder Joghurt — jedes Gericht ist "
            "gekennzeichnet.",
        ),
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
    trust={"since": "2021", "marks": ["Vegan & vegetarisch", "Ayurveda", "Regional"]},
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
    # AF-1: веган-кейтеринг «Catering» (jobs) — событийные поля заявки.
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": ["Firmenfeier", "Geburtstag", "Retreat", "Büro-Catering", "Sonstiges"],
    },
    # MEN-6 (Karte des Betreibers): drei Modi eines Menü-Pakets auf dem Bereich
    # «Catering» — fertig zusammengestellt, nach Wahl und frei kombiniert.
    combos=[
        {
            "name": "Menü Klassik",
            "description": "Vier Gänge, fest zusammengestellt: Suppe, Hauptgang, "
            "Beilage und Salat. Warm geliefert, Aufbau auf Wunsch inklusive.",
            "price": "19.50",
            "per_person": True,
            "min_persons": 15,
            "category": "catering",
            "event_types": ["Firmenfeier", "Geburtstag", "Büro-Catering"],
            "photos": ["borscht,soup", "ragout,red"],
            "groups": [
                {"label": "Suppe", "included": True, "products": ["Borschtsch"]},
                {"label": "Hauptgang", "included": True, "products": ["Rotes Gemüseragout"]},
                {"label": "Beilage", "included": True, "products": ["Reis"]},
                {"label": "Salat", "included": True, "products": ["Sommersalat"]},
            ],
        },
        {
            "name": "Menü nach Wahl",
            "description": "Sie stellen das Menü zusammen: je ein Gericht pro Gang, "
            "Extras optional. Der Preis passt sich Ihrer Auswahl an.",
            "price": "22.90",
            "per_person": True,
            "min_persons": 15,
            "category": "catering",
            "event_types": ["Firmenfeier", "Geburtstag", "Retreat", "Büro-Catering"],
            "photos": ["ragout,red", "spring,salad"],
            "groups": [
                {
                    "label": "Suppe",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Borschtsch",
                        "Dal mit Gemüse",
                        ("Kürbissuppe mit Kürbiskernen", "0.50"),
                        ("Cremige Pilzsuppe", "0.80"),
                    ],
                },
                {
                    "label": "Hauptgang",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Rotes Gemüseragout",
                        ("Kichererbsen-Ragout mit Blumenkohl", "1.00"),
                        ("Weißes Ragout mit Paneer", "1.50"),
                        ("Tofu-Ragout mit Aubergine", "1.80"),
                    ],
                },
                {
                    "label": "Beilage",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Reis",
                        "Buchweizen",
                        "Bulgur",
                        ("Ofenkartoffeln", "0.50"),
                    ],
                },
                {
                    "label": "Salat",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Sommersalat",
                        "Rote-Bete-Salat mit Knoblauch",
                        ("Frühlingssalat", "0.50"),
                        ("Spargelsalat Asberg", "2.00"),
                    ],
                },
                {
                    "label": "Extras",
                    "min": 0,
                    "max": 3,
                    "products": [
                        ("Gemüse-Pakoras", "2.50"),
                        ("Kartoffelpuffer (Draniki)", "2.50"),
                        ("Auberginenkaviar", "2.00"),
                        ("Frische Minzsauce", "1.00"),
                    ],
                },
            ],
        },
        {
            "name": "Ayurveda-Thali",
            "description": "Unser ayurvedisches Tellergericht: Dal, Kitchari, Raita und "
            "Ofengemüse — mild gewürzt, leicht verdaulich und ohne Zwiebel und Knoblauch.",
            "price": "21.00",
            "per_person": True,
            "min_persons": 10,
            "category": "catering",
            "event_types": ["Retreat", "Büro-Catering", "Geburtstag"],
            "photos": ["dal,soup", "kitchari,dal"],
            "groups": [
                {"label": "Suppe", "included": True, "products": ["Dal mit Gemüse"]},
                {"label": "Hauptgang", "included": True, "products": ["Kitchari"]},
                {"label": "Salat", "included": True, "products": ["Gurken-Raita mit Minze"]},
                {"label": "Beilage", "included": True, "products": ["Ofengemüse vom Blech"]},
            ],
        },
        {
            "name": "Freie Auswahl",
            "description": "Stellen Sie Ihr Buffet frei zusammen — alle 49 Gerichte der "
            "Catering-Karte, nach Gängen sortiert. Preise à la carte, pro Person gerechnet.",
            "price": "0.00",
            "per_person": True,
            "min_persons": 10,
            "free_pool": True,
            "category": "catering",
            "event_types": ["Firmenfeier", "Geburtstag", "Retreat", "Büro-Catering", "Sonstiges"],
            "photos": ["roasted,veggies"],
        },
    ],
    # MEN-21: Bewertungen zu den Menü-Paketen (kind="combo") — Index = Reihenfolge
    # der Spezifikation oben. Kundentexte bleiben DE (Regel der DL-Welle).
    combo_reviews=[
        (
            0,
            5,
            "Familie Weber",
            "pr.weber@example.de",
            "Das Klassik-Menü für unsere Feier war rundum gut: Borschtsch heiß, "
            "Ragout würzig, alles pünktlich aufgebaut.",
        ),
        (
            1,
            5,
            "Team Nordlicht",
            "pr.nordlicht@example.de",
            "Wir konnten für jeden etwas auswählen — vegan, glutenfrei, mild. "
            "Die Kolleginnen reden heute noch vom Kichererbsen-Ragout.",
        ),
        (
            1,
            4,
            "Sabine H.",
            "pr.sabine@example.de",
            "Sehr flexibel und gut kalkulierbar. Nur die Lieferung kam zehn Minuten "
            "später als besprochen.",
        ),
        (
            2,
            5,
            "Yoga-Studio Anahata",
            "pr.anahata@example.de",
            "Für unser Retreat-Wochenende genau richtig: leicht, mild gewürzt und "
            "trotzdem sättigend. Das Kitchari war der Favorit.",
        ),
    ],
    # MEN-6: Gang jedes Gerichts — «freie Auswahl» im Menü-Konfigurator
    # gruppiert danach, und die PDF-Speisekarte sortiert danach.
    product_courses={
        "Borschtsch": "suppe",
        "Käsecremesuppe": "suppe",
        "Dal mit Gemüse": "suppe",
        "Cremige Pilzsuppe": "suppe",
        "Kürbissuppe mit Kürbiskernen": "suppe",
        "Gazpacho": "suppe",
        "Okroschka": "suppe",
        "Raita (kalte Joghurtsuppe)": "suppe",
        "Reis": "beilage",
        "Bulgur": "beilage",
        "Nudeln": "beilage",
        "Kitchari": "beilage",
        "Buchweizen": "beilage",
        "Ofenkartoffeln": "beilage",
        "Gemüsereis": "beilage",
        "Couscous": "beilage",
        "Plow (Pilaw)": "beilage",
        "Rotes Gemüseragout": "hauptgang",
        "Weißes Ragout mit Paneer": "hauptgang",
        "Kichererbsen-Ragout mit Blumenkohl": "hauptgang",
        "Kürbisragout": "hauptgang",
        "Brokkoli-Ragout mit grünen Bohnen": "hauptgang",
        "Rosenkohl-Ragout mit Paprika": "hauptgang",
        "Tofu-Ragout mit Aubergine": "hauptgang",
        "Mahabridschal (Auberginen-Ragout)": "hauptgang",
        "Rote Tomatensauce": "beilage",
        "Steinpilz-Rahmsauce": "beilage",
        "Frische Minzsauce": "beilage",
        "Spinatsauce mit Hartkäse": "beilage",
        "Tomaten-Käse-Sauce": "beilage",
        "Soja-Bolognese": "beilage",
        "Seitan-Tomatensauce": "beilage",
        "Auberginenkaviar": "vorspeise",
        "Gemüse-Pakoras": "vorspeise",
        "Gemüsebratlinge": "vorspeise",
        "Kartoffelpuffer (Draniki)": "vorspeise",
        "Reisbratlinge": "vorspeise",
        "Schmorkohl": "vorspeise",
        "Ofengemüse vom Blech": "vorspeise",
        "Chinakohl-Salat": "vorspeise",
        "Morkowtscha (Karottensalat)": "vorspeise",
        "Frühlingssalat": "vorspeise",
        "Sommersalat": "vorspeise",
        "Rote-Bete-Salat mit Knoblauch": "vorspeise",
        "Winegret-Salat": "vorspeise",
        "Gurkensalat mit Kräutern": "vorspeise",
        "Gurken-Raita mit Minze": "vorspeise",
        "Spargelsalat Asberg": "vorspeise",
        "Veganer Caesar-Salat": "vorspeise",
    },
    # Catering-Welle 2026-08-25: Bereich «Catering» wie beim Archetyp — Menü-Pakete,
    # Kennzeichnung in der Preisliste und die Anfrage-Bande auf der Startseite.
    enable_anfrage_section=True,
    config_patch={"menu_labels": True},
    # Фидбэк 2026-08-26: страница «Catering» — как полноценная главная. Блоки
    # ССЫЛОЧНЫЕ (UC2-3b): галерея, отзывы, команда и FAQ берутся из общего
    # контента сайта, поэтому второго набора текстов у страницы не заводится.
    # Заявка внизу — вход в тот же /anfrage/, что и банда главной.
    page_blocks={
        "catalog:catering": [
            ("gallery_ref", {}),
            ("testimonials_ref", {}),
            ("team_ref", {}),
            ("faq_ref", {}),
            ("anfrage_ref", {}),
        ]
    },
    seed_records=True,
    menus=PRANASY_MENUS,
    # M20U-2: слайдер баннеров — единая главная ведёт к ключевым действиям.
    heroes=[
        {
            "image_kw": "vegan,food",
            "title": "Bald geöffnet",
            "text": "Unser veganes Restaurant öffnet bald — die Speisekarte ist schon online.",
            "button_label": "Zur Speisekarte",
            "button_url": "/sortiment/restaurant/",
        },
        {
            "image_kw": "vegan,sausage",
            "title": "Veganer Shop",
            "text": "Würstchen, Aufschnitt und feine Konditorei — alles pflanzlich.",
            "button_label": "Zum Shop",
            "button_url": "/sortiment/shop/",
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
    # Фидбэк владельца 2026-08-27 («категории по 3 в ряд, блюда по 6»): страница
    # «Catering» — витрина карты, где направления (Suppen, Beilagen, Ragouts…)
    # читаются крупными плитками, а сами блюда идут плотной сеткой под тулбаром.
    page_layouts={"catalog": "cols6", "events": "cols2"},
    section_layouts={
        "categories": {"preset": "cols3"},
        "gallery": {"preset": "cols3"},
    },  # DL-11: +галерея 6 = 2×3
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
            # «catering,buffet» zeigt eine Bratwurst-Theke — auf einer rein
            # pflanzlichen Seite das falsche Bild (Sichtcheck 2026-08-25).
            "hero_kw": "vegan,buffet",
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
        "button_url": "/sortiment/restaurant/",
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
            "",  # описание
            "regale",  # DL-16.5 (K2): подкатегории — «полки» лентами со стрелками
        ),
        # Catering-Speisekarte (Karte des Betreibers, 2026-08-25): 49 Gerichte in
        # sechs Gängen unter EINEM Bereich «Catering». Der Bereich ist ein Container —
        # die Gerichte liegen in den Unterkategorien, die Seite zeigt sie zusammen
        # (KAT-1) und darüber die Menü-Pakete (page_style «sets»).
        (
            # Gleich in DE und EN → Inline-Dict statt Identity-Eintrag im
            # Demo-Wörterbuch (ein Projekt-Test verbietet msgstr == msgid).
            {"de": "Catering", "en": "Catering"},
            "catering",
            [],
            [
                (
                    "Suppen",
                    "suppen",
                    [
                        _p(
                            "Borschtsch",
                            "5.90",
                            "Tiefrot, süßsauer und lange geköchelt — der Klassiker der "
                            "osteuropäischen Küche. Bohnen und reichlich Gemüse machen ihn "
                            "auch ohne Fleisch richtig sättigend. Serviert mit frischem Dill "
                            "und einem Löffel Schmand.",
                            "borscht,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Rote Bete, Kartoffeln, Weißkohl, Karotten, Paprika, Tomaten, "
                            "Tomatenmark, Dill, Wasser, Bohnen, Schmand, Gewürze (schwarzer "
                            "Pfeffer, Lorbeerblatt, Salz, Zucker)",
                        ),
                        _p(
                            "Käsecremesuppe",
                            "5.50",
                            "Samtig und mild: Kartoffeln, Sahne und Schmelzkäse ergeben eine "
                            "gleichmäßig cremige Suppe, Tofu gibt ihr Körper und macht sie "
                            "sättigend. Schwarze Oliven und Kurkuma setzen würzige Akzente. "
                            "Ein ruhiger Teller für kühle Tage.",
                            "cheese,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch", "soja"],
                            vat="7.00",
                            ingredients="Kartoffeln, Sahne, Schmelzkäse, schwarze Oliven, Tofu, "
                            "Pflanzenöl, Wasser, frische Kräuter, Gewürze (Salz, Asafötida "
                            "(glutenfrei), schwarzer Pfeffer, Bockshornklee, Kurkuma)",
                        ),
                        _p(
                            "Dal mit Gemüse",
                            "6.20",
                            "Würziger indischer Eintopf aus Kichererbsen oder Mungbohnen, mit "
                            "Karotten, Blumenkohl und Paprika. Kreuzkümmel, Kurkuma und "
                            "Asafötida geben ihm Tiefe, Butter und Sahne machen ihn weich und "
                            "rund. Mit frischem Koriander serviert.",
                            "dal,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Kichererbsen oder Mungbohnen, Karotten, Blumenkohl, Paprika, "
                            "Butter, Sahne oder Schmand, Wasser, Koriandergrün, Gewürze "
                            "(Kreuzkümmel, Chili, Kurkuma, Asafötida (glutenfrei), Salz)",
                        ),
                        _p(
                            "Cremige Pilzsuppe",
                            "6.40",
                            "Kräftiger Pilzgeschmack, dichte und samtige Textur: Pilze "
                            "bringen die erdige Note, Sahne und Tofu machen die Suppe zart "
                            "und sättigend. Tomatenmark und grüne Oliven geben ihr Tiefe, "
                            "Bockshornklee eine feine Kräuterwürze.",
                            "mushroom,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch", "soja"],
                            vat="7.00",
                            ingredients="Kartoffeln, Sahne, Pilze, Karotten, Tomatenmark, grüne Oliven, "
                            "Tofu, Pflanzenöl, Wasser, frische Kräuter, Gewürze (Salz, "
                            "Asafötida (glutenfrei), schwarzer Pfeffer, Bockshornklee, "
                            "Bockshornkleeblätter)",
                        ),
                        _p(
                            "Kürbissuppe mit Kürbiskernen",
                            "5.20",
                            "Sonnengelbe Cremesuppe mit feiner Süße und samtiger Textur. "
                            "Kürbis, Kartoffeln und Karotten werden mit Sahne fein püriert, "
                            "Kurkuma und Bockshornklee runden sie ab. Geröstete Kürbiskerne "
                            "obenauf sorgen für nussigen Biss.",
                            "pumpkin,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Kürbis, Kartoffeln, Karotten, Sahne (20 %), Olivenöl, Wasser, "
                            "Kürbiskerne, Gewürze (Salz, Bockshornklee, Asafötida "
                            "(glutenfrei), Kurkuma, schwarzer Pfeffer)",
                        ),
                        _p(
                            "Gazpacho",
                            "4.90",
                            "Kalte Gemüsesuppe aus Spanien — frisch, leicht säuerlich und so "
                            "dicht, dass sie sich fast wie ein Getränk löffeln lässt. "
                            "Tomaten, Gurke und Paprika werden mit Olivenöl und Weinessig "
                            "oder Zitrone kalt püriert. Mit knusprigen veganen Croutons "
                            "serviert.",
                            "gazpacho,soup",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten", "sellerie", "sulfit"],
                            vat="7.00",
                            ingredients="Tomaten, Gurke, Paprika, Olivenöl, Weinessig oder Zitrone, "
                            "Wasser oder Eis, vegane Croutons, Sellerie, Gewürze (Salz, "
                            "schwarzer Pfeffer, Asafötida)",
                        ),
                        _p(
                            "Okroschka",
                            "5.60",
                            "Die leichte Sommersuppe: gekochte Kartoffeln, frische Gurke und "
                            "Radieschen fein gewürfelt, dazu Paneer und viel Dill. "
                            "Aufgegossen wird mit Kwass oder Kefir — säuerlich, kühl und "
                            "erfrischend, ohne schwer im Magen zu liegen.",
                            "okroschka,suppe,essen",
                            diets=["vegetarisch"],
                            allergens=["gluten", "milch"],
                            vat="7.00",
                            ingredients="gekochte Kartoffeln, frische Gurke, Radieschen, Paneer, frische "
                            "Kräuter, Dill, Schmand, Kwass oder Kefir, Gewürze (Salz)",
                        ),
                        _p(
                            "Raita (kalte Joghurtsuppe)",
                            "4.50",
                            "Kühl und erfrischend: Naturjoghurt mit geriebener Gurke, Tomate "
                            "und frischem Koriander oder Minze. Kreuzkümmel, Pfeffer und "
                            "Asafötida geben der kalten Suppe eine feine Würze. Passt "
                            "besonders gut zu scharf gewürzten Gerichten.",
                            "raita,soup",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Naturjoghurt, Gurke, Tomate, Koriandergrün oder Minze, Wasser, "
                            "Gewürze (gemahlener Kreuzkümmel, schwarzer Pfeffer, Salz, "
                            "Asafötida (glutenfrei))",
                        ),
                    ],
                    "borscht,soup",
                    "Warme und kalte Suppen aus der ayurvedischen und osteuropäischen Küche — "
                    "täglich frisch gekocht, im Glas oder in der Warmhaltebox geliefert.",
                    "preisliste",
                ),
                (
                    "Beilagen",
                    "beilagen",
                    [
                        _p(
                            "Reis",
                            "3.50",
                            "Neutraler Klassiker, der zu Gemüse- und Hülsenfruchtgerichten "
                            "ebenso passt wie zu kräftigen Saucen. Die Körner bleiben locker "
                            "und fallen schön auseinander, dabei nehmen sie die Sauce von "
                            "Ragouts und Currys gut auf. Warm serviert — die Beilage zu fast "
                            "allen warmen Gerichten.",
                            "rice,plain",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Reis, Wasser, Öl, Gewürze (Salz)",
                        ),
                        _p(
                            "Bulgur",
                            "3.90",
                            "Herzhafte Beilage aus vorgegartem Weizen mit feiner Nussnote und "
                            "angenehmem Biss. Das Vollkorn bleibt körnig und nimmt Saucen und "
                            "Gewürze bereitwillig auf. Passt zu Ragouts, geschmortem Gemüse "
                            "und allem, was etwas Sättigendes braucht.",
                            "bulgur,grain",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Bulgur, Wasser, Öl, Gewürze (Salz)",
                        ),
                        _p(
                            "Nudeln",
                            "3.70",
                            "Der Klassiker, den Große und Kleine mögen: Hartweizennudeln, al "
                            "dente gekocht, mit angenehmem Biss. Sie sind die verlässliche "
                            "Grundlage für Gemüseragouts und Saucen — oder ganz schlicht mit "
                            "etwas Öl und frischen Kräutern.",
                            "noodles,durum",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Nudeln (Hartweizen), Wasser, Öl, Gewürze (Salz)",
                        ),
                        _p(
                            "Kitchari",
                            "5.20",
                            "Der ayurvedische Klassiker aus Reis und Mungbohnen, weich gegart "
                            "und leicht sämig. Kurkuma und Ghee geben dem Gericht seine "
                            "goldene Farbe und ein feines, nussiges Aroma. Mild, bekömmlich "
                            "und sättigend — auch für kleine Gäste geeignet.",
                            "kitchari,essen",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Reis, Mung-Dal oder Linsen, Wasser, Ghee, Gewürze (Kurkuma, "
                            "Salz)",
                        ),
                        _p(
                            "Buchweizen",
                            "4.20",
                            "Kräftige Beilage mit unverwechselbarem Geschmack und lockerer, "
                            "körniger Textur. Der Buchweizen bringt eine feine Nussnote mit "
                            "und harmoniert besonders gut mit Pilzsaucen und Gemüseragouts. "
                            "Sättigend und angenehm nussig im Abgang.",
                            "buchweizen,essen",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Buchweizen, Wasser, Öl, Gewürze (Salz)",
                        ),
                        _p(
                            "Ofenkartoffeln",
                            "4.50",
                            "Im Ofen geröstet, bis die Kanten goldbraun und knusprig sind und "
                            "das Innere schön mehlig bleibt. Öl und Gewürze ziehen beim "
                            "Backen ein und geben den Kartoffeln ihr warmes Aroma. Eine gute "
                            "Begleitung zu Gemüsebratlingen und Ragouts.",
                            "roasted,potato",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Kartoffeln, Öl, Gewürze (Salz, Gewürzmischung)",
                        ),
                        _p(
                            "Gemüsereis",
                            "4.90",
                            "Bunter Reis, der als Beilage ebenso funktioniert wie als kleines "
                            "Hauptgericht. Möhren, Paprika, Erbsen und Mais werden "
                            "mitgebraten und geben den Körnern Farbe und einen leicht "
                            "süßlichen Geschmack. Warm serviert, mittags wie abends.",
                            "rice,peas",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Reis, Möhren, Paprika, Erbsen, Mais, Wasser, Öl, Gewürze (Salz)",
                        ),
                        _p(
                            "Couscous",
                            "4.10",
                            "Feiner Hartweizengrieß, schonend gedämpft — locker, körnig und "
                            "angenehm zurückhaltend im Geschmack. Genau deshalb ist Couscous "
                            "die ideale Grundlage für Gemüseragouts und aromatische Saucen. "
                            "Auf Wunsch mit feinen Möhrenwürfeln.",
                            "couscous,semolina",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Couscous, Wasser, Öl, Möhren (nach Wunsch), Gewürze (Salz, "
                            "Pfeffer)",
                        ),
                        _p(
                            "Plow (Pilaw)",
                            "5.90",
                            "Goldener Reis mit Kichererbsen und Möhren, langsam in "
                            "Butterschmalz gegart. Kreuzkümmel, Paprika und Kurkuma geben ihm "
                            "Farbe und ein tiefes, orientalisches Aroma, die Körner bleiben "
                            "dabei locker. Heiß serviert, gern mit frischem Brot.",
                            "plov,pilaf",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Reis, Kichererbsen, Möhren, Butterschmalz (Ghee), Wasser, "
                            "Gewürze (Kreuzkümmel, Paprika, Kurkuma, Salz, Pfeffer, Asafötida "
                            "(glutenfrei))",
                        ),
                    ],
                    "couscous,semolina",
                    "Reis, Getreide und Kartoffeln als Basis jedes Menüs — neutral gewürzt, "
                    "damit Ragouts und Saucen die Hauptrolle spielen.",
                    "preisliste",
                ),
                (
                    "Ragouts & Hauptgerichte",
                    "ragouts",
                    [
                        _p(
                            "Rotes Gemüseragout",
                            "7.50",
                            "Kartoffeln und Karotten braten wir goldbraun an und schmoren sie "
                            "dann in einer Tomatensauce mit Sahne. Kreuzkümmel und Koriander "
                            "geben dem Ragout seine warme, würzige Tiefe, eine Prise Zucker "
                            "nimmt der Tomate die Säure. Sättigend und wohltuend an kühlen "
                            "Tagen.",
                            "ragout,red",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch", "senf"],
                            vat="7.00",
                            ingredients="Kartoffeln, Karotten, Öl zum Anbraten, Sahne (20 %), "
                            "Tomatensauce, Wasser oder selleriefreie Gemüsebrühe, Gewürze "
                            "(schwarze Senfsaat, Kreuzkümmel, gemahlener Koriander, Asafötida "
                            "(glutenfrei), Salz, Zucker)",
                        ),
                        _p(
                            "Weißes Ragout mit Paneer",
                            "9.20",
                            "Kartoffeln und Zucchini schmoren sanft in Sahne, dazu kommen "
                            "zarte Paneer-Würfel. Kurkuma gibt dem Ragout einen goldenen Ton, "
                            "Bockshornklee eine feine, nussige Note. Ein mildes, cremiges "
                            "Gericht für einen ruhigen Mittag.",
                            "paneerragout,essen",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="geschälte Kartoffeln, Zucchini, Paneer, Sahne (20 %), Butter, "
                            "Wasser oder selleriefreie Gemüsebrühe, Gewürze (Kurkuma, "
                            "Bockshornklee, Asafötida (glutenfrei), schwarzer Pfeffer, Salz)",
                        ),
                        _p(
                            "Kichererbsen-Ragout mit Blumenkohl",
                            "8.90",
                            "Viel Gemüse und gekochte Kichererbsen machen dieses Ragout "
                            "angenehm sättigend. Blumenkohl, Kartoffeln und Paprika sorgen "
                            "für Biss, Kreuzkümmel, Koriander und Fenchel für einen tiefen, "
                            "würzigen Geschmack. Ein Schuss Sahne zum Schluss macht alles "
                            "besonders zart.",
                            "chickpea,ragout",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Kichererbsen (gekocht), Kartoffeln, Blumenkohl, Paprika, Öl, "
                            "Wasser oder selleriefreie Gemüsebrühe, Sahne, Gewürze "
                            "(Kreuzkümmel, gemahlener Koriander, Fenchel, Kurkuma, Asafötida "
                            "(glutenfrei), Salz)",
                        ),
                        _p(
                            "Kürbisragout",
                            "8.40",
                            "Zarter Kürbis trifft auf Paprika, Zucchini und Karotte — dazu "
                            "Muskatnuss oder Zimt, die die natürliche Süße des Kürbis "
                            "aufnehmen. Sahne bindet alles zu einem dichten, samtigen Ragout. "
                            "Warm gewürzt, aber nicht scharf.",
                            "kürbisragout,essen",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Kürbis, Karotten, Paprika, Zucchini, Sahne (20 %), Öl oder "
                            "Butter, Wasser oder selleriefreie Gemüsebrühe, Gewürze "
                            "(Kreuzkümmel, Koriander, Kurkuma, Fenchel, Asafötida "
                            "(glutenfrei), Muskatnuss oder Zimt, Salz)",
                        ),
                        _p(
                            "Brokkoli-Ragout mit grünen Bohnen",
                            "8.60",
                            "Brokkoli und grüne Bohnen geben dem Ragout kräftige Farbe und "
                            "angenehmen Biss, die Sahne macht es weich und mild. Schwarze "
                            "Senfsaat, Kreuzkümmel und Muskat sorgen für Tiefe, ohne dass es "
                            "scharf wird. Dazu passt am besten Reis.",
                            "broccoli,ragout",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch", "senf"],
                            vat="7.00",
                            ingredients="Kartoffeln, Brokkoli, grüne Bohnen, Sahne, Öl, Wasser, Gewürze "
                            "(schwarze Senfsaat, Kreuzkümmel, Koriander, Asafötida "
                            "(glutenfrei), weißer Pfeffer, Muskatnuss, Salz)",
                        ),
                        _p(
                            "Rosenkohl-Ragout mit Paprika",
                            "8.20",
                            "Kleine Rosenkohlköpfe geben dem Ragout einen milden, leicht "
                            "süßlichen Ton und eine angenehme Textur. Mit Karotte, Paprika "
                            "und Zucchini wird es bunt und rund, Sahne und eine Prise Zucker "
                            "machen den Geschmack harmonisch. Ein klassisches Gemüseragout.",
                            "sprouts,ragout",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Rosenkohl, Karotten, Paprika, Zucchini, Sahne, Öl, Wasser, "
                            "Gewürze (Kreuzkümmel, Koriander, Kurkuma, Asafötida "
                            "(glutenfrei), Salz, Zucker)",
                        ),
                        _p(
                            "Tofu-Ragout mit Aubergine",
                            "9.40",
                            "Der Tofu wird mit dem Gemüse angebraten und zieht die Aromen der "
                            "würzigen Sauce in sich auf — herzhaft und saftig. Ingwer, "
                            "Koriander und Kreuzkümmel geben dem Ragout einen warmen Ton, der "
                            "gut zu Aubergine, Paprika und Blumenkohl passt. Komplett "
                            "pflanzlich.",
                            "tofu,ragout",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            allergens=["soja"],
                            vat="7.00",
                            ingredients="Tofu, Paprika, Aubergine, Zucchini, Blumenkohl, Wasser, Gewürze "
                            "(Kurkuma, Kreuzkümmel, Koriander, schwarzer Pfeffer, Ingwer)",
                        ),
                        _p(
                            "Mahabridschal (Auberginen-Ragout)",
                            "9.90",
                            "Auberginen werden in Öl weich angebraten und schmoren dann mit "
                            "Zucchini, Karotte und Paprika in einer würzigen Sauce. "
                            "Kreuzkümmel, Koriander, Chili und Garam Masala geben Charakter, "
                            "Sahne und Käse machen die Textur zum Schluss besonders cremig. "
                            "Gut mit Beilage oder für sich.",
                            "mahabridschal,essen",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Auberginen, Paprika, Zucchini, Karotten, Pflanzenöl, Wasser, "
                            "Sahne, Käse, Gewürze (gemahlener Koriander, gemahlener "
                            "Kreuzkümmel, Kurkuma, Asafötida (glutenfrei), Chili, Zucker, "
                            "Salz, Garam Masala)",
                        ),
                    ],
                    "ragout,red",
                    "Herzhafte Gemüseragouts als Hauptgang — cremig, würzig und sättigend, in "
                    "Mengen ab 10 Portionen kalkuliert.",
                    "preisliste",
                ),
                (
                    "Saucen",
                    "saucen",
                    [
                        _p(
                            "Rote Tomatensauce",
                            "2.90",
                            "Dicht eingekochtes Tomatenmark, mit Sahne zu einer samtigen, "
                            "tiefroten Sauce verrührt. Die Gewürze geben ihr eine warme, "
                            "würzige Note. Passt zu Beilagen und Ragouts und ist zugleich die "
                            "Grundlage für viele weitere Gerichte unserer Karte.",
                            "tomato,sauce",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Tomatenmark, Sahne, Wasser, Gewürze",
                        ),
                        _p(
                            "Steinpilz-Rahmsauce",
                            "4.50",
                            "Steinpilze und Zucchini werden in Butter mit Mehl angeschwitzt, "
                            "dann kommt Sahne dazu — so wird die Sauce dicht und samtig, mit "
                            "klarem Waldpilz-Aroma. Asafötida und Pfeffer runden sie ab. "
                            "Klassisch zu Nudeln, Ofenkartoffeln oder Gemüse.",
                            "mushroom,sauce",
                            diets=["vegetarisch"],
                            allergens=["gluten", "milch"],
                            vat="7.00",
                            ingredients="Steinpilze, Zucchini, Butter, Weizenmehl, Sahne, Wasser, Gewürze "
                            "(Salz, Pfeffer, Asafötida)",
                        ),
                        _p(
                            "Frische Minzsauce",
                            "2.50",
                            "Frische Minze, mit heißem Wasser aufgegossen und mit Zucker oder "
                            "Honig abgerundet. Ein Spritzer Essig gibt die feine Säure, die "
                            "Gewürze machen sie pikant. Passt zu Salaten, Ofengemüse und "
                            "gebratenen Beilagen — oder einfach als Dip.",
                            "minzsauce,essen",
                            diets=["vegetarisch", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Minze, Zucker oder Honig, kochendes Wasser, Essig, Gewürze",
                        ),
                        _p(
                            "Spinatsauce mit Hartkäse",
                            "3.90",
                            "Frischer Spinat mit Zwiebel und Knoblauch, gebunden mit Butter, "
                            "Mehl und Sahne — kräftig grün und cremig. Der Hartkäse gibt "
                            "Würze, frisch geriebene Muskatnuss die warme Tiefe. Wir reichen "
                            "sie zu Pasta, Risotto oder gebackenem Gemüse.",
                            "spinach,sauce",
                            diets=["vegetarisch"],
                            allergens=["gluten", "milch"],
                            vat="7.00",
                            ingredients="frischer Spinat, Sahne, Zwiebeln, Knoblauch, Hartkäse "
                            "(mikrobielles Lab), Butter, Weizenmehl, Gewürze (Salz, schwarzer "
                            "Pfeffer, Muskatnuss)",
                        ),
                        _p(
                            "Tomaten-Käse-Sauce",
                            "4.20",
                            "Kräftige Tomatensauce, verfeinert mit Sahne, festem Tofu und "
                            "geriebenem Hartkäse. Der Käse schmilzt ein und macht sie dicht "
                            "und mild, die Gewürze geben Tiefe. Eine sättigende Grundlage für "
                            "Pasta, Pizza oder Aufläufe.",
                            "cheese,sauce",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch", "soja"],
                            vat="7.00",
                            ingredients="Tomatenmark oder Tomatenpüree, Tofu (fest), Sahne 33 %, "
                            "Hartkäse, Pflanzenöl, Gewürze",
                        ),
                        _p(
                            "Soja-Bolognese",
                            "3.40",
                            "Sojagranulat wird eingeweicht und mit Zwiebel und Möhre "
                            "angebraten — so bekommt es Biss und ein herzhaftes Aroma. Mit "
                            "Tomatenmark, Knoblauch und Gewürzen wird daraus eine sättigende "
                            "Sauce für Nudeln, Kartoffeln oder pur.",
                            "bolognese,soja,essen",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten", "soja"],
                            vat="7.00",
                            ingredients="Tomatenmark oder Tomatenpüree, Zwiebeln, Möhren, Knoblauch, "
                            "Weizenmehl, Pflanzenöl, Wasser, Sojagranulat, Gewürze (Salz, "
                            "Pfeffer, Gewürzmischung)",
                        ),
                        _p(
                            "Seitan-Tomatensauce",
                            "4.40",
                            "Seitan, das herzhafte Weizeneiweiß, saugt sich in einer dichten "
                            "Sauce aus Tomatenmark und stückigen Tomaten voll. Zwiebel, "
                            "Knoblauch und Kräuter geben ihr Tiefe, eine Prise Zucker rundet "
                            "die Säure ab. Herzhaft zu Beilagen und Pasta.",
                            "seitan,sauce",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Seitan, Tomatenmark oder Tomatenpüree, Tomaten im eigenen Saft, "
                            "Zwiebeln, Knoblauch, Möhren, Pflanzenöl, Wasser, Gewürze (Salz, "
                            "schwarzer Pfeffer, Zucker, Kräuter)",
                        ),
                    ],
                    "tomato,sauce",
                    "Saucen zu Beilagen und Bratlingen — von der klassischen Tomatensauce bis "
                    "zur Rahmsauce mit Steinpilzen.",
                    "preisliste",
                ),
                (
                    "Warme Vorspeisen",
                    "vorspeisen",
                    [
                        _p(
                            "Auberginenkaviar",
                            "4.90",
                            "Gebackene Auberginen werden mit Tomaten, Zwiebeln und Paprika zu "
                            "einer weichen, rauchig-würzigen Paste geschmort. Knoblauch und "
                            "Petersilie geben Frische und Würze. Wir servieren den Kaviar "
                            "kalt oder lauwarm, dazu passt frisches Brot.",
                            "auberginenkaviar,essen",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Auberginen, Tomaten, Zwiebeln, Paprika, Knoblauch, "
                            "Sonnenblumenöl, Petersilie, Gewürze (Salz, schwarzer Pfeffer)",
                        ),
                        _p(
                            "Gemüse-Pakoras",
                            "5.90",
                            "Goldene Gemüsepuffer aus der indischen Küche: geriebene "
                            "Kartoffeln, Karotten und Kohl werden mit Gewürzen vermengt und "
                            "in heißem Öl ausgebacken. Außen goldbraun und knusprig, innen "
                            "weich und saftig. Heiß serviert, dazu passen Minzsauce oder "
                            "Ketchup.",
                            "vegetable,pakora",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Kohl, Karotten, Kartoffeln, Mehl, Semmelbrösel, Frittieröl, "
                            "frische Kräuter, Gewürze (Salz, Pfeffer, Gewürzmischung)",
                        ),
                        _p(
                            "Gemüsebratlinge",
                            "5.50",
                            "Saftige Bratlinge aus Kohl, Karotten und Kartoffeln, in Mehl "
                            "gewendet und goldbraun gebraten. Die Panade wird knusprig, "
                            "während der Kern zart und weich bleibt. Eine feine pflanzliche "
                            "Alternative zur klassischen Frikadelle.",
                            "vegetable,fritters",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Kohl, Karotten, Kartoffeln, Mehl, Öl zum Braten, Gewürze (Salz, "
                            "Pfeffer)",
                        ),
                        _p(
                            "Kartoffelpuffer (Draniki)",
                            "5.80",
                            "Der belarussische Klassiker: geriebene Kartoffeln mit etwas Mehl "
                            "oder Stärke, in Öl gebraten, bis die Ränder knusprig werden und "
                            "der Kern weich bleibt. Wir servieren die Puffer heiß mit "
                            "Schmand. Gut als Vorspeise oder als Teller zum Teilen.",
                            "potato,pancakes",
                            diets=["vegetarisch"],
                            allergens=["gluten", "milch"],
                            vat="7.00",
                            ingredients="Kartoffeln, Mehl oder Stärke, Öl zum Braten, Schmand, Gewürze "
                            "(Salz, Pfeffer)",
                        ),
                        _p(
                            "Reisbratlinge",
                            "5.20",
                            "Gekochter Reis mit geriebenen Karotten und Kartoffeln, gewürzt "
                            "mit Paprika und Kurkuma und in knuspriger Panade gebraten. Innen "
                            "bleiben die Bratlinge zart und sättigend. Schmecken mit einer "
                            "Sauce ebenso wie für sich allein.",
                            "reisbratling,essen",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Reis, Karotten, Kartoffeln, Mehl, Semmelbrösel, Öl zum Braten, "
                            "frische Kräuter, Gewürze (Salz, Pfeffer, Paprika, Kurkuma)",
                        ),
                        _p(
                            "Schmorkohl",
                            "4.50",
                            "Weißkohl schmort mit Karotten und Tomatenmark langsam weich und "
                            "wird dabei saftig und aromatisch. Zucker und ein Spritzer Essig "
                            "geben ihm eine leicht süßsaure Note. Passt zu Kartoffeln, zu "
                            "Bratlingen oder einfach mit Brot.",
                            "schmorkohl,essen",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten"],
                            vat="7.00",
                            ingredients="Weißkohl, Karotten, Tomatenmark, Pflanzenöl, Weizenmehl, Essig 3 "
                            "%, Wasser oder selleriefreie Gemüsebrühe, Gewürze (Zucker, Salz, "
                            "schwarzer Pfeffer, Lorbeerblatt)",
                        ),
                        _p(
                            "Ofengemüse vom Blech",
                            "6.90",
                            "Buntes Gemüse der Saison — Paprika, Blumenkohl, Zucchini, "
                            "Kürbis, Spargel und Brokkoli — wird mit Öl und Gewürzen im Ofen "
                            "geröstet, bis es weich ist und leichte Röstaromen bekommt. Als "
                            "Beilage oder als leichtes Hauptgericht.",
                            "roasted,veggies",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Paprika, Blumenkohl, Karotten, Zucchini, Kürbis, Spargel, grüne "
                            "Bohnen, Brokkoli, Pflanzenöl, Gewürze (Salz, Pfeffer, "
                            "Gewürzmischung)",
                        ),
                    ],
                    "vegetable,pakora",
                    "Gebackenes und Gebratenes zum Start: Pakoras, Bratlinge und Ofengemüse — "
                    "warm oder lauwarm servierbar.",
                    "preisliste",
                ),
                (
                    "Salate",
                    "salate",
                    [
                        _p(
                            "Chinakohl-Salat",
                            "5.40",
                            "Knackiger Chinakohl, Gurke, Tomate und Karotte — leicht, saftig "
                            "und schön bunt. Ein Dressing aus Olivenöl und Zitronensaft hält "
                            "alles frisch und mild, frische Kräuter und Koriander setzen den "
                            "feinen Akzent.",
                            "cabbage,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Chinakohl, Gurke, Tomate, Karotte, frische Kräuter, "
                            "Zitronensaft, Olivenöl, Gewürze (Salz, Pfeffer, Koriander)",
                        ),
                        _p(
                            "Morkowtscha (Karottensalat)",
                            "4.90",
                            "Fein geraspelte Karotte, mariniert in Öl, Essig und einer Prise "
                            "Zucker — süß-sauer, würzig und angenehm frisch. Koriander und "
                            "Chili geben dem Salat seine orientalische Note und eine leichte "
                            "Schärfe. Passt zu Reis, Kartoffeln und warmen Gerichten.",
                            "carrot,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Karotten, Pflanzenöl, Essig 9 %, Gewürze (Zucker, Salz, "
                            "Koriander, Chilipulver, schwarzer Pfeffer)",
                        ),
                        _p(
                            "Frühlingssalat",
                            "5.90",
                            "Radieschen, Gurke, junge Salatblätter und grüne Erbsen — "
                            "knackig, hell und voller Frühlingsstimmung. Olivenöl mit "
                            "Zitronensaft, Dill und Petersilie hält das Dressing leicht und "
                            "lässt den natürlichen Geschmack des Gemüses ganz nach vorn "
                            "treten.",
                            "spring,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Radieschen, Gurke, Salatblätter, grüne Erbsen, Dill und "
                            "Petersilie, Olivenöl, Zitronensaft, Gewürze (Salz, Pfeffer)",
                        ),
                        _p(
                            "Sommersalat",
                            "5.50",
                            "Der Klassiker aus saftigen Tomaten und frischen Gurken, sanft "
                            "mit Schmand angemacht. Frische Kräuter und etwas schwarzer "
                            "Pfeffer runden die süßen, sonnengereiften Aromen ab — einfach, "
                            "cremig und ganz nach Sommer.",
                            "cucumber,tomato",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Gurken, Tomaten, Schmand, frische Kräuter, Gewürze (Salz, "
                            "Pfeffer)",
                        ),
                        _p(
                            "Rote-Bete-Salat mit Knoblauch",
                            "4.50",
                            "Gekochte Rote Bete, fein geraspelt und mit Knoblauch "
                            "abgeschmeckt — kräftig in Farbe und Geschmack. Pflanzenöl und "
                            "Zitronensaft bringen Frische und eine feine Säure dazu. Schlicht "
                            "zubereitet und trotzdem voller Geschmack — und dabei richtig "
                            "gesund.",
                            "beetroot,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Rote Bete (gekocht), Knoblauch, Pflanzenöl, Zitronensaft, "
                            "Gewürze (Salz, Pfeffer)",
                        ),
                        _p(
                            "Winegret-Salat",
                            "5.20",
                            "Der bekannte Klassiker mit unverwechselbar süß-saurem Geschmack: "
                            "gekochte Rote Bete, Kartoffeln und Karotten treffen auf "
                            "Salzgurken, Sauerkraut, Erbsen und Zwiebel. Pflanzenöl verbindet "
                            "alles zu einem harmonischen, farbenfrohen Ganzen.",
                            "winegret,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            allergens=["sulfit"],
                            vat="7.00",
                            ingredients="Rote Bete (gekocht), Kartoffeln (gekocht), Karotten (gekocht), "
                            "Sauerkraut, Salzgurken, Erbsen (Konserve), Zwiebeln, Pflanzenöl, "
                            "Gewürze (Salz, Pfeffer)",
                        ),
                        _p(
                            "Gurkensalat mit Kräutern",
                            "4.80",
                            "Ganz leicht, knackig und erfrischend — hier steht die Gurke im "
                            "Mittelpunkt. Dill und Petersilie, etwas Pflanzenöl und ein "
                            "Spritzer Zitrone genügen völlig. Eine schlichte Beilage zu allen "
                            "warmen Gerichten, besonders an heißen Sommertagen.",
                            "cucumber,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Frische Gurken, Dill, Petersilie, Pflanzenöl, Zitronensaft, "
                            "Gewürze (Salz, Pfeffer)",
                        ),
                        _p(
                            "Gurken-Raita mit Minze",
                            "5.10",
                            "Kühler, würziger Joghurtsalat nach indischer Art: geraspelte "
                            "Gurke mit frischer Minze und Koriandergrün in cremigem "
                            "Naturjoghurt. Kreuzkümmel und Zitronensaft geben Aroma und feine "
                            "Säure — der ideale Ausgleich zu scharf gewürzten Gerichten.",
                            "cucumber,raita",
                            diets=["vegetarisch", "glutenfrei"],
                            allergens=["milch"],
                            vat="7.00",
                            ingredients="Naturjoghurt, Gurke, frische Minze, Koriandergrün, Zitronensaft, "
                            "Gewürze (Kreuzkümmel, Salz, schwarzer Pfeffer)",
                        ),
                        _p(
                            "Spargelsalat Asberg",
                            "7.90",
                            "Knackiger grüner Spargel, süße Kirschtomaten und zarte "
                            "Salatblätter, angemacht mit Olivenöl und Zitronensaft. Geröstete "
                            "Pinienkerne bringen eine nussige Note und angenehmen Biss dazu. "
                            "Ein feiner, leichter Salat für helle Frühlingstage.",
                            "asparagus,salad",
                            diets=["vegan", "glutenfrei", "laktosefrei"],
                            vat="7.00",
                            ingredients="Grüner Spargel, Kirschtomaten, Salatblätter, Olivenöl, "
                            "Zitronensaft, Pinienkerne, Gewürze (Salz, schwarzer Pfeffer)",
                        ),
                        _p(
                            "Veganer Caesar-Salat",
                            "7.50",
                            "Der berühmte Caesar, rein pflanzlich: knackiger Romana-Salat, "
                            "Kirschtomaten und würzige vegane Croutons unter einem cremigen "
                            "Cashew-Dressing mit Dijon, Kapern und Hefeflocken. Gebratener "
                            "Tofu ersetzt das Hähnchen und macht den Salat schön sättigend.",
                            "vegan,caesar",
                            diets=["vegan", "laktosefrei"],
                            allergens=["gluten", "soja", "schalenfruechte", "senf"],
                            vat="7.00",
                            ingredients="Salatblätter (Eisberg oder Romana), fester Tofu, Kirschtomaten, "
                            "vegane Croutons, Cashewkerne, für das Dressing: Cashewkerne, "
                            "Wasser, Zitronensaft, Knoblauch, Dijon-Senf, Kapern, Hefeflocken",
                        ),
                    ],
                    "spring,salad",
                    "Frische Salate und Joghurt-Salate — als Vorspeise, als Beilage zum "
                    "Buffet oder als leichte Hauptspeise.",
                    "preisliste",
                ),
            ],
            "Veganes und ayurvedisch inspiriertes Catering: 49 Gerichte in sechs Gängen — "
            "einzeln bestellbar oder als fertiges Menü-Paket. Wir kochen frisch, liefern warm "
            "und bauen auf Wunsch vor Ort auf.",
            "sets",
            # Foto des Bereichs: der slug-Fallback griff «catering-buffet.webp» ab —
            # eine Bratwurst-Theke auf einer rein pflanzlichen Seite.
            "vegan,buffet",
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
                    "a": "The restaurant and the shop are 100 % plant-based. Our catering "
                    "menu also has ayurvedic classics with cream, paneer or yoghurt — "
                    "every dish is labelled.",
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
            "trust": {"marks": ["Vegan & vegetarian", "Ayurveda", "Regional"]},
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
        "style": "classic",  # DS-8 (Fokus): шапка одной строкой,
        "sticky": True,
        "items": [
            {"label": "Start", "type": "page", "target": "home"},
            {"label": "Zimmer & Preise", "type": "archetype", "target": "stays"},
            # HF-1 (фидбэк владельца 2026-07-31): у отеля есть услуги, акции и
            # новости, но в шапке их не было — гость их просто не находил.
            {"label": "Wellness & Extras", "type": "archetype", "target": "booking"},
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Neuigkeiten", "type": "archetype", "target": "blog"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
            {"label": "Hausordnung", "type": "url", "target": "/hausordnung/"},
            {"label": "Kontakt", "type": "anchor", "target": "/#kontakt"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Zimmer", "type": "archetype", "target": "stays", "icon": "🛏"},
            {"label": "Galerie", "type": "page", "target": "gallery", "icon": "📷"},
            {"label": "Bewertungen", "type": "page", "target": "reviews", "icon": "⭐"},
            # Аудит 2026-08-06: якорь `/#buchen` вёл в никуда — секция поиска дат
            # у отеля ВЫКЛЮЧЕНА (hero_widget="stays" держит поиск внутри hero, см.
            # _kit_sections), то есть id="buchen" на главной не рендерится.
            {"label": "Buchen", "type": "archetype", "target": "stays", "icon": "📅"},
        ],
    },
}

HOTEL = DemoKit(
    key="hotel",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "stay_rooms": {"preset": "cols2"}},
    label="Pension Seeblick",
    hero_widget="stays",  # E4 «задача-первым»: поиск дат ВНУТРИ hero (первый экран)
    # DS-8 (Fokus для отеля): сплит-баннер с поиском дат, номера сразу под ним,
    # компакт-полоса доверия, CTA «Buchen» в шапке; шумные секции — на страницах.
    look="klar",
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    section_styles={"trust": "compact"},
    sections_off=[
        "archetypes",
        "usp_bar",
        "team",
        "gallery",
        "reviews",
        "testimonials",
        "stay_search",
    ],
    # FB-3 Вариант B демо: свой статус «Anzahlung erhalten» между Anfrage и Bestätigt (держит номер).
    status_defs={
        "stay": [
            {
                "code": "anzahlung_erhalten",
                "label": "Anzahlung erhalten",
                "role": "active",
                "stage": "in_progress",
                "blocks_capacity": True,
            }
        ]
    },
    status_edges={
        "stay": [
            {"src": "pending", "dst": "anzahlung_erhalten"},
            {"src": "anzahlung_erhalten", "dst": "confirmed"},
        ]
    },
    business_type="hotel",
    subdomain="hotel",  # → hotel.<base>
    # 2026-07-30: слайдер над поиском дат (первый экран).
    heroes=[
        {
            "image_kw": "hotel,room",
            "title": "Pension Seeblick",
            "text": "Ruhige Zimmer mit Seeblick — Frühstück inklusive.",
            "button_label": "Zimmer ansehen",
            "button_url": "/unterkunft/",
        },
        {
            "image_kw": "lake,morning",
            "title": "Aufwachen am Wasser",
            "text": "Steg, Ruderboot und Morgennebel — direkt vor der Tür.",
            "button_label": "Verfügbarkeit prüfen",
            "button_url": "/unterkunft/",
        },
        {
            "image_kw": "breakfast,hotel",
            "title": "Frühstück bis 11 Uhr",
            "text": "Regionale Produkte, frisches Brot und Zeit zum Ausschlafen.",
            "button_label": "Angebote ansehen",
            "button_url": "/aktionen/",
        },
    ],
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
        # Ставка 19 %: проживание льготное (7 %), а завтрак, парковка и прочие
        # услуги — обычные (Aufteilungsgebot, § 12 Abs. 2 Nr. 11 UStG).
        ("Frühstücksbuffet", "12", "stays", True, "19.00"),
        ("Parkplatz", "8", "stays", True, "19.00"),
        ("Später Check-out (bis 14 Uhr)", "20", "stays", False, "19.00"),
        ("Haustier", "15", "stays", False, "19.00"),
    ],
    # HF-1: promotions у типа hotel только suited_for (по умолчанию выключен) —
    # включаем явно, иначе пункт меню «Angebote» и секция акций отпадают по гейту.
    enable_modules=["stays", "promotions"],
    promotions_spec=[
        {
            # P6 «ценовой слой»: цель = первый номер (Doppelzimmer Seeblick) — скидка
            # применяется в штатной броне, лимит кампании списывается в той же
            # транзакции. Правил НЕТ намеренно: акция действует всегда, поэтому
            # демо-брони её честно списывают (инвариант ките-теста).
            "title": "Frühbucher: Doppelzimmer Seeblick −10 %",
            "desc": "Direkt online buchen und pro Nacht 10 % sparen — der Aktionspreis "
            "wird bei der Buchung automatisch abgezogen.",
            "stay_unit": 0,
            "percent": 10,
            "compare_at": "89",  # Basispreis/Nacht → durchgestrichen + Prozent-Pille
            "discount_style": "percent",
            "limit": 10,
            "group": "Zimmer-Angebote",
            "ends_in_days": 45,
            "images": ["hotel,room", "lake,view"],
        },
        {
            # Раннее бронирование с ОКНОМ ПРОЖИВАНИЯ (target_rules): матчер проверяет
            # дату ЗАЕЗДА. Даты статические — как SeasonRate этого же кита.
            "title": "Frühbucher Herbst & Winter: Familienzimmer −12 %",
            "desc": "Für Anreisen vom 1. September bis 20. Dezember: jetzt buchen und "
            "12 % pro Nacht sparen — solange die Aktionskontingente reichen.",
            "stay_unit": 2,
            "percent": 12,
            "rules": {"stay_from": "2026-09-01", "stay_to": "2026-12-20"},
            "limit": 8,
            "group": "Zimmer-Angebote",
            "ends_in_days": 60,
            "images": ["family,hotel,room", "kids,room"],
        },
        {
            "title": "Last-Minute: Einzelzimmer Komfort −15 %",
            "desc": "Kurzentschlossen ans Wasser: 58,65 € statt 69 € pro Nacht, "
            "Frühstück inklusive. Nur diese Woche und nur solange Zimmer frei sind.",
            "stay_unit": 1,
            "percent": 15,
            "compare_at": "69",
            "discount_style": "countdown",
            "countdown": True,
            "new": True,
            "limit": 5,
            "group": "Zimmer-Angebote",
            "ends_in_days": 5,
            "images": ["hotel,single,room", "hotel,bathroom"],
        },
        {
            # Ценовой слой на УСЛУГУ: у цели-услуги нет базовой цены внутри акции —
            # new_price/compare_at обязательны (иначе new_price=None и промо-цена
            # к слоту не применяется).
            "title": "Sauna am Nachmittag: 29 € statt 39 €",
            "desc": "Montag bis Donnerstag zwischen 14 und 18 Uhr gehört die "
            "Panorama-Sauna 90 Minuten Ihnen allein — freie Zeit wählen, der "
            "Aktionspreis gilt automatisch.",
            "service": 1,
            "new_price": "29",
            "compare_at": "39",
            "discount_style": "festpreis",
            "rules": {"weekdays": [0, 1, 2, 3], "hour_from": 14, "hour_to": 18},
            "limit": 25,
            "group": "Wellness & Extras",
            "ends_in_days": 60,
            "images": ["sauna,wellness", "hotel,bathroom"],
        },
        {
            "title": "Wochenend-Frühstück am Zimmer −20 %",
            "desc": "Samstags und sonntags servieren wir das Seeblick-Frühstück für "
            "19,20 € statt 24 € pro Person — Bestellung bis 20 Uhr am Vorabend.",
            "service": 2,
            "percent": 20,
            "compare_at": "24",
            "discount_style": "strikethrough",
            "rules": {"weekdays": [5, 6], "hour_from": 8, "hour_to": 11},
            "limit": 30,
            "group": "Wellness & Extras",
            "ends_in_days": 45,
            "images": ["breakfast,hotel", "terrace"],
        },
        {
            # «Свободная» акция (без цели): CTA ведёт в штатный заказ (P5).
            "title": "Kurzurlaub-Paket: 2 Nächte mit Halbpension",
            "desc": "Zwei Nächte im Doppelzimmer Seeblick mit Frühstücksbuffet und "
            "Abendessen — ab 199 € für zwei Personen statt 234 €.",
            "new_price": "199",
            "compare_at": "234",
            "discount_style": "ab",
            "limit": 12,
            "group": "Pakete",
            "ends_in_days": 90,
            "images": ["hotel,bed", "hotel,interior", "garden,terrace"],
        },
    ],
    # HF-1 (п. 14): новости пансиона — лента на главной и страница /blog/.
    blog_posts=[
        (
            "Neue Seeterrasse ab Mai geöffnet",
            "Frühstück und Abendkarte künftig direkt am Wasser.",
            "Den ganzen Winter über haben wir gebaut: Ab Mai servieren wir "
            "Frühstück und Abendkarte auf der neuen Seeterrasse.\n\n"
            "30 Plätze, windgeschützt und mit Blick über den ganzen See. "
            "Für Hausgäste ist keine Reservierung nötig.",
            "garden,terrace",
        ),
        (
            "Wanderwoche im Herbst: geführte Touren ab Haustür",
            "Drei Touren pro Woche, Rucksackverpflegung inklusive.",
            "Im Oktober starten wir dreimal pro Woche zu geführten Wanderungen "
            "rund um den See.\n\n"
            "Die Touren dauern drei bis fünf Stunden, Rucksackverpflegung aus "
            "unserer Küche ist inklusive. Anmeldung an der Rezeption.",
            "forest,path",
        ),
        (
            "Wir sind jetzt klimaneutral beheizt",
            "Neue Pelletheizung ersetzt den alten Ölkessel.",
            "Seit dieser Saison heizen wir mit Pellets aus der Region — "
            "der Ölkessel ist Geschichte.\n\n"
            "Zusammen mit der Photovoltaik auf dem Nebengebäude deckt das den "
            "Großteil unseres Wärmebedarfs.",
            "hotel,interior",
        ),
    ],
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
    # Фидбэк 2026-07-28: у отеля Termine-страница была пустой («Online booking is
    # not set up yet») — гостевые доп-услуги дают архетипу живое содержимое.
    # Фидбэк 2026-07-30: без ресурсов слоты записи не строились («нет доступных») —
    # AvailabilityRule живёт на Resource; два общих ресурса закрывают все 4 услуги.
    resources=[
        {
            "name": "Wellnessbereich",
            "type": "service",
            "start": "09:00",
            "end": "19:00",
            "slot": 30,
            "weekdays": range(0, 7),
        },
        {
            "name": "Rezeption",
            "type": "service",
            "start": "08:00",
            "end": "20:00",
            "slot": 30,
            "weekdays": range(0, 7),
        },
    ],
    # Фидбэк владельца 2026-07-31 («добавь описания к услугам»): у услуг были
    # однострочники — страница услуги выглядела пустой. Теперь у каждой полное
    # описание + характеристики и FAQ (богатая карточка UA4-3).
    services=[
        (
            {"de": "Wellness-Massage", "en": "Wellness massage"},
            50,
            "59",
            {
                "de": "Klassische Rückenmassage im hauseigenen Wellnessbereich. "
                "Unsere Masseurin löst Verspannungen in Nacken, Schultern und "
                "unterem Rücken — mit warmem Mandelöl und einem Tempo, das Sie "
                "vorgeben. Nach der Behandlung ruhen Sie im Kaminzimmer nach, "
                "Kräutertee und Wasser stehen bereit.",
                "en": "Classic back massage in our own wellness area. Our masseuse "
                "releases tension in the neck, shoulders and lower back — with warm "
                "almond oil and at a pace you set. Afterwards you rest in the "
                "fireplace room, herbal tea and water included.",
            },
            "massage,spa",
            {
                "attributes": [
                    "50 Minuten Behandlung + 20 Minuten Ruhezeit",
                    "Warmes Mandelöl (auf Wunsch parfümfrei)",
                    "Auch für Nicht-Hausgäste buchbar",
                    "Handtücher und Bademantel inklusive",
                ],
                "faq": [
                    {
                        "q": "Muss ich im Haus wohnen?",
                        "a": "Nein — die Massage können Sie auch als Tagesgast buchen. "
                        "Bitte kommen Sie 10 Minuten vor dem Termin an die Rezeption.",
                    },
                    {
                        "q": "Was, wenn ich Rückenprobleme habe?",
                        "a": "Sagen Sie es uns vor Beginn: Wir passen Druck und Griffe an "
                        "und lassen empfindliche Stellen auf Wunsch ganz aus.",
                    },
                ],
            },
        ),
        (
            {"de": "Private Sauna", "en": "Private sauna"},
            90,
            "39",
            {
                "de": "Die Panorama-Sauna exklusiv für Sie und Ihre Begleitung. "
                "90 Minuten gehört der ganze Wellnessbereich Ihnen allein: "
                "finnische Sauna bei 85 °C, Kaltwasserbecken und Liegen mit "
                "Blick über den See. Aufgüsse machen Sie selbst — Duftkonzentrate "
                "liegen bereit.",
                "en": "The panorama sauna exclusively for you and your companion. "
                "For 90 minutes the whole wellness area is yours: Finnish sauna at "
                "85 °C, cold plunge pool and loungers overlooking the lake. You do "
                "the infusions yourself — scent concentrates are provided.",
            },
            "sauna,wellness",
            {
                "attributes": [
                    "Bis zu 4 Personen — der Preis gilt pro Buchung",
                    "Finnische Sauna 85 °C + Kaltwasserbecken",
                    "Handtücher, Bademantel und Wasser inklusive",
                    "Letzter Termin 21:00 Uhr",
                ],
                "faq": [
                    {
                        "q": "Gilt der Preis pro Person?",
                        "a": "Nein, pro Buchung — bis zu vier Personen kosten dasselbe.",
                    },
                    {
                        "q": "Können wir spontan verlängern?",
                        "a": "Wenn danach niemand gebucht hat, gerne: 30 Minuten "
                        "Verlängerung kosten 15 €, direkt an der Rezeption.",
                    },
                ],
            },
        ),
        (
            {"de": "Seeblick-Frühstück am Zimmer", "en": "Lake-view breakfast in your room"},
            60,
            "24",
            {
                "de": "Frühstück mit Blick auf den See — direkt aufs Zimmer serviert. "
                "Wir bringen frische Brötchen aus der Dorfbäckerei, Rührei oder "
                "gekochte Eier, Käse und Schinken aus der Region, Obst, Joghurt, "
                "Butter und Marmelade aus eigener Herstellung, dazu Kaffee, Tee "
                "und frisch gepressten Orangensaft.",
                "en": "Breakfast with a lake view — served straight to your room. We "
                "bring fresh rolls from the village bakery, scrambled or boiled eggs, "
                "regional cheese and ham, fruit, yoghurt, butter and our own jam, plus "
                "coffee, tea and freshly squeezed orange juice.",
            },
            "breakfast,hotel",
            {
                "attributes": [
                    "Servierzeit 07:30–10:30 Uhr nach Wunsch",
                    "Preis pro Person, Kinder bis 6 Jahre frei",
                    "Vegetarisch, vegan und glutenfrei möglich",
                    "Bestellung bis 20:00 Uhr am Vorabend",
                ],
                "faq": [
                    {
                        "q": "Bis wann muss ich bestellen?",
                        "a": "Bis 20:00 Uhr am Vorabend — dann ist alles frisch beim "
                        "Bäcker vorbestellt.",
                    },
                    {
                        "q": "Geht das auch vegan?",
                        "a": "Ja. Schreiben Sie es in die Notiz zur Buchung, wir stellen "
                        "das Tablett komplett pflanzlich zusammen.",
                    },
                ],
            },
        ),
        (
            {"de": "E-Bike-Verleih (Tag)", "en": "E-bike rental (day)"},
            480,
            "29",
            {
                "de": "Tourenrad inklusive Helm, Schloss und Kartenmaterial. "
                "Unsere E-Bikes haben 500-Wh-Akkus — damit fahren Sie die "
                "Seeumrundung (42 km) bequem an einem Tag. Wir stellen Sattel "
                "und Lenker vor der Abfahrt auf Sie ein und zeigen Ihnen auf der "
                "Karte die schönsten Einkehrmöglichkeiten.",
                "en": "Touring bike including helmet, lock and maps. Our e-bikes have "
                "500 Wh batteries — enough to ride around the lake (42 km) comfortably "
                "in one day. We adjust saddle and handlebars for you before you set off "
                "and point out the nicest stops on the map.",
            },
            "bike,tour",
            {
                "attributes": [
                    "500-Wh-Akku — rund 80 km Reichweite",
                    "Helm, Schloss und Satteltasche inklusive",
                    "Ausgabe ab 08:00 Uhr, Rückgabe bis 20:00 Uhr",
                    "Körpergrößen 155–195 cm",
                ],
                "faq": [
                    {
                        "q": "Brauche ich Erfahrung mit E-Bikes?",
                        "a": "Nein. Wir erklären Unterstützungsstufen und Bremsen vor "
                        "der Abfahrt und drehen mit Ihnen eine kurze Proberunde.",
                    },
                    {
                        "q": "Was ist bei Regen?",
                        "a": "Bis 18:00 Uhr am Vortag können Sie kostenfrei absagen — "
                        "danach verschieben wir den Termin auf einen trockenen Tag.",
                    },
                ],
            },
        ),
    ],
    stay_units=[
        {
            "name": {"de": "Doppelzimmer Seeblick", "en": "Double room lake view"},
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
            "rooms": ["101", "102", "103", "104"],  # PMS-R: физические номера
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
            "name": {"de": "Einzelzimmer Komfort", "en": "Comfort single room"},
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
    stay_reviews=[
        (
            0,
            5,
            "Familie M.",
            "familie.m@example.de",
            "Wunderschönes Zimmer, sehr sauber und ruhig.",
        ),
        (0, 4, "Petra L.", "petra.l@example.de", "Gemütlich und gut ausgestattet. Frühstück top."),
        (1, 5, "Jens H.", "jens.h@example.de", "Perfekt für einen erholsamen Kurzurlaub."),
    ],
    # UB3-2: подборки номеров → чипы-фасет на /unterkunft/ (индексы — позиции в stay_units).
    collections=[
        ("Mit Seeblick", {"stay_units": [0]}),
        ("Familienzimmer", {"stay_units": [2, 3]}),
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
    # PMS-D: ручной revenue-management — последние номера дороже.
    occupancy_pricing=[
        {"occupancy": 60, "percent": 5},
        {"occupancy": 85, "percent": 12},
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
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            # Аудит 2026-08-06: был якорь `/#aktionen` — прокрутка главной. Страница
            # всех акций работает с любой страницы витрины, а не только с главной.
            {"label": "Aktionen", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🛒"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
            # SF-4a: вход в Merkzettel с мобильного (иконка шапки скрыта на sm-)
            {"label": "Merkliste", "type": "page", "target": "wishlist", "icon": "❤️"},
            {"label": "Treue", "type": "archetype", "target": "loyalty", "icon": "💝"},
        ],
    },
}

AKTIONSMARKT = DemoKit(
    key="aktionsmarkt",
    # SH-24 (решение владельца Р-6): у демо с заказом ТОВАРА доставка включена —
    # иначе выбор «Abholung | Lieferung» на чекауте не показать.
    delivery={
        "enabled": True,
        "fee_cents": 350,
        "free_cents": 3000,
        "min_cents": 1000,
        "area": "Lieferung im Stadtgebiet Köln.",
    },
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    # DL-11: 6 категорий = 2×3 (стиль compact с настроенной раскладкой берёт движок)
    # DL-18.2: 4 корневых направления = 2 полных ряда по 2 (крупные фото-плитки);
    # подкатегории живут внутри «полок» (regale/tabs), а не в корне.
    section_layouts={
        "gallery": {"preset": "cols3"},
        "categories": {"preset": "cols2"},
        # DL-18.2: полки-контейнеры оставили секции товаров 6 позиций — при четырёх
        # колонках это полтора ряда (замок test_fill_rows), при трёх — ровно два.
        "products": {"preset": "cols3"},
    },
    label="Aktionsmarkt Sparfuchs",
    business_type="grocery",
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_angebote",
    look="klar",
    promo_card="preis",  # DL-16.4: «Preis zuerst» — дефолт акционного демо
    # DL-19 (N1): товары — «Regal»: цена ведёт, фото опознавательным квадратом.
    # Дискаунтер выбирают ценой, и на экран помещается вдвое больше позиций.
    card_style="regal",
    # DL-17.2 (фидбэк «карусели нет в демо»): листание фото прямо на карточке
    # (стрелки при наведении + свайп). AMP-2: у большинства товаров остался ОДИН
    # сильный реальный кадр — второй ставим только там, где он честно показывает
    # тот же товар (Bio-Gemüsekiste); один хороший кадр продаёт лучше трёх слабых.
    card_slider="on",
    # SF-4a: Merkzettel у магазина акций (grocery-дефолт опции — False).
    # DL-4: site_defaults.hero_widget — config_patch мерджится ПОСЛЕ сборки
    # (латентный баг сидинга: _FOKUS_BASE.hero_widget="none" затирал плитки
    # kit.hero_widget, комментарий ниже врал с DS-9) → плитки восстановлены.
    config_patch={
        "hero_style": "split",
        "nav": {"cta": True},
        "wishlist": True,
        # DL-20: страница ГРУППЫ акций — «Prospekt» на весь сайт (дискаунтер) …
        "site_defaults": {"hero_widget": "aktionsmarkt", "promo_group_style": "prospekt"},
        # DL-17.2: группы акций — лентами со стрелками (A3); без ключа страница
        # рисовала сетки, и «карусели из макета» в демо не было видно.
        "promo_layout": "slider",
        # … и ДВЕ группы со своим шаблоном поверх общего — приоритет виден на
        # витрине: распродажа идёт на одну дату (Countdown), у спасённых
        # продуктов есть «паровоз» — Überraschungstüte (Schaufenster).
        "promo_groups": {"Räumung": "countdown", "Anti-Food-Waste": "schaufenster"},
        # DL-21.2: обзорная /aktionen/ — «Kopfbild» (фото сайта + «N Angebote · M Gruppen»),
        # ленты групп (promo_layout) остаются.
        "promo_page_style": "kopfbild",
    },
    # DL-4: акции на главной — витриной «Deal der Woche» (spotlight: featured-
    # карточка + полоса «Endet bald»; макет-референс канваса Sparfuchs).
    section_styles={"promotions": "spotlight"},
    subdomain="aktionsmarkt",
    # 2026-07-30: слайдер + плитки hero_widget="aktionsmarkt"
    # (Deals/Sortiment/Treuepunkte/Newsletter).
    hero_widget="aktionsmarkt",
    heroes=[
        {
            "image_kw": "markt-hero",
            "title": "Aktionsmarkt Sparfuchs",
            "text": "Jede Woche neue Angebote — sparen bei allem, was Sie täglich brauchen.",
            "button_label": "Aktuelle Deals",
            "button_url": "/aktionen/",
        },
        {
            "image_kw": "markt-hero-vorrat",
            "title": "Dauertiefpreise",
            "text": "Grundnahrungsmittel dauerhaft günstig — ohne Kleingedrucktes.",
            "button_label": "Sortiment ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "markt-hero-tueten",
            "title": "Überraschungstüten",
            "text": "Gerettete Lebensmittel zum halben Preis — solange der Vorrat reicht.",
            "button_label": "Zu den Aktionen",
            "button_url": "/aktionen/",
        },
    ],
    # DL-4: поле — ФОЛБЭК без look'а; фактический акцент даёт look_accent
    # (grocery×klar = зелёный), Sale-Rot живёт в чипах скидок (красные всегда).
    accent="#dc2626",
    hero_image_kw="markt-hero",
    hero_title="Aktionsmarkt Sparfuchs",
    hero_text="Jede Woche neue Angebote — sparen bei allem, was Sie täglich brauchen.",
    about_title="Über den Aktionsmarkt",
    about_text="Beim Aktionsmarkt Sparfuchs dreht sich alles um gute Angebote: "
    "Wochenangebote, Dauertiefpreise, Räumungsaktionen und gerettete Lebensmittel als "
    "Überraschungstüten. Hier sehen Sie alle Aktionsarten, die unser Shop nutzen kann — "
    "von Prozent-Rabatten über Festpreise bis zu limitierten und wiederkehrenden Aktionen.",
    nav_style="classic",
    address="Marktstraße 1, 50667 Köln",
    # SF-1.1: адрес говорит Köln — city обязан совпадать (сидер по умолчанию
    # ставит Hilden всем китам; без оверрайда hero-eyebrow/SEO/JSON-LD врали).
    city="Köln",
    opening_hours_text="Mo–Sa 8:00–20:00",
    opening_hours={d: ("08:00", "20:00") for d in range(6)},
    gallery_kw=[
        "markt-galerie-markt",
        "markt-galerie-regal",
        "markt-galerie-gemuese",
        "markt-galerie-backwaren",
        "markt-galerie-einkauf",
        "markt-galerie-angebote",
    ],
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
        # DL-17.4 (A1 «Vorschau»): что начнётся на следующей неделе — Prospekt-привычка
        # DACH. `starts_in_days` сеет акцию в статусе `scheduled`: витрина показывает
        # её лентой «Ab dieser Woche» без покупки, beat включит сам в день старта.
        {
            "title": "Kaffee-Woche: −25 % ab Montag",
            "desc": "Nächste Woche ist Kaffee-Woche — alle Röstungen −25 %.",
            "product": 10,
            "percent": 25,
            "group": "Wochenangebote",
            "starts_in_days": 3,
            "ends_in_days": 7,
        },
        {
            "title": "Käse-Tage −20 %",
            "desc": "Ab nächster Woche: Gouda und Bergkäse günstiger.",
            "product": 16,
            "percent": 20,
            "group": "Wochenangebote",
            "starts_in_days": 9,
            "ends_in_days": 5,
        },
        {
            "title": "Sonnenblumenöl 1 L für 1,99 €",
            "desc": "Vorschau: Festpreis statt 2,49 € — ab Montag in zwei Wochen.",
            "product": 13,
            "new_price": 1.99,
            "compare_at": 2.49,
            "discount_style": "festpreis",
            "group": "Dauertiefpreis",
            "starts_in_days": 12,
            "ends_in_days": 10,
        },
        {
            "title": "Äpfel −20 %",
            "product": 0,
            "percent": 20,
            "discount_style": "badge",
            "group": "Wochenangebote",
            "ends_in_days": 7,
            "desc": "Knackige Äpfel aus der Region.",
        },
        {
            "title": "Croissant −30 % – nur heute!",
            "new": True,
            "product": 6,
            "percent": 30,
            # DL-19 (AK3): остаток времени кольцом на фото — «горит сегодня»
            "card_style": "ring",
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 2,
            "group": "Wochenangebote",
        },
        {
            "title": "Brot zum Festpreis 0,99 €",
            "product": 4,
            "new_price": "0.99",
            "discount_style": "festpreis",
            "compare_at": "1.99",
            "group": "Dauertiefpreis",
        },
        {
            "title": "Limonade Dauertiefpreis 0,79 €",
            "product": 9,
            "new_price": "0.79",
            "discount_style": "strikethrough",
            "group": "Dauertiefpreis",
        },
        {
            "title": "Gemahlener Kaffee −25 % (limitiert)",
            "image": "markt-kaffee-aktion",
            "product": 10,
            # DL-19 (AK2): своя форма карточки — купон («резервируй и забери»)
            "card_style": "coupon",
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
        {
            "title": "Sonnenblumenöl −40 % (Räumung)",
            "product": 13,
            "percent": 40,
            "group": "Räumung",
        },
        {
            "title": "Basmatireis −35 % – Countdown",
            "product": 12,
            "percent": 35,
            "countdown": True,
            "ends_in_days": 1,
            "group": "Räumung",
        },
        {
            "title": "Bio-Gemüsekiste −20 % – nur 5 Stück",
            "image": "markt-gemuesekiste-inhalt",
            "product": 3,
            "type": "reservation",
            "percent": 20,
            "available_quantity": 5,
            "group": "Wochenangebote",
        },
        {
            # Фидбэк 2026-07-29: mystery — единственный стиль, которого не было
            # в showcase; цена скрыта до клика-раскрытия.
            "title": "Mystery-Deal der Woche",
            "new": True,
            # Носитель — Bergkäse (4,99 €): половина цены сходится с прайсом,
            # а сам товар mystery-стиль всё равно скрывает до раскрытия.
            "product": 19,
            "new_price": "2.49",
            "compare_at": "4.99",
            "discount_style": "mystery",
            "group": "Wochenangebote",
            "ends_in_days": 7,
            "desc": "Ein Überraschungs-Artikel zum halben Preis — Preis erst beim Klick.",
        },
        # Дополнение: закрывает три недостающих стиля (percent/ab/surprise) и
        # механику «limit» (лимит кампании на ОБЫЧНОЙ скидке, не reservation).
        {
            "title": "Tomaten 500 g −25 %",
            "product": 2,  # Tomaten 500 g 2,99 € → 2,24 €
            "percent": 25,
            "discount_style": "percent",  # ← стиля percent в ките не было
            "group": "Wochenangebote",
            "ends_in_days": 7,
            "image": "tomatoes",  # ← первое использование одиночного image в ките
            "desc": "Sonnengereift aus der Region — nur diese Woche.",
        },
        {
            "title": "Bananen — dauerhaft ab 1,29 €",
            "product": 1,  # Bananen 1 kg 1,79 €
            "new_price": "1.29",
            "discount_style": "ab",  # ← «ab»-Preis (kg-Ware: цена «ab» читается честно)
            "group": "Dauertiefpreis",
            "ends_in_days": 30,
            "image": "bananas",
            "desc": "Fair gehandelt, dauerhaft günstig — ohne Kleingedrucktes.",
        },
        {
            "title": "Orangensaft −20 % — nur 40 Flaschen",
            "new": True,
            "product": 7,  # Orangensaft 1 L 2,49 € → 1,99 €
            "percent": 20,
            "limit": 40,  # ← лимит кампании: «Nur noch N» + стоп после 40 продаж
            "group": "Wochenangebote",
            "ends_in_days": 5,
            "image": "orange,juice",
            "desc": "100 % Direktsaft — die Aktionsmenge ist begrenzt.",
        },
        {
            # СВОБОДНАЯ акция (без товара-цели) — поддержано P2:
            # promotions/services.purchase → create_order(custom_lines) без склада.
            # Стиль surprise: бейдж скрыт, акцент на «Überraschung» + зелёный чип
            # is_surprise; вместе с new_price/compare_at даёт цену 9,99 € vs 25 €.
            "title": "Sparfuchs-Überraschungskiste 9,99 € statt 25 €",
            "surprise": True,
            "discount_style": "surprise",  # ← стиля surprise в ките не было
            "new_price": "9.99",
            "compare_at": "25.00",
            "group": "Anti-Food-Waste",
            "ends_in_days": 3,
            "image": "markt-sparkiste",
            "desc": "Bunt gemischt aus allen Abteilungen — der Inhalt bleibt eine "
            "Überraschung, der Warenwert liegt bei rund 25 €.",
        },
        {
            # DL-11: 15-я активная акция — сетка после spotlight (3) = 12 = 4 ряда × 3
            "title": "Gouda jung −20 %",
            "product": 16,  # Gouda jung 400 g 3,49 € → 2,79 €
            "percent": 20,
            "discount_style": "badge",
            "group": "Wochenangebote",
            "ends_in_days": 7,
            "desc": "Mild und cremig — diese Woche günstiger.",
        },
        # DL-15 («пересей демо, чтоб всё было по ширине»): группы /aktionen/ кратны 3
        # колонкам десктопа — Anti-Food-Waste 6, Räumung 3; сроки > 3 дней, чтобы полоса
        # «Endet bald» осталась на 4 карточках (2 колонки × 2).
        {
            "title": "Butter 250 g −30 % — MHD-Ware",
            "product": 17,
            "percent": 30,
            "discount_style": "percent",
            "group": "Anti-Food-Waste",
            "ends_in_days": 5,
            "desc": "Kurz vor dem Mindesthaltbarkeitsdatum — noch bestens.",
        },
        {
            "title": "Bergkäse-Anschnitt −25 % — Reste retten",
            "product": 19,
            "percent": 25,
            "discount_style": "strikethrough",
            "group": "Anti-Food-Waste",
            "ends_in_days": 6,
            "desc": "Anschnitte und Restlaibe zum kleinen Preis — nichts wegwerfen.",
        },
        {
            "title": "Nudeln −30 % (Räumung)",
            "product": 11,
            "percent": 30,
            "discount_style": "badge",
            "group": "Räumung",
            "ends_in_days": 10,
            "desc": "Sortimentswechsel — der Restbestand muss raus.",
        },
    ],
    categories=[
        # DL-18.2 + AMP-2 (2026-09-03, фидбэк «убери туалетную бумагу и бытовую химию»):
        # каталог — как настоящий продуктовый: четыре направления, внутри полки, и
        # НИЧЕГО непищевого. Бытовая химия заменена «Vorratskammer» (Nudeln/Reis/Öl)
        # ПОЗИЦИЯ В ПОЗИЦИЮ: порядок обхода (Obst → Backwaren → Getränke →
        # Vorratskammer → Tüten → Molkerei) и число товаров прежние, поэтому индексы
        # `promotions_spec.product` остались целы.
        (
            "Frische",
            "frische",
            [],
            [
                (
                    "Obst & Gemüse",
                    "obst-gemuese",
                    [
                        _p(
                            "Äpfel 1 kg",
                            "2.49",
                            "Knackig und regional.",
                            "markt-aepfel",
                            unit="kg",
                            content=1,
                        ),
                        _p(
                            "Bananen 1 kg",
                            "1.79",
                            "Fair gehandelt.",
                            "bananas",
                            unit="kg",
                            content=1,
                        ),
                        _p(
                            "Tomaten 500 g",
                            "2.99",
                            "Sonnengereift.",
                            "tomatoes",
                            unit="kg",
                            content=0.5,
                        ),
                        _p(
                            "Bio-Gemüsekiste",
                            "24.90",
                            "Bunte Auswahl der Saison.",
                            ["vegetable,box", "markt-gemuesekiste-inhalt"],
                        ),
                    ],
                    "fresh-fruit",  # DS-9: фото плитки (было SVG)
                ),
                (
                    "Backwaren",
                    "backwaren",
                    [
                        _p(
                            "Bauernbrot 750 g",
                            "1.99",
                            "Täglich frisch gebacken.",
                            "markt-bauernbrot",
                            allergens=["gluten"],
                            unit="kg",
                            content=0.75,
                        ),
                        _p(
                            "Brötchen 6er",
                            "0.60",
                            "Knusprig und frisch.",
                            "markt-broetchen",
                            allergens=["gluten"],
                        ),
                        _p(
                            "Croissant",
                            "1.50",
                            "Buttrig und zart.",
                            "markt-croissant",
                            allergens=["gluten", "milch"],
                        ),
                    ],
                    "markt-backwaren",  # AMP: фото плитки (было SVG)
                ),
            ],
            "Alles, was täglich frisch ins Regal kommt — Obst, Gemüse und Backwaren "
            "aus der Region.",
            "regale",  # DL-16.5 (K2): подкатегории — «полки» лентами со стрелками
            "farm-vegetables",
        ),
        (
            "Getränke & Vorrat",
            "getraenke-vorrat",
            [],
            [
                (
                    "Getränke",
                    "getraenke",
                    [
                        # DL-13 C5: unit/content → Grundpreis (PAngV) на карточках товара
                        # И на акциях по этим товарам (Limonade/Kaffee — акции кита).
                        _p(
                            "Orangensaft 1 L",
                            "2.49",
                            "100 % Direktsaft.",
                            "markt-orangensaft",
                            unit="l",
                            content=1,
                        ),
                        _p(
                            "Mineralwasser 1,5 L",
                            "0.79",
                            "Spritzig oder still.",
                            "markt-mineralwasser",
                            unit="l",
                            content=1.5,
                        ),
                        _p(
                            "Limonade 1,5 L",
                            "1.49",
                            "Eisgekühlt am besten.",
                            "markt-limonade",
                            unit="l",
                            content=1.5,
                        ),
                        _p(
                            "Gemahlener Kaffee 500 g",
                            "6.90",
                            "Kräftige Röstung.",
                            "markt-kaffee",
                            unit="g",
                            content=500,
                        ),
                    ],
                    # DL-18.2: плитка «Getränke» показывала красное вино — в продуктовом
                    # дискаунтере рядом с соками это читалось как чужой кадр.
                    "markt-getraenke",
                ),
                (
                    "Vorratskammer",
                    "vorratskammer",
                    [
                        _p(
                            "Nudeln 500 g",
                            "1.29",
                            "Hartweizengrieß, al dente.",
                            "markt-nudeln",
                            unit="kg",
                            content=0.5,
                        ),
                        _p(
                            "Basmatireis 1 kg",
                            "2.79",
                            "Langkorn, locker und duftend.",
                            "markt-reis",
                            unit="kg",
                            content=1,
                        ),
                        _p(
                            "Sonnenblumenöl 1 L",
                            "2.49",
                            "Neutral im Geschmack.",
                            "markt-oel",
                            unit="l",
                            content=1,
                        ),
                    ],
                    "markt-vorratskammer",
                ),
            ],
            "Getränke und Vorräte zum Bevorraten — Dauertiefpreise das ganze Jahr.",
            "tabs",  # DL-16.5 (K3): полки табами со счётчиком — демо-потребитель вида
            "markt-vorrat",
        ),
        (
            "Überraschungstüten",
            "ueberraschungstueten",
            [
                _p(
                    "Backwaren-Tüte",
                    "15.00",
                    "Wert ca. 15 € — Anti-Food-Waste.",
                    "markt-backtuete",
                ),
                _p(
                    "Obst & Gemüse-Tüte",
                    "12.00",
                    "Wert ca. 12 € — Anti-Food-Waste.",
                    "markt-obsttuete",
                ),
            ],
            "markt-tueten",  # AMP: фото плитки (было SVG)
            "Gerettete Ware vom Vortag — jeden Abend neu gepackt.",
            # DL-20 (P1): у направления есть флагман — первая тюта ведёт страницу.
            "schaufenster",
        ),
        # DL-11: товары ДОПИСАНЫ В КОНЕЦ — индексы promotions_spec.product целы.
        (
            "Molkerei & Eier",
            "molkerei-eier",
            [
                _p(
                    "Gouda jung 400 g",
                    "3.49",
                    "Mild und cremig, am Stück.",
                    "cheese,wheel",
                    unit="kg",
                    content=0.4,
                ),
                _p("Butter 250 g", "1.99", "Süßrahm, aus der Region.", "butter"),
                _p("Eier 10er Freiland", "2.79", "Aus Freilandhaltung.", "eggs"),
                _p(
                    "Bergkäse am Stück",
                    "4.99",
                    "Würzig, 6 Monate gereift.",
                    "markt-bergkaese",
                ),
            ],
            "markt-molkerei",
            "Käse, Butter und Eier von Höfen aus dem Umland.",
            "kopfbild",  # KAT-1: шапка направления с фото
        ),
    ],
)


BAKERY_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog"},
            {
                "label": "Aktionen",
                "type": "group",
                "children": [
                    {"label": "Wochenangebote", "type": "promo_group", "target": "Wochenangebote"},
                    {
                        "label": "Anti-Food-Waste",
                        "type": "promo_group",
                        "target": "Anti-Food-Waste",
                    },
                ],
            },
            {"label": "Partyservice", "type": "archetype", "target": "jobs"},
            {"label": "Treue", "type": "archetype", "target": "loyalty"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🥨"},
            {"label": "Aktionen", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Party", "type": "archetype", "target": "jobs", "icon": "🎉"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
        ],
    },
}

# A1 Bäckerei (dedicated, 2026-07-10): Handwerksbäckerei mit Vorbestellung zur Abholung
# (C&C ohne Lieferung — realistisch für die Branche), Feierabend-Überraschungstüte
# (Anti-Food-Waste), Wochenangebot, Torten auf Vorbestellung, LMIV-Allergene, Stempelkarte.
BAKERY = DemoKit(
    key="bakery",
    # SH-24 (Р-6): пекарня возит корзины по району.
    delivery={
        "enabled": True,
        "fee_cents": 290,
        "free_cents": 2500,
        "min_cents": 1200,
        "area": "Lieferung im Umkreis von 5 km.",
    },
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "categories": {"preset": "cols2"}},
    page_presets=[("info", "team")],  # ST-2: шаблон «Über uns»
    label="Backhaus Krume",
    # FB-3 Вариант B демо: свой статус заказа «In Kommissionierung» между Bestätigt и Fertig.
    status_defs={
        "order": [
            {
                "code": "in_kommissionierung",
                "label": "In Kommissionierung",
                "role": "active",
                "stage": "in_progress",
            }
        ]
    },
    status_edges={
        "order": [
            {"src": "confirmed", "dst": "in_kommissionierung"},
            {"src": "in_kommissionierung", "dst": "ready"},
        ]
    },
    business_type="bakery",
    subdomain="baeckerei",
    enable_lots=True,  # E1.5: Chargen/MHD (Backwaren mit kurzer Haltbarkeit)
    enable_finder=True,  # FD-1: демо Finder («Was suchst du?» → 3 предложения)
    accent="#a16207",  # Braun-Gold (Kruste)
    hero_image_kw="bread,bakery",
    hero_title="Backhaus Krume",
    hero_text="Handwerksbrot aus dem Steinofen — täglich frisch ab 6 Uhr. "
    "Online vorbestellen und ohne Warten abholen.",
    # Фидбэк 2026-07-30: главная «ловит направления» — слайдер (3 слайда) +
    # плитки hero_widget="bakery" (Aktionen/Sortiment/Wunschzeit/Partyservice).
    # DS-8 (Fokus для пекарни): направления плитками + прайс с фото; плитки
    # hero заменяет CTA шапки + компакт-направления (иначе три ряда действий).
    hero_widget="",
    look="klar",
    enable_categories_section=True,  # DS-8: Fokus ведёт через направления
    config_patch={
        "hero_style": "split",
        "nav": {"cta": True},
        "catalog_layout": {"preset": "preisliste_foto"},
    },
    section_styles={"products": "preisliste_foto", "categories": "compact", "trust": "compact"},
    sections_off=["archetypes", "usp_bar", "team", "gallery", "reviews", "testimonials"],
    heroes=[
        {
            "image_kw": "bread,bakery",
            "title": "Backhaus Krume",
            "text": "Handwerksbrot aus dem Steinofen — täglich frisch ab 6 Uhr.",
            "button_label": "Sortiment ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "strawberry,cake",
            "title": "Torten auf Vorbestellung",
            "text": "Wunschtorte mit 2 Tagen Vorlauf — Motiv nach Absprache.",
            "button_label": "Torten ansehen",
            "button_url": "/sortiment/torten/",
        },
        {
            "image_kw": "bakery,bag",
            "title": "Feierabendtüte ab 17 Uhr",
            "text": "Gerettete Backwaren zum halben Preis — solange der Vorrat reicht.",
            "button_label": "Zu den Aktionen",
            "button_url": "/aktionen/",
        },
    ],
    about_title="Unsere Backstube",
    about_text="Seit 1962 backen wir in Hilden nach eigenen Rezepten: Sauerteig ohne "
    "Fertigmischungen, Mehl aus regionalen Mühlen, alles von Hand geformt. Bestellen Sie "
    "Brot und Brötchen bequem online vor — wir legen es zur Wunschzeit zurück. Torten "
    "fertigen wir auf Vorbestellung mit zwei Tagen Vorlauf. Für Feiern und Firmen "
    "liefern wir Kuchenbuffets und belegte Brötchen — fragen Sie einfach über den "
    "Partyservice an.",
    nav_style="classic",
    address="Bäckergasse 3, 40721 Hilden",
    opening_hours_text="Mo–Fr 6:00–18:00 · Sa 6:00–13:00",
    opening_hours={**{d: ("06:00", "18:00") for d in range(5)}, 5: ("06:00", "13:00")},
    gallery_kw=["bread", "bakery,oven", "croissant", "cake", "pastry", "baker,hands"],
    process=[
        ("Online vorbestellen", "Sortiment wählen, Abholzeit angeben — fertig."),
        ("Wir backen frisch", "Ihre Bestellung liegt zur Wunschzeit bereit."),
        ("Abholen ohne Warten", "An der Theke einfach den Namen nennen."),
    ],
    team=[
        ("Matthias Krume", "Bäckermeister", "baker,man"),
        ("Sofie Krume", "Konditorin", "pastry,chef"),
    ],
    trust={"since": "1962", "marks": ["Handwerksbäckerei", "Meisterbetrieb", "Regionales Mehl"]},
    usp=[
        ("clock", "Frisch ab 6 Uhr"),
        ("local", "Mehl aus der Region"),
        ("quality", "Meisterbetrieb seit 1962"),
        ("payment", "Vorbestellen & abholen"),
    ],
    testimonials=[
        (
            "Frau Albers",
            "Das Sauerteigbrot ist das beste der Stadt — und nie ausverkauft, "
            "wenn man vorbestellt.",
        ),
        ("Herr Yilmaz", "Feierabendtüte gerettet, Familie glücklich. Tolle Idee!"),
        (
            "Frau Novak",
            "Das Kuchenbuffet zur Taufe war ein Traum — pünktlich geliefert und "
            "wunderschön angerichtet.",
        ),
        # DL-11: четвёртый отзыв — 4 = два полных ряда по 2 (testimonials cols2)
        ("Frau Ott", "Samstags sind die Brötchen noch warm — wir kommen extra früh."),
    ],
    reviews_seed=[
        (5, "Das Sauerteigbrot ist das beste der Stadt!", "bk.albers@example.de"),
        (5, "Vorbestellen und ohne Schlange abholen — genau so muss das.", "bk.yilmaz@example.de"),
        (4, "Tolle Torten nach Wunsch, sehr freundliches Team.", "bk.peters@example.de"),
    ],
    faq=[
        (
            "Wann ist frisches Brot da?",
            "Die erste Ofenrunde ist um 6 Uhr fertig, die zweite gegen 10 Uhr. "
            "Vorbestellungen legen wir zur Wunschzeit zurück.",
        ),
        (
            "Wie funktioniert die Vorbestellung?",
            "Online bestellen, Abholzeit wählen, an der Theke den Namen nennen. "
            "Bezahlt wird bei Abholung oder online.",
        ),
        (
            "Was ist die Feierabendtüte?",
            "Gerettete Backwaren vom Tag zum halben Preis — der Inhalt ist eine "
            "Überraschung. Ab 17 Uhr, solange der Vorrat reicht.",
        ),
        (
            "Torten auf Bestellung?",
            "Ja — Wunschtorten mit mindestens 2 Tagen Vorlauf. Motiv, Größe und "
            "Füllung stimmen wir telefonisch oder per Nachricht ab.",
        ),
        (
            "Allergene?",
            "Alle Zutaten und die 14 LMIV-Allergene stehen bei jedem Produkt — "
            "fragen Sie bei Unsicherheit gern an der Theke nach.",
        ),
        (
            "Gibt es einen Partyservice?",
            "Ja — Kuchenbuffets, belegte Brötchen, Brezel- und Frühstückskörbe für "
            "10–80 Gäste. Anfrage stellen — Sie erhalten ein unverbindliches Angebot.",
        ),
    ],
    cta={
        "title": "Ihr Brot wartet schon",
        "text": "Jetzt vorbestellen und morgen früh ohne Warten abholen.",
        "button_label": "Sortiment ansehen",
        "button_url": "/sortiment/",
    },
    # jobs = Partyservice (Kuchenbuffets/belegte Brötchen), как у Metzgerei (2026-07-30).
    enable_modules=["orders", "jobs", "loyalty"],
    # Фидбэк 2026-07-30: «Our offerings» непрактичен — направления ловят плитки
    # hero_widget="bakery" (секция архетипов выключена).
    enable_archetypes_section=False,
    storefront_root="home",
    primary_module="catalog",  # hero-CTA → Sortiment (jobs — дополнение, не primary)
    # AF-1: Partyservice-Anfrage (Kuchenbuffets) — событийные поля заявки.
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": ["Geburtstag", "Hochzeit", "Firmenfrühstück", "Sonstiges"],
    },
    seed_records=True,
    menus=BAKERY_MENUS,
    loyalty={"label": "Brot-Stempelkarte", "stamps": 10, "reward": "1× Brot gratis"},
    vouchers=[
        {"code": "BROT10", "label": "−10 % für Neukunden", "percent": 10, "max_uses": 200},
    ],
    promotions_spec=[
        # Angebot der Woche: Prozent-Badge + wöchentliche Wiederholung + Galerie.
        {
            "title": "Bauernbrot −15 % (Angebot der Woche)",
            "product": 1,
            "percent": 15,
            "discount_style": "percent",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Wochenangebote",
            "images": ["bread,loaf", "bakery,oven", "sourdough"],
            "desc": "Jede Woche ein anderes Brot im Angebot.",
        },
        # «3 für 2» über Festpreis: alter Preis durchgestrichen (3×1,20 = 3,60 → 2,40),
        # Vorrat über limit begrenzt («Nur noch X»).
        {
            "title": "3 Laugenbrezeln zum Preis von 2",
            "product": 6,
            "new_price": "2.40",
            "compare_at": "3.60",
            "discount_style": "strikethrough",
            "limit": 40,
            "ends_in_days": 7,
            "group": "Wochenangebote",
            "desc": "Dreierpack vorbestellen, zwei bezahlen — solange der Vorrat reicht.",
        },
        # Tagesaktion: Countdown-Banner (endet heute) + «🆕 Neu»-Chip.
        {
            "title": "Butter-Croissant −30 % – nur heute",
            "product": 8,
            "percent": 30,
            "discount_style": "countdown",
            "countdown": True,
            "new": True,
            "ends_in_days": 1,
            "group": "Wochenangebote",
            "desc": "Frisch aus dem Ofen — nur heute zum Aktionspreis.",
        },
        # Abendverkauf, täglich wiederkehrend (Anti-Food-Waste).
        {
            "title": "Brötchen ab 17 Uhr −50 %",
            "product": 4,
            "percent": 50,
            "discount_style": "percent",
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Anti-Food-Waste",
            "desc": "Jeden Abend vor Ladenschluss — retten statt wegwerfen.",
        },
        # Überraschungstüte: Festpreis + Surprise-Stil (Badge aus, 🌱-Chip an) + Kontingent.
        {
            "title": "Feierabendtüte 4,50 € statt 9 €",
            "product": 13,
            "surprise": True,
            "discount_style": "surprise",
            "new_price": "4.50",
            "compare_at": "9.00",
            "limit": 12,
            "ends_in_days": 7,
            "group": "Anti-Food-Waste",
            "desc": "Gerettete Backwaren vom Tag — der Inhalt ist eine Überraschung.",
        },
        # Reservierung: 📦-Chip «online sichern, im Laden abholen», bei 0 → Warteliste.
        {
            "title": "Bienenstich −20 % (nur 8 Stück)",
            "product": 11,
            "type": "reservation",
            "percent": 20,
            "available_quantity": 8,
            "ends_in_days": 14,
            "group": "Wochenangebote",
            "desc": "Online sichern, nachmittags abholen.",
        },
    ],
    categories=[
        (
            "Brot",
            "brot",
            [
                _p(
                    "Roggenbrot 750 g",
                    "3.20",
                    "Kräftiger Natursauerteig, lange Teigführung.",
                    "rye,bread",
                    allergens=["gluten"],
                    unit="g",
                    content=750,
                ),
                _p(
                    "Bauernbrot 1 kg",
                    "3.80",
                    "Unser Klassiker aus dem Steinofen.",
                    "bread,loaf",
                    allergens=["gluten"],
                    unit="kg",
                    content=1,
                    badge="beliebt",
                ),
                _p(
                    "Dinkelvollkornbrot 500 g",
                    "4.20",
                    "100 % Dinkel, mit Saaten. Vegan.",
                    "spelt,bread",
                    allergens=["gluten", "sesam"],
                    diets=["vegan"],
                    unit="g",
                    content=500,
                ),
                _p(
                    "Sauerteig-Kruste 750 g",
                    "3.90",
                    "Extra knusprig, 24 h Teigruhe.",
                    "sourdough",
                    allergens=["gluten"],
                    unit="g",
                    content=750,
                    badge="empfehlung",
                ),
            ],
            "bread-loaf",  # DS-8: реальное фото плитки (было SVG-фолбэк)
        ),
        (
            "Brötchen & Kleingebäck",
            "broetchen",
            [
                _p(
                    "Brötchen",
                    "0.60",
                    "Knusprig aus dem Ofen.",
                    "bread,rolls",
                    allergens=["gluten"],
                ),
                _p(
                    "Vollkornbrötchen",
                    "0.75",
                    "Mit Roggen- und Weizenvollkorn.",
                    "wholegrain,roll",
                    allergens=["gluten"],
                    diets=["vegan"],
                ),
                _p(
                    "Laugenbrezel",
                    "1.20",
                    "Bayerische Art, mit grobem Salz.",
                    "pretzel",
                    allergens=["gluten"],
                ),
                _p(
                    "Käsebrötchen",
                    "1.50",
                    "Mit würzigem Bergkäse überbacken.",
                    "cheese,roll",
                    allergens=["gluten", "milch"],
                ),
            ],
            "bread-rolls",  # DS-8: реальное фото плитки (было SVG-фолбэк)
        ),
        (
            "Feingebäck & Kuchen",
            "feingebaeck",
            [
                _p(
                    "Butter-Croissant",
                    "1.80",
                    "Französische Art, 32 Butterschichten.",
                    "croissant",
                    allergens=["gluten", "milch"],
                ),
                _p(
                    "Nussschnecke",
                    "2.20",
                    "Mit Haselnussfüllung und Zuckerguss.",
                    "nut,pastry",
                    allergens=["gluten", "schalenfruechte", "milch"],
                ),
                _p(
                    "Apfeltasche",
                    "2.40",
                    "Mit Zimt und regionalen Äpfeln.",
                    "apple,pastry",
                    allergens=["gluten"],
                ),
                _p(
                    "Bienenstich",
                    "2.80",
                    "Hefeteig, Mandelkruste, Vanillecreme.",
                    "bee,sting,cake",
                    allergens=["gluten", "milch", "eier", "schalenfruechte"],
                ),
                _p(
                    "Käsekuchen (Stück)",
                    "3.20",
                    "Cremig nach Omas Rezept.",
                    "cheesecake",
                    allergens=["gluten", "milch", "eier"],
                ),
                _p(
                    "Feierabendtüte",
                    "9.00",
                    "Gerettete Backwaren vom Tag — Wert ca. 9 €.",
                    "bakery,bag",
                    allergens=["gluten"],
                ),
            ],
            "apple-pastry",  # DS-8: реальное фото плитки (было SVG-фолбэк)
        ),
        (
            "Torten auf Vorbestellung",
            "torten",
            [
                _p(
                    "Erdbeer-Sahnetorte",
                    "24.90",
                    "Für 12 Stücke. Bitte 2 Tage Vorlauf.",
                    "strawberry,cake",
                    allergens=["gluten", "milch", "eier"],
                ),
                _p(
                    "Schwarzwälder Kirschtorte",
                    "26.90",
                    "Mit Kirschwasser. Bitte 2 Tage Vorlauf.",
                    "black,forest,cake",
                    allergens=["gluten", "milch", "eier"],
                ),
                _p(
                    "Wunschtorte nach Motiv",
                    "34.90",
                    "Geburtstag, Taufe, Jubiläum — Motiv nach Absprache.",
                    "birthday,cake",
                    allergens=["gluten", "milch", "eier"],
                    badge="neu",
                ),
            ],
            "black-forest-cake",  # DS-8: реальное фото плитки (было SVG-фолбэк)
        ),
    ],
    job_samples=[
        {
            "title": "Partyservice: Kuchenbuffet zum 60. Geburtstag (30 Gäste)",
            "name": "Familie Winter",
            "email": "bk.party1@example.de",
            "phone": "02103 778899",
            "description": "Jubiläum am Sonntag: Kuchenbuffet aus 4 Torten und "
            "Blechkuchen für 30 Gäste, Lieferung und Aufbau bis 13 Uhr.",
            "lines": [
                {"text": "Torte nach Wahl (12 Stücke)", "qty": 4, "unit_price": "26.90"},
                {"text": "Blechkuchen gemischt (20 Stücke)", "qty": 2, "unit_price": "18.00"},
                {"text": "Lieferung & Aufbau", "qty": 1, "unit_price": "25.00"},
            ],
            "vat_rate": 7,
        },
        {
            "title": "Belegte Brötchen für Firmenfrühstück (35 Personen)",
            "name": "Steuerbüro Hansen",
            "email": "bk.party2@example.de",
            "description": "Monatsmeeting am Freitag: belegte Brötchen gemischt und "
            "Laugengebäck, Anlieferung 8:30 Uhr.",
            "lines": [
                {"text": "Belegtes Brötchen gemischt", "qty": 70, "unit_price": "2.20"},
                {"text": "Laugenbrezel", "qty": 35, "unit_price": "1.20"},
                {"text": "Anlieferung", "qty": 1, "unit_price": "20.00"},
            ],
            "vat_rate": 7,
        },
    ],
    product_reviews=[
        (1, 5, "Anna B.", "bk.rev1@example.de", "Das Bauernbrot hält sich tagelang frisch."),
        (3, 5, "Jens K.", "bk.rev2@example.de", "Die Kruste ist unschlagbar — wie früher."),
        (14, 5, "Familie Roth", "bk.rev3@example.de", "Die Erdbeertorte war der Star der Feier!"),
    ],
)


BUTCHER_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog"},
            {
                "label": "Aktionen",
                "type": "group",
                "children": [
                    {"label": "Wochenangebote", "type": "promo_group", "target": "Wochenangebote"},
                    {"label": "Vorbestellung", "type": "promo_group", "target": "Vorbestellung"},
                    {
                        "label": "Hausmacher-Wochen",
                        "type": "promo_group",
                        "target": "Hausmacher-Wochen",
                    },
                ],
            },
            {"label": "Partyservice", "type": "archetype", "target": "jobs"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🥩"},
            {"label": "Aktionen", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Party", "type": "archetype", "target": "jobs", "icon": "🎉"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
        ],
    },
}

# A1 Metzgerei (dedicated, 2026-07-10): Frischetheke mit Grundpreis €/kg (PAngV),
# Grillpaket-Vorbestellung (reservation, zum Wochenende), Partyservice über jobs
# (Anfrage → Angebot: Buffets/Platten), Hausmacher-Wurst, Herkunft, Stempelkarte.
BUTCHER = DemoKit(
    key="butcher",
    # SH-24 (Р-6): мясная лавка возит Partyservice-заказы.
    delivery={
        "enabled": True,
        "fee_cents": 490,
        "free_cents": 5000,
        "min_cents": 2000,
        "area": "Lieferung im Stadtgebiet.",
    },
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    # DL-11: 4 категории в стиле compact — 2×2 (compact с настроенной раскладкой берёт движок)
    section_layouts={"gallery": {"preset": "cols3"}, "categories": {"preset": "cols2"}},
    label="Metzgerei Bergmann",
    business_type="butcher",
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_theke",
    look="warm",  # DS-9: своя «кожа» семейства
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="metzgerei",
    enable_lots=True,  # E1.5: Chargen/MHD (Fleisch/Wurst mit kurzer Haltbarkeit)
    accent="#991b1b",  # dunkles Metzger-Rot
    hero_image_kw="butcher,meat",
    hero_title="Metzgerei Bergmann",
    hero_text="Fleisch und Wurst aus eigener Herstellung — von Höfen aus der Region. "
    "Grillpakete und Platten bequem online vorbestellen.",
    # 2026-07-30 («тот же набор, что Bäckerei»): главная «ловит направления» —
    # слайдер (3 слайда) + плитки hero_widget="butcher".
    hero_widget="butcher",
    heroes=[
        {
            "image_kw": "butcher,meat",
            "title": "Metzgerei Bergmann",
            "text": "Fleisch und Wurst aus eigener Herstellung — von Höfen aus der Region.",
            "button_label": "Sortiment ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "grill,bbq",
            "title": "Grillpakete fürs Wochenende",
            "text": "Jetzt vorbestellen — samstags frisch mariniert abholen.",
            "button_label": "Grillpakete ansehen",
            "button_url": "/sortiment/grill/",
        },
        {
            "image_kw": "deli",
            "title": "Partyservice für Ihre Feier",
            "text": "Buffets, Platten und Canapés für 10–100 Gäste.",
            "button_label": "Anfrage stellen",
            "button_url": "/anfrage/",
        },
    ],
    about_title="Unsere Metzgerei",
    about_text="Seit 1954 steht der Name Bergmann für ehrliches Handwerk: Wir kaufen "
    "ganze Tiere von Höfen aus dem Umland, zerlegen selbst und räuchern unsere Wurst "
    "in der eigenen Wurstküche. Für Feste liefern wir Buffets und kalte Platten — "
    "fragen Sie einfach über den Partyservice an.",
    nav_style="classic",
    address="Fleischergasse 12, 40721 Hilden",
    opening_hours_text="Mo–Fr 7:00–18:00 · Sa 7:00–13:00",
    opening_hours={**{d: ("07:00", "18:00") for d in range(5)}, 5: ("07:00", "13:00")},
    gallery_kw=["butcher,shop", "meat,counter", "sausage", "grill,bbq", "ham", "deli"],
    process=[
        ("Auswählen & vorbestellen", "Online bestellen oder Partyservice anfragen."),
        ("Wir bereiten frisch zu", "Zerlegt, mariniert und verpackt am Abholtag."),
        ("Abholen oder liefern lassen", "An der Theke abholen — Buffets liefern wir."),
    ],
    team=[
        ("Karl Bergmann", "Metzgermeister", "butcher,man"),
        ("Petra Lang", "Fleischerei-Fachverkäuferin", "shop,assistant"),
    ],
    trust={"since": "1954", "marks": ["Meisterbetrieb", "Eigene Wurstküche", "Regionale Höfe"]},
    usp=[
        ("local", "Fleisch von Höfen aus der Region"),
        ("quality", "Eigene Wurstküche"),
        ("clock", "Frischetheke ab 7 Uhr"),
        ("payment", "Vorbestellen & abholen"),
    ],
    testimonials=[
        ("Herr Brandt", "Das Grillpaket war perfekt vorbereitet — nur noch auf den Rost legen."),
        ("Frau Kaya", "Der Partyservice hat unsere Feier gerettet. Alles pünktlich und köstlich."),
    ],
    reviews_seed=[
        (
            5,
            "Beste Bratwurst weit und breit — eigene Herstellung schmeckt man.",
            "mz.brandt@example.de",
        ),
        (
            5,
            "Grillpaket online vorbestellt, samstags abgeholt — top organisiert.",
            "mz.kaya@example.de",
        ),
        (4, "Beratung an der Theke ist erstklassig.", "mz.otto@example.de"),
    ],
    faq=[
        (
            "Woher kommt das Fleisch?",
            "Von Familienhöfen aus dem Umland (max. 50 km). Herkunft steht bei "
            "jedem Produkt — fragen Sie gern nach dem Hof.",
        ),
        (
            "Wie bestelle ich ein Grillpaket vor?",
            "Online sichern, Abholtag wählen (z. B. Samstag). Wir zerlegen und "
            "marinieren frisch am Abholtag.",
        ),
        (
            "Was macht der Partyservice?",
            "Kalte Platten, Buffets, Canapés und Grillservice für 10–100 Gäste. "
            "Anfrage stellen — Sie erhalten ein unverbindliches Angebot.",
        ),
        (
            "Kann ich nach Gewicht bestellen?",
            "Ja — Preise an der Theke gelten pro kg (Grundpreis steht bei jedem "
            "Produkt). Online bestellen Sie in praktischen Portionen.",
        ),
    ],
    cta={
        "title": "Grillwochenende geplant?",
        "text": "Grillpaket jetzt vorbestellen — am Samstag ohne Warten abholen.",
        "button_label": "Zu den Grillpaketen",
        "button_url": "/sortiment/",
    },
    enable_modules=["orders", "jobs", "loyalty"],
    # 2026-07-30: направления ловят плитки hero_widget="butcher" (архетипы выкл).
    enable_archetypes_section=False,
    storefront_root="home",
    primary_module="catalog",  # hero-CTA → Sortiment (Partyservice — дополнение)
    # AF-1: Partyservice-Anfrage (Platten/Buffets/Grill) — событийные поля заявки.
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": ["Grillfest", "Firmenfeier", "Familienfeier", "Hochzeit", "Sonstiges"],
    },
    seed_records=True,
    menus=BUTCHER_MENUS,
    loyalty={"label": "Theken-Stempelkarte", "stamps": 10, "reward": "1× Bratwurst gratis"},
    vouchers=[
        {
            "code": "GRILL10",
            "label": "−10 % auf die erste Bestellung",
            "percent": 10,
            "max_uses": 200,
        },
    ],
    promotions_spec=[
        # ⚠️ ЗАМОК: единственная акция группы «Vorbestellung» и available_quantity == 20
        # (test_apply_butcher_kit_dedicated_metzgerei делает Promotion.objects.get(group=…)).
        # Ни группу, ни тип, ни количество не менять; вторую акцию в эту группу НЕ добавлять.
        {
            "title": "Grillpaket Familie — jetzt fürs Wochenende vorbestellen",
            "product": 10,
            "type": "reservation",
            "percent": 10,
            "available_quantity": 20,
            "images": ["bbq,family", "grill,bbq", "grill,plate"],
            "group": "Vorbestellung",
            "desc": "Online sichern, samstags frisch abholen — nur 20 Pakete pro Woche.",
        },
        # Angebot der Woche: Prozent-Badge + wöchentliche Wiederholung.
        {
            "title": "Schweineschnitzel −15 % (Angebot der Woche)",
            "product": 1,
            "percent": 15,
            "discount_style": "percent",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Wochenangebote",
            "desc": "Jede Woche ein anderer Thekenklassiker im Angebot.",
        },
        # Grillsaison: Countdown-Stil + Banner mit Tage|Std|Min|Sek, «🆕 Neu»-Chip.
        {
            "title": "Marinierte Nackensteaks −20 % – Grillsaison",
            "product": 11,
            "percent": 20,
            "discount_style": "countdown",
            "countdown": True,
            "new": True,
            "ends_in_days": 2,
            "group": "Wochenangebote",
            "desc": "Paprika oder Kräuter — frisch mariniert, nur dieses Wochenende.",
        },
        # Festpreis: nur der neue Preis im Fokus (alter Preis als Referenz).
        {
            "title": "Hausmacher Leberwurst zum Festpreis 2,49 €",
            "product": 4,
            "new_price": "2.49",
            "compare_at": "3.20",
            "discount_style": "festpreis",
            "ends_in_days": 14,
            "group": "Hausmacher-Wochen",
            "desc": "Aus der eigenen Wurstküche.",
        },
        # «3 für 2» über Bündelpreis (3×5,50 = 16,50 → 11,00), Vorrat über limit.
        {
            "title": "3 Pakete Bratwurst zum Preis von 2",
            "product": 6,
            "new_price": "11.00",
            "compare_at": "16.50",
            "discount_style": "strikethrough",
            "limit": 25,
            "ends_in_days": 10,
            "group": "Hausmacher-Wochen",
            "desc": "12 Bratwürste aus eigener Herstellung — ein Paket geht aufs Haus.",
        },
        # Abendverkauf: täglich wiederkehrend, Betrag-Badge (−2,97 €) + Countdown-Banner.
        {
            "title": "Feierabend-Theke: Rinderhack −30 % ab 17 Uhr",
            "product": 0,
            "percent": 30,
            "discount_style": "badge",
            "countdown": True,
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Wochenangebote",
            "desc": "Was am Abend in der Theke bleibt, geben wir günstiger ab.",
        },
    ],
    categories=[
        (
            "Frischfleisch",
            "frischfleisch",
            [
                _p(
                    "Rinderhackfleisch 1 kg",
                    "9.90",
                    "Täglich frisch gewolft.",
                    "minced,meat",
                    unit="kg",
                    content=1,
                ),
                _p(
                    "Schweineschnitzel 1 kg",
                    "12.90",
                    "Aus der Oberschale, küchenfertig.",
                    "pork,schnitzel",
                    unit="kg",
                    content=1,
                ),
                _p(
                    "Rinderfilet 1 kg",
                    "29.90",
                    "Dry-aged, 21 Tage gereift.",
                    "beef,filet",
                    unit="kg",
                    content=1,
                    badge="empfehlung",
                ),
                _p(
                    "Hähnchenbrust 1 kg",
                    "11.50",
                    "Vom Geflügelhof Weide.",
                    "chicken,breast",
                    unit="kg",
                    content=1,
                ),
            ],
        ),
        (
            "Wurst & Aufschnitt",
            "wurst",
            [
                _p(
                    "Hausmacher Leberwurst 200 g",
                    "3.20",
                    "Grob, aus der eigenen Wurstküche.",
                    "liver,sausage",
                    unit="g",
                    content=200,
                ),
                _p(
                    "Gekochter Schinken 100 g",
                    "2.49",
                    "Mild gepökelt, hauchdünn geschnitten.",
                    "ham,sliced",
                    unit="g",
                    content=100,
                ),
                _p(
                    "Bratwurst (4 Stück)",
                    "5.50",
                    "Fränkische Art, eigene Rezeptur.",
                    "bratwurst",
                    allergens=["senf"],
                    badge="beliebt",
                ),
                _p("Wiener Würstchen (Paar)", "4.50", "Zart geräuchert.", "wiener,sausage"),
                _p(
                    "Salami luftgetrocknet 150 g",
                    "4.90",
                    "3 Monate gereift.",
                    "salami",
                    unit="g",
                    content=150,
                ),
            ],
        ),
        (
            "Grill & Party",
            "grill",
            [
                _p(
                    "Grillplatte für 2",
                    "18.90",
                    "Steaks, Bratwurst, Nackenkotelett — fertig mariniert.",
                    "grill,plate",
                    allergens=["senf"],
                ),
                _p(
                    "Grillpaket Familie (für 6)",
                    "49.90",
                    "Bunte Auswahl für den Familiengrill — auf Vorbestellung.",
                    "bbq,family",
                    allergens=["senf"],
                    badge="beliebt",
                ),
                _p(
                    "Marinierte Nackensteaks (4 St.)",
                    "12.90",
                    "Paprika- oder Kräutermarinade.",
                    "steak,marinated",
                    allergens=["senf"],
                ),
                _p("Grillfackeln (3 St.)", "8.90", "Bauchspeck am Spieß.", "bacon,skewer"),
            ],
        ),
        (
            "Feinkost & Salate",
            "feinkost",
            [
                _p(
                    "Kartoffelsalat 500 g",
                    "4.50",
                    "Hausgemacht mit Mayonnaise.",
                    "potato,salad",
                    allergens=["eier", "senf"],
                    unit="g",
                    content=500,
                ),
                _p(
                    "Fleischsalat 250 g",
                    "3.90",
                    "Der Klassiker zur Brotzeit.",
                    "meat,salad",
                    allergens=["eier", "senf"],
                    unit="g",
                    content=250,
                ),
                _p(
                    "Sülze hausgemacht 300 g",
                    "4.90",
                    "Mit Remoulade nach Art des Hauses.",
                    "aspic",
                    allergens=["eier", "senf"],
                    unit="g",
                    content=300,
                ),
            ],
        ),
    ],
    job_samples=[
        {
            "title": "Partyservice: Geburtstagsbuffet für 25 Gäste",
            "name": "Familie Ott",
            "email": "mz.party1@example.de",
            "phone": "02103 445566",
            "description": "Runder Geburtstag am Samstag: Grillbuffet und kalte Platten "
            "für 25 Gäste, Lieferung und Aufbau bis 17 Uhr.",
            "lines": [
                {"text": "Grillbuffet pro Person", "qty": 25, "unit_price": "14.50"},
                {"text": "Kalte Platten (Aufschnitt & Käse)", "qty": 3, "unit_price": "24.00"},
                {"text": "Lieferung & Aufbau", "qty": 1, "unit_price": "35.00"},
            ],
            "vat_rate": 7,
        },
        {
            "title": "Canapés für Firmenempfang (40 Personen)",
            "name": "Bürotech GmbH",
            "email": "mz.party2@example.de",
            "description": "Empfang zur Geschäftseröffnung: gemischte Canapés und "
            "Fingerfood für ca. 40 Personen, Anlieferung 11 Uhr.",
            "lines": [
                {"text": "Canapés gemischt", "qty": 120, "unit_price": "1.80"},
                {"text": "Anlieferung", "qty": 1, "unit_price": "25.00"},
            ],
            "vat_rate": 7,
        },
    ],
    product_reviews=[
        (
            6,
            5,
            "Markus D.",
            "mz.rev1@example.de",
            "Die Bratwurst ist ein Traum — nie wieder Supermarkt.",
        ),
        (
            10,
            5,
            "Sandra E.",
            "mz.rev2@example.de",
            "Grillpaket für 6: großzügig, frisch, top mariniert.",
        ),
        (13, 4, "Ralf N.", "mz.rev3@example.de", "Kartoffelsalat wie bei Oma."),
    ],
)

CAFE_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Karte", "type": "archetype", "target": "catalog"},
            {"label": "Reservieren", "type": "archetype", "target": "booking"},
            {"label": "Treue", "type": "archetype", "target": "loyalty"},
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Karte", "type": "archetype", "target": "catalog", "icon": "☕"},
            {"label": "Tisch", "type": "archetype", "target": "booking", "icon": "📅"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
            {"label": "Treue", "type": "archetype", "target": "loyalty", "icon": "💝"},
        ],
    },
}

# A4 Café (dedicated, волна 2 демо-трека): компактная кофейня — кофе/завтраки/кухен
# (НЕ ужин-ресторан на 33 позиции), бронь столика, Kaffeepass (7-й кофе гратис),
# Mittagstisch/Happy-Hour-акции. LMIV-аллергены, диет-теги на веган-позициях.
CAFE = DemoKit(
    key="cafe",
    # SH-24 (Р-6): кофе и кухня — с доставкой.
    delivery={
        "enabled": True,
        "fee_cents": 250,
        "free_cents": 2000,
        "min_cents": 800,
        "area": "Wir liefern im Umkreis von 3 km.",
    },
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}},
    card_style="compact",  # ST-7c: строка-прайс (меню)
    variant_style="buttons",  # O-2: размеры/объёмы кнопками
    winback={"inactive_days": 60, "percent": 10},  # B4/LS-5
    # DS-5c: компактный прайс на главной (много позиций у кофейни), страница
    # меню — прайс с мини-фото (config_patch).
    # DS-8 (Fokus для кафе): сплит-баннер, компакт-карта на главной, фото-прайс
    # на странице меню, компакт-доверие.
    look="klar",
    section_styles={
        "cta": "cards",
        "usp_bar": "cards",
        "products": "preisliste_kompakt",
        "trust": "compact",
    },  # ST-7b
    config_patch={
        "catalog_layout": {"preset": "preisliste_foto"},
        "hero_style": "split",
        "nav": {"cta": True},
        # DS-8: плитки задач приходят из шаблона «gastro» — Fokus их снимает.
        "site_defaults": {"hero_widget": ""},
    },
    sections_off=["archetypes", "usp_bar", "team", "gallery", "reviews", "testimonials"],
    label="Café Morgenrot",
    business_type="cafe",
    subdomain="cafe",
    # 2026-07-30: слайдер над гастро-плитками (первый экран).
    heroes=[
        {
            "image_kw": "coffee,cafe",
            "title": "Café Morgenrot",
            "text": "Specialty Coffee und hausgemachte Kuchen — mitten im Viertel.",
            "button_label": "Tisch reservieren",
            "button_url": "/termin/",
        },
        {
            "image_kw": "breakfast,cafe",
            "title": "Frühstück bis 14 Uhr",
            "text": "Auch am Wochenende — mit Zeit für die zweite Tasse.",
            "button_label": "Speisekarte ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "cake,bakery",
            "title": "Kuchen zum Mitnehmen",
            "text": "Ganze Torten auf Vorbestellung — für Ihren Anlass.",
            "button_label": "Jetzt bestellen",
            "button_url": "/sortiment/",
        },
    ],
    accent="#78350f",  # Kaffee-Braun
    hero_image_kw="coffee,cafe",
    hero_title="Café Morgenrot",
    hero_text="Specialty Coffee, hausgemachte Kuchen und Frühstück bis 14 Uhr — "
    "mitten im Viertel. Tisch reservieren oder zum Mitnehmen bestellen.",
    about_title="Unser Café",
    about_text="Seit 2015 rösten wir unseren Espresso bei einer kleinen Rösterei im "
    "Umland und backen jeden Morgen selbst. Frühstück gibt es bis 14 Uhr, freitags "
    "wechselnden Mittagstisch. Mit dem Kaffeepass ist der siebte Kaffee gratis.",
    nav_style="classic",
    hero_widget="gastro",  # батч A: плитки Reservieren/Speisekarte/Angebot des Tages
    address="Sonnenallee 24, 40215 Düsseldorf",
    opening_hours_text="Mo–Sa 8:00–18:00 · So 9:00–17:00",
    opening_hours={**{d: ("08:00", "18:00") for d in range(6)}, 6: ("09:00", "17:00")},
    gallery_kw=["coffee", "cafe,interior", "cake", "breakfast", "barista", "latte,art"],
    process=[
        ("Tisch reservieren", "Online den Wunschtermin sichern — auch fürs Frühstück."),
        ("Genießen", "Kaffee, Kuchen und Frühstück — alles hausgemacht."),
        ("Stempel sammeln", "Kaffeepass: der siebte Kaffee geht aufs Haus."),
    ],
    team=[
        ("Mara Sonn", "Inhaberin & Barista", "barista,woman"),
        ("Tom Feld", "Konditor", "pastry,chef"),
    ],
    trust={
        "since": "2015",
        "marks": ["Specialty Coffee", "Hausgemachte Kuchen", "Regionale Rösterei"],
    },
    usp=[
        ("clock", "Frühstück bis 14 Uhr"),
        ("quality", "Eigene Röstung"),
        ("local", "Kuchen aus eigener Backstube"),
        ("payment", "Tisch online reservieren"),
    ],
    testimonials=[
        ("Lena P.", "Der beste Flat White der Stadt — und der Käsekuchen erst!"),
        ("Herr Groß", "Sonntagsfrühstück mit reserviertem Tisch — entspannter geht's nicht."),
    ],
    reviews_seed=[
        (5, "Der beste Flat White der Stadt!", "cf.lena@example.de"),
        (5, "Frühstück top, Personal herzlich, Tisch war reserviert.", "cf.gross@example.de"),
        (4, "Gemütlich und fair — der Kaffeepass lohnt sich.", "cf.mia@example.de"),
    ],
    faq=[
        (
            "Kann ich einen Tisch reservieren?",
            "Ja — online mit Wunschzeit, auch fürs Wochenendfrühstück. "
            "Ohne Reservierung vergeben wir Tische nach Verfügbarkeit.",
        ),
        (
            "Wie funktioniert der Kaffeepass?",
            "Bei jedem Kaffee einen Stempel sammeln — der siebte Kaffee ist gratis.",
        ),
        (
            "Gibt es vegane Optionen?",
            "Ja: Avocado-Toast, Porridge, veganer Schokokuchen und Hafermilch ohne Aufpreis.",
        ),
        (
            "Was ist der Mittagstisch?",
            "Freitags 12–14 Uhr ein wechselndes Gericht zum Sonderpreis — "
            "online reservierbar, solange der Vorrat reicht.",
        ),
    ],
    cta={
        "title": "Ihr Tisch wartet",
        "text": "Jetzt reservieren — fürs Frühstück, den Kuchen am Nachmittag oder beides.",
        "button_label": "Tisch reservieren",
        "button_url": "/termin/",
    },
    enable_modules=["orders", "booking", "loyalty"],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=CAFE_MENUS,
    loyalty={"label": "Kaffeepass", "stamps": 7, "reward": "1× Kaffee gratis"},
    resources=[
        {
            "name": "Tisch",
            "type": "table",
            "capacity": 18,
            "counts_party_size": True,
            "start": "09:00",
            "end": "17:00",
            "slot": 60,
            "weekdays": range(0, 7),
        }
    ],
    vouchers=[
        {
            "code": "MORGEN10",
            "label": "−10 % auf die erste Bestellung",
            "percent": 10,
            "max_uses": 200,
        },
    ],
    promotions_spec=[
        # (существующая) Mittagstisch — reservation + weekly: замок теста кита
        # test_apply_cafe_kit… требует именно эту комбинацию. НЕ трогаем.
        {
            "title": "Mittagstisch — freitags 12–14 Uhr",
            "product": 5,
            "type": "reservation",
            "percent": 20,
            "available_quantity": 15,
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Mittagstisch",
            "desc": "Wechselndes Gericht zum Sonderpreis — online reservieren.",
        },
        # (существующая) Happy Hour — recurrence="daily": питает плитку hero
        # «Angebot des Tages» и замок теста кита. НЕ трогаем.
        {
            "title": "Kuchen-Happy-Hour ab 16 Uhr −30 %",
            "product": 9,
            "percent": 30,
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Happy Hour",
            "desc": "Jeden Tag ab 16 Uhr auf Kuchen des Tages.",
        },
        # (существующая) + discount_style="countdown" — у акции уже был countdown=True,
        # стиль лишь делает отсчёт акцентом блока цены. Единственная правка старых.
        {
            "title": "Zimtschnecken-Tag −25 % – nur heute",
            "product": 11,
            "percent": 25,
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 1,
            "group": "Happy Hour",
        },
        # НОВОЕ: комбо-завтрак БЕЗ цели-товара («свободная» акция) — фикс-цена,
        # стиль festpreis (старая цена не зачёркивается, показывается только новая).
        {
            "title": "Frühstücks-Kombo: Teller & Kaffee für 9,90 €",
            "desc": "Frühstücksteller mit großem Cappuccino — jeden Morgen bis 14 Uhr.",
            "new_price": "9.90",
            "compare_at": "12.40",  # 8,50 € Teller + 3,90 € Cappuccino groß
            "discount_style": "festpreis",
            "new": True,
            "ends_in_days": 14,
            "group": "Frühstück & Kombi",
            "image": "breakfast",
        },
        # НОВОЕ: фикс-цена с зачёркнутой старой + дневной лимит чашек (scarcity).
        {
            "title": "Espresso-Stunde: Espresso für 1,50 €",
            "desc": "Montag bis Freitag von 15 bis 17 Uhr — Espresso aus eigener Röstung.",
            "product": 2,  # Espresso 2,20 €
            "new_price": "1.50",
            "compare_at": "2.20",
            "discount_style": "strikethrough",
            "recurrence": "daily",
            "ends_in_days": 1,
            "limit": 40,
            "group": "Happy Hour",
            "image": "espresso",
        },
        # НОВОЕ: сюрприз-набор (surprise) с галереей миниатюр и остатком пакетов.
        {
            "title": "Kuchen-Überraschungstüte 3,90 € statt 9,00 €",
            "desc": "Kurz vor Ladenschluss: bunte Auswahl vom Kuchenblech.",
            "surprise": True,
            "new_price": "3.90",
            "compare_at": "9.00",
            "discount_style": "surprise",
            "limit": 6,
            "ends_in_days": 3,
            "group": "Feierabend-Retter",
            "images": ["cake", "cheesecake", "cinnamon,roll"],
        },
    ],
    categories=[
        (
            "Kaffee & Getränke",
            "kaffee",
            [
                _p(
                    "Cappuccino",
                    "3.20",
                    "Doppelter Espresso, samtiger Milchschaum.",
                    "cappuccino",
                    variants=[("Klein", "3.20"), ("Groß", "3.90")],
                    allergens=["milch"],
                    badge="beliebt",
                ),
                _p(
                    "Latte Macchiato",
                    "3.50",
                    "Mit Hafermilch ohne Aufpreis.",
                    "latte",
                    allergens=["milch"],
                ),
                _p("Espresso", "2.20", "Eigene Röstung, kräftig.", "espresso"),
                _p(
                    "Heiße Schokolade",
                    "3.40",
                    "Mit echter Belgischer Schokolade.",
                    "hot,chocolate",
                    allergens=["milch"],
                ),
                _p(
                    "Hausgemachte Limonade",
                    "3.90",
                    "Zitrone-Minze oder Rhabarber.",
                    "lemonade",
                    diets=["vegan"],
                ),
            ],
        ),
        (
            "Frühstück & Brunch",
            "fruehstueck",
            [
                _p(
                    "Frühstücksteller",
                    "8.50",
                    "Brot, Käse, Schinken, Ei, Marmelade — bis 14 Uhr.",
                    "breakfast",
                    allergens=["gluten", "milch", "eier"],
                    badge="beliebt",
                    # O-3: допы ПЛИТКАМИ С ФОТО (носитель вида "tiles" в демо —
                    # фидбэк владельца 2026-08-03 «негде попробовать»).
                    modifiers=[
                        _mg(
                            "Extras",
                            [
                                ("Avocado", "2.00", "avocado"),
                                ("Lachs", "3.50", "salmon,fish"),
                                ("Extra Ei", "1.00", "eggs"),
                                ("Obstsalat", "2.50", "fruit,salad"),
                            ],
                            min=0,
                            max=4,
                            style="tiles",
                        ),
                    ],
                    vat="7.00",
                ),
                _p(
                    "Avocado-Toast",
                    "7.90",
                    "Sauerteig, Avocado, Kirschtomaten. Vegan.",
                    "avocado,toast",
                    allergens=["gluten"],
                    diets=["vegan"],
                    vat="7.00",
                ),
                _p(
                    "Porridge mit Beeren",
                    "5.90",
                    "Haferflocken, Beeren, Ahornsirup. Vegan.",
                    "porridge",
                    allergens=["gluten"],
                    diets=["vegan"],
                    vat="7.00",
                ),
                _p(
                    "Rührei auf Sauerteig",
                    "6.90",
                    "Drei Bio-Eier, Schnittlauch.",
                    "scrambled,eggs",
                    allergens=["gluten", "eier"],
                    vat="7.00",
                ),
            ],
        ),
        (
            "Kuchen & Süßes",
            "kuchen",
            [
                _p(
                    "Käsekuchen (Stück)",
                    "3.80",
                    "Nach Omas Rezept, jeden Tag frisch.",
                    "cheesecake",
                    allergens=["gluten", "milch", "eier"],
                    badge="empfehlung",
                    vat="7.00",
                ),
                _p(
                    "Apfelstrudel",
                    "3.90",
                    "Mit Vanillesoße, lauwarm.",
                    "apple,strudel",
                    allergens=["gluten", "milch"],
                    vat="7.00",
                ),
                _p(
                    "Zimtschnecke",
                    "2.90",
                    "Skandinavisch, mit Kardamom.",
                    "cinnamon,roll",
                    allergens=["gluten", "milch"],
                    vat="7.00",
                ),
                _p(
                    "Veganer Schokokuchen",
                    "3.60",
                    "Saftig, mit Zartbitter. Vegan.",
                    "chocolate,cake",
                    allergens=["gluten"],
                    diets=["vegan"],
                    vat="7.00",
                ),
            ],
        ),
    ],
    product_reviews=[
        (0, 5, "Lena P.", "cf.rev1@example.de", "Cappuccino wie in Mailand."),
        (9, 5, "Jonas T.", "cf.rev2@example.de", "Käsekuchen ist ein Gedicht."),
        (6, 4, "Aylin K.", "cf.rev3@example.de", "Avocado-Toast frisch und großzügig."),
    ],
)


CLOTHING_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Damen", "type": "category", "target": "damen"},
            {"label": "Herren", "type": "category", "target": "herren"},
            {"label": "Accessoires", "type": "category", "target": "accessoires"},
            {"label": "Sale", "type": "promo_group", "target": "Sale"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Shop", "type": "archetype", "target": "catalog", "icon": "👗"},
            {"label": "Sale", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🧺"},
        ],
    },
}

# A1/A2 Mode-Boutique (dedicated, волна 2): одежда с РАЗМЕРНЫМИ вариантами S–XL и
# per-size остатком (ausverkauft → Warteliste), Versand deutschlandweit (без PLZ-зон),
# Sale-акции. Multi-axis (цвет×размер) — гэп D3 в roadmap; демо честно на размерах.
CLOTHING = DemoKit(
    card_slider="on",  # DL-16.4 (P2): 3–4 фото на товар — листаются на карточке
    key="clothing",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}},
    look="nacht",  # ST-1: тёмный Look (мода)
    # DL-19 (N2): «Lookbook» — высокий кадр 3:4 и тихая подпись. До волны ближайшей
    # формой был overlay (текст поверх фото); теперь у моды есть своя.
    card_style="lookbook",
    variant_style="axes",  # O-2: цвет кружками + размеры кнопками
    label="Studio Nordwind",
    business_type="clothing",
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_lookbook",
    # DL-18.3: акции магазина одежды — группами-лентами (Sale · Accessoire-Deals),
    # как в продуктовом демо; страница /aktionen/ становится Sale-витриной.
    config_patch={
        "hero_style": "split",
        "nav": {"cta": True},
        "promo_layout": "slider",
        # DL-20: страница категории — «Navigator» на весь сайт (большой каталог с
        # фасетами размера/цвета); Herren и Accessoires ниже переопределяют его.
        "site_defaults": {"category_page_style": "navigator"},
        # DL-21.1: КОРНЕВАЯ /sortiment/ — «Tabs»: «Alle» + Damen/Herren/Accessoires
        # (свой ключ; дефолт категорий «Navigator» на корень не наследуется).
        "catalog_page_style": "tabs",
    },
    subdomain="mode",
    accent="#1e293b",  # Fashion-Navy
    hero_image_kw="fashion,boutique",
    hero_title="Studio Nordwind",
    hero_text="Faire Mode aus kleinen europäischen Manufakturen — kuratiert in "
    "Hamburg, versandkostenfrei ab 80 €.",
    # M0 (план mode-boutique-plan-2026-07-30): главная «ловит направления» —
    # слайдер (3 слайда) + плитки hero_widget="mode" (Sale/Sortiment/Neuheiten/Gutschein).
    hero_widget="mode",
    heroes=[
        {
            "image_kw": "fashion,boutique",
            "title": "Studio Nordwind",
            "text": "Faire Mode aus kleinen europäischen Manufakturen.",
            "button_label": "Sortiment ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "clothing,rack",
            "title": "Neu eingetroffen",
            "text": "Die neue Kollektion ist da — natürliche Materialien, klare Schnitte.",
            "button_label": "Neuheiten ansehen",
            "button_url": "/sortiment/?sort=newest",
        },
        {
            "image_kw": "dress",
            "title": "Sale bis −30 %",
            "text": "Ausgewählte Teile der Saison reduziert.",
            "button_label": "Zum Sale",
            "button_url": "/aktionen/",
        },
    ],
    about_title="Über Studio Nordwind",
    # M2 (2026-07-30): Warteliste per-size реализована — текст снова честен.
    about_text="Wir wählen jedes Teil selbst aus: faire Produktion, natürliche "
    "Materialien, Schnitte, die bleiben. Bestellt bis 15 Uhr, versenden wir noch am "
    "selben Tag mit DHL. Ist Ihre Größe ausverkauft, trägt die Warteliste Sie ein — "
    "Sie bekommen eine Mail, sobald sie zurück ist.",
    nav_style="classic",
    address="Speicherstraße 7, 20457 Hamburg",
    opening_hours_text="Showroom: Do–Sa 11:00–18:00 · Online-Shop rund um die Uhr",
    opening_hours={d: ("11:00", "18:00") for d in (3, 4, 5)},
    gallery_kw=["fashion", "clothing,rack", "dress", "knitwear", "denim", "accessories"],
    process=[
        ("Aussuchen", "Größe wählen — Größentabelle bei jedem Artikel."),
        ("Bestellen", "Versand in 24 h, kostenlos ab 80 €."),
        ("Anprobieren", "14 Tage Zeit — Rückgabe unkompliziert."),
    ],
    team=[
        ("Frida Nord", "Inhaberin & Einkauf", "fashion,designer"),
        ("Paul Wind", "Versand & Service", "shop,assistant"),
    ],
    trust={"since": "2018", "marks": ["Faire Marken", "Bio-Baumwolle", "Klimaneutraler Versand"]},
    usp=[
        ("payment", "Kostenloser Versand ab 80 €"),
        ("clock", "Versand in 24 h"),
        ("quality", "Faire Produktion"),
        ("local", "Kuratiert in Hamburg"),
    ],
    testimonials=[
        ("Meike S.", "Qualität, die man sofort spürt — und ehrliche Größenangaben."),
        ("Jan H.", "Größe war ausverkauft, Warteliste hat funktioniert: 5 Tage später bestellt."),
    ],
    reviews_seed=[
        (5, "Qualität, die man sofort spürt.", "nw.meike@example.de"),
        (5, "Warteliste für meine Größe hat perfekt funktioniert.", "nw.jan@example.de"),
        (4, "Schneller Versand, schöne Verpackung.", "nw.ines@example.de"),
    ],
    faq=[
        (
            "Wie fallen die Größen aus?",
            "Normal bis leicht großzügig — die Größentabelle mit Maßen in cm finden "
            "Sie bei jedem Artikel.",
        ),
        (
            "Versand & Rückgabe?",
            "DHL, 2–4 Werktage, 4,90 € — kostenlos ab 80 €. 14 Tage Widerruf, "
            "Rückgabe unkompliziert.",
        ),
        (
            "Meine Größe ist ausverkauft — was tun?",
            "Auf der Produktseite in die Warteliste eintragen: Sie erhalten "
            "automatisch eine E-Mail, sobald die Größe wieder da ist.",
        ),
        (
            "Woher kommt die Ware?",
            "Kleine Manufakturen in Portugal, Litauen und Dänemark — faire "
            "Produktion, natürliche Materialien.",
        ),
    ],
    cta={
        "title": "Neu eingetroffen",
        "text": "Die Herbstteile sind da — solange die Größen reichen.",
        "button_label": "Jetzt stöbern",
        "button_url": "/sortiment/",
    },
    enable_modules=["orders", "loyalty"],
    # M0: направления ловят плитки hero_widget="mode" (архетип-секция выкл).
    enable_archetypes_section=False,
    storefront_root="home",
    seed_records=True,
    menus=CLOTHING_MENUS,
    enable_anprobe=True,  # M3: Click&Reserve — киллер-механика бутика
    # M4-B Lookbook: подборки товаров с фото → страницы /lookbook/<slug>/
    # (индексы — позиции товаров в порядке создания сидером).
    collections=[
        (
            "Herbst-Looks",
            # DL-18.3: coat/boots/blazer-кадров в библиотеке нет — «boots,autumn»
            # уезжал по префикс-группе в autumn-hair.webp (причёска в лукбуке одежды).
            {"products": [0, 1, 2], "photos": ["knitwear", "clothing,rack", "fashion,boutique"]},
        ),
        (
            "Business",
            {"products": [3, 4], "photos": ["fashion,designer", "chinos"]},
        ),
        ("Basics", {"products": [5, 6, 7]}),  # без фото → обычный фасет-чип
    ],
    size_tables={
        "damen": "Größe | Brust (cm) | Taille (cm)\nS | 86–90 | 68–72\nM | 91–95 | 73–77\nL | 96–101 | 78–83\nXL | 102–108 | 84–90",
        "herren": "Größe | Brust (cm) | Bund (cm)\n48 | 94–97 | 82–85\n50 | 98–101 | 86–89\n52 | 102–105 | 90–94",
    },
    delivery={
        "enabled": True,
        "fee_cents": 490,
        "free_cents": 8000,  # frei ab 80 €
        "min_cents": 0,
        "pickup_min_cents": 0,
        "area": "Versand deutschlandweit mit DHL — 2–4 Werktage. Kostenlos ab 80 €.",
        "zones": [],
    },
    loyalty={"label": "Style-Karte", "stamps": 10, "reward": "10 € Gutschein"},
    vouchers=[
        {"code": "NORDWIND10", "label": "−10 % für Neukunden", "percent": 10, "max_uses": 200},
    ],
    promotions_spec=[
        # DL-18.3 (фидбэк «тематическое демо одежды со скидками»): Sale-витрина —
        # шесть действующих акций в двух группах (лентами) + предпросмотр зимней
        # распродажи (A1 «Vorschau»: `starts_in_days` → статус scheduled).
        {
            "title": "Winter-Sale: −40 % ab Montag",
            "desc": "Vorschau: Strick, Mäntel und Schals stark reduziert.",
            "product": 7,
            "percent": 40,
            "group": "Sale",
            "starts_in_days": 5,
            "ends_in_days": 14,
        },
        {
            "title": "Leinenbluse Küste −25 %",
            "desc": "Luftiges Leinen zum Saisonende.",
            "product": 2,
            "percent": 25,
            "group": "Sale",
            "discount_style": "percent",
            "ends_in_days": 12,
        },
        {
            "title": "Chino-Hose Deich statt 59,90 € nur 44,90 €",
            "desc": "Zwei Farben, solange der Vorrat reicht.",
            "product": 8,
            "new_price": 44.90,
            "compare_at": 59.90,
            "discount_style": "strikethrough",
            "group": "Sale",
            "ends_in_days": 9,
        },
        {
            "title": "Canvas-Tasche −20 %",
            "desc": "Der Alltagsbegleiter aus schwerem Baumwoll-Canvas.",
            "product": 12,
            "percent": 20,
            "group": "Accessoire-Deals",
            "ends_in_days": 10,
        },
        # Sale-Ядро: %-скидка на hero-товар. Заголовок/desc СОХРАНЕНЫ дословно —
        # у них уже есть переводы в demo_i18n_{en,ru,tr,uk}.json.
        {
            "title": "Schlussverkauf: Sommerkleider −30 %",
            "product": 0,  # Sommerkleid Nordlicht 45,00 € (было 0 — верно)
            "percent": 30,
            "discount_style": "percent",
            "group": "Sale",
            "ends_in_days": 14,
            "image": "summer,dress",
            "desc": "Nur solange die Größen reichen.",
        },
        # ФИКС индекса: 1 → 2 (после вставки «Seidentuch Aurora» акция висела на платке).
        # Направление «sale со strikethrough+compare_at»: 39,90 → 31,90 = ровно −20 %,
        # поэтому прежний заголовок остаётся честным (и сохраняет свои 4 перевода).
        {
            "title": "Style der Woche: Leinenbluse −20 %",
            "product": 2,  # Leinenbluse Küste 39,90 €
            "new_price": "31.90",
            "compare_at": "39.90",
            "discount_style": "strikethrough",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Sale",
            "image": "linen,blouse",
            "desc": "Jede Woche ein Lieblingsteil reduziert — diese Woche die Leinenbluse Küste.",
        },
        # ФИКС индекса: 4 → 5 (акция «Festpreis 14,90 €» стояла на джинсах за 59,90 €).
        # + limit: лимит кампании на обычной скидке («Nur noch N», стоп после 50 продаж).
        {
            "title": "Basic T-Shirt zum Festpreis 14,90 €",
            "product": 5,  # Basic T-Shirt Bio-Baumwolle 19,90 €
            "new_price": "14.90",
            "compare_at": "19.90",
            "discount_style": "festpreis",
            "limit": 50,
            "ends_in_days": 21,
            "group": "Sale",
            "image": "tshirt",
            "desc": "Weiß und Schwarz, Größen S–XL — solange der Aktionsvorrat reicht.",
        },
        # НОВОЕ: резервирование + Anprobe im Showroom (кит уже с enable_anprobe=True).
        # У кардигана размер M ausverkauft (stock 0) → история «letzte Größen» честна.
        {
            "title": "Letzte Größen: Strickcardigan Wolke −40 %",
            "product": 3,  # Strickcardigan Wolke 54,90 € → 32,94 €
            "type": "reservation",
            "percent": 40,
            "available_quantity": 4,
            "ends_in_days": 10,
            "group": "Sale",
            "images": ["cardigan", "knitwear", "clothing,rack"],
            "desc": "Nur noch S und L — online sichern und im Showroom anprobieren.",
        },
        # НОВОЕ: «ab»-цена. Носитель выбран осознанно — у платка варианты стоят
        # по-разному (Dessin Uni 22,90 €, übrige 24,90 €), поэтому «ab» читается честно.
        {
            "title": "Seidentuch Aurora — Aktionspreis ab 19,90 €",
            "product": 1,  # Seidentuch Aurora 24,90 €
            "new_price": "19.90",
            "discount_style": "ab",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Accessoire-Deals",
            "image": "accessories",
            "desc": "Drei Dessins — Blüte, Streifen und Uni — im Aktionspreis ab 19,90 €.",
        },
        # НОВОЕ: mystery — цена скрыта до клика (UE2-3) + таймер. Заголовок намеренно
        # нейтральный (как Mystery-Deal у aktionsmarkt), товар-носитель не называется.
        {
            "title": "Mystery-Accessoire der Woche",
            "new": True,
            "product": 12,  # Canvas-Tasche 16,90 € (Lager 25)
            "new_price": "9.90",
            "compare_at": "16.90",
            "discount_style": "mystery",
            "countdown": True,
            "ends_in_days": 3,
            "group": "Accessoire-Deals",
            "image": "fashion",
            "desc": "Ein Überraschungs-Accessoire aus dem Sale — der Preis erscheint erst beim Klick.",
        },
    ],
    categories=[
        (
            "Damen",
            "damen",
            [
                _p(
                    "Sommerkleid Nordlicht",
                    "45.00",
                    "Leichte Viskose, Midi-Länge. Fällt normal aus.",
                    ["summer,dress", "dress", "fashion"],
                    # M4-A: размер × цвет + фото варианта (label собирается сам).
                    variants=[
                        {
                            "size": "S",
                            "color": "Blau",
                            "price": "45.00",
                            "stock": 3,
                            "images": ["dress"],
                        },
                        {
                            "size": "M",
                            "color": "Blau",
                            "price": "45.00",
                            "stock": 4,
                            "images": ["dress"],
                        },
                        {
                            "size": "L",
                            "color": "Blau",
                            "price": "45.00",
                            "stock": 2,
                            "images": ["dress"],
                        },
                        {
                            "size": "S",
                            "color": "Sand",
                            "price": "45.00",
                            "stock": 3,
                            "images": ["fashion"],
                        },
                        {
                            "size": "M",
                            "color": "Sand",
                            "price": "45.00",
                            "stock": 4,
                            "images": ["fashion"],
                        },
                        {
                            "size": "L",
                            "color": "Sand",
                            "price": "45.00",
                            "stock": 2,
                            "images": ["fashion"],
                        },
                    ],
                    badge="beliebt",
                    material="100 % Viskose (LENZING™ ECOVERO™)",
                    care="30 °C Schonwäsche, nicht trocknergeeignet",
                ),
                _p(
                    "Seidentuch Aurora",
                    "24.90",
                    "Seidiges Tuch, drei Dessins — Auswahl als Foto-Kacheln.",
                    # DL-18.3: ключей scarf-* в библиотеке нет — товар уезжал в
                    # SVG-заглушку; берём кадры, которые реально существуют.
                    ["accessories", "fashion,designer"],
                    # O-2: НОСИТЕЛЬ вида "photo" — варианты фото-плитками
                    # (фидбэк владельца 2026-08-03 «негде попробовать»).
                    variant_style="photo",
                    variants=[
                        {
                            "label": "Dessin Blüte",
                            "price": "24.90",
                            "stock": 6,
                            "images": ["accessories"],
                        },
                        {
                            "label": "Dessin Streifen",
                            "price": "24.90",
                            "stock": 4,
                            "images": ["fashion,designer"],
                        },
                        {
                            "label": "Dessin Uni",
                            "price": "22.90",
                            "stock": 8,
                            "images": ["scarf"],
                        },
                    ],
                    material="100 % Seide",
                    care="Handwäsche kalt",
                ),
                _p(
                    "Leinenbluse Küste",
                    "39.90",
                    "100 % Leinen, luftig geschnitten.",
                    # DL-18.3: linen-shirt.webp — брак набора (на кадре выпечка).
                    ["linen,blouse", "tshirt"],
                    variants=[
                        {"label": "S", "price": "39.90", "stock": 5},
                        {"label": "M", "price": "39.90", "stock": 7},
                        {"label": "L", "price": "39.90", "stock": 3},
                    ],
                    material="100 % Leinen",
                    care="30 °C Schonwäsche, bügelfeucht bügeln",
                ),
                _p(
                    "Strickcardigan Wolke",
                    "54.90",
                    "Weicher Feinstrick aus Bio-Baumwolle.",
                    ["cardigan", "knitwear", "fashion"],
                    variants=[
                        {"label": "S", "price": "54.90", "stock": 4},
                        {"label": "M", "price": "54.90", "stock": 0},  # ausverkauft → Warteliste
                        {"label": "L", "price": "54.90", "stock": 2},
                    ],
                    material="70 % Wolle, 30 % Polyamid",
                    care="Handwäsche kalt, liegend trocknen",
                ),
                _p(
                    "Jeans High-Waist",
                    "59.90",
                    "Stretch-Denim, gerades Bein.",
                    "jeans",
                    variants=[
                        {"label": "36", "price": "59.90", "stock": 5},
                        {"label": "38", "price": "59.90", "stock": 6},
                        {"label": "40", "price": "59.90", "stock": 4},
                        {"label": "42", "price": "59.90", "stock": 3},
                    ],
                    material="99 % Baumwolle, 1 % Elasthan",
                    care="30 °C, auf links waschen, nicht trocknergeeignet",
                ),
            ],
            "summer-dress",  # DS-9: фото плитки (было SVG)
        ),
        (
            "Herren",
            "herren",
            [
                _p(
                    "Basic T-Shirt Bio-Baumwolle",
                    "19.90",
                    "Schwerer Jersey, sitzt gerade.",
                    "tshirt",
                    # M4-A: размер × цвет (без фото — фолбэк на фото товара).
                    variants=[
                        {"size": size, "color": color, "price": "19.90", "stock": stock}
                        for size, stock in (("S", 5), ("M", 6), ("L", 4), ("XL", 3))
                        for color in ("Weiß", "Schwarz")
                    ],
                    badge="beliebt",
                    gtin="4260000011001",
                    material="100 % Bio-Baumwolle (GOTS)",
                    care="40 °C Buntwäsche, trocknergeeignet",
                ),
                _p(
                    "Leinenhemd Hafen",
                    "39.90",
                    "Locker geschnitten, knitterfreundlich.",
                    ["fashion", "clothing,rack"],  # DL-18.3: было linen,shirt (выпечка)
                    variants=[
                        {"label": "M", "price": "39.90", "stock": 5},
                        {"label": "L", "price": "39.90", "stock": 6},
                        {"label": "XL", "price": "39.90", "stock": 3},
                    ],
                    material="100 % Leinen",
                    care="30 °C Schonwäsche, bügelfeucht bügeln",
                ),
                _p(
                    "Strickpullover Merino",
                    "69.90",
                    "100 % Merinowolle, mulesingfrei.",
                    "sweater",
                    variants=[
                        {"label": "M", "price": "69.90", "stock": 4},
                        {"label": "L", "price": "69.90", "stock": 3},
                    ],
                    badge="empfehlung",
                    material="100 % Merinowolle (mulesingfrei)",
                    care="Handwäsche kalt oder Wollprogramm",
                ),
                _p(
                    "Chino-Hose Deich",
                    "49.90",
                    "Bio-Baumwolle, leicht verjüngt.",
                    "chinos",
                    variants=[
                        {"label": "48", "price": "49.90", "stock": 4},
                        {"label": "50", "price": "49.90", "stock": 5},
                        {"label": "52", "price": "49.90", "stock": 3},
                    ],
                    material="98 % Bio-Baumwolle, 2 % Elasthan",
                    care="30 °C, auf links waschen",
                ),
            ],
            "sweater",  # DS-9: фото плитки (linen-shirt.webp — брак набора: выпечка)
            # DL-20 (P3): мало позиций с описанием — обложка + крупные карточки.
            "Hemden, Strick und Hosen — Basics, die bleiben.",
            "magazin",
        ),
        (
            "Accessoires",
            "accessoires",
            [
                _p(
                    "Wollschal",
                    "24.90",
                    "Lammwolle, extra lang.",
                    "wool,scarf",
                    stock=15,
                    material="100 % Lammwolle",
                    care="Handwäsche kalt",
                ),
                _p(
                    "Ledergürtel",
                    "29.90",
                    "Pflanzlich gegerbt, made in Portugal.",
                    "leather,belt",
                    variants=[
                        {"label": "85", "price": "29.90", "stock": 5},
                        {"label": "95", "price": "29.90", "stock": 6},
                        {"label": "105", "price": "29.90", "stock": 4},
                    ],
                ),
                _p(
                    "Strickmütze",
                    "14.90",
                    "Merino, doppelt gestrickt.",
                    "beanie",
                    stock=20,
                    material="100 % Merinowolle",
                    care="Handwäsche kalt",
                ),
                _p(
                    "Canvas-Tasche",
                    "16.90",
                    "Schwerer Canvas, Innentasche.",
                    "canvas,bag",
                    stock=25,
                    badge="neu",
                ),
            ],
            "canvas-bag",  # DS-9: фото плитки (было SVG)
            # DL-20 (P4): сильные фото — плитки разного размера поверх «Navigator».
            "Taschen, Gürtel, Schals — kleine Stücke, große Wirkung.",
            "mosaik",
        ),
    ],
    product_reviews=[
        (0, 5, "Meike S.", "nw.rev1@example.de", "Das Kleid sitzt perfekt — Größentabelle stimmt."),
        # DL-18.3: индексы съехали (5 = Basic T-Shirt, 7 = Strickpullover Merino) —
        # отзывы сидели на джинсах и льняной рубашке.
        (5, 5, "Jan H.", "nw.rev2@example.de", "Bestes Basic-Shirt, das ich je hatte."),
        (7, 5, "Ines W.", "nw.rev3@example.de", "Merino-Pulli kratzt null. Liebe."),
    ],
)


TOURS_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Touren", "type": "archetype", "target": "booking"},
            {"label": "Events & Ausflüge", "type": "archetype", "target": "events"},
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Touren", "type": "archetype", "target": "booking", "icon": "🧭"},
            {"label": "Tickets", "type": "archetype", "target": "events", "icon": "🎟️"},
            {"label": "Kontakt", "type": "page", "target": "contact", "icon": "📞"},
        ],
    },
}

# A6 Tour-Operator (dedicated, волна 3 демо-трека): экскурсии/туры — регулярные по
# времени (booking-слоты с party-size, Treffpunkt) + датированные события с тирами/
# депозитом/QR-билетами (events). Гиды = Teacher-сущности. Без каталога (тур — не
# товар); таймслот-модель «product → слоты дня» — гэп T6 в roadmap, демо честно на
# текущем движке (слот = booking-услуга, дата = событие).
TOURS = DemoKit(
    promotions_spec=[
        {
            # Ценовой слой на УСЛУГУ + «счастливые часы» (Mo–Do 10–14).
            "title": "Werktags-Special: Stadtführung für 14 €",
            "desc": "Montag bis Donnerstag zwischen 10 und 14 Uhr führen wir für 14 € "
            "statt 19 € durch die Altstadt — freie Zeit wählen, der Aktionspreis "
            "gilt automatisch.",
            "service": 0,
            "new_price": "14",
            "compare_at": "19",
            "discount_style": "festpreis",
            "rules": {"weekdays": [0, 1, 2, 3], "hour_from": 10, "hour_to": 14},
            "limit": 30,
            "group": "Stadtführungen",
            "ends_in_days": 45,
            "images": ["old,town", "city,tour"],
        },
        {
            "title": "Last-Minute: Fahrradtour am Fluss −20 %",
            "desc": "Kurzentschlossen aufs Rad: Halbtagestour für 28 € statt 35 €, "
            "Rad und Guide inklusive — solange Plätze in der Gruppe frei sind.",
            "service": 1,
            "percent": 20,
            "compare_at": "35",
            "discount_style": "countdown",
            "countdown": True,
            "new": True,
            "limit": 8,
            "group": "Radtouren",
            "ends_in_days": 5,
            "images": ["bike,tour", "bicycle,city"],
        },
        {
            "title": "Private Gruppenführung: 129 € statt 149 €",
            "desc": "Firmenevent oder Familienfeier: Wunschtermin, Wunschthema, bis "
            "15 Personen — aktuell 20 € günstiger.",
            "service": 2,
            "new_price": "129",
            "compare_at": "149",
            "discount_style": "badge",
            "limit": 5,
            "group": "Gruppen & Firmen",
            "ends_in_days": 60,
            "images": ["group,guide", "tour,guide,woman"],
        },
        {
            # События не могут быть целью акции — «свободная» акция-витрина ведёт
            # в штатный заказ (P5).
            "title": "Frühbucher: Tagesausflug Moseltal & Burg Eltz",
            "desc": "Wer früh bucht, zahlt 79 € statt 89 € — Bus, Burgführung, "
            "Mittagessen im Weindorf und Weinprobe inklusive.",
            "new_price": "79",
            "compare_at": "89",
            "discount_style": "strikethrough",
            "limit": 10,
            "group": "Events & Ausflüge",
            "ends_in_days": 20,
            "images": ["castle", "city,tour"],
        },
        {
            "title": "Kombi-Ticket: Altstadt-Führung + Weinprobe",
            "desc": "Nachmittags durch die Altstadt, abends in den Gewölbekeller — "
            "beides zusammen ab 49 € statt 58 €.",
            "new_price": "49",
            "compare_at": "58",
            "discount_style": "ab",
            "limit": 20,
            "group": "Events & Ausflüge",
            "ends_in_days": 30,
            "images": ["wine,cellar", "old,town"],
        },
        {
            "title": "Mystery-Tour: Ziel wird am Treffpunkt verraten",
            "desc": "Jeden Freitag um 18 Uhr: 90 Minuten mit unbekanntem Ziel — der "
            "Preis wird erst beim Klick verraten.",
            "new_price": "19",
            "compare_at": "25",
            "discount_style": "mystery",
            "recurrence": "weekly",
            "limit": 16,
            "group": "Stadtführungen",
            "ends_in_days": 7,
            "images": ["lantern,night", "old,town"],
        },
    ],
    key="tours",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "services": {"preset": "cols3"}},
    label="Stadtgold Touren",
    business_type="tour_operator",
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_touren",
    look="natur",  # DS-9: своя «кожа» семейства
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="touren",
    # 2026-07-30: слайдер + плитки hero_widget="touren"
    # (Touren & Termine / Private Führung / Gutschein / Aktionen).
    hero_widget="touren",
    heroes=[
        {
            "image_kw": "city,tour",
            "title": "Stadtgold Touren",
            "text": "Stadtführungen und Radtouren in kleinen Gruppen — täglich ab Rathaus.",
            "button_label": "Termine ansehen",
            "button_url": "/veranstaltung/",
        },
        {
            "image_kw": "bicycle,city",
            "title": "Radtour ins Umland",
            "text": "Halbtagestour mit Weinprobe — Räder und Guide inklusive.",
            "button_label": "Plätze sichern",
            "button_url": "/veranstaltung/",
        },
        {
            "image_kw": "group,guide",
            "title": "Private Führung",
            "text": "Firmenevent oder Familienfeier? Wunschtermin auf Anfrage.",
            "button_label": "Wunschtermin anfragen",
            "button_url": "/termin/",
        },
    ],
    accent="#0d9488",  # Reise-Türkis
    hero_image_kw="city,tour",
    hero_title="Stadtgold Touren",
    hero_text="Stadtführungen, Radtouren und Tagesausflüge mit lizenzierten "
    "Gästeführern — kleine Gruppen, echte Geschichten. Online buchen, "
    "QR-Ticket aufs Handy.",
    about_title="Über Stadtgold",
    about_text="Seit 2017 zeigen wir unsere Stadt so, wie Reiseführer sie nicht "
    "kennen: Hinterhöfe, Handwerk, Anekdoten. Öffentliche Touren starten täglich am "
    "Rathaus, private Gruppen führen wir auf Wunsch — auch auf Englisch. Für "
    "Ausflüge und Weinproben gibt es Tickets mit fester Platzzahl.",
    nav_style="classic",
    address="Treffpunkt: Rathausplatz 1, 50667 Köln",
    opening_hours_text="Büro: Mo–Fr 9:00–17:00 · Touren täglich",
    opening_hours={d: ("09:00", "17:00") for d in range(5)},
    gallery_kw=["old,town", "city,tour", "wine,cellar", "castle", "bike,tour", "lantern,night"],
    process=[
        ("Tour wählen", "Öffentlich nach Termin oder privat für Ihre Gruppe."),
        ("Online buchen", "Platz sichern — Bestätigung und QR-Ticket per E-Mail."),
        ("Am Treffpunkt einchecken", "QR zeigen, losgehen. Bei Regen? Wir laufen trotzdem."),
    ],
    team=[
        ("Katrin Gold", "Gästeführerin & Gründerin", "tour,guide,woman"),
        ("Samir Stein", "Gästeführer (DE/EN)", "tour,guide,man"),
    ],
    teachers=[
        (
            "Katrin Gold",
            "Gästeführerin & Gründerin",
            "tour,guide,woman",
            "Katrin ist lizenzierte Gästeführerin und erzählt Stadtgeschichte seit "
            "2017 — mit Vorliebe für Hinterhöfe und Handwerkergeschichten.",
        ),
        (
            "Samir Stein",
            "Gästeführer (DE/EN)",
            "tour,guide,man",
            "Samir führt auf Deutsch und Englisch — Spezialgebiet: Architektur "
            "und die Stadt bei Nacht.",
        ),
    ],
    trust={"since": "2017", "marks": ["Lizenzierte Gästeführer", "Kleine Gruppen", "QR-Ticket"]},
    usp=[
        ("local", "Lizenzierte Gästeführer"),
        ("quality", "Kleine Gruppen — max. 16"),
        ("payment", "Online buchen, QR-Ticket"),
        ("clock", "Touren täglich, auch am Wochenende"),
    ],
    testimonials=[
        (
            "Familie Krüger",
            "Zwei Stunden wie im Flug — die Kinder reden heute noch von der Nachtwächter-Tour.",
        ),
        ("Peter M.", "Moselausflug perfekt organisiert: Bus, Burg, Weingut. Jeden Cent wert."),
    ],
    reviews_seed=[
        (5, "Die beste Stadtführung, die wir je gemacht haben.", "tg.krueger@example.de"),
        (5, "Moselausflug top organisiert — Buchung und QR-Ticket easy.", "tg.peter@example.de"),
        (4, "Radtour sehr schön, Tempo entspannt.", "tg.silke@example.de"),
    ],
    faq=[
        (
            "Wo ist der Treffpunkt?",
            "Alle öffentlichen Touren starten am Rathausplatz 1 (Brunnen). "
            "Der genaue Treffpunkt steht in Ihrer Buchungsbestätigung.",
        ),
        (
            "Was passiert bei Regen?",
            "Touren finden bei fast jedem Wetter statt. Nur bei Unwetter sagen wir "
            "ab — dann erhalten Sie automatisch Ersatztermin oder Erstattung.",
        ),
        (
            "Private Gruppenführung?",
            "Buchen Sie den Slot «Private Gruppenführung» — Festpreis bis 15 "
            "Personen, Wunschtermin und Schwerpunkt nach Absprache.",
        ),
        (
            "Wie funktioniert das Ticket?",
            "Nach der Buchung kommt ein QR-Ticket per E-Mail — einfach am "
            "Treffpunkt vorzeigen, ausgedruckt oder auf dem Handy.",
        ),
    ],
    cta={
        "title": "Die Stadt wartet",
        "text": "Sichern Sie sich Plätze für die nächste Tour — die Gruppen sind klein.",
        "button_label": "Touren ansehen",
        "button_url": "/termin/",
    },
    enable_modules=["events", "booking", "customer_account", "promotions"],
    enable_archetypes_section=True,
    hide_archetypes=["catalog"],
    storefront_root="home",
    seed_records=True,
    menus=TOURS_MENUS,
    services=[
        ("Stadtführung Altstadt (öffentlich)", 90, "19"),
        ("Fahrradtour am Fluss", 180, "35"),
        ("Private Gruppenführung (bis 15 P.)", 120, "149"),
    ],
    resources=[
        {
            "name": "Tour ab Rathausplatz",
            "type": "table",
            "capacity": 16,  # мест в группе; party_size суммируется
            "counts_party_size": True,
            "start": "10:00",
            "end": "18:00",
            "slot": 120,
            "weekdays": range(0, 7),
        }
    ],
    events=[
        {
            "title": "Weinprobe im Gewölbekeller",
            "in_days": 12,
            "hour": 19,
            "duration_hours": 3,
            "capacity": 24,
            "price": "39",
            "tiers": [
                ("Frühbucher", "34"),
                ("Standard", "39"),
            ],
            "location": "Gewölbekeller, Altstadt",
            "city": "Köln",
            "category": "genuss",
            "language": "de",
            "description": "Sechs Weine von Winzern aus der Region, dazu Brot, Käse und "
            "Geschichten aus 700 Jahren Kellergewölbe.",
            "program": [
                "19:00 — Empfang im Gewölbekeller",
                "19:30 — Verkostung: 6 Weine mit Winzer-Anekdoten",
                "21:30 — Ausklang bei Brot & Käse",
            ],
        },
        {
            "title": "Tagesausflug: Moseltal & Burg Eltz",
            "in_days": 25,
            "hour": 8,
            "duration_hours": 10,
            "capacity": 30,
            "price": "89",
            "deposit_percent": 20,
            "location": "Abfahrt Busbahnhof, Steig 4",
            "city": "Köln",
            "category": "ausflug",
            "language": "de",
            "description": "Komfortbus, Burgführung, Mittagessen im Weindorf und "
            "Verkostung bei einem Familienweingut — alles inklusive.",
            "program": [
                "08:00 — Abfahrt (Busbahnhof, Steig 4)",
                "10:30 — Führung Burg Eltz",
                "13:00 — Mittagessen im Weindorf · 15:00 Weingut mit Verkostung",
                "18:00 — Rückkehr",
            ],
        },
        {
            "title": "Nachtwächter-Tour Spezial",
            "in_days": 7,
            "hour": 21,
            "duration_hours": 2,
            "capacity": 20,
            "price": "15",
            "location": "Rathausplatz 1 (Brunnen)",
            "city": "Köln",
            "category": "stadtfuehrung",
            "language": "de",
            "description": "Mit Laterne und Hellebarde durch die dunklen Gassen — "
            "Geschichten von Wächtern, Dieben und Gespenstern.",
        },
    ],
    service_reviews=[
        (
            0,
            5,
            "Familie Krüger",
            "tg.rev1@example.de",
            "Kurzweilig, kinderfreundlich, viele Geschichten — absolute Empfehlung.",
        ),
        (1, 5, "Silke B.", "tg.rev2@example.de", "Wunderschöne Route am Fluss, tolles Tempo."),
        (0, 4, "Tom R.", "tg.rev3@example.de", "Treffpunkt easy gefunden, Guide klasse."),
    ],
    event_reviews=[
        (0, 5, "Peter M.", "tg.rev4@example.de", "Weinprobe mit Herz — der Winzer war live dabei."),
        (1, 5, "Anja L.", "tg.rev5@example.de", "Burg Eltz Ausflug: perfekt durchorganisiert."),
    ],
)


MOTO_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            # MT-1: тур-продукт — своя страница (контент+маршрут), заезды ведут на события.
            {"label": "Reisen", "type": "url", "target": "/touren/"},
            {"label": "Termine", "type": "archetype", "target": "events"},
            # MT-D3/D4: приватный выезд и гиды — обе страницы существуют только
            # при активных модулях (jobs / events), поэтому пункт не «мёртвый».
            {"label": "Privat", "type": "url", "target": "/anfrage/"},
            {"label": "Guides", "type": "url", "target": "/lehrer/"},
            {"label": "Reiseberichte", "type": "url", "target": "/blog/"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Reisen", "type": "url", "target": "/touren/", "icon": "🏍"},
            {"label": "Termine", "type": "archetype", "target": "events", "icon": "🎟️"},
            {"label": "Privat", "type": "url", "target": "/anfrage/", "icon": "✍️"},
            {"label": "Kontakt", "type": "page", "target": "contact", "icon": "📞"},
        ],
    },
}


# MT-1: мото/квадро-туры (Индия/Непал) — многодневный тур-продукт с заездами.
# Демонстрирует то, чего нет у городских туров: маршрут по дням с ХРОНОМЕТРАЖЕМ и
# ПОУРОВНЕВОЙ ВИДИМОСТЬЮ (публичные ключевые места, отели — только участникам,
# наработка гида — закрыта), тиры «своя техника / аренда / пассажир», депозит,
# waiver и анкету допуска к технике.
MOTO = DemoKit(
    key="moto",
    label="Himalaya Riders",
    business_type="tour_operator",
    subdomain="moto",
    accent="#c2410c",  # пыль и закат
    # MT-F3: главная в формате «Fokus» под туры — сплит-баннер, CTA в шапке,
    # поездки сразу под ним, заявка на приватный выезд и компакт-полоса доверия.
    # Шумные секции уходят на свои страницы (ST-8): галерея, отзывы, команда.
    bundle="fokus_touren",
    look="klar",
    enable_anfrage_section=True,
    section_titles={
        "tours": "Unsere Reisen",
        # Форма на главной — про приватный выезд, а не про смету на работы.
        "anfrage": "Eigene Gruppe, eigener Termin",
    },
    section_intros={
        "anfrage": "Ab vier Fahrern fahren wir jede Route privat. Sagen Sie uns "
        "Wunschtermin und Gruppengröße — wir melden uns mit einem Angebot.",
    },
    # Часы работы офиса: без них чек-лист готовности главной честно оставался
    # неполным у ЕДИНСТВЕННОГО кита без часов (сверка 2026-08-19).
    opening_hours_text="Büro: Mo–Fr 10:00–18:00 · Touren saisonal",
    opening_hours={d: ("10:00", "18:00") for d in range(5)},
    hero_image_kw="motorcycle,mountain",
    hero_title="Himalaya Riders",
    hero_text="Geführte Motorradreisen durch Indien und Nepal — kleine Gruppen, "
    "Royal Enfield, Begleitfahrzeug und Mechaniker. Anzahlung online, Rest vor dem Start.",
    menus=MOTO_MENUS,
    heroes=[
        {
            "image_kw": "motorcycle,mountain",
            "title": "Manali – Leh",
            "text": "12 Tage über fünf Pässe bis 5.328 m. Kleine Gruppe, Begleitfahrzeug, "
            "Mechaniker.",
            "button_label": "Reise ansehen",
            "button_url": "/touren/",
        },
        {
            "image_kw": "nepal,mountains",
            "title": "Nepal: Mustang-Enduro",
            "text": "9 Tage Schotter, Hängebrücken und Klöster — leichte Enduros.",
            "button_label": "Termine ansehen",
            "button_url": "/veranstaltung/",
        },
        {
            "image_kw": "motorcycle,camp",
            "title": "Erst 25 % anzahlen",
            "text": "Platz sichern, Rest 30 Tage vor dem Start — mit Rücktrittsregeln.",
            "button_label": "Reisen vergleichen",
            "button_url": "/touren/",
        },
        {
            "image_kw": "quad,bike",
            "title": "Chitwan auf vier Rädern",
            "text": "Quad-Safari im Terai — Autoführerschein genügt, Einweisung inklusive.",
            "button_label": "Quad-Reise ansehen",
            "button_url": "/touren/",
        },
        {
            "image_kw": "motorcycle,group",
            "title": "Eigene Gruppe, eigener Termin",
            "text": "Ab vier Fahrern fahren wir jede Route privat — sagen Sie uns Wunschdatum "
            "und Gruppengröße.",
            "button_label": "Private Reise anfragen",
            "button_url": "/anfrage/",
        },
    ],
    about_title="Wer wir sind",
    about_text="Wir fahren den Himalaya seit 2014 — erst privat, seit 2018 mit Gästen. "
    "Unsere Routen entstehen im Winter am Kartentisch und im Sommer im Sattel: welche "
    "Piste nach der Schneeschmelze hält, wo es sauberes Wasser gibt, welche Lodge auf "
    "4.000 m wirklich heizt. Deshalb zeigen wir die Höhepunkte öffentlich — die "
    "komplette Route bekommen unsere Teilnehmer.\n\n"
    "Angefangen hat alles mit Vikram: aufgewachsen in Manali, seit zwanzig Jahren "
    "im Sattel, erst als Mechaniker, dann als Guide. Er fährt jede neue Route vor der "
    "Saison allein ab — mit Zelt, Werkzeug und ohne Zeitplan. Anne kam 2016 als "
    "Teilnehmerin dazu und blieb als Tourleiterin; Pemba führt seit 2019 unsere "
    "Reisen in Nepal. Zu dritt sind wir das ganze Team: Wer bucht, fährt mit einem "
    "von uns — nicht mit einer Agentur, die den Auftrag weitergibt.",
    # MT-D3: jobs = структурированная заявка на ПРИВАТНЫЙ выезд (своя группа,
    # свои даты) — из неё владелец шлёт Sofort-Angebot и доводит до продажи.
    enable_modules=["events", "customer_account", "blog", "inbox", "jobs"],
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": [
            "Himalaya-Klassiker: Manali – Leh",
            "Ladakh-Runde",
            "Spiti Valley",
            "Rajasthan",
            "Nepal Mustang",
            "Annapurna-Trails",
            "Chitwan Quad-Safari",
            "Solukhumbu",
            "Eigene Route (Wunschtermin)",
        ],
    },
    gallery_kw=[
        "motorcycle,mountain",
        "himalaya,road",
        "mountain,pass",
        "ladakh,lake",
        "nubra,dunes",
        "himalaya,monastery",
        "motorcycle,camp",
        "prayer,flags",
        "suspension,bridge",
        "quad,bike",
        "everest,view",
        "motorcycle,group",
    ],
    hide_archetypes=["catalog"],
    teachers=[
        (
            "Vikram Singh",
            "Guide & Routenplaner",
            "guide,motorcycle",
            "Fährt den Himalaya seit 20 Jahren und kennt jede Werkstatt zwischen Manali "
            "und Leh. Plant unsere Routen im Winter am Kartentisch und fährt sie im "
            "Frühjahr allein ab, bevor die erste Gruppe kommt.",
        ),
        (
            "Anne Kessler",
            "Tourleitung & Mechanikerin",
            "mechanic,portrait",
            "Enduro-Trainerin aus Kempten, schraubt selbst und übersetzt zwischen Gruppe "
            "und lokalen Guides. Fährt seit 2016 jede Saison mit — und bringt jedem bei, "
            "wie man eine Kette im Feld nachspannt.",
        ),
        (
            "Pemba Sherpa",
            "Guide Nepal",
            "guide,nepal",
            "In Solukhumbu aufgewachsen, seit zwölf Jahren auf Enduros in Nepal unterwegs. "
            "Kennt die Lodges, die im Oktober wirklich heizen, und spricht mit jedem "
            "Checkpoint auf dem Weg nach Mustang.",
        ),
    ],
    tours=[
        {
            "title": "Himalaya-Klassiker: Manali – Leh",
            "summary": "12 Tage über fünf Pässe bis auf 5.328 m — Royal Enfield, "
            "Begleitfahrzeug und Sauerstoff an Bord.",
            "region": "Himalaya, Indien",
            "difficulty": "hard",
            "duration_days": 12,
            "distance_km": 1450,
            "country": "Indien",
            "photos": [
                "motorcycle,mountain",
                "himalaya,road",
                "mountain,pass",
                "motorcycle,camp",
                "prayer,flags",
            ],
            "description": "Die Königsetappe des indischen Himalaya: Rohtang, Baralacha La, "
            "Nakee La, Lachulung La und das Tanglang La. Kleine Gruppen, erfahrene lokale "
            "Guides, Mechaniker und Begleitfahrzeug — das Gepäck fährt mit, du fährst frei.",
            "details": {
                "for_whom": [
                    "Fahrer mit Führerschein A und Offroad-Grundgefühl",
                    "Sozius willkommen (eigener Tarif)",
                    "Kein Rennen — wir fahren im Tempo der Gruppe",
                ],
                "price_includes": [
                    "Royal Enfield Himalayan 411 inkl. Sprit",
                    "11 Übernachtungen (Hotel/Camp) mit Frühstück",
                    "Begleitfahrzeug, Mechaniker, Ersatzteile",
                    "Inner-Line-Permits und Sauerstoff an Bord",
                ],
                "price_excludes": [
                    "Flüge nach Delhi und zurück",
                    "Reise- und Auslandskrankenversicherung",
                    "Mittag- und Abendessen unterwegs",
                ],
                "bring": [
                    "Helm (ECE) und Motorradhandschuhe",
                    "Protektorenjacke, Nierengurt",
                    "Sonnenschutz LSF 50, Lippenbalsam",
                    "Kopie von Führerschein und Reisepass",
                ],
                "faq": [
                    (
                        "Welchen Führerschein brauche ich?",
                        "Klasse A plus internationalen Führerschein — beides prüfen wir vor "
                        "der Anzahlung.",
                    ),
                    (
                        "Wie gehen Sie mit der Höhe um?",
                        "Zwei Tage Akklimatisierung in Manali, langsame Passanfahrten, "
                        "Sauerstoff im Begleitfahrzeug.",
                    ),
                    (
                        "Kann ich mein eigenes Motorrad mitbringen?",
                        "Ja — dann buchst du den Tarif «Eigenes Motorrad»; Route, Permits "
                        "und Support bleiben gleich.",
                    ),
                ],
            },
            # Показательно смешанная видимость — витрина покажет только public.
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "09:00",
                    "title": "Ankunft Manali, Bike-Übergabe",
                    "text": "Technik-Check, Probefahrt im Tal, Briefing am Abend.",
                    "overnight": "Manali",
                    "lat": "32.2432",
                    "lng": "77.1892",
                    "visibility": "public",
                },
                {
                    "day": 3,
                    "time_from": "07:00",
                    "time_to": "17:00",
                    "title": "Rohtang-Pass (3.978 m) nach Jispa",
                    "text": "Erster großer Pass, Schotter und Wasserdurchfahrten.",
                    "km": 140,
                    "overnight": "Jispa",
                    "lat": "32.6400",
                    "lng": "77.2460",
                    "visibility": "public",
                },
                {
                    "day": 4,
                    "time_from": "08:00",
                    "title": "Hotel Ibex, Jispa — Zimmerverteilung",
                    "text": "Doppelzimmer mit Heizung, Einzelzimmer gegen Aufpreis.",
                    "overnight": "Hotel Ibex",
                    "visibility": "participants",
                },
                {
                    "day": 6,
                    "time_from": "06:30",
                    "title": "Unser Geheimtipp-Abstecher",
                    "text": "Nebenroute abseits der Hauptpiste — Details vor Ort.",
                    "km": 60,
                    "visibility": "private",
                },
                {
                    "day": 9,
                    "time_from": "07:30",
                    "time_to": "18:00",
                    "title": "Tanglang La (5.328 m) nach Leh",
                    "text": "Höchster Punkt der Reise, danach Abfahrt ins Indus-Tal.",
                    "km": 210,
                    "overnight": "Leh",
                    "lat": "34.1526",
                    "lng": "77.5771",
                    "visibility": "public",
                },
            ],
            "teachers": [0, 1],
        },
        {
            "title": "Nepal Enduro: Kathmandu – Mustang",
            "summary": "9 Tage Schotter, Hängebrücken und Klöster — kleine Gruppe, "
            "leichte Enduros.",
            "region": "Mustang, Nepal",
            "country": "Nepal",
            "difficulty": "medium",
            "duration_days": 9,
            "distance_km": 890,
            "photos": [
                "nepal,mountains",
                "enduro,motorcycle",
                "mustang,cliffs",
                "suspension,bridge",
            ],
            "description": "Vom Kathmandu-Tal ins alte Königreich Mustang: Pisten entlang "
            "des Kali Gandaki, Lodges statt Hotels, Klosterbesuch in Lo Manthang.",
            "details": {
                "for_whom": [
                    "Fahrer mit Enduro-Erfahrung auf Schotter",
                    "Gute Grundkondition — sechs Stunden Fahrzeit sind normal",
                ],
                "price_includes": [
                    "Enduro 250–300 ccm inkl. Sprit",
                    "8 Nächte in Lodges mit Frühstück",
                    "Guide, Mechaniker, Permits für Upper Mustang",
                ],
                "bring": ["Helm und Brille", "Regenkombi", "Warme Schicht für die Lodges"],
                "faq": [
                    (
                        "Wie schwer ist die Strecke?",
                        "Mittel: viel Schotter, wenige technische Passagen — Enduro-"
                        "Erfahrung reicht aus.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "10:00",
                    "title": "Kathmandu: Übergabe und Stadtrunde",
                    "km": 30,
                    "overnight": "Kathmandu",
                    "lat": "27.7172",
                    "lng": "85.3240",
                    "visibility": "public",
                },
                {
                    "day": 4,
                    "title": "Kali-Gandaki-Piste nach Kagbeni",
                    "km": 120,
                    "overnight": "Kagbeni",
                    "lat": "28.8370",
                    "lng": "83.7800",
                    "visibility": "public",
                },
                {
                    "day": 6,
                    "title": "Lodge in Lo Manthang",
                    "text": "Einfache Zimmer, warmes Wasser am Abend.",
                    "overnight": "Lo Manthang",
                    "visibility": "participants",
                },
            ],
            "teachers": [1, 2],
        },
        {
            "title": "Ladakh-Runde: Khardung La und Pangong",
            "summary": "10 Tage ab Leh — der höchste befahrbare Pass, die Dünen von Nubra "
            "und der türkise Pangong-See auf 4.350 m.",
            "region": "Ladakh, Indien",
            "country": "Indien",
            "difficulty": "hard",
            "duration_days": 10,
            "distance_km": 980,
            "photos": [
                "ladakh,lake",
                "mountain,pass",
                "nubra,dunes",
                "himalaya,monastery",
                "motorcycle,group",
            ],
            "description": "Eine Runde ohne lange Anfahrt: Wir starten und enden in Leh, "
            "fahren über den Khardung La ins Nubra-Tal, reiten Kamele zwischen den Dünen "
            "von Hunder und stehen am dritten Tag am Pangong. Kurze Etappen, viel Höhe — "
            "ideal, wenn der Urlaub keine zwei Wochen hergibt.",
            "details": {
                "promise": "Die drei Postkartenmotive Ladakhs in zehn Tagen — ohne Hetze.",
                "for_whom": [
                    "Fahrer mit Führerschein A, Schotter-Erfahrung hilfreich",
                    "Wer wenig Urlaubstage, aber große Bilder will",
                    "Sozius willkommen — die Etappen sind kurz",
                ],
                "price_includes": [
                    "Royal Enfield Himalayan 411 inkl. Sprit",
                    "9 Übernachtungen (Hotel in Leh, Camp in Nubra) mit Frühstück",
                    "Begleitfahrzeug, Mechaniker, Sauerstoff",
                    "Inner-Line-Permits für Nubra und Pangong",
                ],
                "price_excludes": [
                    "Flüge nach Leh oder Delhi",
                    "Reise- und Auslandskrankenversicherung",
                    "Mittag- und Abendessen",
                ],
                "bring": [
                    "Helm (ECE) und Motorradhandschuhe",
                    "Warme Schicht für 4.000 m — auch im Juli",
                    "Sonnenschutz LSF 50 und Lippenbalsam",
                ],
                "faq": [
                    (
                        "Reichen zwei Tage Akklimatisierung?",
                        "Leh liegt schon auf 3.500 m. Wir bleiben zwei Nächte im Tal, "
                        "bevor der erste Pass kommt — das reicht für die meisten.",
                    ),
                    (
                        "Wie kalt wird es am Pangong?",
                        "Nachts um den Gefrierpunkt, tagsüber 15–20 °C. Die Unterkunft "
                        "am See ist ein festes Camp mit Decken und Ofen.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "10:00",
                    "title": "Ankunft Leh, Bike-Übergabe",
                    "text": "Papiere, Technik-Check, kurze Eingewöhnungsrunde im Indus-Tal.",
                    "overnight": "Leh",
                    "lat": "34.1526",
                    "lng": "77.5771",
                    "visibility": "public",
                },
                {
                    "day": 3,
                    "time_from": "07:00",
                    "time_to": "16:00",
                    "title": "Khardung La (5.359 m) ins Nubra-Tal",
                    "text": "Der Klassiker: Schnee an der Passhöhe, Sand im Tal.",
                    "km": 120,
                    "overnight": "Hunder",
                    "lat": "34.2780",
                    "lng": "77.6045",
                    "visibility": "public",
                },
                {
                    "day": 4,
                    "time_from": "09:00",
                    "title": "Camp in Hunder — Zeltverteilung",
                    "text": "Feste Zelte mit Bad, Abendessen im Gemeinschaftszelt.",
                    "overnight": "Wüstencamp Hunder",
                    "visibility": "participants",
                },
                {
                    "day": 6,
                    "time_from": "06:30",
                    "title": "Unsere Abkürzung übers Hochtal",
                    "text": "Piste abseits der Touristenroute — Details am Vorabend.",
                    "km": 70,
                    "visibility": "private",
                },
                {
                    "day": 7,
                    "time_from": "08:00",
                    "time_to": "17:00",
                    "title": "Pangong Tso (4.350 m)",
                    "text": "Der See wechselt im Tagesverlauf fünfmal die Farbe.",
                    "km": 160,
                    "overnight": "Spangmik",
                    "lat": "33.7500",
                    "lng": "78.7500",
                    "visibility": "public",
                },
            ],
            "teachers": [0, 1],
        },
        {
            "title": "Spiti Valley: Klöster über 4.000 m",
            "summary": "11 Tage durch das trockenste Tal Indiens — Kloster Key, Chandratal "
            "und das Dorf Komic auf 4.587 m.",
            "region": "Spiti, Indien",
            "country": "Indien",
            "difficulty": "medium",
            "duration_days": 11,
            "distance_km": 1180,
            "photos": [
                "spiti,valley",
                "himalaya,monastery",
                "mountain,village",
                "motorcycle,camp",
            ],
            "description": "Spiti ist Ladakhs stillere Schwester: dieselbe Mondlandschaft, "
            "halb so viele Motorräder. Wir fahren von Shimla hinauf, schlafen in Kloster-"
            "Gästehäusern und im Zelt am Chandratal und kommen über den Kunzum La zurück.",
            "details": {
                "promise": "Tausendjährige Klöster, in denen wirklich noch gelebt wird.",
                "for_whom": [
                    "Fahrer mit etwas Schotter-Erfahrung",
                    "Wer Kultur mag und nicht nur Pässe zählt",
                    "Gruppen bis acht Motorräder",
                ],
                "price_includes": [
                    "Royal Enfield Himalayan 411 inkl. Sprit",
                    "10 Übernachtungen (Gästehaus, Homestay, ein Zeltcamp)",
                    "Begleitfahrzeug und Mechaniker",
                    "Spenden und Eintritte in den Klöstern",
                ],
                "price_excludes": [
                    "Anreise nach Shimla",
                    "Versicherungen",
                ],
                "bring": [
                    "Schlafsack-Inlett für die Homestays",
                    "Stirnlampe — Strom fällt regelmäßig aus",
                    "Kleidung, die Schultern und Knie bedeckt (Klosterbesuche)",
                ],
                "faq": [
                    (
                        "Wie sind die Unterkünfte?",
                        "Einfach und sauber: Gästehäuser mit heißem Wasser im Eimer, "
                        "zwei Homestays bei Familien, eine Nacht im Zelt am See.",
                    ),
                    (
                        "Gibt es unterwegs Handyempfang?",
                        "In Kaza ja, dazwischen oft tagelang nicht. Wir geben Angehörigen "
                        "vor dem Start eine Satellitennummer für Notfälle.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 2,
                    "time_from": "08:00",
                    "title": "Shimla nach Sangla",
                    "text": "Apfelplantagen, enge Kurven, erster Kontakt mit dem Sutlej.",
                    "km": 220,
                    "overnight": "Sangla",
                    "lat": "31.4270",
                    "lng": "78.2660",
                    "visibility": "public",
                },
                {
                    "day": 5,
                    "time_from": "09:00",
                    "title": "Kloster Key und Komic",
                    "text": "Morgengebet im Kloster, danach das höchste Dorf mit Straße.",
                    "km": 60,
                    "overnight": "Kaza",
                    "lat": "32.2980",
                    "lng": "78.0120",
                    "visibility": "public",
                },
                {
                    "day": 7,
                    "title": "Homestay in Langza",
                    "text": "Zwei Familien, Buchweizen-Pfannkuchen zum Frühstück.",
                    "overnight": "Langza",
                    "visibility": "participants",
                },
                {
                    "day": 9,
                    "time_from": "07:30",
                    "title": "Zeltnacht am Chandratal",
                    "text": "Der «Mondsee» auf 4.250 m — Anfahrt nur bei trockenem Wetter.",
                    "km": 95,
                    "overnight": "Chandratal",
                    "lat": "32.4780",
                    "lng": "77.6180",
                    "visibility": "public",
                },
            ],
            "teachers": [0],
        },
        {
            "title": "Rajasthan: Wüstenfahrt zu den Festungen",
            "summary": "9 Tage auf Asphalt und Sandpisten — Jaipur, Jodhpur, Jaisalmer und "
            "eine Nacht in den Dünen.",
            "region": "Rajasthan, Indien",
            "country": "Indien",
            "difficulty": "easy",
            "duration_days": 9,
            "distance_km": 1320,
            "photos": [
                "rajasthan,fort",
                "desert,dunes",
                "india,street",
                "motorcycle,road",
            ],
            "description": "Die Einsteigerreise: keine Höhe, kein Sauerstoff, dafür Farbe "
            "im Übermaß. Gute Straßen zwischen den Städten, kurze Sandetappen in der Thar, "
            "abends Festungen, Märkte und Dachterrassen.",
            "details": {
                "promise": "Alles, was Indien laut und schön macht — ohne Höhenkrankheit.",
                "for_whom": [
                    "Einsteiger und Wiedereinsteiger",
                    "Paare — die Etappen sind Sozius-tauglich",
                    "Wer im Winter fahren will (November bis Februar)",
                ],
                "price_includes": [
                    "Royal Enfield Classic 350 inkl. Sprit",
                    "8 Übernachtungen in Havelis und ein Wüstencamp",
                    "Frühstück, zwei Abendessen mit Musik",
                    "Begleitfahrzeug, Mechaniker, Eintritte in drei Forts",
                ],
                "price_excludes": [
                    "Flüge nach Delhi oder Jaipur",
                    "Versicherungen und Trinkgelder",
                ],
                "bring": [
                    "Leichte Motorradjacke — tagsüber wird es warm",
                    "Halstuch gegen Staub",
                    "Bargeld für Märkte",
                ],
                "faq": [
                    (
                        "Muss ich Sand fahren können?",
                        "Nein. Die Sandpassage vor dem Camp ist kurz; wer will, fährt "
                        "im Begleitfahrzeug mit und lässt sein Bike überführen.",
                    ),
                    (
                        "Wie ist der Verkehr in den Städten?",
                        "Lebhaft. Wir fahren in Zweierreihen, mit Funk im ersten und "
                        "letzten Bike, und umgehen die Innenstädte zur Rushhour.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "11:00",
                    "title": "Jaipur: Übergabe und Amber Fort",
                    "text": "Eingewöhnungsrunde und erster Festungsbesuch am Nachmittag.",
                    "km": 40,
                    "overnight": "Jaipur",
                    "lat": "26.9124",
                    "lng": "75.7873",
                    "visibility": "public",
                },
                {
                    "day": 4,
                    "time_from": "08:00",
                    "time_to": "15:00",
                    "title": "Jodhpur, die blaue Stadt",
                    "text": "Mehrangarh über den Dächern, abends Markt am Uhrturm.",
                    "km": 290,
                    "overnight": "Jodhpur",
                    "lat": "26.2389",
                    "lng": "73.0243",
                    "visibility": "public",
                },
                {
                    "day": 6,
                    "time_from": "16:00",
                    "title": "Wüstencamp in der Thar",
                    "text": "Zelte mit Bad, Abendessen am Feuer, Sonnenaufgang auf der Düne.",
                    "overnight": "Camp bei Sam",
                    "visibility": "participants",
                },
                {
                    "day": 7,
                    "time_from": "09:00",
                    "title": "Jaisalmer: Fort aus Sandstein",
                    "text": "Die letzte bewohnte Festung Indiens — wir schlafen darin.",
                    "km": 60,
                    "overnight": "Jaisalmer",
                    "lat": "26.9157",
                    "lng": "70.9083",
                    "visibility": "public",
                },
            ],
            "teachers": [0, 1],
        },
        {
            "title": "Annapurna-Trails: Pokhara und Ghorepani",
            "summary": "8 Tage leichte Enduro rund um Pokhara — Terrassenfelder, "
            "Hängebrücken und der Blick auf den Machapuchare.",
            "region": "Annapurna, Nepal",
            "country": "Nepal",
            "difficulty": "medium",
            "duration_days": 8,
            "distance_km": 640,
            "photos": [
                "annapurna,trail",
                "pokhara,lake",
                "suspension,bridge",
                "mountain,village",
            ],
            "description": "Nepal im Kleinen: jeden Tag Schotter, jeden Abend eine warme "
            "Dusche. Wir fahren die Trails über Ghorepani und Sarangkot, baden im "
            "Phewa-See und sehen bei gutem Wetter drei Achttausender auf einmal.",
            "details": {
                "promise": "Die schönsten Pisten Nepals ohne Höhenlager.",
                "for_whom": [
                    "Fahrer mit Grundkenntnissen auf Schotter",
                    "Wer Nepal zum ersten Mal fährt",
                    "Gruppen bis acht Enduros",
                ],
                "price_includes": [
                    "Enduro 250 ccm inkl. Sprit",
                    "7 Nächte in Lodges und einem Hotel in Pokhara",
                    "Guide, Mechaniker, alle Trail-Permits",
                ],
                "price_excludes": [
                    "Flüge nach Kathmandu",
                    "Versicherungen",
                ],
                "bring": [
                    "Enduro-Stiefel und Brille",
                    "Regenkombi — der Monsun endet spät",
                    "Badezeug für den Phewa-See",
                ],
                "faq": [
                    (
                        "Wann ist die beste Zeit?",
                        "Oktober bis Dezember: klare Sicht, trockene Pisten. Im Frühjahr "
                        "blüht der Rhododendron, dafür ist es diesiger.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "09:00",
                    "title": "Pokhara: Übergabe am Phewa-See",
                    "text": "Technik-Check, Trail-Test auf dem Weg nach Sarangkot.",
                    "km": 45,
                    "overnight": "Pokhara",
                    "lat": "28.2096",
                    "lng": "83.9856",
                    "visibility": "public",
                },
                {
                    "day": 3,
                    "time_from": "08:00",
                    "title": "Trail nach Ghorepani",
                    "text": "Steinpisten durch Rhododendronwald, Aussicht am Poon Hill.",
                    "km": 70,
                    "overnight": "Ghorepani",
                    "lat": "28.4020",
                    "lng": "83.6930",
                    "visibility": "public",
                },
                {
                    "day": 5,
                    "title": "Lodge in Ghandruk",
                    "text": "Gurung-Dorf mit Steintreppen — Zimmer mit Bergblick.",
                    "overnight": "Ghandruk",
                    "visibility": "participants",
                },
                {
                    "day": 6,
                    "time_from": "07:00",
                    "title": "Unsere Hausstrecke zurück",
                    "text": "Wenig befahrene Variante über die Grate — wird vor Ort gezeigt.",
                    "km": 85,
                    "visibility": "private",
                },
            ],
            "teachers": [2],
        },
        {
            "title": "Chitwan Quad-Safari: Terai und Dschungel",
            "summary": "6 Tage auf Quads durch das Tiefland — Flussfurten, Elefantengras "
            "und Nashörner am Rapti.",
            "region": "Terai, Nepal",
            "country": "Nepal",
            "difficulty": "easy",
            "duration_days": 6,
            "distance_km": 420,
            "photos": [
                "quad,bike",
                "jungle,river",
                "terai,jungle",
                "quad,safari",
            ],
            "description": "Unsere Quad-Reise: vier Räder, kein Balancieren, dafür Sand, "
            "Wasser und Staub. Wir fahren die Pisten am Rand des Chitwan-Nationalparks, "
            "übernachten in Lodges am Fluss und gehen zweimal mit Ranger ins Gras.",
            "details": {
                "promise": "Die Reise für alle, die nie Motorrad gefahren sind.",
                "for_whom": [
                    "Fahranfänger — Quad fahren lernt man in einer Stunde",
                    "Familien mit Jugendlichen ab 16 (Sozius-Quad)",
                    "Wer Tiere sehen und trotzdem fahren will",
                ],
                "price_includes": [
                    "Quad 450 ccm inkl. Sprit und Einweisung",
                    "5 Nächte in Dschungel-Lodges mit Vollpension",
                    "Zwei Ranger-Touren im Nationalpark",
                    "Begleitfahrzeug und Mechaniker",
                ],
                "price_excludes": [
                    "Flüge nach Kathmandu",
                    "Versicherungen",
                ],
                "bring": [
                    "Lange, helle Kleidung gegen Mücken",
                    "Fernglas",
                    "Wechselkleidung für die Flussdurchfahrten",
                ],
                "faq": [
                    (
                        "Brauche ich einen Motorradführerschein?",
                        "Nein — Klasse B reicht. Die Einweisung machen wir am ersten "
                        "Nachmittag auf einer abgesperrten Piste.",
                    ),
                    (
                        "Sieht man wirklich Nashörner?",
                        "Fast immer. Chitwan hat über 600 Panzernashörner; garantieren "
                        "kann sie niemand — versprechen tun wir es deshalb nicht.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 1,
                    "time_from": "14:00",
                    "title": "Sauraha: Quad-Einweisung",
                    "text": "Bremsen, Kurven, Flussfurt — erst üben, dann fahren.",
                    "km": 25,
                    "overnight": "Sauraha",
                    "lat": "27.5800",
                    "lng": "84.4950",
                    "visibility": "public",
                },
                {
                    "day": 3,
                    "time_from": "08:00",
                    "title": "Pisten am Rapti entlang",
                    "text": "Sandbänke, Dörfer, Mittagspause bei einer Tharu-Familie.",
                    "km": 90,
                    "overnight": "Meghauli",
                    "lat": "27.5700",
                    "lng": "84.2200",
                    "visibility": "public",
                },
                {
                    "day": 4,
                    "title": "Lodge am Flussufer",
                    "text": "Bungalows mit Moskitonetz, Abendessen auf der Terrasse.",
                    "overnight": "Riverside Lodge",
                    "visibility": "participants",
                },
            ],
            "teachers": [2],
        },
        {
            "title": "Solukhumbu: Everest-Vorland auf zwei Rädern",
            "summary": "11 Tage bis dorthin, wo die Straße endet — Steilstücke, "
            "Hängebrücken und der erste Blick auf den Everest.",
            "region": "Solukhumbu, Nepal",
            "country": "Nepal",
            "difficulty": "hard",
            "duration_days": 11,
            "distance_km": 720,
            "photos": [
                "everest,view",
                "mountain,trail",
                "suspension,bridge",
                "prayer,flags",
            ],
            "description": "Die anspruchsvollste Reise im Programm: Pisten mit 20 % "
            "Steigung, Geröll, Flussquerungen und Tage, an denen 60 km sechs Stunden "
            "dauern. Belohnung ist Sherpa-Land — und der Blick, wegen dem alle kommen.",
            "details": {
                "promise": "Für Fahrer, die schon einmal einen Tag lang gefallen sind.",
                "for_whom": [
                    "Erfahrene Enduro-Fahrer mit Geröll-Praxis",
                    "Gute Kondition — Schieben gehört dazu",
                    "Kein Sozius auf dieser Reise",
                ],
                "price_includes": [
                    "Enduro 300 ccm inkl. Sprit",
                    "10 Nächte in Lodges mit Frühstück",
                    "Guide, Mechaniker, Begleitjeep bis Phaplu",
                    "Nationalpark-Permits",
                ],
                "price_excludes": [
                    "Flüge nach Kathmandu",
                    "Versicherung inkl. Hubschrauber-Rettung (Pflicht)",
                ],
                "bring": [
                    "Vollständige Protektoren-Ausrüstung",
                    "Handschuhe zum Wechseln",
                    "Daunenjacke für die Abende",
                ],
                "faq": [
                    (
                        "Ist eine Rettungsversicherung wirklich Pflicht?",
                        "Ja. Ohne Nachweis einer Bergrettungs-Police mit Helikopter "
                        "starten wir nicht — das prüfen wir vor der Restzahlung.",
                    ),
                    (
                        "Wie viele Fahrer nehmt ihr mit?",
                        "Maximal sechs, plus Guide und Mechaniker. Auf diesen Pisten "
                        "kann eine große Gruppe niemanden mehr einsammeln.",
                    ),
                ],
            },
            "itinerary": [
                {
                    "day": 2,
                    "time_from": "07:00",
                    "title": "Kathmandu nach Jiri",
                    "text": "Letzter Asphalt der Reise, ab hier wird es einspurig.",
                    "km": 180,
                    "overnight": "Jiri",
                    "lat": "27.6330",
                    "lng": "86.2300",
                    "visibility": "public",
                },
                {
                    "day": 5,
                    "time_from": "07:30",
                    "time_to": "17:00",
                    "title": "Geröllpiste nach Phaplu",
                    "text": "Sechs Stunden für 55 km — der Tag, von dem alle erzählen.",
                    "km": 55,
                    "overnight": "Phaplu",
                    "lat": "27.5170",
                    "lng": "86.5850",
                    "visibility": "public",
                },
                {
                    "day": 7,
                    "title": "Lodge in Ringmo",
                    "text": "Sherpa-Familie, Ofen im Gastraum, Strom aus Solarzellen.",
                    "overnight": "Ringmo",
                    "visibility": "participants",
                },
                {
                    "day": 8,
                    "time_from": "06:00",
                    "title": "Aussichtsgrat vor Sonnenaufgang",
                    "text": "Unser Platz für den Everest-Blick — Standort bleibt intern.",
                    "km": 30,
                    "visibility": "private",
                },
            ],
            "teachers": [1, 2],
        },
    ],
    events=[
        {
            "title": "Manali – Leh · Juni-Gruppe",
            "tour": 0,
            "in_days": 60,
            "hour": 9,
            "duration_days": 12,
            "capacity": 10,
            "price": "2490",
            "deposit_percent": 25,
            # MX-2d (решение владельца §3.1): тир = категория УЧАСТИЯ; аренда
            # байка — адресная опция с пулом (иначе ёмкость аренды не отследить).
            "tiers": [
                ("Fahrer", "1990", 9),
                ("Sozius (ohne Bike)", "1490", 4),
            ],
            "rental_option": ("Royal Enfield 411 mieten", "500", 6, "Moto-Verleih Manali"),
            "city": "Manali",
            "location": "Treffpunkt Hotel Snow Valley, Manali",
            "language": "de",
            "waiver_required": True,
            "registration_fields": [
                "license_class",
                "riding_experience",
                "height_cm",
                "own_bike",
                "emergency_contact",
            ],
            "description": "Klassische Route über fünf Pässe. Maximal zehn Fahrer, "
            "ein Guide und ein Mechaniker.",
        },
        {
            "title": "Manali – Leh · August-Gruppe",
            "tour": 0,
            "in_days": 115,
            "hour": 9,
            "duration_days": 12,
            "capacity": 10,
            "price": "2490",
            "deposit_percent": 25,
            "tiers": [("Fahrer", "1990", 10)],
            "rental_option": ("Royal Enfield 411 mieten", "500", 7, "Moto-Verleih Manali"),
            "city": "Manali",
            "language": "de",
            "waiver_required": True,
        },
        {
            "title": "Nepal Mustang · Oktober",
            "tour": 1,
            "in_days": 150,
            "hour": 8,
            "duration_days": 9,
            "capacity": 8,
            "price": "1890",
            "deposit_percent": 25,
            "city": "Kathmandu",
            "language": "de",
            "waiver_required": True,
        },
        {
            "title": "Ladakh-Runde · Juli-Gruppe",
            "tour": 2,
            "in_days": 75,
            "hour": 10,
            "duration_days": 10,
            "capacity": 8,
            "price": "2190",
            "deposit_percent": 25,
            "tiers": [("Fahrer", "1790", 8)],
            "rental_option": ("Royal Enfield 411 mieten", "400", 6, "Moto-Verleih Leh"),
            "city": "Leh",
            "location": "Treffpunkt Hotel Ladakh Palace, Leh",
            "language": "de",
            "waiver_required": True,
            "description": "Kurze Etappen, drei Höhepunkte: Khardung La, Nubra und Pangong.",
        },
        {
            "title": "Ladakh-Runde · September-Gruppe",
            "tour": 2,
            "in_days": 135,
            "hour": 10,
            "duration_days": 10,
            "capacity": 8,
            "price": "2190",
            "deposit_percent": 25,
            "city": "Leh",
            "language": "de",
            "waiver_required": True,
        },
        {
            "title": "Rajasthan · November-Gruppe",
            "tour": 4,
            "in_days": 200,
            "hour": 9,
            "duration_days": 9,
            "capacity": 12,
            "price": "1690",
            "deposit_percent": 25,
            "tiers": [
                ("Royal Enfield Classic 350", "1690", 8),
                ("Sozius (ohne Bike)", "990", 4),
            ],
            "city": "Jaipur",
            "location": "Treffpunkt Haveli Jaipur",
            "language": "de",
            "description": "Winterreise ohne Höhe: Forts, Märkte und eine Nacht in den Dünen.",
        },
        {
            "title": "Annapurna-Trails · Oktober-Gruppe",
            "tour": 5,
            "in_days": 160,
            "hour": 9,
            "duration_days": 8,
            "capacity": 8,
            "price": "1590",
            "deposit_percent": 25,
            "city": "Pokhara",
            "language": "de",
            "waiver_required": True,
            "description": "Beste Sicht des Jahres: klare Luft nach dem Monsun.",
        },
        {
            "title": "Chitwan Quad-Safari · Februar",
            "tour": 6,
            "in_days": 240,
            "hour": 11,
            "duration_days": 6,
            "capacity": 10,
            "price": "1290",
            "deposit_percent": 25,
            "tiers": [
                ("Eigenes Quad fahren", "1290", 8),
                ("Mitfahrer auf dem Quad", "890", 4),
            ],
            "city": "Sauraha",
            "language": "de",
            "description": "Familienfreundlich: Einweisung am ersten Tag, kein "
            "Motorradführerschein nötig.",
        },
        {
            "title": "Solukhumbu · Oktober-Gruppe",
            "tour": 7,
            "in_days": 165,
            "hour": 7,
            "duration_days": 11,
            "capacity": 6,
            "price": "2790",
            "deposit_percent": 25,
            "city": "Kathmandu",
            "language": "de",
            "waiver_required": True,
            "registration_fields": [
                "license_class",
                "riding_experience",
                "emergency_contact",
            ],
            "description": "Sechs Fahrer, ein Guide, ein Mechaniker — mehr geht auf "
            "diesen Pisten nicht.",
        },
    ],
    blog_posts=[
        (
            "Rohtang im Juni: Schnee an der Passhöhe",
            "Warum wir die Etappe nach Jispa in diesem Jahr eine Stunde früher starten.",
            "Der Rohtang war Anfang Juni noch beidseitig von Schneewänden gesäumt. "
            "Die Piste taut ab zehn Uhr auf und wird dann tief — deshalb starten wir "
            "die Etappe nach Jispa künftig um sieben statt um acht.\n\n"
            "Für die Gruppe heißt das: früher aufstehen, dafür trockene Kehren und "
            "eine Stunde mehr Licht am Nachmittag.",
            "himalaya,road",
        ),
        (
            "Werkstatt-Tag in Leh: was wir an den Enfields tauschen",
            "Nach 1.400 km auf Schotter ist die Halbzeit-Wartung Pflicht.",
            "In Leh steht ein voller Tag Technik an: Ölwechsel, Kettenspiel, "
            "Bremsbeläge und Speichen nachziehen. Wer will, schraubt mit — unser "
            "Mechaniker erklärt jeden Handgriff.\n\n"
            "Ersatzteile führen wir im Begleitfahrzeug mit, damit niemand wegen "
            "eines Lagers stehenbleibt.",
            "mechanic,motorcycle",
        ),
    ],
    tour_operations={
        "posts": [
            "Servus zusammen! Hier laufen alle Infos zur Juni-Gruppe. "
            "Fragen bitte direkt hier stellen — dann haben alle die Antwort.",
            "Packliste ist online: Helm, Protektoren, warme Schicht für die Pässe. "
            "Wer eine Maschine mietet, schickt mir bitte den Führerschein ins Dokumente-Fach.",
            "Wetterlage am Rohtang ist stabil — wir starten wie geplant um 07:00 in Manali.",
        ],
        # MT-F5: разговор в группе — иначе вкладка «Chat» в демо пустая.
        "comments": [
            (1, "Jens W.", "Reicht eine normale Softshell oder braucht es die Daunenjacke?"),
            (
                1,
                "Vikram Singh",
                "Softshell plus dünne Daune reicht. Am Baralacha La war es letztes Jahr "
                "morgens bei −4 °C.",
            ),
            (2, "Silke H.", "Perfekt, dann sind wir um 06:30 am Treffpunkt. 👍"),
        ],
        "chat": [
            ("Silke H.", "Bin gerade in Delhi gelandet, Anschlussflug nach Kullu läuft."),
            ("Jens W.", "Ich komme mit dem Nachtbus, morgen früh gegen 8 in Manali."),
            (
                "Vikram Singh",
                "Super. Ich hole euch am Busbahnhof ab, die Maschinen stehen ab 10 Uhr bereit.",
            ),
            ("Carola T.", "Gibt es unterwegs Wäsche-Möglichkeiten oder besser mehr mitnehmen?"),
            (
                "Anne Kessler",
                "In Leh haben wir einen ganzen Tag — dort geht Wäsche problemlos.",
            ),
        ],
        "supplier_bookings": [
            {
                "kind": "hotel",
                "supplier": "Hotel Snow Valley, Manali",
                "day": 1,
                "stop": "Manali",
                "qty": 6,
                "cost": "540",
                "currency": "INR",
                "original": 49000,
                "status": "paid",
                "visible": True,
                "note": "2 Nächte Akklimatisierung",
            },
            {
                "kind": "hotel",
                "supplier": "Hotel Ibex, Jispa",
                "day": 4,
                "stop": "Jispa",
                "qty": 6,
                "cost": "390",
                "currency": "INR",
                "original": 35500,
                "status": "confirmed",
                "visible": True,
            },
            {
                "kind": "transport",
                "supplier": "Sharma Logistics",
                "day": 1,
                "stop": "Begleitfahrzeug",
                "cost": "1250",
                "status": "confirmed",
            },
            {
                "kind": "permit",
                "supplier": "Inner Line Permit Office",
                "day": 2,
                "stop": "Keylong",
                "qty": 10,
                "cost": "180",
                "status": "to_book",
                "note": "Pässe aller Teilnehmer nötig",
            },
        ],
        "tasks": [
            {"title": "Inner-Line-Permits beantragen", "in_days": 21},
            {"title": "Maschinen: Ölwechsel und Ketten prüfen", "in_days": 30},
            {"title": "Sauerstoffflaschen auffüllen", "in_days": 35},
            {"title": "Teilnehmer-Briefing verschicken", "in_days": 14, "done": True},
        ],
    },
    # Кабинет демо наполняем сделками (билеты заездов + заявки ниже), иначе доска
    # и «Verkäufe» у мото-демо пустые.
    seed_records=True,
    # MT-D3: демо приватных выездов — заявки уже лежат на доске, из них можно
    # прямо в демо отправить смету (Sofort-Angebot).
    job_samples=[
        {
            "title": "Private Reise Ladakh für 5 Freunde (eigene Termine)",
            "name": "Team Rostock",
            "email": "moto.job1@example.de",
            "phone": "0381 445566",
            "description": "Wir sind fünf Fahrer mit eigener Erfahrung und würden die "
            "Ladakh-Runde gern zwei Wochen früher fahren als die Juli-Gruppe. Zwei von "
            "uns bringen eigene Maschinen mit.",
            "lines": [
                {"text": "Guide und Mechaniker (10 Tage)", "qty": 1, "unit_price": "2400.00"},
                {"text": "Royal Enfield Himalayan inkl. Sprit", "qty": 3, "unit_price": "690.00"},
                {"text": "Begleitfahrzeug mit Fahrer", "qty": 1, "unit_price": "1250.00"},
                {"text": "Permits und Camp-Zuschlag", "qty": 5, "unit_price": "140.00"},
            ],
            "vat_rate": 19,
        },
        {
            "title": "Firmen-Incentive Rajasthan (12 Personen, November)",
            "name": "Hartmann Werkzeuge GmbH",
            "email": "moto.job2@example.de",
            "description": "Incentive-Reise für Vertriebspartner: sechs Fahrer, sechs "
            "Sozius, gehobene Havelis und ein Abend mit Musik im Wüstencamp.",
            "lines": [
                {"text": "Reisepaket Rajasthan (Fahrer)", "qty": 6, "unit_price": "1690.00"},
                {"text": "Reisepaket Rajasthan (Sozius)", "qty": 6, "unit_price": "990.00"},
                {"text": "Abendprogramm im Wüstencamp", "qty": 1, "unit_price": "850.00"},
            ],
            "vat_rate": 19,
        },
    ],
    faq=[
        (
            "Wie läuft die Anzahlung?",
            "25 % online bei der Buchung, der Rest 30 Tage vor dem Start — "
            "die Zahlungserinnerung kommt automatisch.",
        ),
        (
            "Können wir eine Reise privat buchen?",
            "Ja. Sagen Sie uns Wunschtermin und Gruppengröße über das Anfrage-Formular — "
            "ab vier Fahrern fahren wir jede Route auch als geschlossene Gruppe.",
        ),
        (
            "Fahrt ihr auch Quad statt Motorrad?",
            "Im Terai in Nepal ja: die Chitwan-Safari fahren wir komplett auf Quads, "
            "dafür reicht der Autoführerschein.",
        ),
        (
            "Bekomme ich die komplette Route vorab?",
            "Die Höhepunkte stehen öffentlich auf der Reiseseite. Die Tagesroute mit "
            "Unterkünften erhalten Teilnehmer nach der Buchung.",
        ),
        (
            "Was ist, wenn ich unterwegs nicht weiterfahren kann?",
            "Das Begleitfahrzeug nimmt Fahrer und Motorrad auf — deshalb fährt es immer mit.",
        ),
    ],
    usp=[
        "Kleine Gruppen: maximal zehn Motorräder",
        "Begleitfahrzeug, Mechaniker und Ersatzteile inklusive",
        "Permits und Sauerstoff organisieren wir",
    ],
    trust={
        "title": "Warum mit uns",
        "items": [
            "Seit 2014 im Himalaya unterwegs",
            "Lokale Guides mit Lizenz",
            "Anzahlung 25 %, Rest erst vor dem Start",
        ],
    },
    event_reviews=[
        (
            0,
            5,
            "Markus B.",
            "moto.rev1@example.de",
            "Tanglang La bei Sonnenaufgang — und die Organisation lief wie ein Uhrwerk.",
        ),
        (
            2,
            5,
            "Silke H.",
            "moto.rev2@example.de",
            "Nepal war staubig, anstrengend und das Beste, was ich je gefahren bin.",
        ),
        (
            3,
            5,
            "Jens W.",
            "moto.rev6@example.de",
            "Ladakh in zehn Tagen klingt nach Hetze, war es aber nie — kurze Etappen, "
            "viel Zeit für Fotos.",
        ),
        (
            5,
            4,
            "Carola T.",
            "moto.rev7@example.de",
            "Rajasthan als Sozius: warm, laut, wunderschön. Nur die Havelis waren "
            "unterschiedlich gut.",
        ),
        (
            7,
            5,
            "Familie Brenner",
            "moto.rev8@example.de",
            "Unsere Tochter (17) durfte selbst Quad fahren — für sie war das die Reise "
            "ihres Lebens.",
        ),
    ],
    reviews_seed=[
        (
            5,
            "Beste Reiseorganisation, die ich kenne. Alles hielt, was versprochen war.",
            "moto.rev3@example.de",
        ),
        (5, "Guides mit echtem Wissen — nicht nur Vorfahren und Winken.", "moto.rev4@example.de"),
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
            {"label": "News", "type": "url", "target": "/blog/"},
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Meister", "type": "page", "target": "team"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
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
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}},
    look="warm",  # ST-1: тёплый Look (архетип-акцент friseur)
    seed_inbox=True,  # LS-3/4/6: демо «Прямой линии» + Sofort-Angebot
    whatsapp_number="+49 170 2000001",  # LS-1/LS-2
    presence_mode="on",  # LS-2: «Jetzt erreichbar» видна всегда
    label="Salon Schöngut",
    business_type="friseur",  # S6: реальный архетип
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_termin",
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="friseur",
    # Фидбэк 2026-07-30: первый экран «ловит направления» — слайдер (3 слайда) +
    # плитки hero_widget="friseur" (Termin/Aktionen/Pflege/Gutschein).
    hero_widget="friseur",
    heroes=[
        {
            "image_kw": "hair,salon",
            "title": "Salon Schöngut",
            "text": "Schnitt, Farbe und Styling von Profis — mitten in der Altstadt.",
            "button_label": "Termin buchen",
            "button_url": "/termin/",
        },
        {
            "image_kw": "hair,color",
            "title": "Balayage & Farbe",
            "text": "Schonende Farbtechniken mit ausführlicher Beratung vorab.",
            "button_label": "Leistungen ansehen",
            "button_url": "/termin/",
        },
        {
            "image_kw": "hair,products",
            "title": "Pflege für zu Hause",
            "text": "Die Produkte, mit denen wir arbeiten — direkt mitnehmen.",
            "button_label": "Produkte ansehen",
            "button_url": "/sortiment/",
        },
    ],
    enable_finder=True,  # FD-1: демо Finder («Was möchtest du?» → 3 услуги)
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
    # CM-1: блог без модуля событий — «Neuigkeiten» салона (модуль blog
    # recommended у всех типов → активен из коробки).
    blog_posts=[
        (
            "Neu im Team: Willkommen, Lena!",
            "Ab sofort verstärkt Lena unser Farb-Team — jetzt Termin sichern.",
            "Wir freuen uns riesig: Lena bringt acht Jahre Erfahrung in Balayage "
            "und Blondierungen mit.\n\n"
            "Zum Start gibt es bei ihr 10 % auf alle Farbtermine im ersten Monat. "
            "Einfach online buchen und im Kommentar „Lena“ angeben.",
            "hairdresser,portrait",
        ),
        (
            "Herbst-Pflege: so übersteht Ihr Haar die kalte Jahreszeit",
            "Drei Profi-Tipps gegen trockene Spitzen und statische Haare.",
            "Heizungsluft und Mützen strapazieren das Haar.\n\n"
            "1. Einmal pro Woche eine Feuchtigkeitsmaske.\n"
            "2. Hitzeschutz auch beim Föhnen.\n"
            "3. Spitzen alle acht Wochen nachschneiden lassen.\n\n"
            "Alle Produkte aus dem Beitrag gibt es bei uns im Salon.",
            "autumn,hair",
        ),
    ],
    enable_modules=["booking", "loyalty", "orders", "customer_account", "promotions"],
    # P6 «ценовой слой»: демо «счастливых часов» — акция на УСЛУГУ с окном
    # Mo–Mi 10–14 (промо-цена сама применяется в штатной записи + подсветка
    # действующих времён на сетке) + обычная товарная акция каталога.
    promotions_spec=[
        {
            "title": "Happy Hours: Herrenschnitt für 20 €",
            "desc": "Montag bis Mittwoch zwischen 10 und 14 Uhr — einfach freie "
            "Zeit wählen, der Preis gilt automatisch.",
            "service": 1,  # Haarschnitt Herren (25 €)
            "new_price": "20",
            "compare_at": "25",
            "rules": {"weekdays": [0, 1, 2], "hour_from": 10, "hour_to": 14},
            "limit": 20,
            "new": True,
            "image": "man,haircut",
        },
        {
            "title": "Pflege-Woche: 20 % auf Haarpflege",
            "desc": "Unsere Lieblingsprodukte für zu Hause — nur diese Woche.",
            "product": 0,
            "percent": 20,
            "group": "Produkte",
            "image": "hair,products",
        },
        {
            # P6: второй ценовой слой — «тихий» день недели (салон открыт Di–Sa,
            # поэтому weekday 1 = Dienstag). Стиль festpreis: цена-якорь без %.
            "title": "Farb-Dienstag: Färben zum Festpreis 55 €",
            "desc": "Jeden Dienstag von 9 bis 14 Uhr — der Aktionspreis wird bei "
            "der Terminbuchung automatisch angewendet.",
            "service": 3,  # Färben (69 €)
            "new_price": "55",
            "compare_at": "69",
            "rules": {"weekdays": [1], "hour_from": 9, "hour_to": 14},
            "discount_style": "festpreis",
            "limit": 15,
            "group": "Salon-Aktionen",
            "image": "hair,color",
        },
        {
            # Сезонная акция без правил времени — действует на любой слот, но
            # ограничена сроком (30 дней) и контингентом.
            "title": "Balayage-Wochen: Strähnen für 79 € statt 89 €",
            "desc": "Natürliche Highlights zum Aktionspreis — Farbberatung "
            "vorab auch per Video möglich.",
            "service": 4,  # Strähnen / Highlights (89 €)
            "new_price": "79",
            "compare_at": "89",
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 30,
            "limit": 10,
            "new": True,
            "group": "Saison-Aktionen",
            "images": ["hair,highlights", "hair,color", "hairstyle"],
        },
        {
            "title": "Haaröl-Aktion: −25 % — nur 12 Stück",
            "desc": "Pflege für die Spitzen — solange der Vorrat reicht.",
            "product": 2,  # Haaröl 50 ml (16,90 €)
            "type": "reservation",
            "percent": 25,
            "available_quantity": 12,
            "group": "Produkte",
            "images": ["hair,oil", "hair,products"],
        },
        {
            # Свободная акция (без цели) — чекаут штатным заказом; стиль mystery
            # прячет цену до клика-раскрытия.
            "title": "Mystery-Beautybag: 19 € statt 35 €",
            "desc": "Drei Pflegeprodukte im Wert von 35 € — welche, verraten wir erst im Salon.",
            "new_price": "19",
            "compare_at": "35",
            "discount_style": "mystery",
            "limit": 8,
            "ends_in_days": 21,
            "new": True,
            "group": "Produkte",
            "image": "hair,products",
        },
    ],
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
            # L3d: i18n-дикт → база de + EN-оверлей (демо «по нескольку на фичу»)
            {"de": "Haarschnitt Damen", "en": "Women's haircut"},
            45,
            "39",
            {
                "de": "Waschen, Schnitt und Föhnen — individuell auf Sie abgestimmt.",
                "en": "Wash, cut and blow-dry — tailored to you.",
            },
            "woman,haircut",
        ),
        (
            {"de": "Haarschnitt Herren", "en": "Men's haircut"},
            30,
            "25",
            {
                "de": "Klassischer oder moderner Schnitt inkl. Waschen.",
                "en": "Classic or modern cut incl. wash.",
            },
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
            {"is_video": True},  # LS-1: Farbberatung per Video
        ),
        ("Bart trimmen", 15, "12", "Konturen schneiden und in Form bringen.", "beard,barber"),
    ],
    # UB3-2: подборки услуг → чипы-фасет на /termin/ (индексы — позиции в services выше).
    collections=[
        ("Damen", {"services": [0, 2, 3, 4]}),
        ("Herren", {"services": [1, 5]}),
        ("Färben & Pflege", {"services": [2, 3, 4]}),
    ],
    service_reviews=[
        (
            0,
            5,
            "Sabine K.",
            "sabine.k@example.de",
            "Toller Schnitt, genau wie besprochen. Komme wieder!",
        ),
        (0, 4, "Nadine R.", "nadine.r@example.de", "Sehr freundlich und professionell."),
        (1, 5, "Thomas B.", "thomas.b@example.de", "Schnell, unkompliziert, top Ergebnis."),
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
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
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
    promotions_spec=[
        {
            # P6 «ценовой слой»: разгружаем утро будней — промо-цена сама
            # применяется в штатной записи (Mo–Do, 8–12; мастерская Mo–Fr 8–17).
            "title": "Werkstatt-Vormittag: Ölwechsel für 39 €",
            "desc": "Montag bis Donnerstag zwischen 8 und 12 Uhr — freie Zeit "
            "wählen, der Aktionspreis gilt automatisch.",
            "service": 0,  # Ölwechsel (49 €)
            "new_price": "39",
            "compare_at": "49",
            "rules": {"weekdays": [0, 1, 2, 3], "hour_from": 8, "hour_to": 12},
            "limit": 30,
            "new": True,
            "group": "Wochen-Aktionen",
            "image": "motor,oil",
        },
        {
            # Сезон переобувки: Festpreis-стиль (цена-якорь без процентов).
            "title": "Reifenwechsel-Wochen: Festpreis 29 €",
            "desc": "Räder umstecken, wuchten auf Wunsch, Reifendruck prüfen — "
            "zum Aktionspreis während der Wechselsaison.",
            "service": 2,  # Reifenwechsel (39 €)
            "new_price": "29",
            "compare_at": "39",
            "discount_style": "festpreis",
            "limit": 40,
            "ends_in_days": 30,
            "group": "Saison-Aktionen",
            "images": ["tire,change", "car,workshop"],
        },
        {
            "title": "HU/AU-Aktionswoche: 79 € statt 89 €",
            "desc": "Hauptuntersuchung & Abgasuntersuchung direkt vor Ort — "
            "nur in dieser Woche zum Aktionspreis.",
            "service": 3,  # HU/AU (TÜV) (89 €)
            "new_price": "79",
            "compare_at": "89",
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 7,
            "limit": 15,
            "new": True,
            "group": "Wochen-Aktionen",
            "image": "car,inspection",
        },
        {
            "title": "Bremsbeläge vorne −20 %",
            "desc": "Markenqualität — Einbau auf Wunsch im gleichen Termin.",
            "product": 2,  # Bremsbeläge vorne (44,90 €)
            "percent": 20,
            "group": "Teile-Angebote",
            "image": "brake,pad",
        },
        {
            "title": "Motoröl 5W-30 zum Festpreis 29,90 €",
            "desc": "Vollsynthetisch, 5-Liter-Kanister — Dauertiefpreis.",
            "product": 0,  # Motoröl 5W-30 5 L (39,90 €)
            "new_price": "29.90",
            "compare_at": "39.90",
            "discount_style": "strikethrough",
            "group": "Teile-Angebote",
            "image": "motor,oil",
        },
        {
            "title": "Winter-Vorrat: Scheibenfrostschutz −25 % — nur 20 Stück",
            "desc": "Bis −20 °C. Online sichern, im Betrieb abholen.",
            "product": 4,  # Scheibenfrostschutz 3 L (8,90 €)
            "type": "reservation",
            "percent": 25,
            "available_quantity": 20,
            "group": "Saison-Aktionen",
            "image": "antifreeze",
        },
    ],
    key="werkstatt",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "products": {"preset": "cols3"}},
    whatsapp_number="+49 170 2000002",  # LS-1: видео-смета
    label="KFZ-Werkstatt Dreyer",
    # FB-3 Вариант B демо: свой промежуточный статус «Teile bestellt» (держит слот занятым).
    status_defs={
        "booking": [
            {
                "code": "teile_bestellt",
                "label": "Teile bestellt",
                "role": "active",
                "stage": "in_progress",
                "blocks_capacity": True,
            }
        ]
    },
    status_edges={
        "booking": [
            {"src": "confirmed", "dst": "teile_bestellt"},
            {"src": "teile_bestellt", "dst": "fulfilled"},
        ]
    },
    business_type="werkstatt",  # S6: реальный архетип
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_werkstatt",
    look="klar",
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="werkstatt",
    # 2026-07-30: слайдер + плитки hero_widget="werkstatt"
    # (Termin/Kostenvoranschlag/Teile/Aktionen).
    hero_widget="werkstatt",
    heroes=[
        {
            "image_kw": "car,workshop",
            "title": "KFZ-Werkstatt Dreyer",
            "text": "Inspektion, HU-Vorbereitung und Reparatur — Meisterbetrieb seit 1994.",
            "button_label": "Termin vereinbaren",
            "button_url": "/termin/",
        },
        {
            "image_kw": "car,repair",
            "title": "Festpreis statt Überraschung",
            "text": "Schaden beschreiben, Fotos hochladen — Kostenvoranschlag per E-Mail.",
            "button_label": "Kostenvoranschlag",
            "button_url": "/anfrage/",
        },
        {
            "image_kw": "tire,wheel",
            "title": "Reifenwechsel & Einlagerung",
            "text": "Räder wechseln, prüfen und trocken einlagern — alles aus einer Hand.",
            "button_label": "Teile & Zubehör",
            "button_url": "/sortiment/",
        },
    ],
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
    enable_modules=["booking", "jobs", "orders", "customer_account", "promotions"],
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
        (
            "Inspektion",
            120,
            "149",
            "Inspektion nach Herstellervorgabe inkl. Fehlerauslese.",
            "car,inspection",
            {
                # UA4-3 демо-A9: богатая карточка + primary-CTA «Kostenvoranschlag»
                # (request) — цена зависит от Modell, поэтому сперва Angebot mit
                # Fahrzeugangabe (Kennzeichen/HSN/TSN).
                "attributes": [
                    "Nach Herstellervorgabe — Garantie bleibt erhalten",
                    "Inkl. Fehlerspeicher auslesen",
                    "Original- oder Identteile nach Wahl",
                    "Festpreis 149 € für gängige Modelle",
                ],
                "faq": [
                    {
                        "q": "Verliere ich die Herstellergarantie?",
                        "a": "Nein — wir arbeiten nach Herstellervorgabe und "
                        "dokumentieren alle Arbeiten im Serviceheft.",
                    },
                    {
                        "q": "Was kostet die Inspektion für mein Modell?",
                        "a": "149 € gilt für gängige Modelle. Fordern Sie mit "
                        "Fahrzeugangabe (Kennzeichen oder HSN/TSN) ein "
                        "unverbindliches Angebot an.",
                    },
                ],
                "primary_action": "request",
            },
        ),
        ("Reifenwechsel", 45, "39", "Räder umstecken, Wuchten auf Wunsch, Reifendruck prüfen."),
        ("HU/AU (TÜV)", 60, "89", "Hauptuntersuchung & Abgasuntersuchung direkt vor Ort."),
        ("Bremsen-Check", 30, "0", "Kostenloser Sicherheits-Check von Belägen und Scheiben."),
        # DL-11: шестая услуга — 6 = три полных ряда по 2 (services cols2)
        (
            "Klimaservice",
            60,
            "119",
            "Kältemittel auffüllen, Dichtheit prüfen, Verdampfer desinfizieren.",
        ),
    ],
    # UA4-4b демо-A9: отзывы об услугах (generic reviews.Review) — индексы в services.
    service_reviews=[
        (
            1,
            5,
            "Markus V.",
            "markus.v@example.de",
            "Inspektion zum Festpreis, alles sauber dokumentiert — läuft wie neu.",
        ),
        (1, 4, "Julia H.", "julia.h@example.de", "Termin schnell bekommen, faire Beratung."),
        (
            3,
            5,
            "Deniz A.",
            "deniz.a@example.de",
            "HU/AU direkt vor Ort und ohne Wartezeit bestanden. Danke!",
        ),
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
                # DL-11: шестой товар — 6 = два полных ряда по 3 (products cols3)
                _p("Innenraumfilter Pollen", "14.90", "Frische Luft im Innenraum.", "air,filter"),
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
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Referenzen", "type": "page", "target": "gallery"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
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
    promotions_spec=[
        {
            # Контингент сезона: chip «reservieren» + счётчик остатка; цель —
            # услуга, поэтому CTA ведёт в штатную запись (заказов у кита нет).
            "title": "Frühjahrs-Aktion: Zimmer streichen zum Festpreis 249 €",
            "desc": "Bis 20 m², inkl. Abkleben und zweifachem Anstrich — nur "
            "10 Termine im Aktionszeitraum.",
            "service": 1,  # Maler: Zimmer streichen (bis 20 m²) — 290 €
            "new_price": "249",
            "compare_at": "290",
            "type": "reservation",
            "available_quantity": 10,
            "discount_style": "festpreis",
            "ends_in_days": 45,
            "group": "Saison-Aktionen",
            "images": ["painting,room", "painter,wall"],
        },
        {
            # P6 «ценовой слой»: окно будних утренних часов (бригада Mo–Fr 7–17).
            "title": "Werktags-Bonus: −20 % auf Steckdosen & Schalter",
            "desc": "Montag bis Donnerstag zwischen 7 und 12 Uhr — der "
            "Aktionspreis wird beim Termin automatisch angewendet.",
            "service": 2,  # Elektro: Steckdose/Schalter setzen (75 €)
            "percent": 20,
            "compare_at": "75",  # без базовой цены процент не даёт промо-цены
            "rules": {"weekdays": [0, 1, 2, 3], "hour_from": 7, "hour_to": 12},
            "discount_style": "badge",
            "limit": 25,
            "new": True,
            "group": "Wochen-Aktionen",
            "image": "electrician,work",
        },
        {
            "title": "Bad-Wochen: Armatur tauschen ab 99 €",
            "desc": "Alte Armatur demontieren, neue montieren, Dichtheit prüfen "
            "— Material nach Aufwand.",
            "service": 3,  # Sanitär: Armatur tauschen (120 €)
            "new_price": "99",
            "compare_at": "120",
            "discount_style": "ab",
            "limit": 15,
            "ends_in_days": 30,
            "group": "Bad & Sanitär",
            "images": ["bathroom,renovation", "tiles,bathroom"],
        },
        {
            "title": "Aktionswoche: Notdienst-Anfahrt 45 € statt 89 €",
            "desc": "Rohrbruch oder Stromausfall? In dieser Woche zum halben Anfahrtspreis.",
            "service": 4,  # Notdienst-Einsatz (Anfahrt) (89 €)
            "new_price": "45",
            "compare_at": "89",
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 7,
            "limit": 20,
            "new": True,
            "group": "Wochen-Aktionen",
            "image": "handyman,tools",
        },
    ],
    key="handwerker",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "promotions": {"preset": "cols2"}},
    label="Meisterbetrieb Krause",
    business_type="handwerker",  # S6: реальный архетип
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_referenz",
    look="warm",  # DS-9: своя «кожа» семейства
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="handwerker",
    # 2026-07-30: слайдер + плитки hero_widget="handwerker"
    # (Angebot/Termin/Rückruf/Aktionen).
    hero_widget="handwerker",
    heroes=[
        {
            "image_kw": "craftsman,renovation",
            "title": "Meisterbetrieb Krause",
            "text": "Maler, Elektro & Sanitär aus einer Hand — Festpreis-Garantie.",
            "button_label": "Angebot anfordern",
            "button_url": "/anfrage/",
        },
        {
            "image_kw": "bathroom,renovation",
            "title": "Bad-Sanierung schlüsselfertig",
            "text": "Von der Planung bis zur letzten Fuge — ein Ansprechpartner.",
            "button_label": "Vorhaben schildern",
            "button_url": "/anfrage/",
        },
        {
            "image_kw": "electrician,work",
            "title": "24h-Notdienst",
            "text": "Wasserrohrbruch oder Stromausfall? Wir sind erreichbar.",
            "button_label": "Rückruf anfordern",
            "button_url": "/rueckruf/",
        },
    ],
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
    enable_modules=["jobs", "booking", "customer_account", "promotions"],
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
        # DL-11: шестая услуга — 6 = три полных ряда по 2 (services cols2)
        (
            "Kleinreparaturen",
            60,
            "65",
            "Tropfender Hahn, klemmende Tür, lose Fliese — schnell erledigt, Festpreis je Stunde.",
        ),
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

CATERING_MENUS = {
    "top": {
        "style": "classic",  # DS-4b: «лого | меню | иконки» одной строкой (макет)
        "sticky": True,
        "items": [
            {"label": "Anfrage", "type": "archetype", "target": "jobs"},
            # MEN-15 → MEN-20 (фидбэк владельца «в меню два пункта — оставить
            # только выпадающий с картинками»): «Speisekarte» раскрывает подменю
            # направлений С ФОТО (дети собираются из живых категорий), а наборы
            # меню (MEN-13) переехали РУЧНЫМ первым ребёнком того же подменю —
            # отдельный пункт «Menüs» из строки шапки убран как дубль.
            {
                # Фидбэк 2026-08-26: пункт «Menüs & Pakete» убран — наборы стоят
                # плитками с фото В ТОМ ЖЕ подменю, рядом с категориями.
                "label": "Speisekarte",
                "type": "categories",
                "target": "",
                "with_combos": True,
            },
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Unser Team", "type": "page", "target": "team"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Anfrage", "type": "archetype", "target": "jobs", "icon": "📋"},
            {"label": "Speisekarte", "type": "archetype", "target": "catalog", "icon": "🥗"},
            {"label": "Kontakt", "type": "page", "target": "contact", "icon": "📞"},
        ],
    },
}

# GK-1 Catering: кейтеринг как ОСНОВНОЙ бизнес (референс-анализ goodkarma-catering.de,
# docs/goodkarma-catering-gap-analysis-2026-08-11.md). Ядро = jobs (Event-Anfrage с
# полями AF-1 → Angebot); Speisekarte browse-only (catalog core, orders выключен
# пресетом типа); вегетарианский профиль — диет-метки и Bio-USP видны сразу.
CATERING = DemoKit(
    promotions_spec=[
        {
            "title": "Frühbucher-Rabatt: −10 % auf Buffets",
            "desc": "Bei Buchung mindestens 8 Wochen im Voraus — gilt für alle Buffet-Pakete.",
            "product": 0,  # Buffet Vegetarisch (24 € p. P.)
            "percent": 10,
            "compare_at": "24.00",
            "discount_style": "badge",
            "limit": 20,
            "new": True,
            "group": "Frühbucher",
            "image": "buffet,catering",
        },
        {
            "title": "Saison-Aktion: Suppenstation 4,50 € statt 5,50 €",
            "desc": "Saisonale Suppe im Glas mit Brot — perfekt für Herbst-Veranstaltungen.",
            "product": 2,  # Suppenstation (5,50 € p. P.)
            "new_price": "4.50",
            "compare_at": "5.50",
            "discount_style": "strikethrough",
            "ends_in_days": 30,
            "group": "Saison-Aktionen",
            "image": "minestrone,soup",
        },
        {
            "title": "Probier-Paket: Fingerfood für 10 Personen zum Festpreis 79 €",
            "desc": "Fingerfood-Platte Klassik für 10 Gäste — einmal probieren, "
            "dann fürs große Event buchen.",
            "product": 3,  # Fingerfood-Platte Klassik (8,50 € p. P.)
            "new_price": "79",
            "compare_at": "85",
            "discount_style": "festpreis",
            "limit": 10,
            "group": "Probier-Pakete",
            "images": ["antipasti", "caprese,salad"],
        },
        {
            "title": "Letzte Grill-Termine der Saison: −15 % aufs Grillbuffet",
            "desc": "BBQ mit Beilagen, vor Ort zubereitet — nur noch wenige Termine frei.",
            "product": 1,  # Grillbuffet (28 € p. P.)
            "percent": 15,
            "compare_at": "28.00",
            "discount_style": "countdown",
            "countdown": True,
            "ends_in_days": 14,
            "limit": 8,
            "group": "Saison-Aktionen",
            "image": "bbq,grill",
        },
    ],
    key="catering",
    # SH-24 (Р-6): кейтеринг живёт на заявках — доставка включена, чтобы в форме
    # /anfrage/ стоял вопрос «привезём или заберёте сами».
    delivery={
        "enabled": True,
        "fee_cents": 0,
        "free_cents": 0,
        "min_cents": 0,
        "area": "Wir liefern im Umkreis von 30 km um Köln.",
    },
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={
        "gallery": {"preset": "cols3"},
        "promotions": {"preset": "cols2"},
        "categories": {"preset": "cols4", "tablet": 2},
    },
    label="Grüne Tafel Catering",
    business_type="catering",
    subdomain="catering",
    # DS-4: плитки hero убраны — их работу несут CTA шапки + форма на главной
    # (мокап Fokus); сплит-hero рисует строку доверия и primary-CTA сам.
    hero_widget="",
    heroes=[
        {
            "image_kw": "catering,buffet",
            "title": "Grüne Tafel Catering",
            "text": "Frisch gekocht, liebevoll angerichtet — Catering für Feiern, Büro und Events.",
            "button_label": "Angebot anfordern",
            "button_url": "/anfrage/",
        },
        {
            "image_kw": "vegan,cake",
            "title": "Hochzeits-Catering",
            "text": "Vom Sektempfang bis zum Mitternachtssnack — wir begleiten Ihren großen Tag.",
            "button_label": "Termin anfragen",
            "button_url": "/anfrage/",
        },
        {
            "image_kw": "antipasti",
            "title": "Fingerfood fürs Büro",
            "text": "Platten und Buffets für Meetings und Firmenfeiern — geliefert und aufgebaut.",
            "button_label": "Speisekarte ansehen",
            "button_url": "/sortiment/",
        },
    ],
    accent="#15803d",  # frisch/bio-грин (ARCHETYPE_LOOK_ACCENTS)
    hero_image_kw="catering,buffet",
    # DS-4b: заголовок-оффер (не дубль названия из шапки) — как в макете.
    hero_title="Ihr Fest. Unser Buffet.",
    hero_text="Frisch gekocht für Feiern, Büro und Events — Sie erhalten ein "
    "Festpreis-Angebot innerhalb von 24 Stunden.",
    about_title="Über uns",
    about_text="Seit 2012 kochen wir für Feste, Firmen und Familien: frisch, "
    "saisonal und mit Zutaten von Höfen aus der Region. Vom Fingerfood bis zum "
    "Hochzeitsbuffet — Sie feiern, wir kümmern uns um den Rest.",
    nav_style="classic",
    address="Gartenstraße 21, 40479 Düsseldorf",
    city="Düsseldorf",
    opening_hours_text="Mo–Sa 9:00–18:00",
    opening_hours={d: ("09:00", "18:00") for d in range(6)},
    service_area_note="Düsseldorf, Köln und Umgebung — auf Anfrage deutschlandweit",
    # AF-1: событийные поля публичной заявки — витрина архетипа.
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": [
            "Hochzeit",
            "Firmenfeier",
            "Geburtstag",
            "Messe",
            "Privatfeier",
            "Sonstiges",
        ],
    },
    primary_module="jobs",  # страховка: hero-CTA → Anfrage (не каталог)
    # DS-4: пилот сборки «Fokus» (одобренный концепт-макет 2026-08-12) —
    # klar-кожа + split-hero + CTA в шапке + прайс + форма заявки на главной.
    # «Fein» остаётся семейством в галерее Look'ов (выбор владельца сайта).
    look="klar",
    enable_anfrage_section=True,
    config_patch={
        "hero_style": "split",
        "nav": {"cta": True},
        # MEN-20 (фидбэк «не увидел меню кейтерингов в виде меню»): полная
        # Speisekarte — «печатной картой» (центр-заголовки, описание под блюдом);
        # тизер на главной остаётся плоским preisliste из макета Fokus, книга
        # с листанием живёт у ресторана — демо показывают разные виды семейства.
        "catalog_layout": {"preset": "preisliste_karte"},
        "menu_labels": True,  # MEN-24a: маркировка (диеты/аллергены) в прайсе
    },
    # MEN-24c (фидбэк «сколько строк показывать, сейчас 3»): секция-прайс
    # главной — по 3 строки на категорию, дальше «Mehr anzeigen» → /sortiment/.
    section_rows={"products": 3},
    # DS-4b «в точности как макет»: главная = 6 блоков (hero → направления →
    # Speisekarte → шаги → доверие+цифры → форма); остальной контент кита жив
    # на своих страницах (/galerie/ /team/ /bewertungen/ /aktionen/).
    sections_off=[
        "usp_bar",
        "promotions",
        "team",
        "gallery",
        "reviews",
        "faq",
        "testimonials",
        "cta",  # роль CTA несёт anfrage-банда (иначе две зелёные полосы подряд)
        "archetypes",  # «Unsere Bereiche» — дубль путей шапки, в макете нет
        "contact",
    ],
    section_visuals={
        "products": {"background": "#f2f5f0"},
        "trust": {"background": "#f2f5f0"},
    },
    section_titles={
        "categories": "Was wir für Sie kochen",
        "products": "Speisekarte",
        "process": "So funktioniert's",
    },
    enable_categories_section=True,  # GK-15: сетка 6 направлений на главной
    categories=[
        (
            "Buffets & Menüs",
            "buffets",
            [
                _p(
                    "Buffet Vegetarisch",
                    "24.00",
                    "Warmes Buffet mit drei Hauptgerichten, Salaten und Brot — pro Person, ab 20 Personen.",
                    "catering,buffet",
                    diets=["vegetarisch"],
                    badge="beliebt",
                ),
                _p(
                    "Grillbuffet",
                    "28.00",
                    "BBQ mit Gemüse, Halloumi und Saucen, vor Ort zubereitet — pro Person, ab 20 Personen.",
                    "bbq,grill",
                    diets=["vegetarisch"],
                ),
                _p(
                    "Suppenstation",
                    "5.50",
                    "Saisonale Suppe im Glas mit Brot — pro Person, ab 20 Personen.",
                    "minestrone,soup",
                    diets=["vegan"],
                    allergens=["gluten"],
                ),
            ],
            "catering,buffet",  # DS-2: фото плитки (реальный файл, не SVG)
            "Warme Buffets und Menüs für 20 bis 200 Gäste — saisonal, vegetarisch und vor Ort frisch angerichtet. Wir planen Menge, Ablauf und Aufbau gemeinsam mit Ihnen.",
            "kopfbild",  # KAT-1: шаблон страницы — hero-шапка с фото
        ),
        (
            "Fingerfood & Platten",
            "fingerfood",
            [
                _p(
                    "Fingerfood-Platte Klassik",
                    "8.50",
                    "Mini-Quiches, Wraps und Gemüsesticks mit Dips — pro Person, ab 10 Personen.",
                    "antipasti",
                    diets=["vegetarisch"],
                    allergens=["gluten", "milch"],
                    badge="empfehlung",
                ),
                _p(
                    "Wrap-Platte Vegan",
                    "7.50",
                    "Gefüllte Wraps mit Hummus, Gemüse und Kräutern — pro Person, ab 10 Personen.",
                    "salad,bowl",
                    diets=["vegan"],
                    allergens=["gluten", "sesam"],
                ),
                _p(
                    "Dessertauswahl",
                    "6.00",
                    "Mousse, Kuchen und Obst im Glas — pro Person, ab 10 Personen.",
                    "dessert,glass",
                    diets=["vegetarisch"],
                    allergens=["milch", "eier"],
                ),
                # GK-15: тиры пакетов Klassik/Plus/Premium (референс: 3 пакета
                # Fingerfood). НОВЫЕ товары строго ХВОСТОМ категории — индексы
                # promotions_spec (0–3) считают первые позиции первых категорий.
                _p(
                    "Fingerfood-Paket Plus",
                    "11.50",
                    "6 Häppchen p. P., dazu warme Snacks und zwei Dips — "
                    "pro Person, ab 10 Personen.",
                    "caprese,salad",
                    diets=["vegetarisch"],
                    allergens=["gluten", "milch"],
                ),
                _p(
                    "Fingerfood-Paket Premium",
                    "14.50",
                    "8 Häppchen p. P. inkl. Mini-Desserts und Antipasti — "
                    "pro Person, ab 10 Personen.",
                    "antipasti,platter",
                    diets=["vegetarisch"],
                    allergens=["gluten", "milch", "eier"],
                    badge="empfehlung",
                ),
            ],
            "antipasti",  # DS-2: фото плитки (реальный файл, не SVG)
            "Fingerfood-Platten und Häppchen für Empfang, Vernissage oder Stehparty — pro Person kalkuliert, geliefert und hübsch angerichtet.",
        ),
        # GK-15: сетка категорий как у референса (6 направлений-событий) —
        # каждое со своими пакетами «€ p. P. + ab N Personen».
        (
            "Hochzeits-Catering",
            "hochzeit",
            [
                _p(
                    "Hochzeitsbuffet Klassik",
                    "39.00",
                    "Drei Gänge als Buffet, Salatbar und Dessertauswahl — "
                    "pro Person, ab 50 Personen.",
                    "vegan,cake",
                    diets=["vegetarisch"],
                    badge="beliebt",
                ),
                _p(
                    "Hochzeitsbuffet Premium",
                    "49.00",
                    "Fünf Gänge, Live-Station und Mitternachtssnack — pro Person, ab 50 Personen.",
                    "wedding,catering",
                    diets=["vegetarisch"],
                ),
                _p(
                    "Sektempfang & Canapés",
                    "12.00",
                    "Begrüßungssekt, alkoholfreie Alternativen und Canapés — "
                    "pro Person, ab 30 Personen.",
                    "lemonade",
                    diets=["vegetarisch"],
                    allergens=["gluten"],
                ),
                # MEN-6: БЛЮДА (à-la-carte-Preise) — состав фикс/Wahl-Menüs и пул
                # «freie Auswahl». Цены выше, чем im Menü (владелец: «в свободном
                # наборе блюдо дороже»): Carpaccio+Filet+Mousse = 48,00 > 45,00.
                _p(
                    "Rote-Bete-Carpaccio",
                    "12.50",
                    "Dünn gehobelte Bete, Walnusskrokant, Kräuteröl — kalte Vorspeise.",
                    "beet,salad",
                    diets=["vegan"],
                    allergens=["schalenfruechte"],
                ),
                _p(
                    "Ziegenkäse-Tartelette",
                    "13.50",
                    "Blätterteig, Ziegenkäse, karamellisierte Zwiebeln, Thymian.",
                    "tartlet,cheese",
                    diets=["vegetarisch"],
                    allergens=["gluten", "milch"],
                ),
                _p(
                    "Kürbiscremesuppe",
                    "8.50",
                    "Hokkaido, Ingwer, geröstete Kerne — im Glas oder am Tisch serviert.",
                    "minestrone,soup",
                    diets=["vegan"],
                ),
                _p(
                    "Rinderfilet mit Rotweinjus",
                    "26.00",
                    "Rosa gebraten, Rotweinjus, Wintergemüse — vom Hof aus der Region.",
                    "steak,beef",
                ),
                _p(
                    "Skrei auf Fenchelgemüse",
                    "24.00",
                    "Winterkabeljau, Fenchel, Zitrone — leicht und festlich.",
                    "fish,plate",
                    allergens=["fisch"],
                ),
                _p(
                    "Gefüllte Aubergine",
                    "19.50",
                    "Mit Hirse, Tomaten und Kräutern gefüllt, dazu Tahin-Creme.",
                    "eggplant,vegan",
                    diets=["vegan"],
                ),
                _p(
                    "Kartoffelgratin",
                    "6.50",
                    "Sahnegratin mit Bergkäse — klassische Beilage.",
                    "gratin,potato",
                    diets=["vegetarisch"],
                    allergens=["milch"],
                ),
                _p(
                    "Schokoladenmousse",
                    "9.50",
                    "Zartbitter-Mousse mit Sauerkirschen und Minze.",
                    "chocolate,mousse",
                    diets=["vegetarisch"],
                    allergens=["milch", "eier"],
                ),
                _p(
                    "Panna Cotta mit Beeren",
                    "8.50",
                    "Vanille-Panna-Cotta, Beerenragout, Baiserbruch.",
                    "pannacotta,dessert",
                    diets=["vegetarisch"],
                    allergens=["milch"],
                ),
                _p(
                    "Aperitif Hugo",
                    "7.50",
                    "Holunderblüte, Prosecco, Minze — zum Empfang.",
                    "lemonade",
                    diets=["vegetarisch"],
                ),
            ],
            "vegan,cake",  # DS-2: фото плитки (реальный файл, не SVG)
            "Ihr Hochzeitsbuffet ohne Stress: Probeessen, Menüplanung, Sektempfang und Mitternachtssnack — wir begleiten den ganzen Abend.",
            "sets",  # KAT-1: шаблон страницы — Menü-Pakete над сеткой
        ),
        (
            "Business & Seminar",
            "business-seminar",
            [
                _p(
                    "Business-Lunch",
                    "16.50",
                    "Zwei warme Gerichte, Salate und Dessert im Büro serviert — "
                    "pro Person, ab 10 Personen.",
                    "caesar,salad",
                    diets=["vegetarisch"],
                ),
                _p(
                    "Seminar-Tagespauschale",
                    "24.00",
                    "Zwei Kaffeepausen mit Gebäck und Obst plus Mittagsbuffet — "
                    "pro Person, ab 15 Personen.",
                    "coffee,cafe",
                    diets=["vegetarisch"],
                    allergens=["gluten", "milch"],
                ),
            ],
            "coffee,cafe",  # DS-2: фото плитки (реальный файл, не SVG)
            "Business-Lunch, Seminar-Pausen und Konferenz-Catering — pünktlich ins Büro geliefert, inklusive Geschirr und Aufbau.",
        ),
        (
            "Private Feiern & Messe",
            "feiern-messe",
            [
                _p(
                    "Geburtstags-Buffet",
                    "22.00",
                    "Herzhafte Klassiker, Fingerfood und Kuchen nach Wahl — "
                    "pro Person, ab 20 Personen.",
                    "potato,salad",
                    diets=["vegetarisch"],
                    allergens=["gluten"],
                ),
                _p(
                    "Messe-Catering-Paket",
                    "18.00",
                    "Standversorgung ganztägig: Snacks, Getränke und Service — "
                    "pro Person, ab 25 Personen.",
                    "smoothie",
                    diets=["vegetarisch"],
                ),
            ],
            "grill,plate",  # DS-2: фото плитки (реальный файл, не SVG)
            "Geburtstage, Jubiläen und Messen: herzhafte Klassiker und Fingerfood nach Wahl, Standversorgung ganztägig.",
        ),
        (
            "Getränke",
            "getraenke",
            [
                _p(
                    "Getränkepaket",
                    "9.00",
                    "Wasser, Säfte und Kaffee für die ganze Veranstaltung — pro Person, ab 10 Personen.",
                    "orange,juice",
                    diets=["vegan"],
                ),
            ],
            "lemonade",  # DS-2: фото плитки (реальный файл, не SVG)
            "Getränkepakete zur Feier: Wasser, Säfte, Kaffee und mehr — kalkuliert pro Person, geliefert und gekühlt.",
        ),
        # DS-6 (фидбэк «хотя бы 4, лучше 8 плиток»): направления до 8 —
        # сетка «Was wir für Sie kochen» полная при любой раскладке 3–4.
        (
            "Frühstück & Brunch",
            "fruehstueck",
            [
                _p(
                    "Brunch-Buffet",
                    "18.50",
                    "Brötchen, Aufstriche, Obst, Müsli und warme Kleinigkeiten — "
                    "pro Person, ab 10 Personen.",
                    "breakfast,brunch",
                    diets=["vegetarisch"],
                    allergens=["gluten"],
                ),
                _p(
                    "Kaffee & Kuchen",
                    "9.50",
                    "Filterkaffee satt und Kuchenauswahl vom Blech — pro Person.",
                    "coffee,cake",
                    diets=["vegetarisch"],
                    allergens=["gluten"],
                ),
            ],
            "croissant",
            "Brunch-Buffets und Kaffee-Pausen für Vormittags-Events: Brötchen, Aufstriche, Obst und warme Kleinigkeiten.",
        ),
        (
            "Desserts & Süßes",
            "desserts",
            [
                _p(
                    "Dessertbuffet",
                    "12.00",
                    "Mousse, Tiramisu, Obstsalat und Mini-Törtchen — pro Person, ab 15 Personen.",
                    "dessert,tiramisu",
                    diets=["vegetarisch"],
                ),
                _p(
                    "Hochzeitstorte",
                    "180.00",
                    "Dreistöckig nach Absprache — Festpreis inkl. Lieferung und Aufbau.",
                    "cake,wedding",
                    diets=["vegetarisch"],
                    allergens=["gluten"],
                ),
            ],
            "cheesecake",
            "Dessertbuffets, Torten und Süßes vom Blech — vom Mini-Törtchen bis zur mehrstöckigen Hochzeitstorte nach Absprache.",
        ),
    ],
    gallery_kw=[
        "catering,buffet",
        "antipasti",
        "caprese,salad",
        "grill,plate",
        "dessert",
        "salad,bowl",
    ],
    faq=[
        (
            "Wie bekomme ich ein Angebot?",
            "Über «Angebot anfordern» nennen Sie Wunschdatum, Gästezahl und "
            "Anlass — Sie erhalten ein unverbindliches Angebot, meist innerhalb "
            "von 24 Stunden.",
        ),
        (
            "Kocht ihr auch vegan?",
            "Ja — ein Großteil unserer Karte ist vegan oder lässt sich vegan "
            "zubereiten. Allergene kennzeichnen wir zu jedem Gericht.",
        ),
        (
            "Liefert ihr auch außerhalb der Stadt?",
            "Wir sind in Düsseldorf, Köln und Umgebung unterwegs — auf Anfrage "
            "auch deutschlandweit.",
        ),
        (
            "Ab wie vielen Personen liefert ihr?",
            "Fingerfood und Platten ab 10 Personen, Buffets ab 20 Personen.",
        ),
    ],
    testimonials=[
        # GK-15: фото (GK-6) → аватар-ряд в trust как у референса (4.9★ + лица).
        (
            "Familie Sommer",
            "Hochzeitsbuffet für 80 Gäste — alles frisch, pünktlich und wunderschön angerichtet.",
            5,
            demo_image("ayurveda,woman", w=200, h=200, lock=871),
        ),
        (
            "Miriam K.",
            "Fingerfood für unsere Firmenfeier — unkompliziert angefragt, Angebot am nächsten Tag.",
            5,
            demo_image("barista,woman", w=200, h=200, lock=872),
        ),
        (
            "Thomas B.",
            "Seminar-Catering über zwei Tage — heiß geliefert, freundliches Team, faire Preise.",
            5,
            demo_image("cook,man", w=200, h=200, lock=873),
        ),
        # DL-11: четвёртый отзыв — 4 = два полных ряда по 2 (testimonials cols2)
        (
            "Herr Lindner",
            "Firmenevent mit 120 Gästen — Aufbau, Buffet und Abbau liefen wie am Schnürchen.",
            5,
            demo_image("cook,man", w=200, h=200, lock=874),
        ),
    ],
    process=[
        ("Anfrage stellen", "Datum, Gästezahl und Anlass online nennen — unverbindlich."),
        ("Angebot erhalten", "Wir planen Menü und Ablauf und schicken ein Festpreis-Angebot."),
        ("Entspannt feiern", "Wir liefern, bauen auf und kümmern uns um den Rest."),
    ],
    team=[
        ("Lena Berger", "Küchenchefin", "chef,woman"),
        ("Jonas Weber", "Eventleitung", "waiter,man"),
    ],
    trust={"since": "2012", "marks": ["Bio-Zutaten", "Regionale Höfe", "Festpreis-Angebot"]},
    # GK-5: «3 столпа философии» (референс goodkarma) — стиль pillars ниже.
    usp=[
        ("bio", "100 % frisch gekocht", "Alles aus unserer Küche — ohne Fertigprodukte."),
        ("local", "Regionale Zutaten", "Gemüse und Kräuter von Höfen aus der Umgebung."),
        ("quality", "Festpreis-Angebot", "Klarer Preis vor der Zusage — keine Überraschungen."),
    ],
    section_styles={
        "usp_bar": "pillars",
        # MEN-22 (фидбэк «на главной товары списком без картинок — должно быть
        # с картинками в 2 колонки»): фотосписок в 2 колонки вместо плоского.
        "products": "preisliste_foto_2sp",
        "trust": "compact",
        "categories": "compact",  # DS-4b: строки-плитки с «ab €»
        "anfrage": "band",  # DS-4b: слим-форма на акцент-полосе
        "process": "row",
    },
    # GK-15: главная в структуре референса — цифры-полоса после отзывов, цитата
    # основателя (данные пресета «Gründer-Zitat» GK-7) после trust, newsletter в конце.
    home_blocks=[
        {
            "after": "trust",
            "key": "stats",
            "data": {
                "rows": [
                    {"value": "200+", "label": "Events pro Jahr"},
                    {"value": "50.000+", "label": "Gerichte serviert"},
                    {"value": "10.000+", "label": "zufriedene Gäste"},
                    {"value": "seit 2012", "label": "aus Düsseldorf"},
                ]
            },
        },
    ],
    # GK-15: иконки футера — ТОЛЬКО корневые URL (не фиктивные handle: те могли
    # бы указать на чужой реальный аккаунт).
    socials={"instagram": "https://www.instagram.com/", "facebook": "https://www.facebook.com/"},
    # GK-15: демо-кэш Google-строки в trust (референс: 4.9★/40+); фикция демо.
    google_rating={"rating": "4.9", "count": 41},
    reviews_seed=[
        (
            5,
            "Firmenfeier für 40 Personen — großartiges Buffet, alle waren begeistert.",
            "ct.mueller@example.de",
        ),
        (
            5,
            "Anfrage abends gestellt, Angebot am Morgen — so einfach kann Catering sein.",
            "ct.krause@example.de",
        ),
        (
            4,
            "Leckeres veganes Fingerfood, pünktliche Lieferung. Gerne wieder.",
            "ct.lorenz@example.de",
        ),
    ],
    cta={
        "title": "Planen Sie Ihr nächstes Event?",
        "text": "Datum, Gästezahl, Anlass — Sie erhalten ein unverbindliches "
        "Angebot innerhalb von 24 Stunden.",
        "button_label": "Angebot anfordern",
        "button_url": "/anfrage/",
    },
    # Явный список для apply_kit (снимает из disabled; тип-пресет — на сидинге).
    enable_modules=[
        "jobs",
        # MEN-11 (уточнение владельца «корзина не обязательна, можно просто
        # запрос»): кейтеринг остаётся browse-only — гость собирает набор и
        # отправляет заявку. Режим `quote_cart` (корзина-просчёт) существует в
        # коде как ОПЦИЯ для тех, кому корзина нужна, но демо на нём не висит.
        "promotions",
        "crm",
        "inbox",
        "reviews",
        "gift",
        "blog",
        "customer_account",
    ],
    enable_archetypes_section=True,
    storefront_root="home",
    seed_records=True,
    menus=CATERING_MENUS,
    page_presets=[("info", "team")],  # ST-2: «Über uns» с командой
    # MEN-6: типы подачи блюдам свадебного направления — питают «свободную
    # сборку» (группы по Gang'ам) и группировку PDF-Speisekarte.
    product_courses={
        "Rote-Bete-Carpaccio": "vorspeise",
        "Ziegenkäse-Tartelette": "vorspeise",
        "Kürbiscremesuppe": "suppe",
        "Rinderfilet mit Rotweinjus": "hauptgang",
        "Skrei auf Fenchelgemüse": "hauptgang",
        "Gefüllte Aubergine": "hauptgang",
        "Kartoffelgratin": "beilage",
        "Schokoladenmousse": "dessert",
        "Panna Cotta mit Beeren": "dessert",
        "Aperitif Hugo": "getraenk",
    },
    # MEN-6: три режима набора меню на одном направлении «Hochzeits-Catering».
    combos=[
        {
            "name": {"de": "Hochzeitsmenü Klassik", "en": "Wedding menu Classic"},
            "description": {
                "de": "Drei Gänge, fest zusammengestellt — Vorspeise, Hauptgang "
                "und Dessert. Service und Aufbau inklusive.",
                "en": "Three fixed courses — starter, main and dessert. Service included.",
            },
            "price": "45.00",
            "per_person": True,
            "min_persons": 20,
            "category": "hochzeit",
            "event_types": ["Hochzeit"],
            "photos": ["wedding,catering", "steak,beef"],
            "groups": [
                {
                    "label": "Vorspeise",
                    "included": True,
                    "products": ["Rote-Bete-Carpaccio"],
                },
                {
                    "label": "Hauptgang",
                    "included": True,
                    "products": ["Rinderfilet mit Rotweinjus"],
                },
                {"label": "Dessert", "included": True, "products": ["Schokoladenmousse"]},
            ],
        },
        {
            "name": {"de": "Hochzeitsmenü Wahl", "en": "Wedding menu Choice"},
            "description": {
                "de": "Sie stellen das Menü zusammen: je ein Gericht pro Gang, "
                "Extras optional. Preis passt sich Ihrer Auswahl an.",
                "en": "You compose the menu: one dish per course, extras optional.",
            },
            "price": "52.00",
            "per_person": True,
            "min_persons": 20,
            "category": "hochzeit",
            "event_types": ["Hochzeit", "Privatfeier"],
            "photos": ["vegan,cake", "tartlet,cheese"],
            "groups": [
                {
                    "label": "Vorspeise",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Rote-Bete-Carpaccio",
                        ("Ziegenkäse-Tartelette", "2.00"),
                        "Kürbiscremesuppe",
                    ],
                },
                {
                    "label": "Hauptgang",
                    "min": 1,
                    "max": 1,
                    "products": [
                        "Gefüllte Aubergine",
                        ("Skrei auf Fenchelgemüse", "4.00"),
                        ("Rinderfilet mit Rotweinjus", "6.00"),
                    ],
                },
                {
                    "label": "Dessert",
                    "min": 1,
                    "max": 1,
                    "products": ["Panna Cotta mit Beeren", ("Schokoladenmousse", "1.50")],
                },
                {
                    "label": "Extras",
                    "min": 0,
                    "max": 2,
                    "products": [("Kartoffelgratin", "3.50"), ("Aperitif Hugo", "5.00")],
                },
            ],
        },
        {
            "name": {"de": "Freie Auswahl Hochzeit", "en": "Free choice wedding"},
            "description": {
                "de": "Stellen Sie Ihr Menü frei zusammen — alle Gerichte des "
                "Bereichs, nach Gängen sortiert. Preise à la carte.",
                "en": "Compose your menu freely — all dishes of the area, by course.",
            },
            "price": "0.00",
            "per_person": True,
            "min_persons": 20,
            "free_pool": True,
            "category": "hochzeit",
            "event_types": ["Hochzeit", "Privatfeier", "Firmenfeier"],
            "photos": ["antipasti"],
        },
    ],
    # MEN-21: отзывы на наборы (kind="combo") — секция отзывов видна в демо.
    # Тексты реальных клиентов не переводим (правило DL-волны) — остаются DE.
    combo_reviews=[
        (
            0,
            5,
            "Familie Berger",
            "berger@example.de",
            "Das Klassik-Menü war der Höhepunkt unserer Hochzeit — jeder Gang auf den Punkt, der Service unsichtbar gut.",
        ),
        (
            0,
            5,
            "Jana & Tom",
            "jana.tom@example.de",
            "Aufbau, Ablauf, Geschmack — alles wie besprochen. Unsere Gäste reden heute noch vom Rinderfilet.",
        ),
        (
            0,
            4,
            "K. Albers",
            "albers@example.de",
            "Sehr professionell organisiert. Ein Stern Abzug nur, weil das Dessert etwas spät kam.",
        ),
        (
            1,
            5,
            "Sophie L.",
            "sophie.l@example.de",
            "Toll, dass jeder Gang wählbar war — so hatten auch die Vegetarier unter den Gästen ein volles Menü.",
        ),
        (
            1,
            5,
            "M. und C. Winter",
            "winter@example.de",
            "Die Beratung bei der Zusammenstellung war Gold wert. Preis-Leistung stimmt absolut.",
        ),
        (
            1,
            4,
            "R. Neumann",
            "neumann@example.de",
            "Sehr flexibel bei Sonderwünschen, das Tartelette ein Traum. Gerne wieder.",
        ),
        (
            2,
            5,
            "Buchhaltung Feldmann GmbH",
            "feldmann@example.de",
            "Für unsere Firmenfeier frei zusammengestellt — die Gäste konnten nach Gängen wählen, Abrechnung transparent.",
        ),
        (
            2,
            5,
            "Lisa Q.",
            "lisa.q@example.de",
            "Freie Auswahl klingt kompliziert, war aber kinderleicht. Alles frisch, alles pünktlich.",
        ),
        (
            2,
            4,
            "H. Brandt",
            "brandt@example.de",
            "Große Auswahl, faire Preise à la carte. Die Antipasti waren das Highlight.",
        ),
    ],
    job_samples=[
        {
            "title": "Catering Hochzeit (80 Personen)",
            "name": "Anna Sommer",
            "email": "sommer@example.de",
            "phone": "0211 5551234",
            "description": "Sektempfang, warmes Buffet und Dessertbar für 80 "
            "Gäste, Scheune in Ratingen. Bitte vegetarisch mit veganen Optionen.",
            "lines": [
                {
                    "text": "Buffet Vegetarisch (80 P.)",
                    "qty": 80,
                    "unit_price": "24.00",
                    "product_name": "Buffet Vegetarisch",
                },
                {
                    "text": "Dessertauswahl (80 P.)",
                    "qty": 80,
                    "unit_price": "6.00",
                    "product_name": "Dessertauswahl",
                },
                {"text": "Personal & Aufbau (Pauschale)", "qty": 1, "unit_price": "480.00"},
            ],
            "vat_rate": 19,
        },
        {
            "title": "Fingerfood Firmenfeier (25 Personen)",
            "name": "Miriam Klein",
            "email": "klein@example.de",
            "description": "Sommerfest im Büro, Fingerfood und Getränke für 25 "
            "Personen, Lieferung bis 17 Uhr.",
            "lines": [
                {
                    "text": "Fingerfood-Platte Klassik (25 P.)",
                    "qty": 25,
                    "unit_price": "8.50",
                    "product_name": "Fingerfood-Platte Klassik",
                },
                {
                    "text": "Getränkepaket (25 P.)",
                    "qty": 25,
                    "unit_price": "9.00",
                    "product_name": "Getränkepaket",
                },
                {"text": "Lieferung & Abholung", "qty": 1, "unit_price": "60.00"},
            ],
            "vat_rate": 19,
        },
    ],
    archetype_covers={
        "jobs": {
            "intro": "Nennen Sie Wunschdatum, Gästezahl und Anlass — Sie erhalten "
            "ein unverbindliches Angebot.",
            "hero_kw": "catering,buffet",
            "gallery_kw": ["fingerfood,platter", "wedding,catering", "buffet,vegetarian"],
        },
        "catalog": {
            "intro": "Unsere Speisekarte: Buffets, Fingerfood und Getränke — "
            "alles pro Person kalkuliert.",
            "hero_kw": "catering,buffet",  # DS-2: реальный файл (не SVG)
        },
    },
)

RETREAT_MENUS = {
    "top": {
        "style": "centered",
        "sticky": True,
        "items": [
            {"label": "Events", "type": "archetype", "target": "events"},
            # Аудит 2026-08-06: у ретрита есть НОЧЁВКА (8 мест в общей комнате,
            # Doppel-/Einzelzimmer) и заявки, но ни того ни другого не было в меню —
            # гость не мог дойти до размещения иначе как из карточки события.
            {"label": "Unterkunft", "type": "archetype", "target": "stays"},
            {"label": "Lehrer", "type": "url", "target": "/lehrer/"},  # R3
            {"label": "Einzelsitzung", "type": "archetype", "target": "booking"},
            {"label": "Anfrage", "type": "archetype", "target": "jobs"},
            {"label": "Blog", "type": "url", "target": "/blog/"},  # RT4
            {"label": "Shop", "type": "archetype", "target": "catalog"},
            # Аудит 2026-08-06 (фидбэк владельца «не везде есть акции»): акции
            # у кита засеяны, но пути к ним из меню не было.
            {"label": "Angebote", "type": "archetype", "target": "promotions"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Über uns", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Events", "type": "archetype", "target": "events", "icon": "🎫"},
            {"label": "Unterkunft", "type": "archetype", "target": "stays", "icon": "🛏"},
            {"label": "Sitzung", "type": "archetype", "target": "booking", "icon": "🧘"},
            {"label": "Shop", "type": "archetype", "target": "catalog", "icon": "🛍"},
        ],
    },
}

RETREAT = DemoKit(
    promotions_spec=[
        {
            # Ценовой слой на НОЧЁВКУ + окно проживания (проверяется дата заезда).
            "title": "Frühbucher Herbst: Doppelzimmer −15 %",
            "desc": "Wer sein Zimmer für die Herbst-Retreats (1. September bis "
            "30. November) jetzt bucht, zahlt 59,50 € statt 70 € pro Nacht.",
            "stay_unit": 1,
            "percent": 15,
            "compare_at": "70",
            "discount_style": "percent",
            "rules": {"stay_from": "2026-09-01", "stay_to": "2026-11-30"},
            "limit": 8,
            "group": "Übernachtung",
            "ends_in_days": 60,
            "images": ["forest,retreat", "lake,forest"],
        },
        {
            "title": "Last-Minute: Einzelzimmer −20 %",
            "desc": "Spontan ausklinken: das letzte Einzelzimmer für 76 € statt 95 € "
            "pro Nacht — nur wenige Tage buchbar.",
            "stay_unit": 2,
            "percent": 20,
            "compare_at": "95",
            "discount_style": "countdown",
            "countdown": True,
            "new": True,
            "limit": 3,
            "group": "Übernachtung",
            "ends_in_days": 4,
            "images": ["forest,path", "campfire,night"],
        },
        {
            # «Свободная» акция-пакет с фикс-ценой (89 € Workshop + 18 € Mittagessen).
            "title": "Tagesworkshop-Paket: Workshop + Bio-Mittagessen",
            "desc": "Yoga & Achtsamkeit den ganzen Tag, dazu das warme Bio-Mittagessen "
            "aus unserer Küche — 99 € statt 107 €.",
            "new_price": "99",
            "compare_at": "107",
            "discount_style": "festpreis",
            "limit": 12,
            "group": "Kurse & Workshops",
            "ends_in_days": 45,
            "images": ["yoga,nature", "meditation", "tea,ceremony"],
        },
        {
            "title": "Vormittags-Special: Einzel-Yogastunde 44 €",
            "desc": "Montag bis Freitag zwischen 10 und 13 Uhr: die 1:1-Stunde bei Mara "
            "für 44 € statt 55 € — freie Zeit wählen, der Preis gilt automatisch.",
            "service": 0,
            "new_price": "44",
            "compare_at": "55",
            "discount_style": "strikethrough",
            "rules": {"weekdays": [0, 1, 2, 3, 4], "hour_from": 10, "hour_to": 13},
            "limit": 20,
            "group": "Einzeltermine",
            "ends_in_days": 45,
            "images": ["yoga,studio", "yoga,forest"],
        },
        {
            "title": "Achtsamkeits-Coaching: Erstgespräch 49 €",
            "desc": "Das erste 60-Minuten-Gespräch mit Felix zum Kennenlernpreis: "
            "49 € statt 75 €, einmal pro Person.",
            "service": 1,
            "new_price": "49",
            "compare_at": "75",
            "discount_style": "badge",
            "limit": 10,
            "group": "Einzeltermine",
            "ends_in_days": 60,
            "images": ["meditation,man", "candles"],
        },
        {
            "title": "Yogamatte Natur −20 % — online reservieren",
            "desc": "Rutschfeste Naturkautschuk-Matte für 39,20 € statt 49 € — online "
            "reservieren und beim nächsten Besuch mitnehmen.",
            "product": 0,
            "type": "reservation",
            "percent": 20,
            "available_quantity": 6,
            "group": "Shop",
            "ends_in_days": 30,
            "image": "yoga,mat",
        },
    ],
    key="retreat",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}, "services": {"preset": "cols3"}},
    spacers=[{"after": "gallery", "height": "lg"}],  # ST-7a
    label="Waldlicht Retreat",
    business_type="events",  # S6: архетип «Veranstalter/Events» (билеты primary)
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_programm",
    look="natur",  # DS-9: своя «кожа» семейства
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="retreat",
    # 2026-07-30: слайдер + плитки hero_widget="retreat"
    # (Kurse / Übernachtung / Einzeltermin / Anfrage).
    hero_widget="retreat",
    heroes=[
        {
            "image_kw": "yoga,forest",
            "title": "Waldlicht Retreat",
            "text": "Wochenend-Retreats, Tagesworkshops und Abende, die guttun.",
            "button_label": "Termine ansehen",
            "button_url": "/veranstaltung/",
        },
        {
            "image_kw": "cabin,forest",
            "title": "Übernachten am Waldrand",
            "text": "Ruhige Zimmer und Hütten — mit Frühstück aus der Region.",
            "button_label": "Verfügbarkeit prüfen",
            "button_url": "/unterkunft/",
        },
        {
            "image_kw": "massage,wellness",
            "title": "Einzeltermine",
            "text": "Massage, Ayurveda-Beratung und Coaching — auch ohne Retreat.",
            "button_label": "Termin buchen",
            "button_url": "/termin/",
        },
    ],
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
    event_reviews=[
        (0, 5, "Anna S.", "anna.s@example.de", "Ein wunderbares Wochenende — sehr bereichernd!"),
        (0, 5, "Markus T.", "markus.t@example.de", "Tolle Gruppe und achtsame Leitung."),
        (1, 4, "Lea W.", "lea.w@example.de", "Sehr entspannend, gerne wieder."),
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
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
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
    promotions_spec=[
        # Angebot der Woche: Prozent-Badge + wöchentliche Wiederholung + Galerie.
        {
            "title": "Äpfel 'Elstar' −20 % (Angebot der Woche)",
            "product": 0,
            "percent": 20,
            "discount_style": "percent",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Wochenangebote",
            "images": ["apples", "farm,vegetables", "market,stall"],
            "desc": "Jede Woche ein anderes Hofprodukt im Angebot.",
        },
        # «3 für 2» über Bündelpreis (3×5,90 = 17,70 → 11,80), Vorrat über limit.
        {
            "title": "3 Gläser Bio-Honig zum Preis von 2",
            "product": 4,
            "new_price": "11.80",
            "compare_at": "17.70",
            "discount_style": "strikethrough",
            "limit": 15,
            "ends_in_days": 21,
            "group": "Vorratspakete",
            "desc": "Drei Gläser aus eigener Imkerei — das dritte geht aufs Haus.",
        },
        # Abendverkauf: täglich wiederkehrend, Countdown-Stil + «🆕 Neu»-Chip.
        {
            "title": "Feierabend-Frische: Bio-Tomaten −40 % ab 17 Uhr",
            "product": 2,
            "percent": 40,
            "discount_style": "countdown",
            "countdown": True,
            "recurrence": "daily",
            "new": True,
            "ends_in_days": 1,
            "group": "Feierabend-Frische",
            "desc": "Was am Abend übrig ist, geben wir günstig ab — täglich neu.",
        },
        # Freie Aktion OHNE Produkt (Muster: HOTEL-Kit): Bild kommt aus "image",
        # der Kauf erzeugt eine Bestellzeile ohne Lagerbuchung. Kontingent 12.
        {
            "title": "Gemüsekiste der Woche 19,90 € statt 27 €",
            "type": "reservation",
            "available_quantity": 12,
            "new_price": "19.90",
            "compare_at": "27.00",
            "image": "vegetable,box",
            "ends_in_days": 7,
            "group": "Vorbestellung",
            "desc": "Was gerade reif ist, bunt gemischt — online sichern, donnerstags abholen.",
        },
        # Restposten reservieren: Kontingent = tatsächlicher Bestand (6 Gläser).
        {
            "title": "Erdbeer-Marmelade −25 % — nur noch 6 Gläser",
            "product": 7,
            "type": "reservation",
            "percent": 25,
            "available_quantity": 6,
            "ends_in_days": 14,
            "group": "Wochenangebote",
            "desc": "Letzte Gläser der Sommerernte — online sichern, im Hofladen abholen.",
        },
        # «ab»-Preis: Produkt mit Varianten (150 g / 300 g) → «ab 3,83 €».
        {
            "title": "Landwurst −15 % (150 g und 300 g)",
            "product": 9,
            "percent": 15,
            "discount_style": "ab",
            "ends_in_days": 10,
            "group": "Wochenangebote",
            "desc": "Luftgetrocknet nach Hausrezept — Preis je nach Stückgröße.",
        },
    ],
    key="shop",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={"gallery": {"preset": "cols3"}},
    page_presets=[("cart", "vertrauen"), ("info", "geschichte")],  # ST-2
    label="Hofladen Sonnenfeld",
    business_type="retail",
    # DS-9: дизайн «Fokus» для архетипа — своя композиция (реестр BUNDLES).
    bundle="fokus_sortiment",
    look="klar",
    config_patch={"hero_style": "split", "nav": {"cta": True}},
    subdomain="shop",
    # 2026-07-30: слайдер + плитки hero_widget="shop"
    # (Aktionen/Sortiment/Wunschzeit/Treuepunkte).
    hero_widget="shop",
    heroes=[
        {
            "image_kw": "farm,shop",
            "title": "Hofladen Sonnenfeld",
            "text": "Obst, Gemüse und Spezialitäten direkt vom Hof — täglich frisch.",
            "button_label": "Sortiment ansehen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "vegetables,box",
            "title": "Gemüsekiste der Woche",
            "text": "Was gerade reif ist, bunt gemischt — online bestellen, abholen.",
            "button_label": "Jetzt bestellen",
            "button_url": "/sortiment/",
        },
        {
            "image_kw": "cheese,honey",
            "title": "Aus der Region",
            "text": "Käse, Honig und Wurst von Höfen, die wir persönlich kennen.",
            "button_label": "Zu den Aktionen",
            "button_url": "/aktionen/",
        },
    ],
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
            "farm-vegetables",  # DS-10: фото плитки (было SVG)
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
            "honey-jar",  # DS-10: фото плитки (было SVG)
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
            "cheese-wheel",  # DS-10: фото плитки (было SVG)
        ),
    ],
)


# --- Кит «Stadtführung»: Трипстер-гид (§5 классификации MX) --------------------
# Одиночный городской гид: экскурсия = карточка Впечатления (Tour) с датами-
# заездами (platz, цена ЗА ЧЕЛОВЕКА) + anfrage приватной группы (jobs). Живой
# пример MX-2e: адресная опция «Audio-Headset» с пулом. Business_type тот же
# tour_operator — новый архетип НЕ нужен (решение владельца 2026-08-21).

STADTFUEHRUNG_MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {"label": "Touren", "type": "url", "target": "/touren/"},
            {"label": "Termine", "type": "archetype", "target": "events"},
            {"label": "Privat buchen", "type": "url", "target": "/anfrage/"},
            {"label": "Galerie", "type": "page", "target": "gallery"},
            {"label": "Bewertungen", "type": "page", "target": "reviews"},
            {"label": "Über mich", "type": "page", "target": "about"},
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Touren", "type": "url", "target": "/touren/", "icon": "🚶"},
            {"label": "Termine", "type": "archetype", "target": "events", "icon": "🎟️"},
            {"label": "Privat", "type": "url", "target": "/anfrage/", "icon": "✍️"},
        ],
    },
}

OUTLET_MENUS = {
    "top": {
        "style": "minimal",
        "sticky": True,
        "items": [
            {
                "label": "Technik",
                "type": "category",
                "target": "notebooks-pcs",
                "children": [
                    {"label": "Notebooks & PCs", "type": "category", "target": "notebooks-pcs"},
                    {"label": "Smartphones", "type": "category", "target": "smartphones"},
                    {"label": "TV, Audio & Foto", "type": "category", "target": "tv-audio-foto"},
                    {"label": "Haushalt & Küche", "type": "category", "target": "haushalt-kueche"},
                    {
                        "label": "Gaming & Smart Home",
                        "type": "category",
                        "target": "gaming-smarthome",
                    },
                ],
            },
            {
                "label": "Mode",
                "type": "category",
                "target": "damenmode",
                "children": [
                    {"label": "Damenmode", "type": "category", "target": "damenmode"},
                    {"label": "Herrenmode", "type": "category", "target": "herrenmode"},
                    {"label": "Schuhe", "type": "category", "target": "schuhe"},
                    {"label": "Sport & Outdoor", "type": "category", "target": "sport-outdoor"},
                    {
                        "label": "Taschen & Accessoires",
                        "type": "category",
                        "target": "taschen-accessoires",
                    },
                ],
            },
            {"label": "Alle Artikel", "type": "archetype", "target": "catalog"},
            {"label": "Tagesdeals", "type": "promo_group", "target": "Tagesdeal"},
            {"label": "Sets", "type": "page", "target": "combos"},
            {"label": "Merkliste", "type": "url", "target": "/merkzettel/"},
            {
                "label": "Über uns",
                "type": "page",
                "target": "about",
                "children": [
                    {"label": "Über uns", "type": "page", "target": "about"},
                    {"label": "Lager & Team", "type": "page", "target": "team"},
                    {"label": "Bewertungen", "type": "page", "target": "reviews"},
                    {"label": "Galerie", "type": "page", "target": "gallery"},
                ],
            },
        ],
    },
    "bottom": {
        "enabled": True,
        "items": [
            {"label": "Sortiment", "type": "archetype", "target": "catalog", "icon": "🏷️"},
            {"label": "Deals", "type": "archetype", "target": "promotions", "icon": "🔥"},
            {"label": "Merkliste", "type": "url", "target": "/merkzettel/", "icon": "❤️"},
            {"label": "Korb", "type": "archetype", "target": "orders", "icon": "🛒"},
        ],
    },
}

# O-3 (план outlet-demo-plan-2026-09-03): аутлет техники и моды — единственный
# из 16 типов бизнеса, у которого не было СВОЕГО демо (`online_shop` делил
# фермерскую лавку `shop`). Жанр нагружает платформу иначе, чем прочие киты:
# дерево из 10 направлений × 39 полок × 200 позиций, оси размер×цвет, состояние
# B-Ware, UVP-референс, мелкие остатки поштучно и акции всех видов сразу.
OUTLET = DemoKit(
    key="outlet",
    label="Zweitgut Outlet",
    business_type="online_shop",
    subdomain="outlet",
    # O-5: своя кожа и композиция — «Lager» (узкий гротеск, жёсткая рамка,
    # бетонная подложка) + сборка `deal_lager` (направления → деньги → доверие).
    look="lager",
    bundle="deal_lager",
    accent="#e11d48",
    # DL-19 (N1): «Regal» — цена ведёт, фото опознавательным квадратом. В аутлете
    # решают ценой и состоянием, и на экран должно помещаться много позиций.
    # DL-19: «Regal» рассчитан на прайс-полку; на сетке в 4 колонки он ужимал
    # название до «Wollma Trav…» — в аутлете модель и марка решают наравне с
    # ценой, поэтому карточка стандартная, а плотность даёт Look «Lager».
    promo_card="preis",
    # O-2: две оси у одежды и обуви (размер × цвет) — свотчи + кнопки.
    variant_style="axes",
    card_slider="on",
    hero_image_kw="ol-cat-notebooks",
    hero_title="Zweitgut Outlet",
    hero_text="Technik und Mode aus Retouren, Ausstellung und Restposten — "
    "geprüft, mit Rechnung und Gewährleistung. Jedes Stück nur einmal da.",
    hero_widget="none",
    city="Essen",
    address="Ruhrallee 112, 45136 Essen",
    opening_hours_text="Lagerverkauf: Do–Sa 10:00–18:00 · Online rund um die Uhr",
    opening_hours={d: ("10:00", "18:00") for d in (3, 4, 5)},
    heroes=[
        {
            "image_kw": "ol-cat-notebooks",
            "title": "Bis −70 % auf Technik",
            "text": "Retouren und Ausstellungsstücke, im Haus geprüft — mit Rechnung "
            "und 12 Monaten Gewährleistung.",
            "button_label": "Technik ansehen",
            "button_url": "/sortiment/notebooks-pcs/",
        },
        {
            "image_kw": "ol-cat-damen",
            "title": "Mode aus Musterkollektionen",
            "text": "Überhänge und Vorsaison-Ware europäischer Manufakturen — "
            "Größen begrenzt, Preise dauerhaft reduziert.",
            "button_label": "Zur Mode",
            "button_url": "/sortiment/damenmode/",
        },
        {
            "image_kw": "ol-cat-tv",
            "title": "Neu ohne OVP",
            "text": "Fabrikneue Ware, bei der nur der Karton fehlt — der günstigste "
            "Weg zu einwandfreier Technik.",
            "button_label": "Alle Deals",
            "button_url": "/aktionen/",
        },
    ],
    about_title="Woher unsere Ware kommt",
    about_text="Wir kaufen auf, was der Handel nicht mehr im Regal haben will: "
    "Kundenretouren, Ausstellungsstücke, Restposten aus Sortimentswechseln und "
    "Neuware, deren Umkarton auf dem Transport gelitten hat. Jedes Gerät läuft "
    "durch unsere Prüfung, jedes Kleidungsstück durch die Sichtung. Was einen "
    "Kratzer hat, steht mit Kratzer in der Anzeige — deshalb finden Sie bei uns "
    "keine Überraschungen, sondern nur den Preis, der zum Zustand passt.",
    nav_style="minimal",
    menus=OUTLET_MENUS,
    storefront_root="home",
    seed_records=True,
    enable_modules=["orders", "crm"],
    # SH-24: у демо с заказом товара доставка включена — иначе выбор
    # «Abholung | Lieferung» на чекауте не показать.
    delivery={
        "enabled": True,
        "fee_cents": 490,
        "free_cents": 5000,
        "min_cents": 0,
        "pickup_min_cents": 0,
        "area": "Versand deutschlandweit mit DHL — 2–4 Werktage, 4,90 €. "
        "Ab 50 € kostenlos. Abholung im Lagerverkauf Essen.",
        "zones": [],
    },
    usp=[
        ("quality", "Jedes Gerät geprüft"),
        ("payment", "Versand ab 50 € kostenlos"),
        ("clock", "14 Tage Rückgabe"),
        ("local", "Lagerverkauf in Essen"),
    ],
    trust={
        "since": "2016",
        "marks": [
            "12 Monate Gewährleistung",
            "Zustand ehrlich beschrieben",
            "Rechnung mit MwSt.",
            "Kauf auf Rechnung möglich",
        ],
    },
    process=[
        ("Zustand prüfen", "Bei jedem Artikel steht, was ihn vom Neupreis trennt."),
        ("Bestellen", "Versand in 24 h, ab 50 € kostenlos — oder Abholung in Essen."),
        ("Behalten oder zurück", "14 Tage Widerruf, Rücksendung ohne Nachfragen."),
    ],
    team=[
        ("Ilja Bergmann", "Einkauf & Prüfung", "ol-sub-zubehoer"),
        ("Nadine Kroll", "Versand & Service", "ol-cat-herren"),
    ],
    testimonials=[
        (
            "Sven R.",
            "Notebook als Retoure gekauft — kam mit Rechnung, lief sofort, "
            "der beschriebene Kratzer war kleiner als gedacht.",
        ),
        (
            "Petra M.",
            "Mantel aus der Musterkollektion für die Hälfte. Größe stimmte, "
            "Versand war in zwei Tagen da.",
        ),
        ("Timo K.", "Fernseher als Ausstellungsstück — 300 € gespart, Bild einwandfrei."),
        ("Anke L.", "Handy war zurückgesetzt, Akku wie beschrieben, Rechnung lag bei."),
    ],
    reviews_seed=[
        (
            5,
            "Zustand war exakt so beschrieben. Genau so soll ein Outlet sein.",
            "zg.sven@example.de",
        ),
        (5, "Kauf auf Rechnung hat problemlos funktioniert.", "zg.petra@example.de"),
        (4, "Versand schnell, Verpackung könnte stabiler sein.", "zg.timo@example.de"),
        (5, "Endlich ein Shop, der Kratzer benennt statt zu verschweigen.", "zg.anke@example.de"),
    ],
    faq=[
        (
            "Was heißt „Neu ohne OVP“?",
            "Die Ware ist fabrikneu und unbenutzt — nur die Originalverpackung fehlt "
            "oder ist beschädigt. Funktion und Garantie sind davon nicht betroffen.",
        ),
        (
            "Wie lange habe ich Gewährleistung?",
            "Auf geprüfte Retouren und Neuware zwei Jahre, auf ausdrücklich gebrauchte "
            "Artikel zwölf Monate — so steht es auch in der Artikelbeschreibung.",
        ),
        (
            "Sind Kratzer und Gebrauchsspuren angegeben?",
            "Ja. Bei jedem Artikel steht der Zustand und, falls vorhanden, der konkrete "
            "Befund — „Karton geöffnet“, „Kratzer am Standfuß“, „Akku 92 %“.",
        ),
        (
            "Kann ich umtauschen?",
            "14 Tage Widerrufsrecht wie bei Neuware. Rücksendung genügt, eine Begründung "
            "brauchen wir nicht.",
        ),
        (
            "Warum ist ein Artikel nur einmal verfügbar?",
            "Weil wir Einzelstücke kaufen. Was weg ist, kommt in der Regel nicht wieder — "
            "deshalb steht bei jedem Artikel der echte Restbestand.",
        ),
        (
            "Kann ich die Ware vorher ansehen?",
            "Ja, im Lagerverkauf in Essen (Do–Sa 10–18 Uhr). Online reservieren geht nicht, "
            "es gilt: wer zuerst kommt.",
        ),
    ],
    cta={
        "title": "Neu eingetroffen",
        "text": "Jede Woche kommt eine neue Palette — die besten Stücke sind schnell weg.",
        "button_label": "Zu den Tagesdeals",
        "button_url": "/aktionen/",
    },
    gallery_kw=[
        "ol-cat-notebooks",
        "ol-cat-tv",
        "ol-cat-damen",
        "ol-cat-sport",
        "ol-cat-accessoires",
        "ol-cat-herren",
    ],
    # DL-11: ряды плиток без остатка — 10 направлений = 2×5, галерея 2×3,
    # товары главной 4 в ряд (проверяется scripts/demo_rows_audit.py).
    section_layouts={
        "categories": {"preset": "cols5"},
        "gallery": {"preset": "cols3"},
        "products": {"preset": "cols4"},
    },
    section_titles={
        "categories": "Alles im Haus",
        "promotions": "Tagesdeals",
        "products": "Frisch eingetroffen",
    },
    section_intros={
        "categories": "Zehn Abteilungen, über 200 Einzelstücke — jedes mit Zustand und UVP.",
        "promotions": "Läuft ab, wenn der Vorrat weg ist — und der ist bei Einzelstücken klein.",
    },
    config_patch={
        "hero_style": "split",
        "nav": {"cta": True},
        # SF-4a: Merkzettel — в аутлете вещь одна, и «сохранить, пока думаю»
        # это половина сценария.
        "wishlist": True,
        "promo_layout": "slider",
        "site_defaults": {
            # DL-20: страница направления — «Navigator» (фасеты в колонке;
            # 20 позиций и пять осей фильтра иначе не помещаются).
            "category_page_style": "navigator",
            # DL-21.2: обзорная /aktionen/ — «Prospekt» (дискаунтер).
            "promo_group_style": "prospekt",
            "promo_page_style": "kopfbild",
        },
        # DL-21.1: корневая /sortiment/ — «Regale»: направления полками,
        # внутри каждой видны первые позиции.
        "catalog_page_style": "regale",
        "promo_groups": {"Tagesdeal": "countdown", "Neu ohne OVP": "schaufenster"},
    },
    # DL-13.2: акции главной витриной; направления — квадратными плитками.
    section_styles={
        "promotions": "spotlight",
        "categories": "square",
        "trust": "badges",
        "usp_bar": "compact",
        "contact": "compact",
    },
    size_tables={
        "damenmode": "Größe | Brust (cm) | Taille (cm)\nXS | 82–85 | 62–66\nS | 86–90 | 67–71\n"
        "M | 91–95 | 72–77\nL | 96–101 | 78–83\nXL | 102–108 | 84–90",
        "herrenmode": "Größe | Brust (cm) | Bund (cm)\n48 | 94–97 | 82–85\n50 | 98–101 | 86–89\n"
        "52 | 102–105 | 90–94\n54 | 106–110 | 95–99",
        "schuhe": "Größe | Fußlänge (cm)\n38 | 24,3\n39 | 25,0\n40 | 25,7\n41 | 26,3\n"
        "42 | 27,0\n43 | 27,7\n44 | 28,3\n45 | 29,0",
    },
    vouchers=[
        {"code": "ZWEITGUT10", "label": "−10 % für Neukunden", "percent": 10, "max_uses": 300},
    ],
    # ── Акции. Индекс `product` — позиция товара в обходе категорий (DFS
    # pre-order: направление → полка → позиции). Голден-замок test_outlet_photos
    # держит соответствие «акция → товар»: любая правка ассортимента обязана быть
    # позиция-в-позицию, иначе акции молча уедут на чужие товары.
    #
    # Аутлет живёт акциями, поэтому демо показывает ВСЕ виды сразу: проценты,
    # зачёркнутую цену, фиксированную цену, «ab», обратный отсчёт, mystery,
    # «Überraschung», резервирование и предпросмотр будущей распродажи.
    promotions_spec=[
        # ── Tagesdeal: один товар в день, обратный отсчёт до полуночи.
        {
            "title": "Tagesdeal: Saugroboter Vireo Round −35 %",
            "product": 71,
            "percent": 35,
            "discount_style": "countdown",
            "countdown": True,
            "recurrence": "daily",
            "ends_in_days": 1,
            "group": "Tagesdeal",
            "desc": "Vorführgerät mit neuen Bürsten — jeden Tag ein anderes Gerät im Tagesdeal.",
        },
        {
            "title": "Tagesdeal: Kaffeevollautomat statt 399 € nur 329 €",
            "product": 60,
            "new_price": "329.00",
            "compare_at": "399.00",
            "discount_style": "strikethrough",
            "countdown": True,
            "ends_in_days": 2,
            "group": "Tagesdeal",
            "desc": "Ausstellungsstück aus dem Showroom, entkalkt und geprüft.",
        },
        {
            "title": "Tagesdeal: Over-Ear Kamira Studio 2 zum Festpreis 69 €",
            "product": 45,
            "new_price": "69.00",
            "compare_at": "89.00",
            "discount_style": "festpreis",
            "limit": 12,
            "ends_in_days": 3,
            "group": "Tagesdeal",
            "desc": "Aktive Geräuschunterdrückung, geprüfte Retoure — zwölf Stück im Aktionspreis.",
        },
        # ── Neu ohne OVP: жанровая витрина аутлета.
        {
            "title": "Neu ohne OVP: Notebook Nordvolt N15 −20 %",
            "product": 1,
            "percent": 20,
            "discount_style": "percent",
            "ends_in_days": 10,
            "group": "Neu ohne OVP",
            "desc": "Fabrikneu, nur der Originalkarton fehlt — die Garantie bleibt voll.",
        },
        {
            "title": "Neu ohne OVP: Wollmantel Traverso Nord ab 89 €",
            "product": 100,
            "new_price": "89.00",
            "discount_style": "ab",
            "ends_in_days": 14,
            "group": "Neu ohne OVP",
            "desc": "Musterteil aus der Kollektion, ungetragen — Größen 36 bis 42.",
        },
        {
            "title": "Neu ohne OVP: Armbanduhr Traverso Stahl −25 %",
            "product": 184,
            "percent": 25,
            "discount_style": "badge",
            "ends_in_days": 12,
            "group": "Neu ohne OVP",
            "desc": "Saphirglas, 5 bar — Uhrenbox fehlt, Uhr ist unberührt.",
        },
        # ── Lagerräumung: место под новую палету.
        {
            "title": "Lagerräumung: Fernseher Ferrit 55 Zoll −30 %",
            "product": 40,
            "percent": 30,
            "discount_style": "percent",
            "ends_in_days": 6,
            "group": "Lagerräumung",
            "desc": "Ausstellungsstück mit feiner Schramme am Rahmen — Bild einwandfrei.",
        },
        {
            "title": "Lagerräumung: Beamer Ferrit Cine Mini 139 € statt 179 €",
            "product": 93,
            "new_price": "139.00",
            "compare_at": "179.00",
            "discount_style": "strikethrough",
            "ends_in_days": 5,
            "group": "Lagerräumung",
            "desc": "Letztes Stück aus dem Vorjahresmodell.",
        },
        {
            "title": "Lagerräumung: Toaster Halden Duo −40 %",
            "product": 64,
            "percent": 40,
            "discount_style": "percent",
            "limit": 20,
            "ends_in_days": 8,
            "group": "Lagerräumung",
            "desc": "Zwanzig Stück aus einer Filialauflösung.",
        },
        # ── Mode-Sale.
        {
            "title": "Mode-Sale: Kleid Silvana Sommer −40 %",
            "product": 109,
            "percent": 40,
            "discount_style": "percent",
            "ends_in_days": 11,
            "group": "Mode-Sale",
            "desc": "Ausstellungsstück aus dem Showroom — Größen 36 bis 40.",
        },
        {
            "title": "Mode-Sale: Sneaker Traverso Court 39,90 € statt 49,90 €",
            "product": 140,
            "new_price": "39.90",
            "compare_at": "49.90",
            "discount_style": "strikethrough",
            "ends_in_days": 9,
            "group": "Mode-Sale",
            "desc": "Anprobierte Retoure, Sohle unbenutzt — Größen 40 bis 45.",
        },
        {
            "title": "Mode-Sale: Chelsea-Boots Brentwood −25 %",
            "product": 146,
            "percent": 25,
            "discount_style": "badge",
            "ends_in_days": 13,
            "group": "Mode-Sale",
            "desc": "Rindsleder, profilierte Laufsohle — zwei Farben.",
        },
        {
            "title": "Mode-Sale: Pullover Traverso Merino ab 39,90 €",
            "product": 132,
            "new_price": "39.90",
            "discount_style": "ab",
            "recurrence": "weekly",
            "ends_in_days": 7,
            "group": "Mode-Sale",
            "desc": "Jede Woche ein Strickteil reduziert — diese Woche der Merino-Pullover.",
        },
        # ── Technik-Deals.
        {
            "title": "Technik-Deal: Monitor Kamira View 27 QHD −22 %",
            "product": 7,
            "percent": 22,
            "discount_style": "percent",
            "ends_in_days": 10,
            "group": "Technik-Deals",
            "desc": "Showroom-Gerät, Standfuß leicht zerkratzt, Panel makellos.",
        },
        {
            "title": "Technik-Deal: Externe SSD Ferrit 1 TB zum Festpreis 54,90 €",
            "product": 16,
            "new_price": "54.90",
            "compare_at": "69.90",
            "discount_style": "festpreis",
            "limit": 30,
            "ends_in_days": 15,
            "group": "Technik-Deals",
            "desc": "Originalverpackt, dreißig Stück aus einem Restposten.",
        },
        {
            "title": "Technik-Deal: VR-Brille Ferrit View −20 %",
            "product": 98,
            "percent": 20,
            "discount_style": "percent",
            "ends_in_days": 9,
            "group": "Technik-Deals",
            "desc": "Geprüfte Retoure, zwei Controller und gepolstertes Trageband dabei.",
        },
        # ── Mystery: цена скрыта до клика (UE2-3).
        {
            "title": "Mystery-Deal der Woche",
            "new": True,
            "product": 24,
            "new_price": "39.50",
            "compare_at": "79.00",
            "discount_style": "mystery",
            "countdown": True,
            "ends_in_days": 4,
            "group": "Tagesdeal",
            "desc": "Ein Gerät aus der Technik-Abteilung zum halben Preis — "
            "der Preis erscheint erst beim Klick.",
        },
        # ── Überraschungspaket: свободная акция БЕЗ товара (кит hotel-паттерн).
        {
            "title": "Technik-Wundertüte 29 € statt 79 €",
            "type": "reservation",
            "available_quantity": 15,
            "new_price": "29.00",
            "compare_at": "79.00",
            "surprise": True,
            "image": "ol-cat-notebooks",
            "ends_in_days": 20,
            "group": "Lagerräumung",
            "desc": "Drei geprüfte Kleingeräte aus dem Lager — was drin ist, "
            "sehen Sie beim Auspacken. Warenwert mindestens 79 €.",
        },
        # ── Резервирование: контингент = фактический остаток.
        {
            "title": "Nur noch 4 Stück: Siebträger Bragg Espresso Pro −25 %",
            "product": 61,
            "type": "reservation",
            "percent": 25,
            "available_quantity": 4,
            "ends_in_days": 7,
            "group": "Technik-Deals",
            "images": ["ol-espresso", "ol-sub-kaffee"],
            "desc": "Entkalkt und mit neuer Dichtung — online sichern, in Essen abholen.",
        },
        # ── Легаси-стиль (без `discount_style`): так выглядит акция, заведённая
        # владельцем без выбора вида — в showcase это тоже должно быть видно.
        {
            "title": "Shopper Traverso Leder −20 %",
            "product": 180,
            "percent": 20,
            "ends_in_days": 16,
            "group": "Mode-Sale",
            "desc": "Weiches Rindsleder, Musterteil ohne Gebrauchsspuren.",
        },
        {
            "title": "Laufschuh Ahlberg Road Neutral 54,90 € statt 69,90 €",
            "product": 164,
            "new_price": "54.90",
            "compare_at": "69.90",
            "discount_style": "strikethrough",
            "ends_in_days": 8,
            "group": "Mode-Sale",
            "desc": "Geprüfte Retoure, Dämpfung wie neu — Größen 41 bis 45.",
        },
        # ── Vorschau (A1): запланированная акция, видна лентой «Ab …».
        {
            "title": "Ab Montag: Winter-Räumung bis −50 %",
            "product": 121,
            "percent": 50,
            "starts_in_days": 4,
            "ends_in_days": 14,
            "group": "Lagerräumung",
            "desc": "Vorschau: Mäntel, Jacken und Strick der Vorsaison stark reduziert.",
        },
    ],
    # ── Подборки: у аутлета фасет-чипы отвечают на вопросы, которых нет в
    # категориях («что тут вообще как новое?», «что до 20 €?»).
    collections=[
        (
            "Neu ohne OVP",
            {
                "products": [
                    1,
                    5,
                    21,
                    25,
                    41,
                    44,
                    62,
                    64,
                    80,
                    85,
                    100,
                    103,
                    120,
                    124,
                    141,
                    143,
                    160,
                    163,
                    180,
                    184,
                ],
                "photos": ["ol-cat-notebooks", "ol-sub-huellen", "ol-w-coat"],
            },
        ),
        (
            "Ausstellungsstücke",
            {
                "products": [
                    2,
                    7,
                    19,
                    23,
                    36,
                    40,
                    49,
                    59,
                    60,
                    67,
                    71,
                    83,
                    92,
                    94,
                    102,
                    109,
                    122,
                    134,
                    151,
                    154,
                    183,
                    197,
                ],
                "photos": ["ol-cat-tv", "ol-sub-monitore", "ol-monitor-qhd"],
            },
        ),
        (
            "Unter 25 €",
            {
                "products": [
                    13,
                    15,
                    25,
                    26,
                    43,
                    44,
                    64,
                    68,
                    84,
                    86,
                    105,
                    113,
                    125,
                    126,
                    143,
                    145,
                    161,
                    163,
                    186,
                    187,
                ]
            },
        ),
        (
            "Homeoffice",
            {
                "products": [1, 8, 12, 13, 14, 15, 16, 35],
                "photos": ["ol-sub-zubehoer", "ol-monitor-24"],
            },
        ),
    ],
    # ── Наборы: аутлет продаёт «всё сразу дешевле», это его вторая механика.
    combos=[
        {
            "name": "Homeoffice-Starter",
            "description": "Notebook, Monitor, Tastatur und Maus — geprüft und "
            "aufeinander abgestimmt. Einzeln 632,80 €.",
            "price": "549.00",
            "photos": ["ol-sub-zubehoer", "ol-cat-notebooks"],
            "groups": [
                {"label": "Notebook", "products": ["Notebook Nordvolt N15 Office"]},
                {"label": "Monitor", "products": ["Monitor Nordvolt 24 Full HD"]},
                {
                    "label": "Eingabe",
                    "products": ["Tastatur Nordvolt Mech TKL", "Maus Kamira Silent M2"],
                },
            ],
        },
        {
            "name": "Küchen-Erstausstattung",
            "description": "Wasserkocher, Toaster und Stabmixer aus Restposten — einzeln 75,70 €.",
            "price": "59.00",
            "photos": ["ol-sub-kaffee", "ol-kettle"],
            "groups": [
                {"label": "Kochen", "products": ["Wasserkocher Lumeo Temp", "Toaster Halden Duo"]},
                {"label": "Zubereiten", "products": ["Stabmixer Halden Stick"]},
            ],
        },
        {
            "name": "Winter-Outfit Herren",
            "description": "Steppjacke, Merino-Pullover und Chino — einzeln 179,80 €.",
            "price": "139.00",
            "photos": ["ol-cat-herren", "ol-m-puffer"],
            "groups": [
                {"label": "Jacke", "products": ["Steppjacke Brentwood Winter"]},
                {"label": "Oberteil", "products": ["Pullover Traverso Merino"]},
                {"label": "Hose", "products": ["Chino Marlow Alltag"]},
            ],
        },
        {
            "name": "Sport-Einstieg",
            "description": "Yogamatte, Kurzhantel-Set und Trinkflasche — einzeln 76,70 €.",
            "price": "59.90",
            "photos": ["ol-cat-sport", "ol-yogamat"],
            "groups": [
                {"label": "Boden", "products": ["Yogamatte Silvana Grip"]},
                {"label": "Gewichte", "products": ["Kurzhantel-Set Ferrit 2×5 kg"]},
                {"label": "Trinken", "products": ["Trinkflasche Ahlberg Steel 0,75 l"]},
            ],
        },
    ],
    # ── Отзывы о товарах: без них фасет рейтинга не показывается, а звёзды на
    # карточке — сильный сигнал именно у B-Ware («не обманули ли с состоянием»).
    product_reviews=[
        (
            0,
            5,
            "Sven R.",
            "zg.sven@example.de",
            "Akku wirklich bei 97 %, Kratzer war kaum zu finden. Für den Preis top.",
        ),
        (
            0,
            4,
            "Marek P.",
            "zg.marek@example.de",
            "Gerät läuft einwandfrei, Netzteil war ein Nachbau — hätte im Text stehen können.",
        ),
        (
            0,
            5,
            "Julia F.",
            "zg.julia@example.de",
            "Zweites Notebook hier gekauft, wieder alles korrekt.",
        ),
        (
            40,
            5,
            "Timo K.",
            "zg.timo@example.de",
            "300 € gespart, Bild einwandfrei. Die Schramme sieht man nur, wenn man sie sucht.",
        ),
        (40, 4, "Bea H.", "zg.bea@example.de", "Aufbau allein war schwer, Bild und Ton super."),
        (
            20,
            5,
            "Anke L.",
            "zg.anke@example.de",
            "Handy war zurückgesetzt, Akku wie beschrieben. Rechnung lag bei.",
        ),
        (20, 4, "Ferdi S.", "zg.ferdi@example.de", "Kleine Schleifspur am Rahmen, sonst wie neu."),
        (
            100,
            5,
            "Petra M.",
            "zg.petra@example.de",
            "Mantel für die Hälfte, ungetragen. Größe fällt normal aus.",
        ),
        (100, 5, "Lena B.", "zg.lena@example.de", "Verarbeitung deutlich besser als erwartet."),
        (
            60,
            4,
            "Ralf D.",
            "zg.ralf@example.de",
            "Vollautomat war frisch entkalkt. Milchsystem braucht etwas Übung.",
        ),
        (140, 5, "Mira T.", "zg.mira@example.de", "Sneaker sahen aus wie aus dem Karton."),
        (71, 5, "Nils W.", "zg.nils@example.de", "Saugroboter mit neuen Bürsten — läuft täglich."),
        (45, 4, "Ida K.", "zg.ida@example.de", "Kopfhörer top, Etui hatte eine Delle."),
        (16, 5, "Ben O.", "zg.ben@example.de", "SSD originalverpackt, Tempo wie angegeben."),
    ],
    # ST-8: галерея/команда/отзывы отдельными страницами (гейт по наличию контента).
    seed_inbox=True,
    categories=[
        (
            "Notebooks & PCs",
            "notebooks-pcs",
            [],
            [
                (
                    "Notebooks",
                    "notebooks",
                    [
                        _p(
                            "Notebook Nordvolt N14 Pro",
                            "549.00",
                            "14 Zoll IPS, 16 GB RAM, 512 GB SSD. Kundenretoure, technisch geprüft, Akku 97 % Kapazität.",
                            "ol-laptop-silver",
                            variants=[
                                {"color": "Silber", "price": "549.00", "stock": 3},
                                {"color": "Space Grau", "price": "549.00", "stock": 1},
                            ],
                            condition="retoure",
                            note="Akku-Kapazität 97 % — Funktionstest ohne Befund.",
                            brand="Nordvolt",
                            uvp="899.00",
                        ),
                        _p(
                            "Notebook Nordvolt N15 Office",
                            "389.00",
                            "15,6 Zoll, 8 GB RAM, 256 GB SSD. Fabrikneu — nur der Originalkarton fehlt.",
                            "ol-laptop-open",
                            variants=[
                                {"size": "256 GB", "price": "389.00", "stock": 1},
                                {"size": "512 GB", "price": "389.00", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Nordvolt",
                            uvp="649.00",
                        ),
                        _p(
                            "Ultrabook Kamira Air 13",
                            "699.00",
                            "1,1 kg leicht, Aluminium-Gehäuse. Ausstellungsstück aus unserem Showroom.",
                            "ol-ultrabook",
                            stock=5,
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Kamira",
                            uvp="1149.00",
                        ),
                        _p(
                            "Gaming-Notebook Ferrit Raptor 16",
                            "899.00",
                            "16 Zoll 165 Hz, dedizierte Grafik, 1 TB SSD. Retoure mit vollem Funktionstest.",
                            "ol-gaming-laptop",
                            stock=2,
                            condition="retoure",
                            note="Funktionstest bestanden, Zubehör vollständig.",
                            brand="Ferrit",
                            uvp="1499.00",
                        ),
                        _p(
                            "Notebook Halden Basic 14",
                            "279.00",
                            "Für Büro und Studium: 8 GB RAM, 256 GB SSD, leises Lüfterkonzept.",
                            "ol-laptop-grey",
                            stock=4,
                            condition="wie_neu",
                            note="Wie neu — einmal kurz im Einsatz gewesen.",
                            brand="Halden",
                            uvp="449.00",
                        ),
                        _p(
                            "Convertible Vireo Flip 14",
                            "529.00",
                            "Touchscreen, 360°-Scharnier, Stift liegt bei. Neu, Umkarton beschädigt.",
                            "ol-convertible",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Vireo",
                            uvp="849.00",
                        ),
                        _p(
                            "Mini-PC Ostrand Cube",
                            "249.00",
                            "Handflächengroßer Desktop, 16 GB RAM, lautlos. Originalverpackt.",
                            "ol-mini-pc",
                            stock=6,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Ostrand",
                            uvp="399.00",
                        ),
                    ],
                    "ol-sub-notebooks",
                ),
                (
                    "Monitore",
                    "monitore",
                    [
                        _p(
                            "Monitor Kamira View 27 QHD",
                            "179.00",
                            "27 Zoll, 2560×1440, höhenverstellbar. Showroom-Gerät, Standfuß leicht zerkratzt.",
                            "ol-monitor-qhd",
                            stock=1,
                            condition="ausstellung",
                            note="Standfuß leicht zerkratzt, Panel makellos.",
                            brand="Kamira",
                            uvp="299.00",
                        ),
                        _p(
                            "Monitor Nordvolt 24 Full HD",
                            "89.00",
                            "Der Zweitmonitor fürs Homeoffice: 24 Zoll, HDMI und DisplayPort.",
                            "ol-monitor-24",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Nordvolt",
                            uvp="149.00",
                        ),
                        _p(
                            "Curved-Monitor Ferrit Arc 32",
                            "289.00",
                            "32 Zoll Curved, 144 Hz. Retoure — Bildtest ohne Befund, keine Pixelfehler.",
                            "ol-curved-monitor",
                            stock=2,
                            condition="retoure",
                            note="Bildtest ohne Befund, keine Pixelfehler.",
                            brand="Ferrit",
                            uvp="499.00",
                        ),
                        _p(
                            "Portabler Monitor Vireo Go 15,6",
                            "119.00",
                            "Zweitbildschirm für unterwegs, USB-C, mit Schutzhülle.",
                            "ol-portable-monitor",
                            stock=4,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Vireo",
                            uvp="199.00",
                        ),
                        _p(
                            "Monitorhalterung Halden Arm",
                            "34.90",
                            "Gasdruckfeder, für Bildschirme bis 32 Zoll und 9 kg.",
                            "ol-monitor-arm",
                            stock=1,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Halden",
                            uvp="59.00",
                        ),
                    ],
                    "ol-sub-monitore",
                ),
                (
                    "PC-Zubehör",
                    "pc-zubehoer",
                    [
                        _p(
                            "Tastatur Nordvolt Mech TKL",
                            "49.90",
                            "Mechanisch, taktil, ohne Nummernblock. Deutsches Layout.",
                            "ol-keyboard",
                            variants=[
                                {"color": "Schwarz", "price": "49.90", "stock": 5},
                                {"color": "Weiß", "price": "49.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Nordvolt",
                            uvp="89.00",
                        ),
                        _p(
                            "Maus Kamira Silent M2",
                            "14.90",
                            "Leise Tasten, 2,4 GHz Funk, bis 18 Monate Batterielaufzeit.",
                            "ol-mouse",
                            variants=[
                                {"color": "Schwarz", "price": "14.90", "stock": 3},
                                {"color": "Grau", "price": "14.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Kamira",
                            uvp="29.00",
                        ),
                        _p(
                            "Dockingstation Vireo Hub 11-in-1",
                            "59.90",
                            "USB-C auf HDMI, LAN, SD und 4× USB. Ein Kabel für alles.",
                            "ol-docking",
                            stock=2,
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Vireo",
                            uvp="109.00",
                        ),
                        _p(
                            "Webcam Ostrand View HD",
                            "24.90",
                            "1080p, Autofokus, Sichtschutzblende, Stereomikrofon.",
                            "ol-webcam",
                            stock=6,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ostrand",
                            uvp="49.00",
                        ),
                        _p(
                            "Externe SSD Ferrit 1 TB",
                            "69.90",
                            "Bis 1050 MB/s, stoßfestes Gehäuse, USB-C und USB-A Kabel dabei.",
                            "ol-ssd",
                            variants=[
                                {"size": "500 GB", "price": "69.90", "stock": 1},
                                {"size": "1 TB", "price": "69.90", "stock": 4},
                                {"size": "2 TB", "price": "69.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Ferrit",
                            uvp="119.00",
                        ),
                    ],
                    "ol-sub-zubehoer",
                ),
                (
                    "Tablets",
                    "tablets",
                    [
                        _p(
                            "Tablet Kamira Tab 10",
                            "149.00",
                            "10,4 Zoll, 64 GB, LTE-fähig. Geprüfte Retoure mit neuem Displayschutz.",
                            "ol-tablet",
                            variants=[
                                {"size": "64 GB", "price": "149.00", "stock": 4},
                                {"size": "128 GB", "price": "149.00", "stock": 2},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Kamira",
                            uvp="249.00",
                        ),
                        _p(
                            "Tablet Nordvolt Pad 11",
                            "229.00",
                            "11 Zoll 120 Hz, 128 GB, Stiftunterstützung. Neu ohne Originalkarton.",
                            "ol-tablet-hand",
                            variants=[
                                {"color": "Anthrazit", "price": "229.00", "stock": 2},
                                {"color": "Silber", "price": "229.00", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Nordvolt",
                            uvp="379.00",
                        ),
                        _p(
                            "Tablet-Tastaturhülle Vireo",
                            "39.90",
                            "Magnetische Hülle mit abnehmbarer Tastatur, passend für 10–11 Zoll.",
                            "ol-tablet-case",
                            stock=3,
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Vireo",
                            uvp="69.00",
                        ),
                    ],
                    "ol-sub-tablets",
                ),
            ],
            "Notebooks, Monitore und Zubehör aus Retouren, Ausstellung und Restposten — jedes Gerät geprüft, mit 12 Monaten Gewährleistung.",
            "",
            "ol-cat-notebooks",
        ),
        (
            "Smartphones & Zubehör",
            "smartphones",
            [],
            [
                (
                    "Smartphones",
                    "handys",
                    [
                        _p(
                            "Smartphone Kamira K7",
                            "299.00",
                            "6,5 Zoll AMOLED, 128 GB, Dreifachkamera. Akku-Kapazität 92 %.",
                            "ol-phone-black",
                            variants=[
                                {
                                    "size": "128 GB",
                                    "color": "Schwarz",
                                    "price": "299.00",
                                    "stock": 3,
                                },
                                {
                                    "size": "256 GB",
                                    "color": "Schwarz",
                                    "price": "299.00",
                                    "stock": 1,
                                },
                                {"size": "128 GB", "color": "Blau", "price": "299.00", "stock": 5},
                                {"size": "256 GB", "color": "Blau", "price": "299.00", "stock": 2},
                            ],
                            condition="retoure",
                            note="Akku-Kapazität 92 %, Gerät zurückgesetzt.",
                            brand="Kamira",
                            uvp="499.00",
                        ),
                        _p(
                            "Smartphone Nordvolt V5",
                            "199.00",
                            "5000 mAh Akku, 64 GB, Dual-SIM. Neu, Karton geöffnet.",
                            "ol-phone-hand",
                            variants=[
                                {"color": "Graphit", "price": "199.00", "stock": 1},
                                {"color": "Grün", "price": "199.00", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Nordvolt",
                            uvp="349.00",
                        ),
                        _p(
                            "Smartphone Vireo Lite 4",
                            "129.00",
                            "Das solide Zweithandy: 6,1 Zoll, 64 GB, Klinkenanschluss.",
                            "ol-phone-flat",
                            stock=5,
                            condition="wie_neu",
                            note="Zweitgerät aus Firmenauflösung, zurückgesetzt.",
                            brand="Vireo",
                            uvp="219.00",
                        ),
                        _p(
                            "Smartphone Ferrit Pro Cam",
                            "449.00",
                            "Kamera-Flaggschiff der Vorsaison, 256 GB. Vorführgerät aus dem Showroom.",
                            "ol-phone-camera",
                            stock=2,
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Ferrit",
                            uvp="749.00",
                        ),
                        _p(
                            "Smartwatch Lumeo Fit 2",
                            "79.00",
                            "Herzfrequenz, SpO2, GPS, 10 Tage Akku. Originalverpackt.",
                            "ol-smartwatch",
                            variants=[
                                {"color": "Schwarz", "price": "79.00", "stock": 4},
                                {"color": "Sand", "price": "79.00", "stock": 2},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Lumeo",
                            uvp="139.00",
                        ),
                    ],
                    "ol-sub-handys",
                ),
                (
                    "Hüllen & Schutz",
                    "huellen",
                    [
                        _p(
                            "Schutzhülle Bragg Clear",
                            "9.90",
                            "Transparente Silikonhülle mit erhöhtem Kameraring.",
                            "ol-phone-case",
                            variants=[
                                {"color": "Transparent", "price": "9.90", "stock": 2},
                                {"color": "Schwarz", "price": "9.90", "stock": 6},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Bragg",
                            uvp="19.90",
                        ),
                        _p(
                            "Handytasche Traverso Leder",
                            "24.90",
                            "Echtleder-Klapphülle mit drei Kartenfächern.",
                            "ol-phone-wallet",
                            variants=[
                                {"color": "Cognac", "price": "24.90", "stock": 6},
                                {"color": "Schwarz", "price": "24.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Traverso",
                            uvp="44.90",
                        ),
                        _p(
                            "Panzerglas Bragg 2er-Pack",
                            "7.90",
                            "9H Härte, kratzfest, Montagerahmen liegt bei.",
                            "ol-screen-glass",
                            stock=1,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Bragg",
                            uvp="14.90",
                        ),
                        _p(
                            "Handyhalterung Ostrand Auto",
                            "12.90",
                            "Magnethalter fürs Lüftungsgitter, hält auch große Geräte.",
                            "ol-phone-mount",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ostrand",
                            uvp="24.90",
                        ),
                    ],
                    "ol-sub-huellen",
                ),
                (
                    "Powerbanks & Laden",
                    "powerbanks",
                    [
                        _p(
                            "Powerbank Lumeo 20 000 mAh",
                            "29.90",
                            "Zwei Geräte gleichzeitig laden, USB-C Power Delivery 30 W.",
                            "ol-powerbank",
                            variants=[
                                {"size": "10 000 mAh", "price": "29.90", "stock": 2},
                                {"size": "20 000 mAh", "price": "29.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Lumeo",
                            uvp="54.90",
                        ),
                        _p(
                            "Netzteil Nordvolt GaN 65 W",
                            "19.90",
                            "Lädt Notebook und Handy gleichzeitig, kompakt durch GaN-Technik.",
                            "ol-charger",
                            stock=4,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Nordvolt",
                            uvp="39.90",
                        ),
                        _p(
                            "USB-C Kabel Bragg 2 m (3er-Set)",
                            "11.90",
                            "Nylon-Geflecht, 100 W, Datenrate 480 Mbit/s.",
                            "ol-cable",
                            stock=1,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Bragg",
                            uvp="22.90",
                        ),
                        _p(
                            "Ladepad Lumeo Wireless 15 W",
                            "16.90",
                            "Induktives Laden, rutschfeste Oberfläche, Netzteil dabei.",
                            "ol-wireless-charger",
                            stock=5,
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Lumeo",
                            uvp="34.90",
                        ),
                    ],
                    "ol-sub-powerbanks",
                ),
                (
                    "Kopfhörer & Zubehör",
                    "in-ear",
                    [
                        _p(
                            "In-Ear Kamira Buds Air",
                            "39.90",
                            "True Wireless mit Geräuschunterdrückung, 24 h mit Ladecase.",
                            "ol-earbuds",
                            variants=[
                                {"color": "Weiß", "price": "39.90", "stock": 3},
                                {"color": "Schwarz", "price": "39.90", "stock": 2},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Kamira",
                            uvp="79.00",
                        ),
                        _p(
                            "Sport-In-Ear Lumeo Move",
                            "24.90",
                            "Bügel für festen Sitz, IPX5 gegen Schweiß und Regen.",
                            "ol-earbuds-sport",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Lumeo",
                            uvp="49.90",
                        ),
                        _p(
                            "Headset Ostrand Talk",
                            "19.90",
                            "USB-Headset für Videocalls, Mikrofon mit Stummschaltung.",
                            "ol-headset-usb",
                            stock=6,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Ostrand",
                            uvp="39.90",
                        ),
                        _p(
                            "In-Ear Bragg Quiet ANC",
                            "54.90",
                            "Aktive Geräuschunterdrückung, Transparenzmodus, kabelloses Laden.",
                            "ol-earbuds-anc",
                            stock=1,
                            condition="ausstellung",
                            note="Showroom-Gerät: aufgebaut gestanden, voll funktionsfähig.",
                            brand="Bragg",
                            uvp="109.00",
                        ),
                        _p(
                            "Ständer Halden Desk",
                            "9.90",
                            "Aluminium-Ständer für Handy und Tablet, klappbar.",
                            "ol-phone-holder",
                            stock=4,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Halden",
                            uvp="19.90",
                        ),
                        _p(
                            "Speicherkarte Ferrit 128 GB",
                            "12.90",
                            "microSD mit Adapter, 100 MB/s, für Kamera und Handy.",
                            "ol-memory-card",
                            variants=[
                                {"size": "64 GB", "price": "12.90", "stock": 2},
                                {"size": "128 GB", "price": "12.90", "stock": 3},
                                {"size": "256 GB", "price": "12.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Ferrit",
                            uvp="24.90",
                        ),
                        _p(
                            "Stativ-Selfiestick Vireo",
                            "16.90",
                            "Dreibein, Bluetooth-Auslöser, bis 1,1 m ausziehbar.",
                            "ol-selfie-stick",
                            stock=3,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Vireo",
                            uvp="32.90",
                        ),
                    ],
                    "ol-sub-inear",
                ),
            ],
            "Smartphones aus Retoure und Vorführung — alle Geräte gelöscht, auf Werkseinstellung gesetzt und mit Akku-Test über 85 %.",
            "",
            "ol-cat-smartphones",
        ),
        (
            "TV, Audio & Foto",
            "tv-audio-foto",
            [],
            [
                (
                    "Fernseher",
                    "fernseher",
                    [
                        _p(
                            "Fernseher Ferrit 55 Zoll 4K",
                            "399.00",
                            "55 Zoll UHD, HDR10, Smart-TV. Ausstellungsstück, Rahmen mit feiner Schramme.",
                            "ol-tv-55",
                            stock=3,
                            condition="ausstellung",
                            note="Rahmen mit feiner Schramme, Bild einwandfrei.",
                            brand="Ferrit",
                            uvp="699.00",
                        ),
                        _p(
                            "Fernseher Kamira 43 Zoll Full HD",
                            "229.00",
                            "43 Zoll für Küche oder Schlafzimmer, Triple-Tuner, zwei HDMI.",
                            "ol-tv-43",
                            stock=1,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Kamira",
                            uvp="379.00",
                        ),
                        _p(
                            "OLED-Fernseher Nordvolt 65 Zoll",
                            "1099.00",
                            "65 Zoll OLED, 120 Hz, perfektes Schwarz. Retoure mit Panel-Test.",
                            "ol-tv-65",
                            stock=5,
                            condition="retoure",
                            note="Panel-Test bestanden, Fernbedienung neu beigelegt.",
                            brand="Nordvolt",
                            uvp="1899.00",
                        ),
                        _p(
                            "TV-Wandhalterung Halden Slim",
                            "24.90",
                            "Neigbar, für 32–65 Zoll, Wandabstand nur 3,5 cm.",
                            "ol-tv-stand",
                            stock=2,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Halden",
                            uvp="49.00",
                        ),
                        _p(
                            "Streaming-Stick Vireo Cast",
                            "22.90",
                            "Macht jeden Fernseher smart: 4K, Sprachfernbedienung.",
                            "ol-streaming-stick",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Vireo",
                            uvp="44.90",
                        ),
                    ],
                    "ol-sub-tv",
                ),
                (
                    "Kopfhörer",
                    "kopfhoerer",
                    [
                        _p(
                            "Over-Ear Kamira Studio 2",
                            "89.00",
                            "Bügelkopfhörer mit aktiver Geräuschunterdrückung, 40 h Akku.",
                            "ol-headphones",
                            variants=[
                                {"color": "Schwarz", "price": "89.00", "stock": 2},
                                {"color": "Beige", "price": "89.00", "stock": 6},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Kamira",
                            uvp="179.00",
                        ),
                        _p(
                            "Studio-Kopfhörer Bragg Monitor",
                            "59.00",
                            "Geschlossen, kabelgebunden, 3 m Spiralkabel — fürs Aufnehmen.",
                            "ol-headphones-wire",
                            stock=6,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Bragg",
                            uvp="109.00",
                        ),
                        _p(
                            "Kinderkopfhörer Lumeo Safe",
                            "16.90",
                            "Lautstärke auf 85 dB begrenzt, faltbar, Aufkleber zum Gestalten.",
                            "ol-headphones-kids",
                            variants=[
                                {"color": "Blau", "price": "16.90", "stock": 1},
                                {"color": "Rosa", "price": "16.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Lumeo",
                            uvp="32.90",
                        ),
                    ],
                    "ol-sub-kopfhoerer",
                ),
                (
                    "Lautsprecher",
                    "lautsprecher",
                    [
                        _p(
                            "Bluetooth-Box Lumeo Roll",
                            "34.90",
                            "Wasserdicht nach IPX7, 20 h Spielzeit, Trageschlaufe.",
                            "ol-speaker-bt",
                            variants=[
                                {"color": "Schwarz", "price": "34.90", "stock": 3},
                                {"color": "Petrol", "price": "34.90", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Lumeo",
                            uvp="69.00",
                        ),
                        _p(
                            "Soundbar Ferrit Wave 2.1",
                            "119.00",
                            "Mit drahtlosem Subwoofer, HDMI-ARC, Dialog-Modus.",
                            "ol-soundbar",
                            stock=2,
                            condition="ausstellung",
                            note="Leichte Lagerspuren am Gehäuse.",
                            brand="Ferrit",
                            uvp="229.00",
                        ),
                        _p(
                            "Regallautsprecher Bragg Duo",
                            "149.00",
                            "Passives Paar aus MDF, 120 W, echte Holzfurnier-Front.",
                            "ol-speaker-shelf",
                            stock=4,
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Bragg",
                            uvp="279.00",
                        ),
                        _p(
                            "Plattenspieler Ostrand Vinyl",
                            "129.00",
                            "Riemenantrieb, Vorverstärker eingebaut, USB-Digitalisierung.",
                            "ol-turntable",
                            stock=1,
                            condition="wie_neu",
                            note="Nadel neu, Riemen erneuert.",
                            brand="Ostrand",
                            uvp="239.00",
                        ),
                    ],
                    "ol-sub-lautsprecher",
                ),
                (
                    "Kameras & Studio",
                    "kameras",
                    [
                        _p(
                            "Systemkamera Kamira X20",
                            "549.00",
                            "24 MP APS-C, 4K-Video, mit 16–50 mm Objektiv. Auslösungen unter 900.",
                            "ol-camera",
                            stock=5,
                            condition="retoure",
                            note="Auslösungen unter 900, Sensor gereinigt.",
                            brand="Kamira",
                            uvp="899.00",
                        ),
                        _p(
                            "Objektiv Kamira 50 mm f/1.8",
                            "129.00",
                            "Die Festbrennweite für Porträts — lichtstark und leicht.",
                            "ol-camera-lens",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Kamira",
                            uvp="229.00",
                        ),
                        _p(
                            "Action-Cam Vireo Go 4K",
                            "99.00",
                            "Wasserdicht bis 10 m ohne Gehäuse, Bildstabilisierung, zwei Akkus.",
                            "ol-action-cam",
                            stock=2,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Vireo",
                            uvp="189.00",
                        ),
                        _p(
                            "Stativ Halden Travel",
                            "39.90",
                            "Aluminium, 1,55 m Auszug, Kugelkopf, Transporttasche dabei.",
                            "ol-tripod",
                            stock=6,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Halden",
                            uvp="74.90",
                        ),
                        _p(
                            "Kameratasche Marlow Schutz",
                            "29.90",
                            "Gepolstert, für Body und zwei Objektive, wasserabweisend.",
                            "ol-camera-bag",
                            stock=1,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Marlow",
                            uvp="59.90",
                        ),
                        _p(
                            "Sofortbildkamera Lumeo Print",
                            "59.90",
                            "Fotos zum Anfassen, zehn Blatt Papier liegen bei.",
                            "ol-instant-camera",
                            variants=[
                                {"color": "Weiß", "price": "59.90", "stock": 4},
                                {"color": "Mint", "price": "59.90", "stock": 2},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Lumeo",
                            uvp="109.00",
                        ),
                        _p(
                            "Ringlicht Ostrand Stream",
                            "24.90",
                            "26 cm, drei Lichtfarben, Handyhalter und Stativ dabei.",
                            "ol-ring-light",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Ostrand",
                            uvp="49.90",
                        ),
                        _p(
                            "Mikrofon Bragg Podcast",
                            "49.90",
                            "USB-Kondensator, Nierencharakteristik, Tischstativ mit Spinne.",
                            "ol-microphone",
                            stock=3,
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Bragg",
                            uvp="99.00",
                        ),
                    ],
                    "ol-sub-kameras",
                ),
            ],
            "Fernseher, Klang und Kameras — Ausstellungsstücke und Retouren aus dem Elektrofachhandel, geprüft und mit Restgarantie.",
            "",
            "ol-cat-tv",
        ),
        (
            "Haushalt & Küche",
            "haushalt-kueche",
            [],
            [
                (
                    "Kaffee & Frühstück",
                    "kaffee",
                    [
                        _p(
                            "Kaffeevollautomat Ostrand Barista",
                            "399.00",
                            "Mahlwerk aus Keramik, Milchsystem, zehn Getränke auf Knopfdruck.",
                            "ol-coffee-machine",
                            stock=3,
                            condition="ausstellung",
                            note="Showroom-Gerät: aufgebaut gestanden, voll funktionsfähig.",
                            brand="Ostrand",
                            uvp="699.00",
                        ),
                        _p(
                            "Siebträger Bragg Espresso Pro",
                            "199.00",
                            "15 bar, Doppelsieb, Dampflanze. Retoure mit Entkalkungsservice.",
                            "ol-espresso",
                            stock=1,
                            condition="retoure",
                            note="Entkalkt und mit neuer Dichtung ausgeliefert.",
                            brand="Bragg",
                            uvp="349.00",
                        ),
                        _p(
                            "Filterkaffeemaschine Halden Morgen",
                            "34.90",
                            "1,25 l Glaskanne, Timer, Warmhalteplatte.",
                            "ol-filter-coffee",
                            stock=5,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Halden",
                            uvp="64.90",
                        ),
                        _p(
                            "Wasserkocher Lumeo Temp",
                            "27.90",
                            "Temperaturwahl von 40 bis 100 °C, Edelstahl, 1,7 l.",
                            "ol-kettle",
                            stock=2,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Lumeo",
                            uvp="49.90",
                        ),
                        _p(
                            "Toaster Halden Duo",
                            "22.90",
                            "Zwei lange Schlitze, Brötchenaufsatz, Krümelschublade.",
                            "ol-toaster",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Halden",
                            uvp="42.90",
                        ),
                    ],
                    "ol-sub-kaffee",
                ),
                (
                    "Küchengeräte",
                    "kuechengeraete",
                    [
                        _p(
                            "Standmixer Ostrand Power 1200",
                            "59.90",
                            "1200 W, Tritan-Behälter 1,8 l, Smoothie- und Ice-Crush-Programm.",
                            "ol-blender",
                            stock=2,
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Ostrand",
                            uvp="109.00",
                        ),
                        _p(
                            "Heißluftfritteuse Lumeo Air 5,5 l",
                            "69.90",
                            "Für vier Personen, acht Programme, herausnehmbarer Korb.",
                            "ol-airfryer",
                            stock=6,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Lumeo",
                            uvp="129.00",
                        ),
                        _p(
                            "Küchenmaschine Bragg Chef",
                            "179.00",
                            "Planetenrührwerk, 5,5 l Edelstahlschüssel, drei Werkzeuge.",
                            "ol-mixer",
                            variants=[
                                {"color": "Creme", "price": "179.00", "stock": 1},
                                {"color": "Anthrazit", "price": "179.00", "stock": 3},
                            ],
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Bragg",
                            uvp="329.00",
                        ),
                        _p(
                            "Stabmixer Halden Stick",
                            "24.90",
                            "800 W, Edelstahlfuß, mit Zerkleinerer und Schneebesen.",
                            "ol-hand-blender",
                            stock=3,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Halden",
                            uvp="44.90",
                        ),
                        _p(
                            "Mikrowelle Nordvolt Solo 20 l",
                            "64.90",
                            "20 l Garraum, 700 W, Auftauprogramm. Neu, Karton eingedrückt.",
                            "ol-microwave",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Nordvolt",
                            uvp="119.00",
                        ),
                    ],
                    "ol-sub-kuechengeraete",
                ),
                (
                    "Reinigen",
                    "reinigen",
                    [
                        _p(
                            "Akku-Staubsauger Ferrit Sweep",
                            "129.00",
                            "Beutellos, 45 Minuten Laufzeit, Elektrobürste und Fugendüse.",
                            "ol-vacuum-stick",
                            stock=4,
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Ferrit",
                            uvp="229.00",
                        ),
                        _p(
                            "Saugroboter Vireo Round",
                            "179.00",
                            "Laser-Navigation, Wischfunktion, App-Steuerung. Vorführgerät.",
                            "ol-robot-vacuum",
                            stock=1,
                            condition="ausstellung",
                            note="Vorführgerät, Bürsten und Filter erneuert.",
                            brand="Vireo",
                            uvp="349.00",
                        ),
                        _p(
                            "Dampfreiniger Ostrand Clean",
                            "79.00",
                            "Ohne Chemie gegen Fett und Keime, mit acht Aufsätzen.",
                            "ol-steam-cleaner",
                            stock=5,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ostrand",
                            uvp="139.00",
                        ),
                        _p(
                            "Dampfbügelstation Halden Press",
                            "89.00",
                            "6 bar Druck, 1,4 l Tank, Kalkschutzsystem.",
                            "ol-iron",
                            stock=3,
                            condition="wie_neu",
                            note="Entkalkt, Sohle ohne Kratzer.",
                            brand="Halden",
                            uvp="169.00",
                        ),
                    ],
                    "ol-sub-reinigen",
                ),
                (
                    "Körperpflege",
                    "pflege",
                    [
                        _p(
                            "Haartrockner Silvana Ion",
                            "34.90",
                            "2200 W, Ionen-Funktion, Diffusor und zwei Düsen.",
                            "ol-hairdryer",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Silvana",
                            uvp="64.90",
                        ),
                        _p(
                            "Rasierer Bragg Clean 5",
                            "59.90",
                            "Nass und trocken, Reinigungsstation, 60 Minuten Laufzeit.",
                            "ol-shaver",
                            stock=6,
                            condition="retoure",
                            note="Funktionstest bestanden, Zubehör vollständig.",
                            brand="Bragg",
                            uvp="109.00",
                        ),
                        _p(
                            "Schallzahnbürste Lumeo Smile",
                            "39.90",
                            "Fünf Programme, Drucksensor, Reiseetui und zwei Bürstenköpfe.",
                            "ol-toothbrush",
                            variants=[
                                {"color": "Weiß", "price": "39.90", "stock": 1},
                                {"color": "Schwarz", "price": "39.90", "stock": 4},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Lumeo",
                            uvp="79.00",
                        ),
                        _p(
                            "Glätteisen Silvana Glatt",
                            "29.90",
                            "Keramikplatten, 15 Sekunden aufgeheizt, Abschaltautomatik.",
                            "ol-hair-straightener",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Silvana",
                            uvp="59.90",
                        ),
                        _p(
                            "Körperwaage Lumeo Body",
                            "24.90",
                            "Misst Gewicht, Fett- und Wasseranteil, App-Verlauf.",
                            "ol-scale",
                            stock=2,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Lumeo",
                            uvp="49.90",
                        ),
                        _p(
                            "Massagepistole Ferrit Relax",
                            "49.90",
                            "Sechs Aufsätze, fünf Stufen, leiser Bürstenlosmotor.",
                            "ol-massage-gun",
                            stock=3,
                            condition="retoure",
                            note="Funktionstest bestanden, Zubehör vollständig.",
                            brand="Ferrit",
                            uvp="99.00",
                        ),
                    ],
                    "ol-sub-pflege",
                ),
            ],
            "Küchengeräte und Haushaltshelfer aus Vorführung und Retoure — gereinigt, funktionsgeprüft, oft nur der Karton ist unterwegs beschädigt worden.",
            "",
            "ol-cat-haushalt",
        ),
        (
            "Gaming & Smart Home",
            "gaming-smarthome",
            [],
            [
                (
                    "Gaming",
                    "gaming",
                    [
                        _p(
                            "Controller Ferrit Grip Wireless",
                            "39.90",
                            "Bluetooth, Hall-Sensor-Sticks, austauschbare Kappen.",
                            "ol-controller",
                            variants=[
                                {"color": "Schwarz", "price": "39.90", "stock": 3},
                                {"color": "Weiß", "price": "39.90", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ferrit",
                            uvp="74.90",
                        ),
                        _p(
                            "Gaming-Headset Ferrit Sound 7.1",
                            "49.90",
                            "Virtueller Raumklang, abnehmbares Mikrofon, Memory-Foam-Polster.",
                            "ol-gaming-headset",
                            stock=1,
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Ferrit",
                            uvp="99.00",
                        ),
                        _p(
                            "Gaming-Maus Ferrit Snap 8K",
                            "34.90",
                            "26 000 dpi, 58 g leicht, sechs programmierbare Tasten.",
                            "ol-gaming-mouse",
                            stock=5,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Ferrit",
                            uvp="69.00",
                        ),
                        _p(
                            "Gaming-Stuhl Ostrand Race",
                            "149.00",
                            "Wippmechanik, Lordosenkissen, bis 120 kg. Ausstellungsstück.",
                            "ol-gaming-chair",
                            variants=[
                                {"color": "Schwarz-Rot", "price": "149.00", "stock": 2},
                                {"color": "Schwarz-Grau", "price": "149.00", "stock": 4},
                            ],
                            condition="ausstellung",
                            note="Bezug ohne Beschädigung.",
                            brand="Ostrand",
                            uvp="279.00",
                        ),
                        _p(
                            "XXL-Mauspad Ferrit Desk",
                            "14.90",
                            "90 × 40 cm, vernähter Rand, rutschfeste Unterseite.",
                            "ol-gaming-pad",
                            stock=4,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Ferrit",
                            uvp="27.90",
                        ),
                    ],
                    "ol-sub-gaming",
                ),
                (
                    "Smart Home",
                    "smart-home",
                    [
                        _p(
                            "Smart-Lautsprecher Lumeo Voice",
                            "39.90",
                            "Sprachsteuerung, Multiroom, Aux-Ausgang für alte Anlagen.",
                            "ol-smart-speaker",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Lumeo",
                            uvp="79.00",
                        ),
                        _p(
                            "Smart-Steckdose Vireo Plug (4er)",
                            "24.90",
                            "Verbrauch messen, Zeitpläne, funktioniert ohne Bridge.",
                            "ol-smart-plug",
                            stock=6,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Vireo",
                            uvp="49.90",
                        ),
                        _p(
                            "Heizkörperthermostat Vireo Warm (3er)",
                            "59.90",
                            "Spart spürbar Heizkosten, Fenster-offen-Erkennung, App-Zeitplan.",
                            "ol-smart-thermostat",
                            stock=1,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Vireo",
                            uvp="109.00",
                        ),
                        _p(
                            "Video-Türklingel Ostrand Ring",
                            "79.00",
                            "1080p, Bewegungserkennung, Gegensprechfunktion, Akkubetrieb.",
                            "ol-doorbell",
                            stock=3,
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Ostrand",
                            uvp="149.00",
                        ),
                        _p(
                            "Innenkamera Vireo Watch",
                            "34.90",
                            "Schwenkbar, Nachtsicht, lokale Aufnahme auf SD-Karte.",
                            "ol-camera-indoor",
                            stock=2,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Vireo",
                            uvp="64.90",
                        ),
                    ],
                    "ol-sub-smarthome",
                ),
                (
                    "Licht & Zubehör",
                    "beleuchtung",
                    [
                        _p(
                            "Smarte Lampe Lumeo Color (3er)",
                            "29.90",
                            "16 Millionen Farben, dimmbar, E27 — direkt per WLAN.",
                            "ol-smart-bulb",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Lumeo",
                            uvp="59.90",
                        ),
                        _p(
                            "LED-Streifen Lumeo Line 5 m",
                            "19.90",
                            "Selbstklebend, kürzbar, mit Fernbedienung und Netzteil.",
                            "ol-led-strip",
                            stock=1,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Lumeo",
                            uvp="39.90",
                        ),
                        _p(
                            "Schreibtischlampe Halden Focus",
                            "27.90",
                            "Stufenlos dimmbar, Farbtemperatur einstellbar, USB-Ladeport.",
                            "ol-desk-lamp",
                            variants=[
                                {"color": "Weiß", "price": "27.90", "stock": 5},
                                {"color": "Schwarz", "price": "27.90", "stock": 3},
                            ],
                            condition="ausstellung",
                            note="Showroom-Gerät: aufgebaut gestanden, voll funktionsfähig.",
                            brand="Halden",
                            uvp="54.90",
                        ),
                        _p(
                            "Beamer Ferrit Cine Mini",
                            "179.00",
                            "Full HD, Autofokus, WLAN — Kinoabend an jeder weißen Wand.",
                            "ol-projector",
                            stock=3,
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Ferrit",
                            uvp="329.00",
                        ),
                        _p(
                            "Stehleuchte Halden Bogen",
                            "69.90",
                            "Bogenlampe mit Marmorfuß, dimmbar, warmweiß.",
                            "ol-floor-lamp",
                            stock=2,
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Halden",
                            uvp="139.00",
                        ),
                        _p(
                            "Nachtlicht Lumeo Sanft (2er)",
                            "12.90",
                            "Bewegungssensor, warmes Licht, Akku mit Magnethalter.",
                            "ol-night-light",
                            stock=6,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Lumeo",
                            uvp="24.90",
                        ),
                        _p(
                            "Türschloss Vireo Key",
                            "99.00",
                            "Nachrüstbar ohne Bohren, Fingerabdruck und App, Notschlüssel.",
                            "ol-smart-lock",
                            stock=1,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Vireo",
                            uvp="189.00",
                        ),
                        _p(
                            "Sensor-Set Vireo Sicher (5er)",
                            "39.90",
                            "Tür- und Fensterkontakte mit Push-Nachricht, Batterie 2 Jahre.",
                            "ol-sensor-set",
                            stock=4,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Vireo",
                            uvp="79.00",
                        ),
                        _p(
                            "VR-Brille Ferrit View",
                            "199.00",
                            "Autarke Brille, zwei Controller, Trageband gepolstert.",
                            "ol-vr-headset",
                            stock=2,
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Ferrit",
                            uvp="379.00",
                        ),
                        _p(
                            "Konsolen-Ständer Ostrand Cool",
                            "22.90",
                            "Vertikaler Halter mit Lüfter und vier USB-Ports.",
                            "ol-console-stand",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ostrand",
                            uvp="44.90",
                        ),
                    ],
                    "ol-sub-licht",
                ),
            ],
            "Konsolen-Zubehör, Gaming-Hardware und vernetzte Technik fürs Zuhause — Restposten aus Sortimentswechseln.",
            "",
            "ol-cat-gaming",
        ),
        (
            "Damenmode",
            "damenmode",
            [],
            [
                (
                    "Jacken & Mäntel",
                    "damen-jacken",
                    [
                        _p(
                            "Wollmantel Traverso Nord",
                            "119.00",
                            "Klassischer Mantel aus Wollmischgewebe, gefüttert, verdeckte Knopfleiste.",
                            "ol-w-coat",
                            variants=[
                                {"size": "36", "color": "Camel", "price": "119.00", "stock": 3},
                                {"size": "38", "color": "Camel", "price": "119.00", "stock": 1},
                                {"size": "40", "color": "Camel", "price": "119.00", "stock": 5},
                                {"size": "42", "color": "Camel", "price": "119.00", "stock": 2},
                                {"size": "36", "color": "Anthrazit", "price": "119.00", "stock": 4},
                                {"size": "38", "color": "Anthrazit", "price": "119.00", "stock": 2},
                                {"size": "40", "color": "Anthrazit", "price": "119.00", "stock": 6},
                                {"size": "42", "color": "Anthrazit", "price": "119.00", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Musterteil aus der Kollektion, ungetragen.",
                            brand="Traverso",
                            uvp="249.00",
                        ),
                        _p(
                            "Steppjacke Ahlberg Light",
                            "69.90",
                            "Leicht, wärmend, packbar auf Faustgröße. Recycelte Füllung.",
                            "ol-w-puffer",
                            variants=[
                                {"size": "S", "color": "Schwarz", "price": "69.90", "stock": 1},
                                {"size": "M", "color": "Schwarz", "price": "69.90", "stock": 5},
                                {"size": "L", "color": "Schwarz", "price": "69.90", "stock": 2},
                                {"size": "S", "color": "Salbei", "price": "69.90", "stock": 4},
                                {"size": "M", "color": "Salbei", "price": "69.90", "stock": 2},
                                {"size": "L", "color": "Salbei", "price": "69.90", "stock": 6},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Ahlberg",
                            uvp="139.00",
                        ),
                        _p(
                            "Trenchcoat Silvana Regen",
                            "89.00",
                            "Wasserabweisende Baumwolle, Gürtel, Schulterklappen.",
                            "ol-w-trench",
                            variants=[
                                {"size": "36", "price": "89.00", "stock": 5},
                                {"size": "38", "price": "89.00", "stock": 2},
                                {"size": "40", "price": "89.00", "stock": 4},
                            ],
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Silvana",
                            uvp="179.00",
                        ),
                        _p(
                            "Blazer Brentwood Office",
                            "59.90",
                            "Taillierter Schnitt, zwei Knöpfe, leicht elastisch.",
                            "ol-w-blazer",
                            variants=[
                                {"size": "36", "color": "Marine", "price": "59.90", "stock": 2},
                                {"size": "38", "color": "Marine", "price": "59.90", "stock": 4},
                                {"size": "40", "color": "Marine", "price": "59.90", "stock": 2},
                                {"size": "42", "color": "Marine", "price": "59.90", "stock": 6},
                                {"size": "36", "color": "Schwarz", "price": "59.90", "stock": 1},
                                {"size": "38", "color": "Schwarz", "price": "59.90", "stock": 3},
                                {"size": "40", "color": "Schwarz", "price": "59.90", "stock": 2},
                                {"size": "42", "color": "Schwarz", "price": "59.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Brentwood",
                            uvp="119.00",
                        ),
                    ],
                    "ol-sub-damen-jacken",
                ),
                (
                    "Oberteile",
                    "damen-oberteile",
                    [
                        _p(
                            "Bluse Silvana Leinen",
                            "34.90",
                            "Reines Leinen, luftiger Schnitt, Perlmuttknöpfe.",
                            "ol-w-blouse",
                            variants=[
                                {"size": "34", "color": "Weiß", "price": "34.90", "stock": 4},
                                {"size": "36", "color": "Weiß", "price": "34.90", "stock": 2},
                                {"size": "38", "color": "Weiß", "price": "34.90", "stock": 6},
                                {"size": "40", "color": "Weiß", "price": "34.90", "stock": 1},
                                {"size": "34", "color": "Sand", "price": "34.90", "stock": 3},
                                {"size": "36", "color": "Sand", "price": "34.90", "stock": 2},
                                {"size": "38", "color": "Sand", "price": "34.90", "stock": 4},
                                {"size": "40", "color": "Sand", "price": "34.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Silvana",
                            uvp="69.90",
                        ),
                        _p(
                            "T-Shirt Kastanie Bio (2er-Pack)",
                            "19.90",
                            "Bio-Baumwolle, Rundhals, zwei Farben im Set.",
                            "ol-w-shirt",
                            variants=[
                                {"size": "XS", "price": "19.90", "stock": 2},
                                {"size": "S", "price": "19.90", "stock": 6},
                                {"size": "M", "price": "19.90", "stock": 1},
                                {"size": "L", "price": "19.90", "stock": 3},
                                {"size": "XL", "price": "19.90", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Kastanie",
                            uvp="39.90",
                        ),
                        _p(
                            "Feinstrickpullover Traverso Wolke",
                            "44.90",
                            "Merinomischung, weich und formstabil, Rundhals.",
                            "ol-w-knit",
                            variants=[
                                {"size": "S", "color": "Creme", "price": "44.90", "stock": 6},
                                {"size": "M", "color": "Creme", "price": "44.90", "stock": 1},
                                {"size": "L", "color": "Creme", "price": "44.90", "stock": 3},
                                {"size": "S", "color": "Rosé", "price": "44.90", "stock": 2},
                                {"size": "M", "color": "Rosé", "price": "44.90", "stock": 4},
                                {"size": "L", "color": "Rosé", "price": "44.90", "stock": 1},
                            ],
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Traverso",
                            uvp="89.90",
                        ),
                        _p(
                            "Strickjacke Ahlberg Lang",
                            "49.90",
                            "Longcardigan mit Taschen, offene Front.",
                            "ol-w-cardigan",
                            variants=[
                                {"size": "S", "price": "49.90", "stock": 1},
                                {"size": "M", "price": "49.90", "stock": 3},
                                {"size": "L", "price": "49.90", "stock": 2},
                                {"size": "XL", "price": "49.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ahlberg",
                            uvp="99.00",
                        ),
                    ],
                    "ol-sub-damen-oberteile",
                ),
                (
                    "Hosen & Kleider",
                    "damen-hosen",
                    [
                        _p(
                            "Jeans Ruhrtal High Waist",
                            "39.90",
                            "Stretch-Denim, gerades Bein, hoher Bund.",
                            "ol-w-jeans",
                            variants=[
                                {"size": "26", "color": "Blau", "price": "39.90", "stock": 3},
                                {"size": "27", "color": "Blau", "price": "39.90", "stock": 2},
                                {"size": "28", "color": "Blau", "price": "39.90", "stock": 4},
                                {"size": "29", "color": "Blau", "price": "39.90", "stock": 1},
                                {"size": "30", "color": "Blau", "price": "39.90", "stock": 5},
                                {"size": "26", "color": "Schwarz", "price": "39.90", "stock": 3},
                                {"size": "27", "color": "Schwarz", "price": "39.90", "stock": 2},
                                {"size": "28", "color": "Schwarz", "price": "39.90", "stock": 6},
                                {"size": "29", "color": "Schwarz", "price": "39.90", "stock": 1},
                                {"size": "30", "color": "Schwarz", "price": "39.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ruhrtal",
                            uvp="79.90",
                        ),
                        _p(
                            "Kleid Silvana Sommer",
                            "44.90",
                            "Midi-Länge aus Viskose, fließender Fall, Taillenband.",
                            "ol-w-dress",
                            variants=[
                                {"size": "36", "color": "Blau", "price": "44.90", "stock": 2},
                                {"size": "38", "color": "Blau", "price": "44.90", "stock": 4},
                                {"size": "40", "color": "Blau", "price": "44.90", "stock": 1},
                                {"size": "36", "color": "Bordeaux", "price": "44.90", "stock": 5},
                                {"size": "38", "color": "Bordeaux", "price": "44.90", "stock": 3},
                                {"size": "40", "color": "Bordeaux", "price": "44.90", "stock": 2},
                            ],
                            condition="ausstellung",
                            note="Leichte Lagerspuren am Gehäuse.",
                            brand="Silvana",
                            uvp="89.90",
                        ),
                        _p(
                            "Rock Brentwood Plissee",
                            "34.90",
                            "Plissee-Midirock mit elastischem Bund.",
                            "ol-w-skirt",
                            variants=[
                                {"size": "36", "price": "34.90", "stock": 4},
                                {"size": "38", "price": "34.90", "stock": 1},
                                {"size": "40", "price": "34.90", "stock": 5},
                                {"size": "42", "price": "34.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Brentwood",
                            uvp="69.90",
                        ),
                        _p(
                            "Stoffhose Marlow Fließend",
                            "39.90",
                            "Weiter Schnitt, Bundfalten, angenehm kühl.",
                            "ol-w-trousers",
                            variants=[
                                {"size": "36", "color": "Schwarz", "price": "39.90", "stock": 1},
                                {"size": "38", "color": "Schwarz", "price": "39.90", "stock": 5},
                                {"size": "40", "color": "Schwarz", "price": "39.90", "stock": 3},
                                {"size": "36", "color": "Beige", "price": "39.90", "stock": 2},
                                {"size": "38", "color": "Beige", "price": "39.90", "stock": 6},
                                {"size": "40", "color": "Beige", "price": "39.90", "stock": 1},
                            ],
                            condition="wie_neu",
                            note="Ungetragen, Etikett fehlt.",
                            brand="Marlow",
                            uvp="79.00",
                        ),
                    ],
                    "ol-sub-damen-hosen",
                ),
                (
                    "Wäsche & Homewear",
                    "damen-waesche",
                    [
                        _p(
                            "Homewear-Set Kastanie Weich",
                            "34.90",
                            "Sweatshirt und Hose aus Bio-Baumwolle — der Feierabend-Zweiteiler.",
                            "ol-w-lounge",
                            variants=[
                                {"size": "S", "color": "Grau", "price": "34.90", "stock": 5},
                                {"size": "M", "color": "Grau", "price": "34.90", "stock": 3},
                                {"size": "L", "color": "Grau", "price": "34.90", "stock": 2},
                                {"size": "S", "color": "Altrosa", "price": "34.90", "stock": 6},
                                {"size": "M", "color": "Altrosa", "price": "34.90", "stock": 1},
                                {"size": "L", "color": "Altrosa", "price": "34.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Kastanie",
                            uvp="69.90",
                        ),
                        _p(
                            "Socken Fenja Merino (5er-Pack)",
                            "19.90",
                            "Merinowolle, verstärkte Ferse, ohne drückende Naht.",
                            "ol-w-socks",
                            variants=[
                                {"size": "35-38", "price": "19.90", "stock": 3},
                                {"size": "39-42", "price": "19.90", "stock": 2},
                                {"size": "43-46", "price": "19.90", "stock": 6},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Fenja",
                            uvp="34.90",
                        ),
                        _p(
                            "Bademantel Fenja Frottee",
                            "39.90",
                            "Baumwollfrottee 400 g/m², Kapuze, zwei Taschen.",
                            "ol-w-bathrobe",
                            variants=[
                                {"size": "S/M", "price": "39.90", "stock": 2},
                                {"size": "L/XL", "price": "39.90", "stock": 6},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Fenja",
                            uvp="79.00",
                        ),
                        _p(
                            "Schal & Mütze Traverso (Set)",
                            "24.90",
                            "Grobstrick-Set aus Wollmischung, weich gefüttert.",
                            "ol-w-scarf-set",
                            variants=[
                                {"color": "Grau", "price": "24.90", "stock": 6},
                                {"color": "Beere", "price": "24.90", "stock": 1},
                            ],
                            condition="retoure",
                            note="Funktionstest bestanden, Zubehör vollständig.",
                            brand="Traverso",
                            uvp="49.90",
                        ),
                        _p(
                            "Pyjama Fenja Baumwolle",
                            "29.90",
                            "Langarm und lange Hose, weiche Baumwolle mit Elastikbund.",
                            "ol-w-pyjama",
                            variants=[
                                {"size": "S", "price": "29.90", "stock": 1},
                                {"size": "M", "price": "29.90", "stock": 4},
                                {"size": "L", "price": "29.90", "stock": 2},
                                {"size": "XL", "price": "29.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Fenja",
                            uvp="59.90",
                        ),
                        _p(
                            "Strumpfhose Silvana 60 den (3er)",
                            "16.90",
                            "Blickdicht, formender Bund, drei Stück im Set.",
                            "ol-w-tights",
                            variants=[
                                {"size": "S", "price": "16.90", "stock": 4},
                                {"size": "M", "price": "16.90", "stock": 2},
                                {"size": "L", "price": "16.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Silvana",
                            uvp="32.90",
                        ),
                        _p(
                            "Trägertop Kastanie Bio (2er)",
                            "17.90",
                            "Bio-Baumwolle mit Elasthan, verstellbare Träger.",
                            "ol-w-vest-top",
                            variants=[
                                {"size": "S", "color": "Weiß", "price": "17.90", "stock": 2},
                                {"size": "M", "color": "Weiß", "price": "17.90", "stock": 3},
                                {"size": "L", "color": "Weiß", "price": "17.90", "stock": 3},
                                {"size": "S", "color": "Schwarz", "price": "17.90", "stock": 1},
                                {"size": "M", "color": "Schwarz", "price": "17.90", "stock": 5},
                                {"size": "L", "color": "Schwarz", "price": "17.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Kastanie",
                            uvp="34.90",
                        ),
                        _p(
                            "Wollmütze Traverso Rippe",
                            "16.90",
                            "Doppellagige Rippenstrickmütze aus Merino.",
                            "ol-w-hat",
                            variants=[
                                {"color": "Anthrazit", "price": "16.90", "stock": 3},
                                {"color": "Camel", "price": "16.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Traverso",
                            uvp="32.90",
                        ),
                    ],
                    "ol-sub-damen-waesche",
                ),
            ],
            "Musterteile, Überhänge und Vorsaison-Ware aus europäischen Manufakturen — Größen begrenzt, Preise dauerhaft reduziert.",
            "",
            "ol-cat-damen",
        ),
        (
            "Herrenmode",
            "herrenmode",
            [],
            [
                (
                    "Jacken",
                    "herren-jacken",
                    [
                        _p(
                            "Übergangsjacke Ahlberg Feld",
                            "79.00",
                            "Wasserabweisend, Stehkragen, vier Taschen.",
                            "ol-m-jacket",
                            variants=[
                                {"size": "M", "color": "Oliv", "price": "79.00", "stock": 3},
                                {"size": "L", "color": "Oliv", "price": "79.00", "stock": 1},
                                {"size": "XL", "color": "Oliv", "price": "79.00", "stock": 5},
                                {"size": "M", "color": "Navy", "price": "79.00", "stock": 2},
                                {"size": "L", "color": "Navy", "price": "79.00", "stock": 4},
                                {"size": "XL", "color": "Navy", "price": "79.00", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ahlberg",
                            uvp="159.00",
                        ),
                        _p(
                            "Steppjacke Brentwood Winter",
                            "89.00",
                            "Warme Kunstfaserfüllung, abnehmbare Kapuze.",
                            "ol-m-puffer",
                            variants=[
                                {"size": "M", "color": "Schwarz", "price": "89.00", "stock": 1},
                                {"size": "L", "color": "Schwarz", "price": "89.00", "stock": 5},
                                {"size": "XL", "color": "Schwarz", "price": "89.00", "stock": 2},
                                {"size": "XXL", "color": "Schwarz", "price": "89.00", "stock": 4},
                                {"size": "M", "color": "Anthrazit", "price": "89.00", "stock": 2},
                                {"size": "L", "color": "Anthrazit", "price": "89.00", "stock": 6},
                                {"size": "XL", "color": "Anthrazit", "price": "89.00", "stock": 1},
                                {"size": "XXL", "color": "Anthrazit", "price": "89.00", "stock": 3},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Brentwood",
                            uvp="179.00",
                        ),
                        _p(
                            "Sakko Traverso Wolle",
                            "99.00",
                            "Halbgefüttert, Schurwollmischung, moderne Passform.",
                            "ol-m-blazer",
                            variants=[
                                {"size": "48", "price": "99.00", "stock": 5},
                                {"size": "50", "price": "99.00", "stock": 2},
                                {"size": "52", "price": "99.00", "stock": 4},
                                {"size": "54", "price": "99.00", "stock": 2},
                            ],
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Traverso",
                            uvp="199.00",
                        ),
                        _p(
                            "Weste Ruhrtal Stepp",
                            "49.90",
                            "Leichte Steppweste für die Übergangszeit, Stehkragen.",
                            "ol-m-vest",
                            variants=[
                                {"size": "M", "price": "49.90", "stock": 2},
                                {"size": "L", "price": "49.90", "stock": 4},
                                {"size": "XL", "price": "49.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Ruhrtal",
                            uvp="99.00",
                        ),
                    ],
                    "ol-sub-herren-jacken",
                ),
                (
                    "Hemden & Shirts",
                    "herren-hemden",
                    [
                        _p(
                            "Hemd Brentwood Oxford",
                            "29.90",
                            "Oxford-Baumwolle, Button-Down-Kragen, bügelleicht.",
                            "ol-m-oxfordhemd",
                            variants=[
                                {"size": "39", "color": "Weiß", "price": "29.90", "stock": 4},
                                {"size": "40", "color": "Weiß", "price": "29.90", "stock": 2},
                                {"size": "41", "color": "Weiß", "price": "29.90", "stock": 6},
                                {"size": "42", "color": "Weiß", "price": "29.90", "stock": 1},
                                {"size": "43", "color": "Weiß", "price": "29.90", "stock": 3},
                                {"size": "39", "color": "Hellblau", "price": "29.90", "stock": 2},
                                {"size": "40", "color": "Hellblau", "price": "29.90", "stock": 4},
                                {"size": "41", "color": "Hellblau", "price": "29.90", "stock": 1},
                                {"size": "42", "color": "Hellblau", "price": "29.90", "stock": 5},
                                {"size": "43", "color": "Hellblau", "price": "29.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Brentwood",
                            uvp="59.90",
                        ),
                        _p(
                            "Poloshirt Marlow Piqué",
                            "24.90",
                            "Klassisches Piqué aus Baumwolle, Knopfleiste mit drei Knöpfen.",
                            "ol-m-polo",
                            variants=[
                                {"size": "M", "color": "Navy", "price": "24.90", "stock": 2},
                                {"size": "L", "color": "Navy", "price": "24.90", "stock": 6},
                                {"size": "XL", "color": "Navy", "price": "24.90", "stock": 1},
                                {"size": "M", "color": "Weiß", "price": "24.90", "stock": 3},
                                {"size": "L", "color": "Weiß", "price": "24.90", "stock": 2},
                                {"size": "XL", "color": "Weiß", "price": "24.90", "stock": 4},
                                {"size": "M", "color": "Grün", "price": "24.90", "stock": 1},
                                {"size": "L", "color": "Grün", "price": "24.90", "stock": 5},
                                {"size": "XL", "color": "Grün", "price": "24.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Marlow",
                            uvp="49.90",
                        ),
                        _p(
                            "T-Shirt Kastanie Basic (3er-Pack)",
                            "22.90",
                            "Drei Shirts aus Bio-Baumwolle, Rundhals, mittelschwer.",
                            "ol-m-tshirt",
                            variants=[
                                {"size": "S", "price": "22.90", "stock": 6},
                                {"size": "M", "price": "22.90", "stock": 1},
                                {"size": "L", "price": "22.90", "stock": 3},
                                {"size": "XL", "price": "22.90", "stock": 2},
                                {"size": "XXL", "price": "22.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Kastanie",
                            uvp="44.90",
                        ),
                        _p(
                            "Flanellhemd Ruhrtal Karo",
                            "34.90",
                            "Weich angeraut, klassisches Karo, Brusttasche.",
                            "ol-m-flannel",
                            variants=[
                                {"size": "M", "color": "Rot", "price": "34.90", "stock": 1},
                                {"size": "L", "color": "Rot", "price": "34.90", "stock": 3},
                                {"size": "XL", "color": "Rot", "price": "34.90", "stock": 2},
                                {"size": "M", "color": "Blau", "price": "34.90", "stock": 4},
                                {"size": "L", "color": "Blau", "price": "34.90", "stock": 1},
                                {"size": "XL", "color": "Blau", "price": "34.90", "stock": 5},
                            ],
                            condition="wie_neu",
                            note="Einmal gewaschen, ohne Gebrauchsspuren.",
                            brand="Ruhrtal",
                            uvp="69.90",
                        ),
                    ],
                    "ol-sub-herren-hemden",
                ),
                (
                    "Hosen",
                    "herren-hosen",
                    [
                        _p(
                            "Jeans Ruhrtal Straight",
                            "44.90",
                            "Gerades Bein, fester Denim mit leichtem Stretch.",
                            "ol-m-jeans",
                            variants=[
                                {"size": "31/32", "color": "Blau", "price": "44.90", "stock": 3},
                                {"size": "32/32", "color": "Blau", "price": "44.90", "stock": 2},
                                {"size": "33/34", "color": "Blau", "price": "44.90", "stock": 4},
                                {"size": "34/34", "color": "Blau", "price": "44.90", "stock": 1},
                                {"size": "36/34", "color": "Blau", "price": "44.90", "stock": 5},
                                {"size": "31/32", "color": "Schwarz", "price": "44.90", "stock": 3},
                                {"size": "32/32", "color": "Schwarz", "price": "44.90", "stock": 2},
                                {"size": "33/34", "color": "Schwarz", "price": "44.90", "stock": 6},
                                {"size": "34/34", "color": "Schwarz", "price": "44.90", "stock": 1},
                                {"size": "36/34", "color": "Schwarz", "price": "44.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ruhrtal",
                            uvp="89.90",
                        ),
                        _p(
                            "Chino Marlow Alltag",
                            "34.90",
                            "Baumwoll-Twill, moderne Passform, angenehm elastisch.",
                            "ol-m-chinos",
                            variants=[
                                {"size": "48", "color": "Beige", "price": "34.90", "stock": 2},
                                {"size": "50", "color": "Beige", "price": "34.90", "stock": 4},
                                {"size": "52", "color": "Beige", "price": "34.90", "stock": 1},
                                {"size": "54", "color": "Beige", "price": "34.90", "stock": 5},
                                {"size": "48", "color": "Navy", "price": "34.90", "stock": 3},
                                {"size": "50", "color": "Navy", "price": "34.90", "stock": 2},
                                {"size": "52", "color": "Navy", "price": "34.90", "stock": 6},
                                {"size": "54", "color": "Navy", "price": "34.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Marlow",
                            uvp="69.90",
                        ),
                        _p(
                            "Jogginghose Kastanie Sweat",
                            "29.90",
                            "Schwerer Sweatstoff, Bündchen, zwei Reißverschlusstaschen.",
                            "ol-m-jogger",
                            variants=[
                                {"size": "M", "price": "29.90", "stock": 4},
                                {"size": "L", "price": "29.90", "stock": 1},
                                {"size": "XL", "price": "29.90", "stock": 5},
                            ],
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Kastanie",
                            uvp="59.90",
                        ),
                        _p(
                            "Shorts Ahlberg Sommer",
                            "24.90",
                            "Leichte Baumwolle, Gürtelschlaufen, Knielänge.",
                            "ol-m-shorts",
                            variants=[
                                {"size": "48", "price": "24.90", "stock": 1},
                                {"size": "50", "price": "24.90", "stock": 5},
                                {"size": "52", "price": "24.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ahlberg",
                            uvp="49.90",
                        ),
                    ],
                    "ol-sub-herren-hosen",
                ),
                (
                    "Strick & Sweat",
                    "herren-strick",
                    [
                        _p(
                            "Pullover Traverso Merino",
                            "54.90",
                            "Feine Merinowolle, Rundhals, formstabile Bündchen.",
                            "ol-m-knit",
                            variants=[
                                {"size": "M", "color": "Grau", "price": "54.90", "stock": 5},
                                {"size": "L", "color": "Grau", "price": "54.90", "stock": 3},
                                {"size": "XL", "color": "Grau", "price": "54.90", "stock": 2},
                                {"size": "M", "color": "Dunkelblau", "price": "54.90", "stock": 6},
                                {"size": "L", "color": "Dunkelblau", "price": "54.90", "stock": 1},
                                {"size": "XL", "color": "Dunkelblau", "price": "54.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Traverso",
                            uvp="109.00",
                        ),
                        _p(
                            "Hoodie Kastanie Heavy",
                            "39.90",
                            "400 g/m² Bio-Baumwolle, Kängurutasche, gefütterte Kapuze.",
                            "ol-m-hoodie",
                            variants=[
                                {"size": "M", "color": "Schwarz", "price": "39.90", "stock": 3},
                                {"size": "L", "color": "Schwarz", "price": "39.90", "stock": 2},
                                {"size": "XL", "color": "Schwarz", "price": "39.90", "stock": 6},
                                {"size": "XXL", "color": "Schwarz", "price": "39.90", "stock": 1},
                                {"size": "M", "color": "Sand", "price": "39.90", "stock": 4},
                                {"size": "L", "color": "Sand", "price": "39.90", "stock": 2},
                                {"size": "XL", "color": "Sand", "price": "39.90", "stock": 3},
                                {"size": "XXL", "color": "Sand", "price": "39.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Kastanie",
                            uvp="79.90",
                        ),
                        _p(
                            "Strickjacke Brentwood Zopf",
                            "59.90",
                            "Zopfmuster, Knopfleiste aus Horn, Wollmischung.",
                            "ol-m-cardigan",
                            variants=[
                                {"size": "M", "price": "59.90", "stock": 2},
                                {"size": "L", "price": "59.90", "stock": 6},
                                {"size": "XL", "price": "59.90", "stock": 1},
                            ],
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Brentwood",
                            uvp="119.00",
                        ),
                        _p(
                            "Socken Fenja Business (6er)",
                            "19.90",
                            "Feine Baumwolle, sechs Paar in drei Tönen, ohne Gummidruck.",
                            "ol-m-socks",
                            variants=[
                                {"size": "39-42", "price": "19.90", "stock": 6},
                                {"size": "43-46", "price": "19.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Fenja",
                            uvp="34.90",
                        ),
                        _p(
                            "Sweatjacke Ruhrtal Zip",
                            "39.90",
                            "Durchgehender Reißverschluss, angeraute Innenseite.",
                            "ol-m-sweatjacket",
                            variants=[
                                {"size": "M", "price": "39.90", "stock": 1},
                                {"size": "L", "price": "39.90", "stock": 4},
                                {"size": "XL", "price": "39.90", "stock": 2},
                                {"size": "XXL", "price": "39.90", "stock": 3},
                            ],
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Ruhrtal",
                            uvp="79.00",
                        ),
                        _p(
                            "Troyer Brentwood Halfzip",
                            "49.90",
                            "Stehkragen mit kurzem Reißverschluss, Baumwollstrick.",
                            "ol-m-halfzip",
                            variants=[
                                {"size": "M", "color": "Beige", "price": "49.90", "stock": 4},
                                {"size": "L", "color": "Beige", "price": "49.90", "stock": 2},
                                {"size": "XL", "color": "Beige", "price": "49.90", "stock": 3},
                                {"size": "M", "color": "Marine", "price": "49.90", "stock": 3},
                                {"size": "L", "color": "Marine", "price": "49.90", "stock": 1},
                                {"size": "XL", "color": "Marine", "price": "49.90", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Brentwood",
                            uvp="99.00",
                        ),
                        _p(
                            "Leinenhemd Marlow Sommer",
                            "39.90",
                            "Reines Leinen, kühlend, mit Kentkragen.",
                            "ol-m-shirt-linen",
                            variants=[
                                {"size": "M", "color": "Weiß", "price": "39.90", "stock": 2},
                                {"size": "L", "color": "Weiß", "price": "39.90", "stock": 3},
                                {"size": "XL", "color": "Weiß", "price": "39.90", "stock": 3},
                                {"size": "M", "color": "Salbei", "price": "39.90", "stock": 1},
                                {"size": "L", "color": "Salbei", "price": "39.90", "stock": 5},
                                {"size": "XL", "color": "Salbei", "price": "39.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Marlow",
                            uvp="79.00",
                        ),
                        _p(
                            "Boxershorts Kastanie (4er)",
                            "24.90",
                            "Bio-Baumwolle mit Elasthan, weicher Webbund, vier Stück.",
                            "ol-m-underwear",
                            variants=[
                                {"size": "M", "price": "24.90", "stock": 3},
                                {"size": "L", "price": "24.90", "stock": 3},
                                {"size": "XL", "price": "24.90", "stock": 1},
                                {"size": "XXL", "price": "24.90", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Kastanie",
                            uvp="44.90",
                        ),
                    ],
                    "ol-sub-herren-strick",
                ),
            ],
            "Hemden, Jacken und Strick aus Restposten — Markenqualität ohne Markenaufschlag, viele Teile nur einmal am Lager.",
            "",
            "ol-cat-herren",
        ),
        (
            "Schuhe",
            "schuhe",
            [],
            [
                (
                    "Sneaker",
                    "sneaker",
                    [
                        _p(
                            "Sneaker Traverso Court",
                            "49.90",
                            "Klassischer Ledersneaker, herausnehmbares Fußbett.",
                            "ol-sneaker-white",
                            variants=[
                                {"size": "40", "color": "Weiß", "price": "49.90", "stock": 3},
                                {"size": "41", "color": "Weiß", "price": "49.90", "stock": 1},
                                {"size": "42", "color": "Weiß", "price": "49.90", "stock": 5},
                                {"size": "43", "color": "Weiß", "price": "49.90", "stock": 2},
                                {"size": "44", "color": "Weiß", "price": "49.90", "stock": 4},
                                {"size": "45", "color": "Weiß", "price": "49.90", "stock": 2},
                                {"size": "40", "color": "Schwarz", "price": "49.90", "stock": 6},
                                {"size": "41", "color": "Schwarz", "price": "49.90", "stock": 1},
                                {"size": "42", "color": "Schwarz", "price": "49.90", "stock": 3},
                                {"size": "43", "color": "Schwarz", "price": "49.90", "stock": 2},
                                {"size": "44", "color": "Schwarz", "price": "49.90", "stock": 4},
                                {"size": "45", "color": "Schwarz", "price": "49.90", "stock": 1},
                            ],
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Traverso",
                            uvp="99.00",
                        ),
                        _p(
                            "Retro-Sneaker Ahlberg 78",
                            "39.90",
                            "Wildleder-Details, Gummisohle mit Waffelprofil.",
                            "ol-sneaker-retro",
                            variants=[
                                {"size": "38", "color": "Blau", "price": "39.90", "stock": 1},
                                {"size": "39", "color": "Blau", "price": "39.90", "stock": 5},
                                {"size": "40", "color": "Blau", "price": "39.90", "stock": 2},
                                {"size": "41", "color": "Blau", "price": "39.90", "stock": 4},
                                {"size": "42", "color": "Blau", "price": "39.90", "stock": 2},
                                {"size": "38", "color": "Beige", "price": "39.90", "stock": 6},
                                {"size": "39", "color": "Beige", "price": "39.90", "stock": 1},
                                {"size": "40", "color": "Beige", "price": "39.90", "stock": 3},
                                {"size": "41", "color": "Beige", "price": "39.90", "stock": 2},
                                {"size": "42", "color": "Beige", "price": "39.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Ahlberg",
                            uvp="84.90",
                        ),
                        _p(
                            "Strick-Sneaker Silvana Air",
                            "34.90",
                            "Leicht wie ein Socken, atmungsaktives Strickobermaterial.",
                            "ol-sneaker-knit",
                            variants=[
                                {"size": "36", "color": "Grau", "price": "34.90", "stock": 5},
                                {"size": "37", "color": "Grau", "price": "34.90", "stock": 2},
                                {"size": "38", "color": "Grau", "price": "34.90", "stock": 4},
                                {"size": "39", "color": "Grau", "price": "34.90", "stock": 2},
                                {"size": "40", "color": "Grau", "price": "34.90", "stock": 6},
                                {"size": "36", "color": "Rosé", "price": "34.90", "stock": 1},
                                {"size": "37", "color": "Rosé", "price": "34.90", "stock": 3},
                                {"size": "38", "color": "Rosé", "price": "34.90", "stock": 2},
                                {"size": "39", "color": "Rosé", "price": "34.90", "stock": 4},
                                {"size": "40", "color": "Rosé", "price": "34.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Silvana",
                            uvp="69.90",
                        ),
                        _p(
                            "Canvas-Sneaker Kastanie Basic",
                            "24.90",
                            "Baumwoll-Canvas, Vulkanisiersohle, zum Waschen geeignet.",
                            "ol-sneaker-canvas",
                            variants=[
                                {"size": "38", "color": "Marine", "price": "24.90", "stock": 2},
                                {"size": "39", "color": "Marine", "price": "24.90", "stock": 4},
                                {"size": "40", "color": "Marine", "price": "24.90", "stock": 2},
                                {"size": "41", "color": "Marine", "price": "24.90", "stock": 6},
                                {"size": "42", "color": "Marine", "price": "24.90", "stock": 1},
                                {"size": "43", "color": "Marine", "price": "24.90", "stock": 3},
                                {"size": "38", "color": "Weiß", "price": "24.90", "stock": 2},
                                {"size": "39", "color": "Weiß", "price": "24.90", "stock": 4},
                                {"size": "40", "color": "Weiß", "price": "24.90", "stock": 1},
                                {"size": "41", "color": "Weiß", "price": "24.90", "stock": 5},
                                {"size": "42", "color": "Weiß", "price": "24.90", "stock": 3},
                                {"size": "43", "color": "Weiß", "price": "24.90", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Kastanie",
                            uvp="49.90",
                        ),
                        _p(
                            "High-Top Ruhrtal Street",
                            "44.90",
                            "Knöchelhoch, gepolsterter Einstieg, robuste Zehenkappe.",
                            "ol-sneaker-high",
                            variants=[
                                {"size": "40", "price": "44.90", "stock": 4},
                                {"size": "41", "price": "44.90", "stock": 2},
                                {"size": "42", "price": "44.90", "stock": 6},
                                {"size": "43", "price": "44.90", "stock": 1},
                                {"size": "44", "price": "44.90", "stock": 3},
                            ],
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Ruhrtal",
                            uvp="89.00",
                        ),
                        _p(
                            "Kinder-Sneaker Fenja Klett",
                            "22.90",
                            "Zwei Klettverschlüsse, leichte Sohle, reflektierende Details.",
                            "ol-sneaker-kids",
                            variants=[
                                {"size": "28", "price": "22.90", "stock": 2},
                                {"size": "30", "price": "22.90", "stock": 6},
                                {"size": "32", "price": "22.90", "stock": 1},
                                {"size": "34", "price": "22.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Fenja",
                            uvp="44.90",
                        ),
                    ],
                    "ol-sub-sneaker",
                ),
                (
                    "Stiefel",
                    "stiefel",
                    [
                        _p(
                            "Chelsea-Boots Brentwood Leder",
                            "79.00",
                            "Rindsleder, Gummizug, profilierte Laufsohle.",
                            "ol-boots-chelsea",
                            variants=[
                                {"size": "39", "color": "Braun", "price": "79.00", "stock": 6},
                                {"size": "40", "color": "Braun", "price": "79.00", "stock": 1},
                                {"size": "41", "color": "Braun", "price": "79.00", "stock": 3},
                                {"size": "42", "color": "Braun", "price": "79.00", "stock": 2},
                                {"size": "43", "color": "Braun", "price": "79.00", "stock": 4},
                                {"size": "39", "color": "Schwarz", "price": "79.00", "stock": 1},
                                {"size": "40", "color": "Schwarz", "price": "79.00", "stock": 5},
                                {"size": "41", "color": "Schwarz", "price": "79.00", "stock": 3},
                                {"size": "42", "color": "Schwarz", "price": "79.00", "stock": 2},
                                {"size": "43", "color": "Schwarz", "price": "79.00", "stock": 6},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Brentwood",
                            uvp="159.00",
                        ),
                        _p(
                            "Winterstiefel Ruhrtal Warm",
                            "69.90",
                            "Warmfutter, wasserabweisend, griffige Sohle bis −20 °C.",
                            "ol-boots-winter",
                            variants=[
                                {"size": "38", "price": "69.90", "stock": 1},
                                {"size": "39", "price": "69.90", "stock": 3},
                                {"size": "40", "price": "69.90", "stock": 2},
                                {"size": "41", "price": "69.90", "stock": 4},
                                {"size": "42", "price": "69.90", "stock": 1},
                            ],
                            condition="retoure",
                            note="Funktionstest bestanden, Zubehör vollständig.",
                            brand="Ruhrtal",
                            uvp="139.00",
                        ),
                        _p(
                            "Wanderschuh Ahlberg Trail",
                            "89.00",
                            "Knöchelhoch, Membran gegen Nässe, Vibram-ähnliche Sohle.",
                            "ol-boots-hiking",
                            variants=[
                                {"size": "41", "price": "89.00", "stock": 3},
                                {"size": "42", "price": "89.00", "stock": 2},
                                {"size": "43", "price": "89.00", "stock": 4},
                                {"size": "44", "price": "89.00", "stock": 1},
                                {"size": "45", "price": "89.00", "stock": 5},
                            ],
                            condition="wie_neu",
                            note="Einmal anprobiert, Sohle unbenutzt.",
                            brand="Ahlberg",
                            uvp="169.00",
                        ),
                        _p(
                            "Stiefelette Silvana Absatz",
                            "59.90",
                            "5 cm Blockabsatz, weiches Leder, Reißverschluss innen.",
                            "ol-boots-ankle",
                            variants=[
                                {"size": "37", "color": "Schwarz", "price": "59.90", "stock": 2},
                                {"size": "38", "color": "Schwarz", "price": "59.90", "stock": 4},
                                {"size": "39", "color": "Schwarz", "price": "59.90", "stock": 1},
                                {"size": "40", "color": "Schwarz", "price": "59.90", "stock": 5},
                                {"size": "37", "color": "Taupe", "price": "59.90", "stock": 3},
                                {"size": "38", "color": "Taupe", "price": "59.90", "stock": 2},
                                {"size": "39", "color": "Taupe", "price": "59.90", "stock": 6},
                                {"size": "40", "color": "Taupe", "price": "59.90", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Silvana",
                            uvp="119.00",
                        ),
                        _p(
                            "Gummistiefel Ruhrtal Regen",
                            "34.90",
                            "Naturkautschuk, herausnehmbare Einlegesohle, kurzer Schaft.",
                            "ol-boots-rubber",
                            variants=[
                                {"size": "38", "price": "34.90", "stock": 4},
                                {"size": "40", "price": "34.90", "stock": 1},
                                {"size": "42", "price": "34.90", "stock": 5},
                                {"size": "44", "price": "34.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Ruhrtal",
                            uvp="69.90",
                        ),
                    ],
                    "ol-sub-stiefel",
                ),
                (
                    "Business & Halbschuhe",
                    "business-schuhe",
                    [
                        _p(
                            "Derby Traverso Anzug",
                            "89.00",
                            "Rahmengenäht, Glattleder, Ledersohle mit Gummiauflage.",
                            "ol-shoes-derby",
                            variants=[
                                {"size": "41", "price": "89.00", "stock": 1},
                                {"size": "42", "price": "89.00", "stock": 5},
                                {"size": "43", "price": "89.00", "stock": 3},
                                {"size": "44", "price": "89.00", "stock": 2},
                            ],
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Traverso",
                            uvp="179.00",
                        ),
                        _p(
                            "Loafer Silvana Weich",
                            "59.90",
                            "Weiches Nappaleder, ungefüttert, flexible Sohle.",
                            "ol-shoes-loafer",
                            variants=[
                                {"size": "37", "color": "Schwarz", "price": "59.90", "stock": 5},
                                {"size": "38", "color": "Schwarz", "price": "59.90", "stock": 3},
                                {"size": "39", "color": "Schwarz", "price": "59.90", "stock": 2},
                                {"size": "40", "color": "Schwarz", "price": "59.90", "stock": 6},
                                {"size": "37", "color": "Cognac", "price": "59.90", "stock": 1},
                                {"size": "38", "color": "Cognac", "price": "59.90", "stock": 4},
                                {"size": "39", "color": "Cognac", "price": "59.90", "stock": 2},
                                {"size": "40", "color": "Cognac", "price": "59.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Silvana",
                            uvp="119.00",
                        ),
                        _p(
                            "Ballerina Fenja Basic",
                            "34.90",
                            "Klassisch, mit Gummizug am Einstieg, gepolsterte Sohle.",
                            "ol-shoes-ballerina",
                            variants=[
                                {"size": "36", "price": "34.90", "stock": 3},
                                {"size": "37", "price": "34.90", "stock": 2},
                                {"size": "38", "price": "34.90", "stock": 6},
                                {"size": "39", "price": "34.90", "stock": 1},
                                {"size": "40", "price": "34.90", "stock": 4},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Fenja",
                            uvp="69.90",
                        ),
                        _p(
                            "Monkstrap Brentwood Leder",
                            "79.00",
                            "Doppelschnalle, Glattleder, Ledersohle.",
                            "ol-shoes-monk",
                            variants=[
                                {"size": "41", "price": "79.00", "stock": 2},
                                {"size": "42", "price": "79.00", "stock": 6},
                                {"size": "43", "price": "79.00", "stock": 1},
                                {"size": "44", "price": "79.00", "stock": 4},
                            ],
                            condition="ausstellung",
                            note="Vorführmodell, gereinigt und geprüft; Zubehör vollständig.",
                            brand="Brentwood",
                            uvp="159.00",
                        ),
                        _p(
                            "Schuhpflege-Set Traverso",
                            "19.90",
                            "Bürsten, Creme in zwei Tönen und Poliertuch in der Holzkiste.",
                            "ol-shoes-care",
                            stock=6,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Traverso",
                            uvp="39.90",
                        ),
                    ],
                    "ol-sub-business-schuhe",
                ),
                (
                    "Hausschuhe & Sandalen",
                    "hausschuhe",
                    [
                        _p(
                            "Hausschuhe Fenja Filz",
                            "24.90",
                            "Walkfilz aus Schurwolle, Ledersohle, atmungsaktiv.",
                            "ol-filzhausschuh",
                            variants=[
                                {"size": "37", "price": "24.90", "stock": 1},
                                {"size": "38", "price": "24.90", "stock": 4},
                                {"size": "39", "price": "24.90", "stock": 2},
                                {"size": "40", "price": "24.90", "stock": 3},
                                {"size": "41", "price": "24.90", "stock": 3},
                                {"size": "42", "price": "24.90", "stock": 1},
                                {"size": "43", "price": "24.90", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Fenja",
                            uvp="49.90",
                        ),
                        _p(
                            "Sandale Kastanie Sommer",
                            "29.90",
                            "Korkfußbett, zwei verstellbare Riemen.",
                            "ol-sandals",
                            variants=[
                                {"size": "37", "color": "Braun", "price": "29.90", "stock": 4},
                                {"size": "38", "color": "Braun", "price": "29.90", "stock": 2},
                                {"size": "39", "color": "Braun", "price": "29.90", "stock": 3},
                                {"size": "40", "color": "Braun", "price": "29.90", "stock": 3},
                                {"size": "41", "color": "Braun", "price": "29.90", "stock": 1},
                                {"size": "37", "color": "Schwarz", "price": "29.90", "stock": 5},
                                {"size": "38", "color": "Schwarz", "price": "29.90", "stock": 2},
                                {"size": "39", "color": "Schwarz", "price": "29.90", "stock": 4},
                                {"size": "40", "color": "Schwarz", "price": "29.90", "stock": 2},
                                {"size": "41", "color": "Schwarz", "price": "29.90", "stock": 6},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Kastanie",
                            uvp="59.90",
                        ),
                        _p(
                            "Badeschuhe Ruhrtal Pool",
                            "12.90",
                            "Rutschhemmende Sohle, schnell trocknend.",
                            "ol-flipflops",
                            variants=[
                                {"size": "38", "price": "12.90", "stock": 2},
                                {"size": "40", "price": "12.90", "stock": 3},
                                {"size": "42", "price": "12.90", "stock": 3},
                                {"size": "44", "price": "12.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Ruhrtal",
                            uvp="24.90",
                        ),
                        _p(
                            "Hüttenschuhe Fenja Plüsch",
                            "19.90",
                            "Warm gefüttert, rutschfeste Noppensohle, waschbar.",
                            "ol-slippers-plush",
                            variants=[
                                {"size": "36-38", "price": "19.90", "stock": 3},
                                {"size": "39-41", "price": "19.90", "stock": 3},
                                {"size": "42-44", "price": "19.90", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Fenja",
                            uvp="39.90",
                        ),
                    ],
                    "ol-sub-hausschuhe",
                ),
            ],
            "Anprobierte Retouren und Vorjahresmodelle — original geprüft, sauber, im Karton oder mit Karton-Delle zum halben Preis.",
            "",
            "ol-cat-schuhe",
        ),
        (
            "Sport & Outdoor",
            "sport-outdoor",
            [],
            [
                (
                    "Sportbekleidung",
                    "sportbekleidung",
                    [
                        _p(
                            "Sportleggings Silvana Move",
                            "29.90",
                            "Hoher Bund, blickdicht, seitliche Handytasche.",
                            "ol-s-leggings",
                            variants=[
                                {"size": "XS", "color": "Schwarz", "price": "29.90", "stock": 3},
                                {"size": "S", "color": "Schwarz", "price": "29.90", "stock": 1},
                                {"size": "M", "color": "Schwarz", "price": "29.90", "stock": 5},
                                {"size": "L", "color": "Schwarz", "price": "29.90", "stock": 2},
                                {"size": "XS", "color": "Petrol", "price": "29.90", "stock": 4},
                                {"size": "S", "color": "Petrol", "price": "29.90", "stock": 2},
                                {"size": "M", "color": "Petrol", "price": "29.90", "stock": 6},
                                {"size": "L", "color": "Petrol", "price": "29.90", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Silvana",
                            uvp="59.90",
                        ),
                        _p(
                            "Funktionsshirt Ahlberg Dry",
                            "19.90",
                            "Feuchtigkeitstransport, flache Nähte, geruchshemmend.",
                            "ol-s-shirt",
                            variants=[
                                {"size": "S", "color": "Grau", "price": "19.90", "stock": 1},
                                {"size": "M", "color": "Grau", "price": "19.90", "stock": 5},
                                {"size": "L", "color": "Grau", "price": "19.90", "stock": 2},
                                {"size": "XL", "color": "Grau", "price": "19.90", "stock": 4},
                                {"size": "S", "color": "Limette", "price": "19.90", "stock": 2},
                                {"size": "M", "color": "Limette", "price": "19.90", "stock": 6},
                                {"size": "L", "color": "Limette", "price": "19.90", "stock": 1},
                                {"size": "XL", "color": "Limette", "price": "19.90", "stock": 3},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Ahlberg",
                            uvp="39.90",
                        ),
                        _p(
                            "Laufjacke Ruhrtal Wind",
                            "49.90",
                            "Winddicht, Reflektoren, packbar in die eigene Tasche.",
                            "ol-s-jacket",
                            variants=[
                                {"size": "S", "price": "49.90", "stock": 5},
                                {"size": "M", "price": "49.90", "stock": 2},
                                {"size": "L", "price": "49.90", "stock": 4},
                                {"size": "XL", "price": "49.90", "stock": 2},
                            ],
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Ruhrtal",
                            uvp="99.00",
                        ),
                        _p(
                            "Sportshorts Marlow Zwei-in-eins",
                            "24.90",
                            "Innenhose gegen Scheuern, Reißverschlusstasche hinten.",
                            "ol-s-shorts",
                            variants=[
                                {"size": "S", "price": "24.90", "stock": 2},
                                {"size": "M", "price": "24.90", "stock": 4},
                                {"size": "L", "price": "24.90", "stock": 2},
                                {"size": "XL", "price": "24.90", "stock": 6},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Marlow",
                            uvp="49.90",
                        ),
                    ],
                    "ol-sub-sportbekleidung",
                ),
                (
                    "Laufschuhe",
                    "laufschuhe",
                    [
                        _p(
                            "Laufschuh Ahlberg Road Neutral",
                            "69.90",
                            "Dämpfung für Asphalt, neutraler Abrollvorgang, 265 g.",
                            "ol-run-neutral",
                            variants=[
                                {"size": "41", "color": "Blau", "price": "69.90", "stock": 4},
                                {"size": "42", "color": "Blau", "price": "69.90", "stock": 2},
                                {"size": "43", "color": "Blau", "price": "69.90", "stock": 6},
                                {"size": "44", "color": "Blau", "price": "69.90", "stock": 1},
                                {"size": "45", "color": "Blau", "price": "69.90", "stock": 3},
                                {"size": "41", "color": "Schwarz", "price": "69.90", "stock": 2},
                                {"size": "42", "color": "Schwarz", "price": "69.90", "stock": 4},
                                {"size": "43", "color": "Schwarz", "price": "69.90", "stock": 1},
                                {"size": "44", "color": "Schwarz", "price": "69.90", "stock": 5},
                                {"size": "45", "color": "Schwarz", "price": "69.90", "stock": 3},
                            ],
                            condition="retoure",
                            note="Kundenretoure, im Haus geprüft — ohne Befund.",
                            brand="Ahlberg",
                            uvp="139.00",
                        ),
                        _p(
                            "Trailschuh Ruhrtal Wald",
                            "79.00",
                            "Grobes Profil, Steinschutzkappe, schnell schnürbar.",
                            "ol-run-trail",
                            variants=[
                                {"size": "40", "price": "79.00", "stock": 2},
                                {"size": "41", "price": "79.00", "stock": 6},
                                {"size": "42", "price": "79.00", "stock": 1},
                                {"size": "43", "price": "79.00", "stock": 3},
                                {"size": "44", "price": "79.00", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Ruhrtal",
                            uvp="149.00",
                        ),
                        _p(
                            "Laufschuh Silvana Light",
                            "59.90",
                            "Leicht und atmungsaktiv, breitere Zehenbox.",
                            "ol-run-women",
                            variants=[
                                {"size": "36", "price": "59.90", "stock": 6},
                                {"size": "37", "price": "59.90", "stock": 1},
                                {"size": "38", "price": "59.90", "stock": 3},
                                {"size": "39", "price": "59.90", "stock": 2},
                                {"size": "40", "price": "59.90", "stock": 4},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Silvana",
                            uvp="119.00",
                        ),
                    ],
                    "ol-sub-laufschuhe",
                ),
                (
                    "Rucksäcke & Reise",
                    "rucksaecke",
                    [
                        _p(
                            "Rucksack Ahlberg Trek 30 l",
                            "49.90",
                            "Belüftetes Rückensystem, Regenhülle, Trinksystem-Vorbereitung.",
                            "ol-backpack",
                            variants=[
                                {"color": "Oliv", "price": "49.90", "stock": 1},
                                {"color": "Grau", "price": "49.90", "stock": 3},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ahlberg",
                            uvp="99.00",
                        ),
                        _p(
                            "Daypack Marlow City 18 l",
                            "29.90",
                            "Laptopfach bis 15 Zoll, wasserabweisend, RV-Rückfach.",
                            "ol-daypack",
                            variants=[
                                {"color": "Schwarz", "price": "29.90", "stock": 3},
                                {"color": "Navy", "price": "29.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Marlow",
                            uvp="59.90",
                        ),
                        _p(
                            "Trolley Brentwood Hard 55 cm",
                            "79.00",
                            "Handgepäckmaß, vier Rollen, TSA-Zahlenschloss. Schale mit Kratzern.",
                            "ol-suitcase",
                            variants=[
                                {"color": "Anthrazit", "price": "79.00", "stock": 2},
                                {"color": "Petrol", "price": "79.00", "stock": 4},
                            ],
                            condition="retoure",
                            note="Schale mit Kratzern, Rollen und Schloss geprüft.",
                            brand="Brentwood",
                            uvp="159.00",
                        ),
                        _p(
                            "Reisetasche Ruhrtal Duffel 40 l",
                            "39.90",
                            "Robustes Segeltuch, abnehmbarer Schultergurt.",
                            "ol-duffel",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Ruhrtal",
                            uvp="79.00",
                        ),
                    ],
                    "ol-sub-rucksaecke",
                ),
                (
                    "Fitness",
                    "fitness",
                    [
                        _p(
                            "Yogamatte Silvana Grip",
                            "24.90",
                            "6 mm, rutschfest, schadstoffgeprüft, mit Tragegurt.",
                            "ol-yogamat",
                            variants=[
                                {"color": "Petrol", "price": "24.90", "stock": 1},
                                {"color": "Aubergine", "price": "24.90", "stock": 5},
                            ],
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Silvana",
                            uvp="49.90",
                        ),
                        _p(
                            "Kurzhantel-Set Ferrit 2×5 kg",
                            "34.90",
                            "Neopren-Ummantelung, rutschfester Griff, Ständer dabei.",
                            "ol-dumbbells",
                            stock=5,
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Ferrit",
                            uvp="69.90",
                        ),
                        _p(
                            "Fitnessbänder Lumeo (5er-Set)",
                            "12.90",
                            "Fünf Stärken, Textilbänder, Übungsheft und Beutel.",
                            "ol-resistance",
                            stock=3,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Lumeo",
                            uvp="24.90",
                        ),
                        _p(
                            "Trinkflasche Ahlberg Steel 0,75 l",
                            "16.90",
                            "Doppelwandig, 12 h heiß, 24 h kalt, auslaufsicher.",
                            "ol-bottle",
                            variants=[
                                {"color": "Schwarz", "price": "16.90", "stock": 2},
                                {"color": "Salbei", "price": "16.90", "stock": 6},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Ahlberg",
                            uvp="32.90",
                        ),
                        _p(
                            "Kettlebell Ferrit 12 kg",
                            "29.90",
                            "Gusseisen mit Kunststoffmantel, breiter Griff, standfest.",
                            "ol-kettlebell",
                            variants=[
                                {"size": "8 kg", "price": "29.90", "stock": 6},
                                {"size": "12 kg", "price": "29.90", "stock": 1},
                                {"size": "16 kg", "price": "29.90", "stock": 4},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Ferrit",
                            uvp="59.90",
                        ),
                        _p(
                            "Springseil Lumeo Speed",
                            "9.90",
                            "Kugelgelagert, längenverstellbar, Zähler in der Kugel.",
                            "ol-jump-rope",
                            stock=1,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Lumeo",
                            uvp="19.90",
                        ),
                        _p(
                            "Faszienrolle Silvana Med",
                            "16.90",
                            "Zwei Härtegrade in einer Rolle, 33 cm, mit Übungsposter.",
                            "ol-foam-roller",
                            stock=4,
                            condition="neu_ohne_ovp",
                            note="Neuware aus aufgelöster Filiale, Umkarton beschädigt.",
                            brand="Silvana",
                            uvp="32.90",
                        ),
                        _p(
                            "Fitnessband Lumeo Track",
                            "34.90",
                            "Schritte, Schlaf und Puls, 14 Tage Akku, wasserdicht.",
                            "ol-fitness-tracker",
                            variants=[
                                {"color": "Schwarz", "price": "34.90", "stock": 2},
                                {"color": "Koralle", "price": "34.90", "stock": 3},
                            ],
                            condition="retoure",
                            note="Zurückgesandt und geprüft; Verpackung geöffnet.",
                            brand="Lumeo",
                            uvp="69.90",
                        ),
                        _p(
                            "Sporttasche Ruhrtal Gym",
                            "29.90",
                            "Nassfach für Schuhe, verstärkter Boden, 35 l.",
                            "ol-gym-bag",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ruhrtal",
                            uvp="59.90",
                        ),
                    ],
                    "ol-sub-fitness",
                ),
            ],
            "Sportbekleidung und Ausrüstung aus Kollektionswechseln — funktionsgeprüft, mit vollständigem Zubehör.",
            "",
            "ol-cat-sport",
        ),
        (
            "Taschen & Accessoires",
            "taschen-accessoires",
            [],
            [
                (
                    "Taschen",
                    "taschen",
                    [
                        _p(
                            "Shopper Traverso Leder",
                            "89.00",
                            "Weiches Rindsleder, Innentasche mit Reißverschluss, ungefüttert.",
                            "ol-bag-shopper",
                            variants=[
                                {"color": "Cognac", "price": "89.00", "stock": 3},
                                {"color": "Schwarz", "price": "89.00", "stock": 1},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Traverso",
                            uvp="179.00",
                        ),
                        _p(
                            "Umhängetasche Silvana Klein",
                            "44.90",
                            "Kompakt für Handy, Karten und Schlüssel, verstellbarer Gurt.",
                            "ol-bag-crossbody",
                            variants=[
                                {"color": "Beere", "price": "44.90", "stock": 1},
                                {"color": "Creme", "price": "44.90", "stock": 5},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Silvana",
                            uvp="89.00",
                        ),
                        _p(
                            "Laptoptasche Marlow Filz",
                            "34.90",
                            "Wollfilz mit Lederriegel, für Notebooks bis 14 Zoll.",
                            "ol-bag-laptop",
                            stock=5,
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Marlow",
                            uvp="69.90",
                        ),
                        _p(
                            "Weekender Brentwood Canvas",
                            "69.90",
                            "Schweres Baumwoll-Canvas mit Lederboden, Schuhfach.",
                            "ol-bag-weekender",
                            stock=2,
                            condition="ausstellung",
                            note="Feine Kratzer an der Unterseite.",
                            brand="Brentwood",
                            uvp="139.00",
                        ),
                    ],
                    "ol-sub-taschen",
                ),
                (
                    "Uhren",
                    "uhren",
                    [
                        _p(
                            "Armbanduhr Traverso Stahl",
                            "79.00",
                            "Edelstahlgehäuse 40 mm, Saphirglas, 5 bar wasserdicht.",
                            "ol-watch-steel",
                            variants=[
                                {"color": "Silber", "price": "79.00", "stock": 4},
                                {"color": "Schwarz", "price": "79.00", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Traverso",
                            uvp="169.00",
                        ),
                        _p(
                            "Armbanduhr Silvana Leder",
                            "59.90",
                            "Schlankes 34-mm-Gehäuse, Lederband, Datumsanzeige.",
                            "ol-watch-leather",
                            variants=[
                                {"color": "Cognac", "price": "59.90", "stock": 2},
                                {"color": "Schwarz", "price": "59.90", "stock": 6},
                            ],
                            condition="neu",
                            note="Fabrikneu, Originalkarton ungeöffnet.",
                            brand="Silvana",
                            uvp="119.00",
                        ),
                        _p(
                            "Uhrenarmband Bragg Milanaise",
                            "19.90",
                            "Edelstahl-Mesh mit Magnetverschluss, 20 mm.",
                            "ol-watch-band",
                            stock=6,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Bragg",
                            uvp="39.90",
                        ),
                    ],
                    "ol-sub-uhren",
                ),
                (
                    "Gürtel & Tücher",
                    "guertel-tuecher",
                    [
                        _p(
                            "Gürtel Brentwood Vollleder",
                            "24.90",
                            "35 mm, pflanzlich gegerbt, kürzbare Länge.",
                            "ol-belt",
                            variants=[
                                {"size": "85", "price": "24.90", "stock": 1},
                                {"size": "95", "price": "24.90", "stock": 3},
                                {"size": "105", "price": "24.90", "stock": 2},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Brentwood",
                            uvp="49.90",
                        ),
                        _p(
                            "Seidentuch Silvana Muster",
                            "29.90",
                            "Reine Seide, 90 × 90 cm, gerollter Saum.",
                            "ol-scarf-silk",
                            variants=[
                                {"color": "Blau", "price": "29.90", "stock": 3},
                                {"color": "Ocker", "price": "29.90", "stock": 2},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Silvana",
                            uvp="59.90",
                        ),
                        _p(
                            "Lederhandschuhe Traverso Warm",
                            "34.90",
                            "Lammnappa, Kaschmirfutter, touchfähige Fingerkuppen.",
                            "ol-gloves",
                            variants=[
                                {"size": "7", "price": "34.90", "stock": 2},
                                {"size": "7,5", "price": "34.90", "stock": 4},
                                {"size": "8", "price": "34.90", "stock": 1},
                                {"size": "8,5", "price": "34.90", "stock": 5},
                                {"size": "9", "price": "34.90", "stock": 3},
                            ],
                            condition="retoure",
                            note="Aus 14-Tage-Widerruf, technisch nachgemessen.",
                            brand="Traverso",
                            uvp="69.90",
                        ),
                        _p(
                            "Geldbörse Marlow Kompakt",
                            "29.90",
                            "RFID-Schutz, sechs Kartenfächer, Münzfach mit Druckknopf.",
                            "ol-wallet",
                            variants=[
                                {"color": "Braun", "price": "29.90", "stock": 4},
                                {"color": "Schwarz", "price": "29.90", "stock": 1},
                            ],
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Marlow",
                            uvp="59.90",
                        ),
                    ],
                    "ol-sub-guertel",
                ),
                (
                    "Brillen & Kleinkram",
                    "brillen",
                    [
                        _p(
                            "Sonnenbrille Ahlberg Panto",
                            "24.90",
                            "UV400, polarisiert, Federscharniere, Etui dabei.",
                            "ol-sunglasses",
                            variants=[
                                {"color": "Schildpatt", "price": "24.90", "stock": 1},
                                {"color": "Schwarz", "price": "24.90", "stock": 5},
                            ],
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Ahlberg",
                            uvp="54.90",
                        ),
                        _p(
                            "Sportbrille Ruhrtal Speed",
                            "19.90",
                            "Wechselgläser für Sonne und Dämmerung, rutschfeste Nasenpads.",
                            "ol-sunglasses-sport",
                            stock=5,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Ruhrtal",
                            uvp="39.90",
                        ),
                        _p(
                            "Schlüsselanhänger Bragg Finder",
                            "14.90",
                            "Bluetooth-Finder mit App, Batterie wechselbar.",
                            "ol-keychain",
                            stock=3,
                            condition="neu",
                            note="Neu und originalverpackt, aus aufgelöstem Lagerbestand.",
                            brand="Bragg",
                            uvp="29.90",
                        ),
                        _p(
                            "Taschenschirm Fenja Sturm",
                            "16.90",
                            "Sturmfest bis 80 km/h, Auf-Zu-Automatik, Hülle dabei.",
                            "ol-umbrella",
                            stock=2,
                            condition="neu_ohne_ovp",
                            note="Neu, Schutzfolien noch drauf; Umverpackung entfällt.",
                            brand="Fenja",
                            uvp="32.90",
                        ),
                        _p(
                            "Bildschirmbrille Bragg Klar",
                            "19.90",
                            "Filtert blaues Licht, ohne Sehstärke, mit Etui.",
                            "ol-glasses-blue",
                            stock=6,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Bragg",
                            uvp="39.90",
                        ),
                        _p(
                            "Kartenetui Marlow Slim",
                            "19.90",
                            "Sechs Karten, RFID-Schutz, aus Vollrindleder.",
                            "ol-cardholder",
                            variants=[
                                {"color": "Schwarz", "price": "19.90", "stock": 1},
                                {"color": "Cognac", "price": "19.90", "stock": 4},
                            ],
                            condition="neu_ohne_ovp",
                            note="Fabrikneu und unbenutzt — nur der Originalkarton fehlt.",
                            brand="Marlow",
                            uvp="39.90",
                        ),
                        _p(
                            "Schmuckkasten Silvana Samt",
                            "24.90",
                            "Zwei Etagen mit Spiegel, Samtfutter, Schloss.",
                            "ol-jewelry-box",
                            stock=4,
                            condition="ausstellung",
                            note="Leichte Lagerspuren am Gehäuse.",
                            brand="Silvana",
                            uvp="49.90",
                        ),
                        _p(
                            "Haarspangen-Set Fenja (6er)",
                            "12.90",
                            "Sechs Spangen in gedeckten Tönen, bruchfest.",
                            "ol-hairclips",
                            stock=2,
                            condition="neu",
                            note="Originalverpackt und versiegelt — Restposten aus Sortimentswechsel.",
                            brand="Fenja",
                            uvp="24.90",
                        ),
                        _p(
                            "Packwürfel Marlow Reise (4er)",
                            "22.90",
                            "Vier Größen, netzbelüftet, beschriftbare Lasche.",
                            "ol-travel-organizer",
                            stock=3,
                            condition="neu_ohne_ovp",
                            note="Neu — Karton bei der Anlieferung eingedrückt, Ware unberührt.",
                            brand="Marlow",
                            uvp="44.90",
                        ),
                    ],
                    "ol-sub-brillen",
                ),
            ],
            "Musterteile und Einzelstücke: Taschen, Uhren und Kleinigkeiten, die im regulären Sortiment längst ausverkauft sind.",
            "",
            "ol-cat-accessoires",
        ),
    ],
)


STADTFUEHRUNG = DemoKit(
    key="stadtfuehrung",
    # DL-11: колонки под число элементов — ряды плиток полные (scripts/demo_rows_audit.py)
    section_layouts={
        "gallery": {"preset": "cols3"},
        "events": {"preset": "cols2"},
        "tours": {"preset": "cols3"},
    },
    label="Kölner Spaziergänge",
    business_type="tour_operator",
    subdomain="stadtfuehrung",
    accent="#9d174d",
    bundle="fokus_touren",
    look="warm",
    hero_image_kw="city,tour",
    hero_title="Kölner Spaziergänge",
    hero_text="Stadtführungen abseits der Trampelpfade — kleine Gruppen, echte "
    "Geschichten, eine Gastgeberin. Öffentliche Termine oder Ihre private Tour.",
    section_titles={
        "tours": "Meine Touren",
        "anfrage": "Private Führung anfragen",
    },
    section_intros={
        "anfrage": "Ab sechs Personen laufe ich jede Tour privat — auch abends. "
        "Wunschtermin nennen, ich melde mich innerhalb eines Tages.",
    },
    opening_hours_text="Touren täglich · Büro Mo–Fr 9:00–17:00",
    opening_hours={d: ("09:00", "17:00") for d in range(5)},
    menus=STADTFUEHRUNG_MENUS,
    # Замок test_kits_have_first_screen: у каждого кита слайдер или hero-виджет.
    heroes=[
        {
            "image_kw": "city,tour",
            "title": "Altstadt & Dom — der Klassiker",
            "text": "Zwei Stunden vom Dom bis an den Rhein — samstags und sonntags, "
            "Einzelplätze ab 19 €.",
            "button_label": "Termine ansehen",
            "button_url": "/touren/",
        },
        {
            "image_kw": "beer",
            "title": "Kölsch & Brauhauskultur",
            "text": "Freitagabend durch drei Brauhäuser — Geschichten inklusive, Kölsch auch.",
            "button_label": "Private Tour anfragen",
            "button_url": "/anfrage/",
        },
    ],
    enable_modules=["events", "customer_account", "inbox", "jobs"],
    hide_archetypes=["catalog"],
    anfrage_form={
        "fields": ["date", "guests", "event_type"],
        "event_types": [
            "Altstadt & Dom privat",
            "Kölsch & Brauhauskultur",
            "Frauen, die Köln prägten",
            "Firmen-Event / Teamausflug",
            "Eigene Idee",
        ],
    },
    about_title="Über mich",
    about_text="Ich bin Katharina — Kunsthistorikerin und seit zwölf Jahren "
    "Stadtführerin in Köln. Ich laufe nur Touren, die ich selbst liebe: kleine "
    "Gruppen, keine Mikrofon-Kolonnen, dafür Geschichten, die im Reiseführer "
    "fehlen. Öffentliche Termine finden ab vier Gästen statt; private Touren "
    "laufen auf Deutsch und Englisch.",
    gallery_kw=[
        "city,tour",
        "old,town",
        "beer",
        "market,stall",
        "red,wine",
        "suspension,bridge",
    ],  # DL-11: 6 = 2×3
    teachers=[
        (
            "Katharina Vogt",
            "Stadtführerin & Kunsthistorikerin",
            "guide,portrait",
            "Zwölf Jahre Stadtführungen in Köln, davor Museumsdienst. "
            "Lieblingsecke: die Höfe hinter Groß St. Martin kurz vor Sonnenuntergang.",
        ),
    ],
    tours=[
        {
            "title": "Altstadt & Dom — der Klassiker",
            "summary": "Zwei Stunden vom Dom durchs Martinsviertel bis an den Rhein "
            "— die Pflichttour, ohne Trampelpfad-Gefühl.",
            "region": "Altstadt, Köln",
            "country": "Deutschland",
            "difficulty": "easy",
            "duration_days": 0,
            "photos": ["city,tour", "old,town"],
            "description": "Warum steht der Dom schief zur Straße? Wo stand das "
            "römische Köln? Zwei Stunden zu Fuß, maximal zwölf Gäste, viele "
            "Geschichten — am Ende wissen Sie, warum die Kölner ihre Stadt nie "
            "fertig bauen.",
            "details": {
                "for_whom": [
                    "Köln-Besucher und Neu-Kölner",
                    "Gut zu Fuß — wir laufen ca. 3 km",
                ],
                "price_includes": [
                    "2 Stunden Führung, max. 12 Gäste",
                    "Audio-Headset ab 8 Gästen",
                ],
                "faq": [
                    (
                        "Findet die Tour bei Regen statt?",
                        "Ja — Köln bei Regen ist ehrlicher. Bei Sturmwarnung sage "
                        "ich ab und Sie buchen kostenlos um.",
                    ),
                ],
            },
            "teachers": [0],
        },
        {
            "title": "Kölsch & Brauhauskultur",
            "summary": "Drei Brauhäuser, viele Geschichten und die Frage, warum "
            "der Köbes nie fragt, ob Sie noch eins möchten.",
            "region": "Altstadt, Köln",
            "country": "Deutschland",
            "difficulty": "easy",
            "duration_days": 0,
            "photos": ["beer", "old,town"],
            "description": "Eine Abendtour durch die Brauhauskultur: Geschichte "
            "des Kölsch, Brauhaus-Knigge und drei Stationen mit Verkostung. "
            "Ab 18 Jahren.",
            "details": {
                "price_includes": [
                    "3 Stationen, je ein Kölsch inklusive",
                    "2,5 Stunden, max. 10 Gäste",
                ],
            },
            "teachers": [0],
        },
        {
            "title": "Frauen, die Köln prägten",
            "summary": "Von der Stifterin Plectrudis bis zur ersten Ratsfrau — "
            "die Stadtgeschichte, die sonst ausgelassen wird.",
            "region": "Innenstadt, Köln",
            "country": "Deutschland",
            "difficulty": "easy",
            "duration_days": 0,
            "photos": ["old,town", "city,tour"],
            "description": "Zwei Stunden Stadtgeschichte aus weiblicher "
            "Perspektive — Orte, Namen und Archivfunde, die in klassischen "
            "Führungen fehlen.",
            "teachers": [0],
        },
    ],
    events=[
        {
            "title": "Altstadt & Dom · Samstagstour",
            "tour": 0,
            "in_days": 6,
            "hour": 11,
            "capacity": 12,
            "price": "19",
            "city": "Köln",
            "location": "Treffpunkt Domplatte, Hauptportal",
            "language": "de",
            # MX-2e: адресная опция с ПУЛОМ — 15 headset-гарнитур на всех.
            "rental_option": ("Audio-Headset", "3", 15, "Kopfhörer-Service Rheinland"),
            "description": "Öffentlicher Termin — Einzelplätze buchbar.",
        },
        {
            "title": "Altstadt & Dom · Sonntagstour",
            "tour": 0,
            "in_days": 7,
            "hour": 14,
            "capacity": 12,
            "price": "19",
            "city": "Köln",
            "location": "Treffpunkt Domplatte, Hauptportal",
            "language": "de",
            "description": "Öffentlicher Termin — Einzelplätze buchbar.",
        },
        {
            "title": "Kölsch & Brauhauskultur · Freitagabend",
            "tour": 1,
            "in_days": 5,
            "hour": 18,
            "capacity": 10,
            "price": "34",
            "city": "Köln",
            "location": "Treffpunkt Heumarkt, Reiterdenkmal",
            "language": "de",
            "description": "Drei Brauhäuser inkl. je einem Kölsch.",
        },
        {
            "title": "Frauen, die Köln prägten · Themenabend",
            "tour": 2,
            "in_days": 12,
            "hour": 17,
            "capacity": 12,
            "price": "21",
            "city": "Köln",
            "location": "Treffpunkt Rathausvorplatz",
            "language": "de",
            "description": "Öffentlicher Termin — Einzelplätze buchbar.",
        },
    ],
    extras=[
        ("Kölsch-Verkostung zum Abschluss", "4.50", "events", False),
    ],
    reviews_seed=[
        (5, "Beste Stadtführung, die wir je hatten — witzig und fundiert.", "sf.rev1@example.de"),
        (5, "Katharina kennt jede Ecke. Die Brauhaustour ist ein Muss.", "sf.rev2@example.de"),
        (4, "Toller Themenabend, gern mit etwas mehr Zeit am Rhein.", "sf.rev3@example.de"),
    ],
)


KITS = {
    RESTAURANT.key: RESTAURANT,
    PRANASY.key: PRANASY,
    HOTEL.key: HOTEL,
    AKTIONSMARKT.key: AKTIONSMARKT,
    BAKERY.key: BAKERY,
    BUTCHER.key: BUTCHER,
    CAFE.key: CAFE,
    CLOTHING.key: CLOTHING,
    TOURS.key: TOURS,
    MOTO.key: MOTO,  # MT-1: мото/квадро-туры
    FRISEUR.key: FRISEUR,
    WERKSTATT.key: WERKSTATT,
    HANDWERKER.key: HANDWERKER,
    CATERING.key: CATERING,  # GK-1
    RETREAT.key: RETREAT,
    SHOP.key: SHOP,
    STADTFUEHRUNG.key: STADTFUEHRUNG,  # Трипстер-гид (MX §5)
    OUTLET.key: OUTLET,  # O-3: аутлет техники и моды (демо типа online_shop)
}


#: Бюджет ширины строки меню в пикселях. Контейнер шапки — `max-w-7xl`, и на меню
#: приходится ~788 px на широком экране (замер 1280/1440/1920), но на 1024 px
#: остаётся заметно меньше. Берём с запасом, чтобы `fitNav` не уводил хвост в
#: дропдаун «Mehr» и на ноутбучных ширинах (фидбэк владельца 2026-08-07).
#: Считаем ШИРИНУ, а не число пунктов: «Veranstaltungen» и «Shop» стоят по-разному.
_MENU_ROW_BUDGET_PX = 620
#: Оценка ширины пункта: text-sm ≈ 8.2 px на символ + горизонтальные паддинги.
_MENU_ITEM_PADDING_PX = 24
_MENU_CHAR_PX = 8.2


def _menu_row_width(labels) -> float:
    return sum(len(str(x)) * _MENU_CHAR_PX + _MENU_ITEM_PADDING_PX for x in labels)


#: Что уезжает под «Über uns», когда пунктов слишком много: это разделы «о нас»,
#: а не то, что мы продаём. Продающие пункты (каталог/бронь/акции) остаются в
#: строке всегда.
_SECONDARY_PAGE_TARGETS = ("gallery", "reviews", "team")
_SECONDARY_URLS = ("/hausordnung/", "/lehrer/")


def _is_secondary(node: dict) -> bool:
    kind, target = node.get("type"), str(node.get("target") or "")
    if kind == "page":
        return target in _SECONDARY_PAGE_TARGETS
    if kind == "anchor":
        return "kontakt" in target
    if kind == "url":
        return target in _SECONDARY_URLS
    return False


def _compact_menu(menus: dict | None) -> dict | None:
    """Свернуть второстепенные пункты верхнего меню под «Über uns».

    Меню кита — данные; чем богаче кит, тем длиннее строка. Вместо того чтобы
    полагаться на автоматический overflow, складываем «о нас»-разделы в подменю
    у пункта «Über uns»: он остаётся ССЫЛКОЙ на /ueber-uns/ (узел `page` с
    детьми), а наведение/тап раскрывает остальное. Нижнее меню не трогаем — там
    свой набор из 3-4 иконок.
    """
    if not menus or "top" not in menus:
        return menus
    items = list(menus["top"].get("items") or [])
    if _menu_row_width(i.get("label", "") for i in items) <= _MENU_ROW_BUDGET_PX:
        return menus
    about = next((i for i in items if i.get("type") == "page" and i.get("target") == "about"), None)
    if about is None:
        return menus  # некуда складывать — оставляем как есть

    # Сворачиваем ровно столько, сколько нужно, чтобы уложиться в бюджет: берём
    # с конца (ближе к «Über uns»), чтобы не рвать смысловой порядок строки.
    movable = [i for i in items if i is not about and _is_secondary(i)]
    remaining, chosen = list(items), []
    for node in reversed(movable):
        if _menu_row_width(i.get("label", "") for i in remaining) <= _MENU_ROW_BUDGET_PX:
            break
        remaining.remove(node)
        chosen.append(node)
    chosen.reverse()
    if not chosen:
        return menus

    kept = [i for i in items if i is not about and i not in chosen]
    grouped = dict(about)
    grouped["children"] = [dict(c, children=[]) for c in chosen] + list(about.get("children") or [])
    top = dict(menus["top"], items=[*kept, grouped])
    return dict(menus, top=top)


def _kit_sections(kit: DemoKit) -> list[dict]:
    """Раскладка секций кита: фото-hero, меню, акции, галерея, отзывы, FAQ, CTA, контакты."""
    rows = [
        {"key": "hero", "enabled": True},
        # GK-15: фото-плитки категорий сразу после первого экрана (референс
        # catering: сетка направлений ПЕРЕД «столпами»). Опт-ин китом.
        {"key": "categories", "enabled": kit.enable_categories_section},
        # A.3 (T-B): полоса доверия сразу под hero (если заданы пункты).
        {"key": "usp_bar", "enabled": bool(kit.usp)},
        # H2/E4: поиск размещения по датам. При hero_widget="stays" поиск живёт
        # ВНУТРИ hero (первый экран) → секцию гасим, чтобы не было дубля.
        {"key": "stay_search", "enabled": bool(kit.stay_units) and kit.hero_widget != "stays"},
        # Карточки номеров прямо на главной — для отелей/пансионов.
        {"key": "stay_rooms", "enabled": bool(kit.stay_units)},
        # A3: блок услуг «Leistungen & Preise» — если у кита есть услуги (booking).
        {"key": "services", "enabled": bool(kit.services)},
        # MT-F1: поездки (тур-продукт) — главный товар тур-оператора.
        {"key": "tours", "enabled": bool(kit.tours)},
        {"key": "archetypes", "enabled": kit.enable_archetypes_section},  # S2: «Unsere Bereiche»
        # Акции/товары — только если у кита есть каталог (иначе пустые секции).
        # HF-1: акции бывают и без каталога (отель: «3 Nächte zum Preis von 2») —
        # секция включается и по наличию промо-спеки.
        {"key": "promotions", "enabled": bool(kit.categories or kit.promotions_spec)},
        {"key": "products", "enabled": bool(kit.categories)},
        # HF-1: лента новостей — если у кита есть посты (иначе секция была бы пустой).
        {"key": "blog", "enabled": bool(kit.blog_posts)},
        {"key": "process", "enabled": bool(kit.process)},
        {"key": "team", "enabled": bool(kit.team)},
        {"key": "gallery", "enabled": bool(kit.gallery_kw)},
        # A7: «Vorher / Nachher» — кейсы санации (если заданы у кита).
        {"key": "before_after", "enabled": bool(kit.before_after)},
        {"key": "testimonials", "enabled": bool(kit.testimonials)},
        {"key": "trust", "enabled": bool(kit.trust)},
        # DS-4/4b (Fokus): мини-форма заявки — в КОНЦЕ страницы (макет: доверие →
        # форма → футер); выкл, если кит не включил.
        {"key": "anfrage", "enabled": kit.enable_anfrage_section},
        {"key": "reviews", "enabled": bool(kit.reviews_seed)},  # G8/#6: отзывы клиентов
        {"key": "faq", "enabled": bool(kit.faq)},
        {"key": "cta", "enabled": bool(kit.cta)},
        {"key": "about", "enabled": bool(kit.about_text)},
        {"key": "contact", "enabled": True},
    ]
    # ST-2c/ST-7b: вариант отображения секции (валидность — normalize по SECTION_STYLES).
    for s in rows:
        style = kit.section_styles.get(s["key"])
        if style:
            s["style"] = style
        rows_cap = kit.section_rows.get(s["key"])
        if rows_cap:
            s["rows"] = rows_cap  # MEN-24c: кап строк прайс-вида (normalize клампит)
        lay = kit.section_layouts.get(s["key"])
        if lay:
            s["layout"] = dict(lay)  # фидбэк 2026-08-27: число колонок секции
        # DS-4b: тонированные полосы макета (visual чистит normalize) + принуди-
        # тельное выключение секций (контент кита жив — страницы ST-8 работают).
        vis = kit.section_visuals.get(s["key"])
        if vis:
            s["visual"] = dict(vis)
        if s["key"] in kit.sections_off:
            s["enabled"] = False
    # GK-15: C-блоки главной из спеки кита (stats/founder-цитата/newsletter…) —
    # тот же принцип якоря «после секции», данные чистит normalize.
    for i, spec in enumerate(kit.home_blocks):
        idx = next((j for j, s in enumerate(rows) if s["key"] == spec.get("after")), None)
        block = {
            "key": spec.get("key", ""),
            "id": f"demo-block-{i + 1}",
            "enabled": True,
            "data": spec.get("data") or {},
        }
        if spec.get("visual"):
            block["visual"] = spec["visual"]
        rows.insert(idx + 1 if idx is not None else len(rows), block)
    # ST-7a: демо-spacer'ы между секциями (высота presence-minimal; "" = py-6).
    for i, spec in enumerate(kit.spacers):
        idx = next((j for j, s in enumerate(rows) if s["key"] == spec.get("after")), None)
        block = {
            "key": "spacer",
            "id": f"demo-spacer-{i + 1}",
            "enabled": True,
            "data": {"height": spec.get("height", "")},
        }
        rows.insert(idx + 1 if idx is not None else len(rows), block)
    return rows


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
        base = Decimal(item["price"])
        name_i18n = _i18n_text(item["name"])
        product = Product.objects.create(
            name=name_i18n,
            description=_i18n_text(item["desc"]),
            base_price=base,
            category=category,
            # DL-16.4 (P2): список ключей → несколько фото (первое — главное, остальные
            # листаются на карточке/галерея детали); строка — как раньше.
            images=_product_images(item["img"], lock, name_i18n.get("de", "")),
            allergens=item["allergens"],
            diets=item.get("diets", []),  # A4 диет-теги
            badge=item.get("badge", ""),
            unit=item.get("unit", ""),  # R2 Grundpreis
            content_amount=Decimal(str(content)) if content is not None else None,
            stock_quantity=stock,  # R3 остаток (None = без учёта)
            # T5: EK ≈ 55 % VK (Marge ~45 %) + Meldebestand/Sollbestand для демо
            # (Warenwert/Marge/Bestellvorschläge видны в кабинете склада).
            cost_price=(base * Decimal("0.55")).quantize(Decimal("0.01")),
            # SH-4: ставка НДС позиции — демо показывает СМЕШАННЫЙ чек (в DACH
            # еда 7 %, напитки/прочее 19 %). Ключ спеки `vat` необязателен.
            vat_rate=Decimal(str(item.get("vat", "19.00"))),
            reorder_point=8 if stock is not None else None,
            reorder_target=24 if stock is not None else None,
            gtin=item.get("gtin", ""),  # A1 EAN
            # SH-19 (фидбэк «артикул на витрине»): у демо-товаров SKU был пуст у ВСЕХ китов
            # → Art.-Nr. нигде не показывался. Детерминированный артикул из ключа кита и
            # порядкового номера (явный `sku` спеки сильнее).
            sku=item.get("sku") or f"{key.upper()[:3]}-{lock:03d}",
            material=item.get("material", ""),  # M1 Textilkennzeichnung
            care=item.get("care", ""),
            # Ф2: состав блюда — витрина показывает «Zutaten», перевод локалей
            # приезжает оверлеем ingredients_i18n (translate_tenant_content).
            ingredients=item.get("ingredients", ""),
            # O-2: per-товарный вид выбора вариантов ("" = дефолт сайта/кита)
            variant_style=item.get("variant_style", ""),
            # DL-19: своя форма карточки этой позиции (побеждает дефолт сайта)
            card_style=item.get("card_style", ""),
            # O-1 (Outlet): состояние/марка/UVP. Пустые значения = прежнее поведение.
            condition=item.get("condition", ""),
            condition_note=item.get("condition_note", ""),
            brand=item.get("brand", ""),
            list_price=(Decimal(str(item["uvp"])) if item.get("uvp") else None),
            is_active=True,
            is_featured=(len(created_products) < 3),
            metadata={"demo": True},
        )
        lock += 1
        # T1: стартовый остаток демо-товара → в склад-леджер (Startbestand),
        # чтобы реконсиляция /dashboard/stock/ сходилась и была история.
        if stock is not None:
            from apps.inventory.services import record_movement

            record_movement(
                product=product,
                kind="receipt",
                delta=stock,
                source="manual",
                note="Startbestand (Demo)",
            )
        for vsort, v in enumerate(item["variants"]):
            # Вариант — кортеж (label, price) ИЛИ dict с остатком/Grundpreis/EAN.
            if isinstance(v, dict):
                vc = v.get("content")
                vprice = Decimal(str(v["price"]))
                vstock = v.get("stock")
                # M4-A: оси размер/цвет (label собирается моделью, если не задан)
                # + фото варианта (подмена главного фото при выборе).
                vimages = [
                    _image_ref(kw, lock + 1000 + vsort, v.get("color", ""))
                    for kw in (v.get("images") or [])
                ]
                variant = ProductVariant.objects.create(
                    product=product,
                    label=v.get("label", ""),
                    size=v.get("size", ""),
                    color=v.get("color", ""),
                    images=vimages,
                    price=vprice,
                    content_amount=Decimal(str(vc)) if vc is not None else None,
                    stock_quantity=vstock,
                    # T5: EK ≈ 55 % VK + Meldebestand/Sollbestand (демо)
                    cost_price=(vprice * Decimal("0.55")).quantize(Decimal("0.01")),
                    reorder_point=5 if vstock is not None else None,
                    reorder_target=15 if vstock is not None else None,
                    gtin=v.get("gtin", ""),
                    sku=v.get("sku") or f"{product.sku}-{vsort + 1}",  # SH-19: артикул варианта
                    sort_order=vsort,
                )
                if v.get("stock") is not None:
                    from apps.inventory.services import record_movement

                    record_movement(
                        product=product,
                        variant=variant,
                        kind="receipt",
                        delta=v["stock"],
                        source="manual",
                        note="Startbestand (Demo)",
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
                # O-2: вид выбора группы («tiles»/«list»/«chips»); "" = как раньше.
                display_style=group.get("style", ""),
                sort_order=gsort,
                is_active=True,
            )
            for osort, opt in enumerate(group["options"]):
                # Опция — (label, delta) ИЛИ (label, delta, image_kw) — O-3:
                # фото опции для вида «плитки с фото».
                olabel, odelta = opt[0], opt[1]
                oimage = _image_ref(opt[2], 700 + osort, olabel) if len(opt) > 2 else {}
                ModifierOption.objects.create(
                    group=mg,
                    label=olabel,
                    price_delta=Decimal(odelta),
                    image=oimage,
                    sort_order=osort,
                )
        created_products.append(product)
        refs["products"].append(str(product.pk))
        return product

    def _make_category(entry, sort, parent=None):
        # entry: (name, slug, items) ИЛИ (name, slug, items, children) ИЛИ
        # (name, slug, items, "photo,kw") — DS-2: 4-й элемент-СТРОКА задаёт ключ
        # фото плитки (иначе ключ = slug; немецкие слоги давали SVG-фолбэк).
        # 7-й элемент — ключ фото для категории С ДЕТЬМИ (4-й занят детьми).
        # children — подкатегории той же формы (1 уровень). Первый товар
        # категории — в category_firsts (S6).
        name, slug, items = entry[0], entry[1], entry[2]
        extra = entry[3] if len(entry) > 3 else []
        photo_kw = extra if isinstance(extra, str) else ""
        children = extra if isinstance(extra, list) else []
        # Kategorie MIT Unterkategorien belegt Element 3 mit den Kindern und kam
        # deshalb nie an ein eigenes Foto — der slug-Fallback griff dann irgendein
        # Bibliotheksbild ab (bei «catering» eine Bratwurst-Theke auf einer veganen
        # Seite). Element 7 gibt Container-Kategorien ihren Foto-Schlüssel.
        if not photo_kw and len(entry) > 6:
            photo_kw = entry[6]
        # DS-7a: 5-й элемент — описание направления (шапка страницы категории).
        landing_desc = entry[4] if len(entry) > 4 else ""
        # KAT-6: слаг демо-категории — КАК У ЖИВЫХ (без префикса demo-; URL
        # /sortiment/kaese-wurst/ выглядит как настоящий). unique_slug обязателен:
        # recreate на схеме с ручными категориями иначе падал бы на constraint.
        from apps.catalog.slugs import unique_slug as _unique_slug

        actual_slug = _unique_slug(Category, slug)
        category = Category.objects.create(
            name=_i18n_text(name),
            description={"de": landing_desc} if landing_desc else {},
            slug=actual_slug,
            # KAT-1: шаблон страницы категории из спеки кита (6-й элемент).
            page_style=(entry[5] if len(entry) > 5 else ""),
            sort_order=sort,
            is_active=True,
            parent=parent,
            size_table=kit.size_tables.get(slug, ""),  # M2 Größentabelle
            # Фидбэк 2026-08-07 («категории картинками»): фото категории брали
            # только вручную в кабинете, поэтому у ВСЕХ демо `images` был пуст и
            # витрина откатывалась на текстовые чипы. Ключ фото — slug категории
            # (тематичный демо-генератор), lock от сортировки → стабильно.
            images=[
                _image_ref(
                    photo_kw or slug.replace("-", ","),
                    400 + sort,
                    str(_i18n_text(name).get("de", "")),
                )
            ],
        )
        refs["categories"].append(str(category.pk))
        # KAT-6: карта «слаг спеки → фактический» (unique_slug мог досуффиксовать) —
        # ей пользуется привязка комбо к категории.
        refs.setdefault("category_slugs", {})[slug] = actual_slug
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
    # P6 «ценовой слой»: акции с целью-услугой/номером создаются ВТОРЫМ проходом
    # после _seed_kit_modules (services/stay_units существуют только там).
    deferred_promos = []

    def _create_spec_promo(spec, *, service=None, stay_unit=None):
        nonlocal lock
        idx = spec.get("product")
        product = (
            created_products[idx] if isinstance(idx, int) and idx < len(created_products) else None
        )
        fields = {
            "title": {"de": spec["title"]},
            "description": {"de": spec.get("desc", "")},
            "product": product,
            "service": service,
            "stay_unit": stay_unit,
            # P6: правила действия (счастливые часы / окно проживания).
            "target_rules": spec.get("rules") or {},
            "promo_type": Promotion.RESERVATION
            if spec.get("type") == "reservation"
            else Promotion.DISCOUNT,
            # DL-17.4 (A1 «Vorschau»): `starts_in_days` делает акцию ЗАПЛАНИРОВАННОЙ —
            # она видна витриной лентой «Ab dieser Woche», но ещё не продаётся
            # (beat `roll_due_promotions` включит её сам на старте).
            "status": "scheduled" if spec.get("starts_in_days") else "active",
            # Фидбэк 2026-07-29: чип «Neu» (is_new ≤ 7 дней) — только у явно
            # помеченных spec'ов, иначе у свежего сида все акции «новые».
            "starts_at": (
                now + timedelta(days=spec["starts_in_days"])
                if spec.get("starts_in_days")
                else (now if spec.get("new") else now - timedelta(days=10))
            ),
            "ends_at": now
            + timedelta(days=spec.get("starts_in_days", 0) + spec.get("ends_in_days", 14)),
            "group": spec.get("group", ""),
            "show_countdown": bool(spec.get("countdown")),
            "is_surprise": bool(spec.get("surprise")),
            "recurrence": spec.get("recurrence", ""),
            "metadata": {"demo": True},
        }
        if spec.get("percent"):
            fields["discount_percent"] = spec["percent"]
        # UE2-2: стиль вывода скидки (showcase 7 стилей на aktionsmarkt).
        if spec.get("discount_style"):
            fields["discount_style"] = spec["discount_style"]
        # DL-19: своя ФОРМА карточки этой акции (побеждает дефолт сайта)
        if spec.get("card_style"):
            fields["card_style"] = spec["card_style"]
        if spec.get("new_price"):
            fields["price_override"] = Decimal(str(spec["new_price"]))
        if spec.get("compare_at"):
            fields["compare_at_price"] = Decimal(str(spec["compare_at"]))
        if spec.get("type") == "reservation":
            fields["available_quantity"] = spec.get("available_quantity", 10)
        elif spec.get("limit"):  # P6: лимит кампании обычной акции (новые рельсы)
            fields["available_quantity"] = spec["limit"]
        if spec.get("image"):
            lock += 1
            fields["images"] = [_image_ref(spec["image"], lock, spec["title"])]
        elif spec.get("images"):  # 2026-07-29: галерея детали (миниатюры)
            refs_imgs = []
            for kw in spec["images"]:
                lock += 1
                refs_imgs.append(_image_ref(kw, lock, spec["title"]))
            refs_imgs[0]["is_primary"] = True
            fields["images"] = refs_imgs
        promo = Promotion.objects.create(**fields)
        refs["promotions"].append(str(promo.pk))

    if kit.promotions_spec:
        # Богатая спецификация — все типы/виды акций (showcase).
        for spec in kit.promotions_spec:
            if "service" in spec or "stay_unit" in spec:
                deferred_promos.append(spec)
                continue
            _create_spec_promo(spec)
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
    # P6 «ценовой слой»: акции с целью-услугой/номером — цели созданы модулями выше;
    # индексы — позиции в refs["services"]/["stay_units"] (как в service_reviews).
    if deferred_promos:
        from apps.booking.models import Service as _BookSvc
        from apps.stays.models import StayUnit as _StayU

        _svc_refs = refs.get("services") or []
        _unit_refs = refs.get("stay_units") or []
        for spec in deferred_promos:
            svc = un = None
            sidx, uidx = spec.get("service"), spec.get("stay_unit")
            if isinstance(sidx, int) and sidx < len(_svc_refs):
                svc = _BookSvc.objects.filter(pk=_svc_refs[sidx]).first()
            if isinstance(uidx, int) and uidx < len(_unit_refs):
                un = _StayU.objects.filter(pk=_unit_refs[uidx]).first()
            if svc is None and un is None:
                continue  # цель не досеялась (модуль выключен) — акцию не плодим
            _create_spec_promo(spec, service=svc, stay_unit=un)
    _seed_kit_records(tenant, kit, refs, created_products)
    if kit.seed_inbox:  # LS-3/4/6: демо «Прямой линии» + Sofort-Angebot
        _seed_kit_inbox()
    if kit.winback:  # B4/LS-5: активная auto-win-back кампания
        _seed_kit_winback(kit)
    _seed_demo_lots(kit, created_products)  # E1.5: демо-партии/MHD (еда)
    _seed_demo_purchasing(kit, created_products)  # E3: демо-закупки (Lieferant+Bestellung)
    _seed_kit_reviews(tenant, kit)
    _seed_product_reviews(kit, created_products)
    _seed_entity_reviews(kit, refs)  # UA4-4b: отзывы об услуге/номере/событии в демо
    _seed_blog_posts(tenant, kit)
    if kit.extras:  # #7 универсальные доп-услуги (Extra)
        from apps.core.models import Extra

        for sort, spec in enumerate(kit.extras):
            label, price, scope, per_night = spec[0], spec[1], spec[2], spec[3]
            # VAT-3: 5-й элемент — своя ставка НДС допа (у отеля завтрак и
            # парковка облагаются 19 %, хотя проживание 7 % — Aufteilungsgebot).
            # Отсутствует → None = «как у сделки», прежнее поведение кита.
            vat_rate = spec[4] if len(spec) > 4 else None
            Extra.objects.create(
                label=label,
                price_cents=int(Decimal(str(price)) * 100),
                scope=scope,
                per_night=per_night,
                sort_order=sort,
                is_active=True,
                vat_rate=Decimal(str(vat_rate)) if vat_rate is not None else None,
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
            # _compact_menu: длинную строку сворачиваем под «Über uns», иначе
            # хвост уводит автоматический overflow-дропдаун «Mehr».
            "menus": _compact_menu(kit.menus) or None,  # S7 (пусто → из nav)
            "storefront_root": kit.storefront_root,  # S4 стартовая страница
            "primary_module": kit.primary_module,  # явный primary (пусто → эвристика)
            "anprobe": kit.enable_anprobe,  # M3 Click&Reserve (presence-minimal)
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
            "section_intros": kit.section_intros or {},
            # M20U-7 (per-page): раскладки страниц-листингов (пусто → дефолт страницы).
            "catalog_layout": {"preset": kit.page_layouts.get("catalog", "")},
            "stay_index_layout": {"preset": kit.page_layouts.get("stay_index", ""), "mobile": 1},
            "events_index_layout": {"preset": kit.page_layouts.get("events", "")},
            "detail_related_layout": {"preset": kit.page_layouts.get("related", "")},
            "about_title": kit.about_title,
            "about_text": kit.about_text,
            "cta": kit.cta,
            "faq": [{"q": q, "a": a} for q, a in kit.faq],
            # GK-6: кортежи (name, text[, stars[, photo]]) — extras presence-minimal.
            "testimonials": [
                {
                    "name": u[0],
                    "text": u[1],
                    **({"stars": u[2]} if len(u) > 2 and u[2] else {}),
                    **({"photo": u[3]} if len(u) > 3 and u[3] else {}),
                }
                for u in kit.testimonials
            ],
            "process": [{"title": t, "text": x} for t, x in kit.process],
            "team": [
                {"name": n, "role": r, "photo": demo_image(kw, w=600, h=600, lock=700 + i)}
                for i, (n, r, kw) in enumerate(kit.team)
            ],
            "trust": kit.trust or {"since": "", "marks": []},
            # GK-5: кортежи (icon, label[, text]) — text presence-minimal (clean_usp).
            "usp_bar": [
                {"icon": u[0], "label": u[1], **({"text": u[2]} if len(u) > 2 and u[2] else {})}
                for u in kit.usp
            ],
            "gallery": [
                {"url": demo_image(kw, lock=500 + i), "alt": {"de": kit.label}}
                for i, kw in enumerate(kit.gallery_kw)
            ],
            "gallery_video": kit.gallery_video,
            "jobs_vehicle": kit.jobs_vehicle,  # A9: Kfz-Werkstatt — структурные авто-поля
            "anfrage": kit.anfrage_form,  # AF-1: событийные поля (normalize дропнет пустое)
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
    # FB-3 Вариант B: демо кастом-статусы + рёбра (только у китов, где заданы).
    if kit.status_defs:
        cfg["status_defs"] = kit.status_defs
    if kit.status_edges:
        cfg["status_edges"] = kit.status_edges
    if kit.enable_lots:  # Склад-2 E1.5: тумблер учёта партий/MHD (еда)
        cfg["lots_enabled"] = True
    if kit.enable_finder:  # FD-1: Finder — опция, в демо показываем
        cfg["finder"] = {"enabled": True}
    # --- Демо «по новой идеологии» (2026-07-19): пост-патчи новых фич ---
    accent = kit.accent
    if kit.look:
        # ST-1: визуальный оверлей Look-семейства (паттерн stateless-превью
        # ST-1b) — секции/тексты кита целы, полный apply_look их переписал бы.
        from apps.tenants import sitetemplates

        fam = sitetemplates.get_look_family(kit.look)
        if fam is not None:
            cfg["font"] = fam["font"]
            cfg["typography"] = siteconfig.normalize_typography(fam["typography"])
            cfg["site_defaults"] = dict(siteconfig.normalize_site_defaults(fam["site_defaults"]))
            nav_cfg = dict(cfg.get("nav") or {})
            nav_cfg["style"] = fam["nav_style"]
            cfg["nav"] = nav_cfg
            cfg["hero_style"] = fam["hero_style"]
            if fam["theme"] == "dark":
                cfg["theme"] = "dark"
            accent = sitetemplates.look_accent(kit.business_type, kit.look)
    # ST-7c/DL-19: форма карточек — значения из реестра `core.card_forms`.
    if kit.card_style in card_forms.keys_for(card_forms.PRODUCT):
        sd = dict(cfg.get("site_defaults") or {})
        sd["card_style"] = kit.card_style
        cfg["site_defaults"] = sd
    if kit.promo_card in card_forms.keys_for(card_forms.PROMO):  # DL-16.4 AK1 / DL-19
        sd = dict(cfg.get("site_defaults") or {})
        sd["promo_card"] = kit.promo_card
        cfg["site_defaults"] = sd
    if kit.card_slider:  # DL-16.4 P2: фото на карточке товара листаются
        sd = dict(cfg.get("site_defaults") or {})
        sd["card_slider"] = "on"
        cfg["site_defaults"] = sd
    if kit.variant_style:  # O-2: вид выбора вариантов (normalize отбросит мусор)
        sd = dict(cfg.get("site_defaults") or {})
        sd["variant_style"] = kit.variant_style
        cfg["site_defaults"] = sd
    if kit.hero_widget in siteconfig.HERO_WIDGETS:  # 07-30: кастомные + реестр плиток
        sd = dict(cfg.get("site_defaults") or {})
        sd["hero_widget"] = kit.hero_widget
        cfg["site_defaults"] = sd
    if kit.bundle:  # DS-9: композиция сборки Fokus (реестр BUNDLES)
        from apps.tenants import sitetemplates as _sitetemplates

        _sitetemplates.apply_bundle_config(cfg, kit.bundle)
    if kit.config_patch:  # DS-4 (Fokus): точечные оси сборки поверх look-оверлея
        for _k, _v in kit.config_patch.items():
            if isinstance(_v, dict) and isinstance(cfg.get(_k), dict):
                cfg[_k] = {**cfg[_k], **_v}
            else:
                cfg[_k] = _v
    if kit.presence_mode in ("on", "off"):  # LS-2: «Jetzt erreichbar»
        cfg["presence"] = {"mode": kit.presence_mode}
    if kit.page_presets:  # ST-2: пресеты страниц (блоки выживают normalize — замок)
        from apps.core import page_presets as page_presets_mod

        for host, preset_id in kit.page_presets:
            page_presets_mod.apply_page_preset(cfg, host, preset_id)
    if kit.page_blocks:  # блоки конкретных страниц (в т.ч. «catalog:<slug>»)
        _pb = dict(cfg.get("page_blocks") or {})
        for _host, _specs in kit.page_blocks.items():
            # KAT-6: слаг категории мог досуффиксоваться unique_slug — берём
            # фактический (иначе хост указывал бы на несуществующую страницу).
            if _host.startswith("catalog:"):
                _slug = _host.split(":", 1)[1]
                _host = "catalog:" + refs.get("category_slugs", {}).get(_slug, _slug)
            _pb[_host] = [
                {
                    "key": _key,
                    "id": f"pb-kit-{i}",
                    "enabled": True,
                    "data": dict(_data or {}),
                }
                for i, (_key, _data) in enumerate(_specs, start=1)
            ]
        cfg["page_blocks"] = _pb
    _demo_locales = [loc for loc in (kit.enabled_locales or []) if loc != "de"]
    if _demo_locales:  # DL-2/DL-3: оверлей текстов на все включённые локали
        from . import demo_i18n

        demo_i18n.overlay_config(cfg, _demo_locales)
    tenant.site_config = cfg
    tenant.primary_color = accent
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
    if kit.whatsapp_number:  # LS-1/LS-2: гейт видео-CTA и presence-пилюли
        tenant.whatsapp_number = kit.whatsapp_number
        update_fields.append("whatsapp_number")
    if kit.city:  # DS-4b: город кита сильнее дефолта сидера (eyebrow/SEO)
        tenant.city = kit.city
        update_fields.append("city")
    if kit.socials:  # GK-15: иконки футера (GK-9) — whitelist полей Tenant
        for f in ("instagram", "facebook", "linkedin", "tiktok", "youtube"):
            if kit.socials.get(f):
                setattr(tenant, f, kit.socials[f])
                update_fields.append(f)
    if kit.google_rating:  # GK-15: демо-кэш GK-11 (place_id пуст → beat молчит)
        tenant.google_rating = Decimal(str(kit.google_rating.get("rating", "0")))
        tenant.google_rating_count = int(kit.google_rating.get("count", 0))
        tenant.google_rating_updated_at = timezone.now()
        update_fields += ["google_rating", "google_rating_count", "google_rating_updated_at"]
    if kit.enabled_locales:  # DL-1: языки витрины (переключатель в шапке демо)
        # Только валидные коды из реестра LANGUAGES; первый — default_locale.
        valid = [c for c in kit.enabled_locales if c in dict(settings.LANGUAGES)]
        if valid:
            tenant.enabled_locales = valid
            tenant.default_locale = valid[0]
            update_fields += ["enabled_locales", "default_locale"]
    tenant.save(update_fields=update_fields)
    _seed_legal_docs(tenant, kit)  # E-2/L5: честное право в демо (вместо placeholder)
    if _demo_locales:  # DL-2/DL-3: переводы контента на все включённые локали
        from . import demo_i18n

        demo_i18n.translate_tenant_content(tenant, _demo_locales)
    # Решение владельца 2026-08-19: демо-кит пропускает мастер. Без этого свежий
    # демо-тенант открывался не кабинетом, а мастером настройки (AB5-редирект на
    # «нетронутом» состоянии) — вскрыто серверным обходом кабинета.
    from . import onboarding

    onboarding.mark_complete(tenant)
    return True


def _seed_legal_docs(tenant, kit: DemoKit) -> None:
    """E-2/L5: правовые DE-тексты демо-кита в LegalDoc (кабинет «Recht» заполнен,
    витрина без placeholder). Impressum/Datenschutz/Widerruf — из генераторов
    Tenant (контакты уже засеяны), без строки «Bitte anpassen»; AGB — заготовка
    по модулям кита. Вызывать в схеме тенанта, ПОСЛЕ tenant.save."""
    from apps.core.models import LegalDoc

    def _strip_hint(text: str) -> str:
        return text.replace("\n\nHinweis: Bitte passen Sie diesen Text an Ihr Geschäft an.", "")

    texts = {
        "impressum": tenant.impressum_text(),
        "datenschutz": _strip_hint(tenant.privacy_text()),
        "widerruf": _strip_hint(tenant.withdrawal_text()),
        "agb": _agb_template(tenant, kit),
    }
    for kind, text in texts.items():
        if text.strip():
            LegalDoc.objects.update_or_create(kind=kind, locale="de", defaults={"text": text})


def _agb_template(tenant, kit: DemoKit) -> str:
    """AGB-заготовка по типу бизнеса кита (какие модули продают). Честный
    базовый текст: Geltung, Vertragsschluss (§312j), Preise (PAngV), Zahlung +
    блоки по модулям (Abholung/Lieferung, Termine, Übernachtung, Tickets)."""
    mods = set(kit.enable_modules or [])
    kontakt = tenant.public_email or tenant.name
    # MEN-9: в режиме просчёта корзина НЕ заключает договор — §2 обязан описывать
    # реальный флоу (запрос → предложение → подтверждение), иначе AGB врёт.
    quote_mode = bool((kit.config_patch or {}).get("quote_cart"))
    vertragsschluss = (
        "§ 2 Vertragsschluss\nDie Darstellung unserer Leistungen ist kein bindendes "
        "Angebot. Über den Warenkorb senden Sie eine UNVERBINDLICHE Anfrage — daraus "
        "entsteht keine Zahlungspflicht. Wir prüfen Termin und Details und senden ein "
        "verbindliches Angebot; der Vertrag kommt mit Ihrer Annahme zustande."
        if quote_mode
        else "§ 2 Vertragsschluss\nDie Darstellung unserer Produkte und Leistungen ist "
        "kein bindendes Angebot. Mit Klick auf «Zahlungspflichtig bestellen» bzw. "
        "Absenden einer Buchung geben Sie ein verbindliches Angebot ab; der Vertrag "
        "kommt mit unserer Bestätigung zustande."
    )
    parts = [
        "Allgemeine Geschäftsbedingungen (AGB)\n",
        f"§ 1 Geltungsbereich\nDiese AGB gelten für alle Bestellungen und Buchungen "
        f"über die Website von {tenant.name}.",
        vertragsschluss,
        "§ 3 Preise und Zahlung\nAlle Preise verstehen sich in Euro inkl. der "
        "gesetzlichen MwSt. Es gelten die beim jeweiligen Angebot ausgewiesenen "
        "Zahlungsarten.",
    ]
    n = 4
    if "orders" in mods:
        extra = (
            " Bei Lieferung fallen die im Warenkorb ausgewiesenen Versand-/Lieferkosten an."
            if getattr(tenant, "delivery_enabled", False)
            else ""
        )
        parts.append(
            f"§ {n} Abholung und Lieferung\nBestellte Waren werden zur Abholung "
            f"bereitgestellt bzw. — sofern angeboten — ausgeliefert.{extra}"
        )
        n += 1
    if "booking" in mods:
        parts.append(
            f"§ {n} Termine\nGebuchte Termine sind verbindlich. Eine kostenfreie "
            "Stornierung ist bis 24 Stunden vor dem Termin möglich; bitte "
            f"kontaktieren Sie uns unter {kontakt}."
        )
        n += 1
    if "stays" in mods:
        parts.append(
            f"§ {n} Übernachtung\nFür Unterkunftsbuchungen gelten die beim Angebot "
            "ausgewiesenen Tarif- und Stornobedingungen; ggf. anfallende Kurtaxe "
            "wird gesondert ausgewiesen."
        )
        n += 1
    if "events" in mods:
        parts.append(
            f"§ {n} Veranstaltungen und Tickets\nTickets gelten für die angegebene "
            "Veranstaltung. Bei Absage durch den Veranstalter wird der Ticketpreis "
            "erstattet."
        )
        n += 1
    parts += [
        f"§ {n} Widerrufsrecht\nVerbrauchern steht ein Widerrufsrecht nach Maßgabe "
        "der Widerrufsbelehrung (siehe Seite «Widerruf») zu, soweit gesetzlich "
        "vorgesehen.",
        f"§ {n + 1} Streitbeilegung\nZur Teilnahme an einem "
        "Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle sind "
        "wir nicht verpflichtet und nicht bereit.",
        f"§ {n + 2} Schlussbestimmungen\nEs gilt deutsches Recht. Sollten einzelne "
        "Bestimmungen unwirksam sein, bleibt der Vertrag im Übrigen wirksam.",
    ]
    return "\n\n".join(parts)


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
    """A1/A2: отзывы о товаре (generic `reviews.Review`, entity_kind='product') на
    демо-товарах кита.

    Создаём опубликованные отзывы напрямую (демо доверенный — без проверки заказа,
    которая работает на витрине). Вызывается в схеме тенанта."""
    if not kit.product_reviews:
        return
    from apps.reviews.models import Review

    for idx, rating, name, email, comment in kit.product_reviews:
        if not isinstance(idx, int) or idx >= len(created_products):
            continue
        Review.objects.update_or_create(
            entity_kind="product",
            entity_id=created_products[idx].pk,
            email=email.lower(),
            defaults={
                "rating": rating,
                "author_name": name,
                "comment": comment,
                "verified": True,
                "is_published": True,
            },
        )


def _seed_entity_reviews(kit: DemoKit, refs: dict) -> None:
    """UA4-4b: отзывы об услуге/номере/событии (generic reviews.Review) на демо-
    сущностях кита — чтобы секция отзывов на детали была видна в демо.

    index — позиция в refs[<key>] (pk-список в порядке создания сидером). Пишем
    опубликованные отзывы напрямую (демо доверенный; верификация — на витрине).
    Вызывать в схеме тенанта ПОСЛЕ `_seed_kit_modules` (refs заполнены)."""
    specs = [
        (kit.service_reviews, "service", "services"),
        (kit.stay_reviews, "stay", "stay_units"),
        (kit.event_reviews, "event", "events"),
        (kit.combo_reviews, "combo", "combos"),  # MEN-21: наборы меню
    ]
    if not any(review_list for review_list, _kind, _key in specs):
        return
    from apps.reviews.models import Review

    for review_list, entity_kind, ref_key in specs:
        pks = refs.get(ref_key) or []
        for idx, rating, name, email, comment in review_list:
            if not isinstance(idx, int) or idx >= len(pks):
                continue
            Review.objects.update_or_create(
                entity_kind=entity_kind,
                entity_id=pks[idx],
                email=email.lower(),
                defaults={
                    "rating": rating,
                    "author_name": name,
                    "comment": comment,
                    "verified": True,
                    "is_published": True,
                },
            )


def _seed_blog_posts(tenant, kit: DemoKit) -> None:
    """RT4: опубликованные записи блога (events.BlogPost). Вызывать в схеме тенанта."""
    # CM-1: блог — свой модуль (recommended у всех типов), события не нужны.
    if not kit.blog_posts or not tenant.is_module_active("blog"):
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
            name, name_ov = _split_i18n(spec[0])  # L3d: строка ИЛИ i18n-дикт
            minutes, price = spec[1], spec[2]
            desc, desc_ov = _split_i18n(spec[3] if len(spec) > 3 else "")
            image_kw = spec[4] if len(spec) > 4 else ""
            rich = spec[5] if len(spec) > 5 and isinstance(spec[5], dict) else {}
            image = (
                {"url": demo_image(image_kw, w=600, h=400, lock=620 + i), "alt": {"de": name}}
                if image_kw
                else {}
            )
            svc = Service.objects.create(
                name=name,
                name_i18n=name_ov,
                description=desc,
                description_i18n=desc_ov,
                image=image,
                duration_minutes=minutes,
                price_cents=int(Decimal(price) * 100),
                attributes=rich.get("attributes", []),
                faq=rich.get("faq", []),
                primary_action=rich.get("primary_action", ""),
                # LS-1: видео-услуга (CTA «Per Video zeigen lassen» — гейт
                # whatsapp_number кита).
                is_video=bool(rich.get("is_video")),
            )
            refs["services"].append(str(svc.pk))
    if kit.combos and is_active("catalog"):
        # L3d.3: комбо-наборы с i18n (дыра master-track §7.0 — combo в демо не было).
        # MEN-6: спека += поля «набора меню» (photos/category/per_person/min_persons/
        # event_types/free_pool; группы — included/min/max; опция может нести
        # надбавку кортежем ("Name", "6.00")).
        from apps.catalog.models import Category, Combo, ComboGroup, ComboOption, Product

        refs["combos"] = []  # MEN-21: pk-лист для combo_reviews (порядок спеки)
        for ci, cspec in enumerate(kit.combos):
            cname, cname_ov = _split_i18n(cspec.get("name", ""))
            cdesc, cdesc_ov = _split_i18n(cspec.get("description", ""))
            category = None
            if cspec.get("category"):
                # KAT-6: слаг спеки → фактический (unique_slug мог досуффиксовать).
                actual = refs.get("category_slugs", {}).get(cspec["category"], cspec["category"])
                category = Category.objects.filter(slug=actual).first()
            combo = Combo.objects.create(
                name=cname,
                name_i18n=cname_ov,
                description=cdesc,
                description_i18n=cdesc_ov,
                price=Decimal(str(cspec.get("price", "0"))),
                images=[
                    _image_ref(kw, 8700 + ci * 10 + j, cname)
                    for j, kw in enumerate(cspec.get("photos", []))
                ],
                category=category,
                price_per_person=bool(cspec.get("per_person")),
                min_persons=int(cspec.get("min_persons", 0)),
                event_types=list(cspec.get("event_types", [])),
                free_pool=bool(cspec.get("free_pool")),
                sort_order=ci,
                is_active=True,
            )
            refs["combos"].append(str(combo.pk))
            for gi, gspec in enumerate(cspec.get("groups", [])):
                entries = [
                    (p, "0") if isinstance(p, str) else (p[0], str(p[1]))
                    for p in gspec.get("products", [])
                ]
                # Product.name — i18n-JSONField: матчим по базовой de-строке.
                by_name = {
                    p.get_i18n("name"): p
                    for p in Product.objects.filter(name__de__in=[n for n, _d in entries])
                }
                if not by_name:  # fail-soft: без товаров группа не нужна
                    continue
                group = ComboGroup.objects.create(
                    combo=combo,
                    label=gspec.get("label", ""),
                    included=bool(gspec.get("included")),
                    min_select=int(gspec.get("min", 1)),
                    max_select=int(gspec.get("max", 1)),
                    sort_order=gi,
                )
                for oi, (pname, delta) in enumerate(entries):
                    if pname in by_name:
                        ComboOption.objects.create(
                            group=group,
                            product=by_name[pname],
                            price_delta=Decimal(delta),
                            sort_order=oi,
                        )
    if kit.product_courses and is_active("catalog"):
        # MEN-6: тип подачи (Gang) блюдам — питает «свободную сборку» и PDF.
        from apps.catalog.models import Product

        for pname, course in kit.product_courses.items():
            Product.objects.filter(name__de=pname).update(course=course)
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

        from apps.stays.models import Room, SeasonRate, StayUnit

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
                _un, _un_ov = _split_i18n(spec["name"])  # L3d
                _ud, _ud_ov = _split_i18n(spec.get("description", ""))
                unit = StayUnit.objects.create(
                    name=_un,
                    name_i18n=_un_ov,
                    type=spec.get("type", "room"),
                    description=_ud,
                    description_i18n=_ud_ov,
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
                # PMS-R: физические номера («101») — число = qty (синк ёмкости).
                for j, num in enumerate(spec.get("rooms", [])):
                    Room.objects.create(unit=unit, number=str(num), sort_order=j)
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
    # UB3-2: подборки (Collection) — чипы-фасет листингов услуг/номеров. Спека кита:
    # [(name, {"services": [idx…], "stay_units": [idx…]})], индексы — позиции в
    # refs["services"]/refs["stay_units"] (порядок создания сидером выше).
    if kit.collections:
        from django.utils.text import slugify

        from apps.collections.models import Collection

        refs["collections"] = []
        for i, (col_name, members) in enumerate(kit.collections):
            col = Collection.objects.create(name=col_name, slug=slugify(col_name), sort_order=i)
            svc_ids = refs.get("services", [])
            for idx in members.get("services", []):
                if idx < len(svc_ids):
                    col.services.add(svc_ids[idx])
            unit_ids = refs.get("stay_units", [])
            for idx in members.get("stay_units", []):
                if idx < len(unit_ids):
                    col.stay_units.add(unit_ids[idx])
            # M4-B Lookbook: товары подборки + фото образа (страница /lookbook/<slug>/).
            prod_ids = refs.get("products", [])
            for idx in members.get("products", []):
                if idx < len(prod_ids):
                    col.products.add(prod_ids[idx])
            photos = members.get("photos") or []
            if photos:
                col.images = [
                    {
                        **_image_ref(kw, 9300 + i * 10 + n, col_name),
                        "id": f"look-{i}-{n}",
                        "is_primary": n == 0,
                        "sort_order": n,
                    }
                    for n, kw in enumerate(photos)
                ]
                col.save(update_fields=["images", "updated_at"])
            refs["collections"].append(str(col.pk))
    if (
        kit.kurtaxe or kit.house_rules or kit.auto_discounts or kit.occupancy_pricing
    ) and is_active("stays"):
        from apps.stays.models import StaySettings  # H9 Kurtaxe + H6 Hausordnung + G4 авто-скидки

        settings_obj = StaySettings.load()
        if kit.kurtaxe:
            settings_obj.kurtaxe_cents = int(Decimal(str(kit.kurtaxe)) * 100)
        if kit.house_rules:
            settings_obj.house_rules = kit.house_rules
        if kit.auto_discounts:  # G4: список правил {kind, threshold, percent}
            settings_obj.auto_discount_rules = list(kit.auto_discounts)
        if kit.occupancy_pricing:  # PMS-D: ручные occupancy-правила цены
            settings_obj.occupancy_rules = list(kit.occupancy_pricing)
        settings_obj.save(
            update_fields=[
                "kurtaxe_cents",
                "house_rules",
                "auto_discount_rules",
                "occupancy_rules",
                "updated_at",
            ]
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
        # MT-1: тур-продукты создаём ДО заездов — событие ссылается на тур индексом.
        refs["tours"] = []
        if kit.tours:
            from django.utils.text import slugify

            from apps.events import details as _tourdetails
            from apps.events import itinerary as _itinerary
            from apps.events.models import Tour

            for tidx, spec in enumerate(kit.tours):
                photos = [
                    _image_ref(kw, 9600 + tidx * 10 + j, spec["title"])
                    for j, kw in enumerate(spec.get("photos", []))
                ]
                for j, ref in enumerate(photos):
                    ref["is_primary"] = j == 0
                    ref["sort_order"] = j
                tour = Tour.objects.create(
                    title=spec["title"],
                    slug=slugify(spec["title"])[:200] or f"tour-{tidx + 1}",
                    summary=spec.get("summary", ""),
                    description=spec.get("description", ""),
                    region=spec.get("region", ""),
                    country=spec.get("country", ""),  # MT-D2: ключ группировки листинга
                    difficulty=spec.get("difficulty", ""),
                    duration_days=spec.get("duration_days", 0),
                    distance_km=spec.get("distance_km", 0),
                    images=photos,
                    details=_tourdetails.normalize(spec.get("details") or {}),
                    itinerary=_itinerary.normalize(spec.get("itinerary") or []),
                    is_published=spec.get("published", True),
                    sort_order=tidx,
                )
                picked = spec.get("teachers")
                if refs.get("teachers"):
                    ids = (
                        [refs["teachers"][i] for i in picked if i < len(refs["teachers"])]
                        if picked is not None
                        else refs["teachers"]
                    )
                    tour.teachers.set(Teacher.objects.filter(pk__in=ids))
                refs["tours"].append(str(tour.pk))
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
                    # MT-1: событие как заезд тура (индекс в kit.tours; вне диапазона —
                    # просто самостоятельное событие, сид не падает).
                    tour_id=(
                        refs["tours"][spec["tour"]]
                        if spec.get("tour") is not None
                        and spec["tour"] < len(refs.get("tours") or [])
                        else None
                    ),
                )
                # MX-2d: адресная опция аренды у ЭТОГО заезда — тир перестал
                # смешивать участие с арендой; пул и поставщик на опции.
                rental = spec.get("rental_option")
                if rental:
                    from apps.core.models import Extra as _Extra
                    from apps.inventory.models import Lieferant as _Lieferant

                    r_label, r_price, r_pool, r_supplier = rental
                    _sup, _created = _Lieferant.objects.get_or_create(name=r_supplier)
                    _Extra.objects.create(
                        label=r_label,
                        price_cents=int(Decimal(str(r_price)) * 100),
                        scope=_Extra.SCOPE_EVENTS,
                        entity_kind="event",
                        entity_id=str(event.pk),
                        tracker=_Extra.TRACKER_POOL,
                        pool_size=int(r_pool),
                        supplier=_sup,
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
        _seed_tour_operations(kit, refs)


def _seed_group_chat(kit: DemoKit, space, event) -> None:
    """MT-F5: реплики чата и комментарии к объявлениям гида.

    Авторы — имена (`author_name`): чат сеется вместе с пространством, то есть
    ДО билетов (`_seed_kit_records`), поэтому связать реплику с реальным
    Customer нечем. Для демо важно, что видно имя и разговор — а не чей это id.
    Текст остаётся немецким: у `FeedPost` нет i18n-оверлея (закрытая зона
    участников), словарь демо туда не доезжает — врать переводом не будем.
    """
    from apps.community.models import FeedPost
    from apps.community.services import add_comment, add_post

    ops = kit.tour_operations or {}
    posts = list(
        FeedPost.objects.filter(space=space, kind=FeedPost.KIND_POST).order_by("created_at")
    )
    for idx, name, text in ops.get("comments", []):
        if idx < len(posts):
            add_comment(posts[idx], body=text, name=name)
    for name, text in ops.get("chat", []):
        add_post(space, body=text, kind=FeedPost.KIND_MESSAGE, name=name)


def _seed_tour_operations(kit: DemoKit, refs: dict) -> None:
    """MT-3/4/6 в демо: пространство поездки, закупки по точкам и чек-лист.

    Наполняем ПЕРВЫЙ заезд кита — так демо показывает волны вживую, а не пустыми
    экранами. Всё через штатные сервисы, чтобы демо ходило тем же путём, что и
    живой тенант.
    """
    if not kit.tour_operations or not refs.get("events"):
        return
    from datetime import timedelta

    from django.utils import timezone

    from apps.community.services import add_post, space_for_event
    from apps.events.logistics import SupplierBooking, TourTask
    from apps.events.models import Event

    event = Event.objects.filter(pk=refs["events"][0]).first()
    if event is None:
        return
    space = space_for_event(event)
    for text in kit.tour_operations.get("posts", []):
        add_post(space, body=text)
    # MT-F5: вкладка «Chat» была пустой — засеваем реплики участников и
    # комментарии к объявлениям гида. Авторы — реальные клиенты этого заезда
    # (билеты уже созданы seed_records), иначе просто имя.
    _seed_group_chat(kit, space, event)
    for spec in kit.tour_operations.get("supplier_bookings", []):
        SupplierBooking.objects.create(
            event=event,
            kind=spec.get("kind", SupplierBooking.KIND_HOTEL),
            supplier_name=spec.get("supplier", ""),
            day=spec.get("day", 0),
            stop=spec.get("stop", ""),
            qty=spec.get("qty", 1),
            cost_cents=int(Decimal(str(spec.get("cost", "0"))) * 100),
            currency=spec.get("currency", ""),
            amount_original=spec.get("original"),
            status=spec.get("status", SupplierBooking.STATUS_TO_BOOK),
            visible_to_participants=bool(spec.get("visible")),
            note=spec.get("note", ""),
        )
    today = timezone.localdate()
    for idx, spec in enumerate(kit.tour_operations.get("tasks", [])):
        TourTask.objects.create(
            event=event,
            title=spec.get("title", ""),
            due_date=today + timedelta(days=spec.get("in_days", 7)),
            done_at=timezone.now() if spec.get("done") else None,
            sort_order=idx,
        )


def _seed_demo_lots(kit: DemoKit, products: list) -> None:
    """Склад-2 E1.5: демо-партии (Chargen/MHD) для еда-китов. Первым ~8 товарам без
    вариантов заводим партии с реалистичным MHD, чтобы кабинет склада показал фичу
    наполненной. Если у демо-товара нет учёта остатка (stock_quantity=None — еда часто
    «immer verfügbar»), назначаем демо-остаток и создаём партии под него (Σlot ==
    счётчик, реконсиляция Вариант A). Товары с вариантами пропускаем — они ведут остаток
    отдельно (демо-партии — на товар-уровне)."""
    if not kit.enable_lots:
        return
    from datetime import timedelta

    from django.utils import timezone

    from apps.inventory.models import Lot

    today = timezone.localdate()
    seeded = 0
    for i, product in enumerate(products):
        if seeded >= 8:
            break
        if getattr(product, "pk", None) is None or product.variants.exists():
            continue  # варианты ведут остаток отдельно — демо-партии на товар-уровне
        product.refresh_from_db(fields=["stock_quantity"])
        qty = product.stock_quantity
        if qty is None:  # еда без учёта → назначаем демо-остаток (12..36)
            qty = 12 + (i % 5) * 6
            product.stock_quantity = qty
            product.save(update_fields=["stock_quantity", "updated_at"])
        if qty <= 0:
            continue
        # Первая партия (короткий срок, ~1/3) + свежая (остальное) — так в кабинете
        # видно и «läuft bald ab», и запас. Один товар (i%4==0) делаем просроченным.
        near_days = -1 if i % 4 == 0 else 2 + i % 3
        near = max(1, qty // 3)
        Lot.objects.create(
            product=product,
            qty_received=near,
            qty_remaining=near,
            mhd=today + timedelta(days=near_days),
            lot_code=f"CH-{1000 + i}",
        )
        rest = qty - near
        if rest > 0:
            Lot.objects.create(
                product=product,
                qty_received=rest,
                qty_remaining=rest,
                mhd=today + timedelta(days=10 + i % 5),
                lot_code=f"CH-{2000 + i}",
            )
        seeded += 1


def _seed_demo_purchasing(kit: DemoKit, products: list) -> None:
    """Склад-2 E3: демо-закупки для еда-китов (enable_lots как маркер «склад важен»):
    поставщик + одна received-Bestellung (история) + одна ordered (можно принять в демо).
    Приёмка received-заказа НЕ книжится повторно (демо-остатки уже выставлены) — просто
    отмечаем qty_received, история движений не раздувается."""
    if not kit.enable_lots:
        return
    from apps.inventory import purchasing
    from apps.inventory.models import Bestellung

    plain = [p for p in products if getattr(p, "pk", None) is not None][:4]
    if len(plain) < 2:
        return
    supplier = purchasing.Lieferant.objects.create(
        name="Großhandel Westfalen",
        contact_person="H. Brinkmann",
        email="bestellung@grosshandel-westfalen.example",
        phone="0231 555 0192",
        customer_number="K-40412",
    )
    done = purchasing.create_po(supplier=supplier, actor="demo", note="Wocheneinkauf")
    for i, product in enumerate(plain[:2]):
        line = purchasing.add_po_line(done, product=product, qty=10 + i * 5)
        line.qty_received = line.qty  # история: принят без повторной проводки склада
        line.save(update_fields=["qty_received", "updated_at"])
    purchasing.set_po_status(done, Bestellung.STATUS_ORDERED)
    purchasing.set_po_status(done, Bestellung.STATUS_RECEIVED)
    pending = purchasing.create_po(supplier=supplier, actor="demo", note="Nachbestellung")
    for product in plain[2:4]:
        purchasing.add_po_line(pending, product=product, qty=8)
    purchasing.set_po_status(pending, Bestellung.STATUS_ORDERED)


def _seed_kit_inbox() -> None:
    """LS-3/4/6: демо-треды «Прямой линии» — вопрос клиента со staff-ответом и
    открытым Sofort-Angebot (карточка в треде + публичная /o/<token>/) + high-тред
    «Etwas stimmt nicht?» (красная полоса на доске, SLA-бейджи). Сеем ПРЯМО
    моделями — без enqueue-хуков, демо не шлёт писем."""
    from decimal import Decimal as D

    from django.utils import timezone as tz

    from apps.inbox.models import Conversation, Message
    from apps.orders.models import Offer, OfferLine
    from apps.promotions.models import Customer

    kunde, _ = Customer.objects.get_or_create(
        email="sabine.k@example.de", defaults={"name": "Sabine K."}
    )
    conv = Conversation.objects.create(
        customer=kunde,
        subject="Balayage für schulterlanges Haar?",
        status=Conversation.STATUS_PENDING,
        channel=Conversation.CHANNEL_WEB,
        last_message_at=tz.now(),
    )
    Message.objects.create(
        conversation=conv,
        author_role=Message.AUTHOR_CUSTOMER,
        body="Hallo! Was würde ein Balayage bei schulterlangem Haar ungefähr kosten?",
    )
    Message.objects.create(
        conversation=conv,
        author_role=Message.AUTHOR_STAFF,
        body="Gern! Ich habe Ihnen ein persönliches Angebot zusammengestellt — siehe unten.",
    )
    offer = Offer.objects.create(
        conversation=conv,
        customer=kunde,
        customer_name="Sabine K.",
        customer_email="sabine.k@example.de",
        note="Inklusive Pflege-Kur und Beratung vor Ort.",
        valid_until=(tz.now() + timedelta(days=14)).date(),
    )
    OfferLine.objects.create(
        offer=offer, title="Balayage inkl. Beratung", qty=1, unit_price=D("119.00"), position=1
    )
    OfferLine.objects.create(
        offer=offer, title="Pflege-Kur Intensiv", qty=1, unit_price=D("15.00"), position=2
    )
    problem = Conversation.objects.create(
        customer=kunde,
        subject="Problem: Termin",
        priority=Conversation.PRIORITY_HIGH,
        status=Conversation.STATUS_OPEN,
        channel=Conversation.CHANNEL_WEB,
        ref_kind="booking",
        ref_id="DEMO-1",
        ref_label="Termin Sa 10:00",
        unread_for_staff=True,
        last_message_at=tz.now(),
    )
    Message.objects.create(
        conversation=problem,
        author_role=Message.AUTHOR_CUSTOMER,
        body="Ich stehe vor dem Salon, aber es ist geschlossen — mein Termin war doch heute?",
    )


def _seed_kit_winback(kit: DemoKit) -> None:
    """B4/LS-5: активная auto-win-back кампания — видна в /promotions/kampagnen/
    и в обзоре напоминаний Marketing-центра (ST-6). Писем не шлёт (beat)."""
    from apps.promotions.models import CouponCampaign

    wb = kit.winback
    CouponCampaign.objects.create(
        name="Wir vermissen Sie",
        kind=CouponCampaign.KIND_AUTO_WINBACK,
        status=CouponCampaign.STATUS_ACTIVE,
        inactive_days=wb.get("inactive_days", 60),
        discount_percent=wb.get("percent", 10),
        valid_days=30,
        subject=wb.get("subject", "Wir vermissen Sie — 10 % auf Ihren nächsten Besuch"),
        body="Kommen Sie wieder vorbei — Ihr persönlicher Code liegt bei.",
    )


def _seed_kit_records(tenant, kit: DemoKit, refs: dict, products: list) -> None:
    """Примеры транзакций по активным архетипам (заказы/заявки/брони/билеты) —
    чтобы кабинет демо был наполнен «как настоящий». Демо-тенант одноразовый
    (схема дропается), спец-маркировка не нужна. Адреса @example.de (RFC 2606) —
    реальным людям письма не уходят. Каждый блок изолирован (сбой не рушит сид)."""
    # Bugfix: timezone/timedelta ниже импортируются в условных ветках (booking/
    # stays) — при их пропуске (напр. shop-кит) имена оставались функц-локальными
    # и не связанными → UnboundLocalError на marketing_opt_in. Связываем на входе.
    from datetime import timedelta

    from django.utils import timezone

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
        from apps.catalog.models import Product

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
                # VF-9 (фидбэк 2026-08-24 «Detail (Katalog) пусто»): строка сметы
                # может ссылаться на позицию каталога по имени (product_name) —
                # иначе ВСЕ демо-строки Freitext и колонка выглядит пустой.
                # Fail-soft: товара нет → строка остаётся свободной.
                lines = []
                for ln in spec.get("lines", []):
                    ln = dict(ln)
                    pname = ln.pop("product_name", "")
                    if pname:
                        ln["product"] = Product.objects.filter(
                            is_active=True, name__de=pname
                        ).first()
                    lines.append(ln)
                set_lines(job, lines, vat_rate=spec.get("vat_rate", 19))
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
            # MX-2d: адресные опции события (аренда байка) — первый гость берёт
            # первую, чтобы Zusatzverkäufe в демо был не пустым.
            from apps.core import extras as _extras_engine

            _addressed = [
                e
                for e in _extras_engine.active_for(
                    "events", entity_kind="event", entity_id=str(ev.pk)
                )
                if e.entity_kind
            ]
            for idx, (who, mail, qty) in enumerate(
                [
                    ("Nina Roth", "nina@example.de", 2),
                    ("Paul Adam", "paul@example.de", 1),
                ]
            ):
                try:
                    _snap = (
                        _extras_engine.snapshot(
                            [_addressed[0].pk],
                            "events",
                            entity_kind="event",
                            entity_id=str(ev.pk),
                        )
                        if idx == 0 and _addressed
                        else None
                    )
                    # R8: подписываем waiver (на случай waiver_required события).
                    book_ticket(
                        ev,
                        name=who,
                        email=mail,
                        quantity=qty,
                        auto_confirm=True,
                        extras=_snap,
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

            # VS-3: демо связи «якорь + прикреплённая услуга» — к первой брони
            # номера цепляем запись-услугу (велопрокат). Обе сделки остаются
            # самостоятельными: своя вкладка, свой статус, своя цена.
            if created_bookings and is_active("booking"):
                try:
                    from datetime import datetime as _datetime
                    from datetime import time as _time

                    from apps.booking.models import Resource as _Resource
                    from apps.booking.services import book as _book
                    from apps.core import deal_links as _deal_links

                    anchor = created_bookings[0]
                    velo_res, _ = _Resource.objects.get_or_create(
                        name="Fahrradverleih", defaults={"capacity": 4}
                    )
                    start = timezone.make_aware(
                        _datetime.combine(anchor.arrival + timedelta(days=1), _time(9, 0))
                    )
                    velo = _book(
                        velo_res,
                        start=start,
                        end=start + timedelta(hours=8),
                        name=anchor.customer.name if anchor.customer_id else "Gast",
                        email=anchor.customer.email if anchor.customer_id else "gast@example.de",
                        auto_confirm=True,
                        # Со СВОЕЙ ценой: смысл связи в том, что услуга считается
                        # отдельно от брони (стенд ловил пустой справочный итог).
                        price_cents=2400,
                    )
                    _deal_links.attach(
                        "stay", anchor.pk, "booking", velo.pk, note="Fahrradverleih, 1 Tag"
                    )
                except Exception:
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
