# План: волна DCC «демо-покрытие каталога Золингена» (2026-10-15)

Документ для `docs/demo-city-coverage-plan-2026-10-15.md`. Кода в нём нет: только структуры, сигнатуры, реестр, тесты, оценки и порядок инкрементов. Все утверждения о коде сверены с файлами, ссылки в формате файл:строка.

---

## §0. Что нашла разведка

### 0.1 Справочник и как вычисляется категория листинга
- В справочнике **15 разделов** (`apps/core/city_categories.py:36-52`) и **76 категорий** (`:54-131`). Признаки — отдельная ось (`:134-153`), какие признаки допустимы в каком разделе — `TAGS_BY_SECTION` (`:159-199`). Подсказка категории по типу бизнеса — `BY_BUSINESS_TYPE` (`:206-223`), по теме события — `BY_EVENT_THEME` (`:226-236`).
- Категорию листинга считает `_city_fields` (`apps/aggregator/tasks.py:65-103`):
  - **product**: категория полки бизнеса (`Category.city_category`, её проставляет `apply_kit`, `demo_kits.py:24543`), иначе категория бизнеса. Признаки берутся **только из диет товара** (`:96-97`).
  - **service** и **business**: всегда категория бизнеса, **признаков нет никогда** (`:98-99`). Поэтому салон с массажем и ногтями даст одну категорию на всё.
  - **stay**: всегда `hotels` (`:87-88`). Категорию `ferienwohnungen` через номер **заполнить нельзя**, только через карточку бизнеса или акцию.
  - **event**: категория по `BY_EVENT_THEME`, иначе `events` (`:89-93`). Категории `kino`, `sport`, `familienausfluege` событием не получить, только категорией бизнеса или акцией.
  - **promotion**: своя категория → категория товара → категория бизнеса (`:80-86`). Но **спека акции в китах не умеет задавать `city_category`/`city_tags`**: в `_create_spec_promo` их нет (`demo_kits.py:24600-24669`). Отсюда признаки `regional`, `handgemacht`, `barrierefrei`, `hundefreundlich` у демо сегодня **не ставятся ничем**.
- Гейты попадания в каталог города:
  - товар: активен, есть фото (`url`), цена > 0, не скрыт (`tasks.py:894-901`);
  - **профиль «Nur Aktionen» удаляет листинги товаров** (`tasks.py:954-958`);
  - услуга требует активного модуля `booking` (`tasks.py:1024-1029`).
  - **Следствие для волны:** «лёгкий» бизнес (профиль `aktionen`) с 3–8 товарами в каталоге города не появится. Это противоречие в постановке, решение — §1.1, Р-1.
- SVG-плейсхолдер считается фото, потому что URL есть (`tasks.py:877-878`): товар с ним гейт проходит.
- Листинг события показывает **логотип бизнеса, а не фото события** (`tasks.py:412`), город берётся из события с откатом на город бизнеса (`:405`).
- Заголовок карточки бизнеса — только `{"de": tenant.name}` (`tasks.py:1087`). Это правильно: названия не переводим.

### 0.2 Киты
- Поля `DemoKit` (`demo_kits.py:80-384`), которые нужны волне: `profile`/`phone`/`lat`/`lng` (`:373-376`), `district` (`:379`), `city_categories` (`:382`), `business_city_category` (`:384`). Конструктор товара — `_p` (`:392-455`).
- 6 лёгких китов — `_LITE_COMMON` + `_lite_menus` (`:22473-22498`); пример `LITE_BAKERY` (`:22500-22608`).
- 11 китов T-8.22 — `_SOLINGEN_COMMON`, `_solingen_hours`, `_solingen_menus`, `_solingen_heroes` (`:23160-23205`); пример `KLINGENWERK` (`:23208-23310`). Один бизнес сегодня занимает **80–120 строк**. Реестр `KITS` — `:24119-24160`, файл длиннее 26 000 строк (`_seed_kit_records` на `:26155`).
- Что делает `apply_kit` с тенантом (`:24345-25089`): `is_demo=True` (`:25048`), район (`:25050`), `city_category` (`:25053`), координаты (`:25056`), перевод (`:25082`), пропуск мастера (`:25088`). Модули — `_seed_kit_modules`: услуги `:25347`, номера `:25466`, события `:25624`.
- **Грабля SKU:** `sku = f"{key.upper()[:3]}-{lock:03d}"` (`:24400`). При ключах `sg_…` все ~80 китов получили бы артикулы вида «SG_-001». Генератор обязан задавать `sku` явно.
- **Реальные улицы с номерами** у китов T-8.22: «Hauptstraße 41», «Düsseldorfer Straße 18», «Kölner Straße 22» (`:23236`, `:23339`, `:24037`). Есть риск указать на чужой реальный бизнес. Лёгкие киты используют вымышленные улицы («Klingenweg 7», `:22534`) — так и нужно.
- Телефоны `+49 212 5550xxx`, WhatsApp `+49 170 2000xxx` (`:22535-22536`) — **настоящие диапазоны**, вымышленных среди них нет (§8).
- «Elektro Schmitz» — фамилия плюс ремесло, высокий шанс совпасть с реальной фирмой (§8).

### 0.3 Фото
- Резолвер — `photo_static_name` (`apps/tenants/demo_images.py:738-778`). Порядок поиска: `{slug}-{lock}` при lock≠1 (`:748`) → точный файл → токены через запятую → псевдонимы (`:697-706`) → **префиксная группа, то есть кадр соседа** (`:765-775`). Акции и товары получают растущий lock (`demo_kits.py:24381`, `:24659-24661`), поэтому путь через lock реален.
- **Чужие пространства закрыты замками:**
  - `ol-*` — `test_outlet_photos.py:135-146`. Это почти вся электроника и часть «дома» фонда;
  - `markt-*` — `test_aktionsmarkt_photos.py:196-207`;
  - **дубли файлов по md5 запрещены** (`test_demo_photo_files.py:21-24`), так что скопировать кадр под новым именем нельзя.
- У китов T-8.22 большинство ключей **без файлов**, на витрине плейсхолдеры. Проверено: нет `chef-knife`, `bread-knife`, `santoku-knife`, `pocket-knife`, `scissors`, `knife-gift`, `knife-sharpening`, `kitchen-knife`, `smartphone-repair`, `battery`, `wallbox`, `yoga-class`. Ключ `electrician` берёт префиксную группу `electrician-man`/`-work`.
- Эмодзи-плейсхолдер — `_EMOJI` (`:27…`) и `_emoji_for` (`:612-619`). Незнакомая тема даёт ✨ или 🍽️, это и есть дефект «пустое место».
- Готовый образец замка «свой кадр или тематический плейсхолдер, но не кадр соседа» — `test_outlet_photos.py:100-131`.
- Инструменты добора: `scripts/fetch_cc0_photos.py` (лицензия жёстко `cc0,pdm`, `:27-43`), `scripts/demo_photo_sheet.py`, `scripts/demo_photo_fetch.py`.

### 0.4 Переводы
- Словари `{de: перевод}` на локаль, общие для всех китов (`demo_i18n.py:31-45`, `t()` на `:85-89`). `PROPER_NAMES` — `:52-82`. Identity-записи запрещены замком `test_demo_kits.py:199-206`.
- `scripts/demo_i18n_gap.py::measure()` работает **по спеке, без БД** (`:322-348`), умеет `--kit` (`:351-355`). Его можно превратить в CI-замок без сидинга.

### 0.5 Сидинг и CI
- `seed_demo_tenants` обходит киты **последовательно** (`:121-141`). На каждый `create_business` уходит около минуты на миграции схемы (докстринг `:33-34`, `services.py:134`). Затем `apply_kit` и `reconcile_schema` (`:183-188`).
- `_ensure_city_portal` вызывается **только для лёгких китов** (`:195-197`): `--group solingen-shops` без лёгких портал не создаст.
- Группы `KIT_GROUPS` (`:52-65`) считаются по полям кита, новые киты попадут в них сами.
- `deploy.sh:68` гоняет `migrate_schemas` **по всем схемам последовательно**. Каждые +80 демо-схем удлиняют каждый деплой (§5.4).
- **CI:**
  - `test_demo_lists.py:40-57` засевает **все** киты из `KITS` (сейчас 36, не 19). +80 китов — это +80 вызовов `apply_kit`, недопустимо;
  - статические замки по всем китам дёшевы и полезны: `test_demo_menus.py` (`:51-154`, `:217-249`), `test_demo_photo_report.py:100-104`;
  - сигналы `post_save` товаров и услуг ставят Celery-задачи при сидинге (`aggregator/apps.py:70-87`, `tasks.py:1163-1166`) — дубль работы `reconcile_schema`.
- Портал:
  - блоки главной: `BLOCK_LIMIT=6`, `per_business` 1–2 (`portal_home_blocks.py:27-28`, `:82`, `:96-139`);
  - повторяющиеся акции сами продлеваются (`promotions/tasks.py:142-159`), **события — нет**, демо-события протухают.
- `demo_switch._demo_slugs` строится по всем китам (`apps/core/demo_switch.py:19-23`): любой тенант со слагом демо считается демо. Поэтому новые слаги не должны занимать «натуральные» имена бизнесов.

### 0.6 Где Золинген сегодня
17 бизнесов закрывают каждый раздел хотя бы одним (`test_solingen_coverage.py:44-46`). Но на раздел приходится 1–3 бизнеса, а около 40 из 76 категорий пустые: `restaurants`, `mittagessen`, `takeaway`, `lieferservice`, `catering`, `herrenmode`, `kindermode`, `schmuck`, `computer`, `tv-audio`, `haushaltsgeraete`, `moebel`, `beleuchtung`, `kueche`, `kosmetik`, `naegel`, `massage`, `pflegeprodukte`, `yoga`, `wellness`, `optik`, `physiotherapie`, `kino`, `sport`, `outdoor`, `familienausfluege`, `kinder-aktivitaeten`, `autoteile`, `kfz-reparatur`, `vermietung`, `sanitaer`, `bau`, `montage`, `reparatur`, `it`, `beratung`, `reinigung`, `bueroservice`, `weitere-dienstleistungen`, `ferienwohnungen`, `touren`, `ausfluege`, `grooming`, `tierdienstleistungen`, `kunst`, `geschenke`.

---

## §1. Архитектура: компактная спека и генератор

### 1.1 Профили бизнеса (решение Р-1)
- **K «Kompakt»** (по умолчанию, ~85 %). Ступень 2 как у T-8.22: без `profile`, каталог и/или `booking`/`events`/`stays`, 3–8 позиций с фото и ценой, 1–3 акции. Только так товары и услуги попадают в каталог города (`tasks.py:956`, `:1028`).
- **A «Nur Aktionen»** (~15 %, где это естественно: кафе-мороженое, цветочный, присмотр за животными). 4–6 акций без товаров. В каталог идут только акции и карточка бизнеса.

### 1.2 Где живёт код
```
apps/tenants/demo_city/
  __init__.py        # CITY_KITS: dict[str, DemoKit] (eager-сборка всех спек)
  spec.py            # dataclass'ы спеки (frozen)
  builder.py         # build_kit(biz) -> DemoKit; пресеты часов/usp; меню/hero
  validate.py        # validate(biz) -> list[str]; predicted_categories(kit) -> set[str]
  photos.py          # photo_status(key) -> "own"|"placeholder"|"borrowed"
  solingen/
    __init__.py      # BUSINESSES = (*lebensmittel.BUSINESSES, …)
    lebensmittel.py  essen.py  mode.py  elektronik.py  haus.py  beauty.py
    gesundheit.py  freizeit.py  kinder.py  auto.py  handwerk.py
    dienstleistungen.py  reisen.py  tiere.py  kunst.py   # SECTION = "<ключ>" + BUSINESSES
```
- **Формат — Python, не YAML.** Это типы, проверка ruff, никакой новой зависимости и загрузчика, переиспользование `_p` и пресетов. Файл раздела — табличные конструкторы по 15–40 строк на бизнес.
- **Регистрация.** В конце `demo_kits.py`, после `KITS` (`:24160`): `KITS.update(_city_kits())`, где `_city_kits()` импортирует `demo_city`. Цикл импорта безопасен, потому что `demo_city` берёт из `demo_kits` только имена, определённые выше места импорта (`DemoKit`, `_p`, `_mg`, `_solingen_menus`, `_lite_menus`). Это держит замок импорта.
- **Новое поле `DemoKit.origin: str = ""`** (`"city:solingen"`) — маркер для групп и выборочных тестов. По умолчанию пустое, существующие киты не меняются.

### 1.3 Структуры спеки (`spec.py`)
```python
@dataclass(frozen=True)
class Item:            # товар полки
    name: str; price: str; desc: str; photo: str | tuple[str, ...]
    diets: tuple[str, ...] = (); allergens: tuple[str, ...] = ()
    badge: str = ""; unit: str = ""; content: str | None = None   # PAngV Grundpreis
    vat: str = ""; origin: str = ""; stock: int | None = None; sku: str = ""

@dataclass(frozen=True)
class Shelf:           # категория кита = одна категория справочника
    name: str; slug: str; city_category: str; items: tuple[Item, ...]

@dataclass(frozen=True)
class Svc:             # услуга (booking)
    name: str; minutes: int; price: str; desc: str; photo: str

@dataclass(frozen=True)
class Offer:           # акция
    title: str; desc: str; price: str; was: str = ""          # was → compare_at (UWG: > price)
    ends: str = "week"   # "today" | "week" (recurrence weekly) | "14d" | "none" (no_end)
    response: str = ""   # "" | show | coupon | reserve | inquire (T-8.2/T-8.3)
    photo: str = ""; group: str = ""; style: str = ""          # discount_style
    city_category: str = ""; tags: tuple[str, ...] = ()        # → Promotion.city_category/city_tags
    item: str = ""       # цель по ИМЕНИ товара (STU-18h, не индекс)

@dataclass(frozen=True)
class Ev:              # событие (events)
    title: str; in_days: int; hour: int; price: str; capacity: int
    desc: str; photo: str; theme: str = ""   # theme → BY_EVENT_THEME

@dataclass(frozen=True)
class Room:            # номер (stays)
    name: str; kind: str; qty: int; price: str; guests: int; desc: str; photos: tuple[str, ...]

@dataclass(frozen=True)
class Biz:
    key: str                 # "sg_trattoria_lumetto"
    label: str               # «Trattoria Lumetto» (не переводится)
    btype: str               # Tenant.BUSINESS_TYPES
    category: str            # Tenant.city_category (business_city_category)
    district: str            # slug apps/core/districts
    street: str; house: str  # ВЫМЫШЛЕННАЯ улица из реестра STREETS[district]
    lat: str; lng: str
    phone: str               # из выделенного диапазона (§8, Р-5)
    profile: str = "K"       # "K" | "A"
    accent: str = "#334155"; hero_photo: str = ""
    tagline: str = ""        # hero_text
    about: str = ""
    hours: str = "laden"     # ключ пресета HOURS
    usp: tuple[str, ...] = ()            # ключи библиотеки USP
    shelves: tuple[Shelf, ...] = (); services: tuple[Svc, ...] = ()
    events: tuple[Ev, ...] = (); rooms: tuple[Room, ...] = ()
    offers: tuple[Offer, ...] = ()
    anfrage: tuple[str, ...] = ()        # поля формы заявки AF-1 → jobs
    delivery_plz: tuple[str, ...] = ()   # lieferservice
    whatsapp: str = ""
```

### 1.4 Генератор (`builder.py`)
```python
HOURS: dict[str, dict[int, tuple[str, str]]]   # ~11 пресетов: laden, lebensmittel, baeckerei,
                                               # gastro, cafe, praxis, handwerk, studio, kultur, hotel, freizeit
USP: dict[str, tuple[str, str]]                # ~60 фраз: ключ → (icon, текст) — общие строки
def hours_text(hours: dict) -> str             # единый формат «Mo–Fr 9:30–18:30 · Sa 10:00–14:00»
def build_kit(biz: Biz) -> DemoKit
def city_kits(businesses) -> dict[str, DemoKit]
```
Правила сборки:
- `subdomain = "sg-" + key[3:].replace("_", "-")`. Явная пометка демо: не занимает «натуральные» слаги реальных бизнесов, проходит гейт `demo_switch`.
- `city="Solingen"`, `origin="city:solingen"`, `business_city_category=biz.category`. Адрес собирается как `f"{street} {house}, {PLZ района} Solingen"`, PLZ берётся из `districts.CITIES` (`districts.py:27-45`).
- Модули: `shelves` → каталог (core); `services` → `["booking"]`; `events` → `["events"]`; `rooms` → `["stays"]`; `anfrage` → `["jobs"]` + `anfrage_form`; `delivery_plz` → `delivery`.
- Меню — `_solingen_menus(*filled)` по наполненным модулям; профиль A — `_lite_menus()` + `_LITE_COMMON`. Это закрывает `test_demo_menus.py:126-154`.
- Hero: два слайда `_solingen_heroes` (первая акция + сам бизнес), кнопка — по главному модулю (`/sortiment/`, `/termin/`, `/veranstaltung/`, `/unterkunft/`, `/anfrage/`).
- `categories=[(shelf.name, shelf.slug, [_p(…)])]`, `city_categories={slug: shelf.city_category}`. `sku` формируется как аббревиатура названия плюс номер.
- `Offer` превращается в dict `promotions_spec`. `ends="week"` → `recurrence="weekly"`, `ends_in_days=7`, акция сама продлевается (`promotions/tasks.py:142-159`).
- `opening_hours` и `opening_hours_text` — **из одного пресета**: строки часов повторяются у всех, переводов нужно около 11.
- `enable_categories_section` при ≥2 полках; `section_layouts` cols3 как у T-8.22.

### 1.5 Пример спеки (один бизнес ≈ 30 строк)
```python
Biz(
    key="sg_trattoria_lumetto", label="Trattoria Lumetto", btype="restaurant",
    category="restaurants", district="mitte", street="Schleifergasse", house="9",
    lat="51.1688", lng="7.0815", phone="<диапазон Р-5>", accent="#b91c1c",
    hero_photo="pizza-margherita", hours="gastro", usp=("hausgemacht", "terrasse", "familie"),
    tagline="Pizza aus dem Steinofen und Pasta wie in Ligurien — mitten in Solingen.",
    about="Familienbetrieb seit 2009: …",
    shelves=(Shelf("Pizza & Pasta", "pizza-pasta", "restaurants", (
        Item("Pizza Margherita", "9.50", "Tomate, Fior di Latte, Basilikum.", "pizza-margherita",
             diets=("vegetarisch",), allergens=("a", "g"), vat="7.00"),
        Item("Spaghetti Carbonara", "12.90", "…", "carbonara", allergens=("a", "c", "g"), vat="7.00"),
        # …ещё 3–4
    )),),
    offers=(Offer("Mittagstisch: Pasta + Salat 9,90 €", "Mo–Fr 11:30–14:30.", "9.90", was="13.40",
                  ends="week", response="show", photo="caprese-salad", group="Diese Woche"),),
)
```

### 1.6 Правки существующего кода (минимальные)
1. В `_create_spec_promo` (`demo_kits.py:24600-24669`) — ключи спеки `city_category` и `city_tags` → поля `Promotion`. Значения нормализуются через `cc.normalize_category`/`allowed_tags`. Без этого признаки демо невыразимы (§0.1).
2. `DemoKit.origin` (§1.2).
3. `seed_demo_tenants`: группа `solingen-dcc` и группы по разделам `sg:<раздел>`; `--jobs N` (§5); `_ensure_city_portal` для **любого** кита, город которого есть в реестре районов (`:195-197`).
4. *(Опция, Р-3.)* У номера категория = `tenant.city_category`, если она из раздела `reisen-uebernachten`, иначе `hotels` (`tasks.py:87-88`). Тогда `ferienwohnungen` заполнится честно.

---

## §2. Реестр: 15 разделов × бизнесы

Обозначения:
- районы: **MI** Mitte (42651) · **GR** Gräfrath (42653) · **WA** Wald (42719) · **BH** Burg/Höhscheid (42659) · **OAM** Ohligs/Aufderhöhe/Merscheid (42697);
- профиль: **K** — компактный, **A** — «Nur Aktionen»;
- фото: **✓** — кадры есть в фонде, **½** — частично или конфликт уникальности, **⚠** — добор (§3).

Все названия вымышленные, без схемы «фамилия + ремесло». Каждое название ещё проверяется на совпадение с реальными фирмами (§7h). «Klingenhalle» исключено: это реальная площадка Золингена. Существующие киты указаны *курсивом*.

**1. Lebensmittel & Getränke** — было 3, станет 8

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *klingenbrot* | *Bäckerei Klingenbrot* | bakery | MI | brot-backwaren | A | — | — |
| *wupperhof* | *Hofladen Wupperhof* | grocery | OAM | lebensmittel | A | — | — |
| *feinkost_markt* | *Feinkost am Markt* | grocery | MI | feinkost | K | — | — |
| sg_fleischerei_wupperbogen | Fleischerei Wupperbogen | butcher | BH | fleisch-wurst | K | 6 товаров (Bratwurst, Leberwurst, Schinken, Hack, Grillpaket, Fleischsalat) + «Grillwochenende» | ✓ bratwurst, ham-sliced, steak, butcher-meat, meat-salad, beef-filet |
| sg_klingenquelle | Getränkemarkt Klingenquelle | grocery | OAM | getraenke | K | 5 (соки, пиво ящиком, вино, вода — Grundpreis €/l) | ½ apple-juice, orange-juice, beer, red-wine; ⚠ вода |
| sg_obsthof_am_hang | Obsthof am Hang | grocery | GR | obst-gemuese | K | 5 + акция с признаком `regional` | ✓ apples, carrots, vegetable-box, farm-vegetables, honey |
| sg_kornblume | Bioladen Kornblume | grocery | WA | lebensmittel | K | 5 с диетами bio/vegan | ✓ noodles-durum, herbal-tea, honey-jar; ½ |
| sg_roesterei_bergbohne | Kaffeerösterei Bergbohne | grocery | MI | feinkost | K | 5 (Espresso, Filter, Entkoffeiniert, Cold Brew, Sencha) | ✓ kaffee-*, tee-* |

**2. Essen & Gastronomie** — было 1, станет 9

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *ohligser_eck* | *Café Ohligser Eck* | cafe | OAM | cafes | A | — | — |
| sg_trattoria_lumetto | Trattoria Lumetto | restaurant | MI | restaurants | K | 5 + Mittagstisch | ✓ pizza-margherita, pizza-salami, pasta-bolognese, carbonara, caprese-salad |
| sg_morgenstund | Frühstückshaus Morgenstund | cafe | GR | fruehstueck | K | 5 | ½ avocado-toast, bruschetta; ⚠ кадры breakfast/cappuccino/croissant заняты Золингеном |
| sg_kantine_42 | Mittagstisch Kantine 42 | restaurant | WA | mittagessen | K | 5 (суп/боул/карри) | ✓ minestrone-soup, salad-bowl, potato-salad, dal-soup |
| sg_grill_wrap | Grill & Wrap Ohligs | restaurant | OAM | takeaway | K | 5 с диетами vegan | ✓ vegan-pita, vegan-burger, vegan-currywurst, vegan-hotdog |
| sg_pizzabote | Pizzabote Klingenstadt | restaurant | BH | lieferservice | K | 5 + доставка по PLZ | ✓ pizza-vegetables, vegan-pizza, pasta, spring-salad |
| sg_tafelrunde | Tafelrunde Catering | catering | BH | catering | K | 4 пакета + заявка (дата/гости/тип) | ✓ catering-buffet, vegan-buffet, antipasti |
| sg_gelatino | Eiscafé Gelatino | cafe | WA | cafes | A | 5 акций (Eisbecher, Affogato, «Kugel-Montag») | ✓ ice-cream, affogato; ½ |
| sg_waffelstube | Waffelstube Unterburg | cafe | BH | cafes | K | 4 | ½ bee-sting-cake, black-forest-cake; ⚠ |

**3. Mode & Accessoires** — было 2, станет 7

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *walder_faden* | *Modehaus Walder Faden* | clothing | WA | damenmode | A | — | — |
| *schuhhaus* | *Schuhhaus Ohligs* | clothing | OAM | schuhe | K | — | — |
| sg_nadelstreif | Herrenausstatter Nadelstreif | clothing | MI | herrenmode | K | 5 | ✓ mode-* (кит clothing, не Золинген) |
| sg_puenktchen | Pünktchen Kindermode | clothing | GR | kindermode | K | 5 | ✓ mode-kinder* |
| sg_funkenflug | Goldschmiede Funkenflug | retail | WA | schmuck | K | 5 + акция с `handgemacht` | ✓ ring-firn, kette-kiesel, armband-ufer, armreif-moos |
| sg_riemenwerk | Lederwerkstatt Riemenwerk | retail | BH | taschen | K | 4 | ✓ bags-collection, canvas-bag, backpacks-shelf, backpack-office |
| sg_kleiderkreisel | Second-Hand Kleiderkreisel | clothing | OAM | damenmode | K | 4 + акция с `gebraucht` | ⚠ (`ol-w-*` закрыты) |

**4. Elektronik & Technik** — было 1, станет 6; фото — целиком добор

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *handy_doktor* | *Handy-Doktor Ohligs* | retail | OAM | smartphones | K | — | — |
| sg_bitbruecke | PC-Werkstatt Bitbrücke | retail | MI | computer | K | 4 + ремонт (booking) | ⚠ |
| sg_klangraum | HiFi-Studio Klangraum | retail | WA | tv-audio | K | 5 | ⚠ |
| sg_hausgeraete_wupper | Hausgeräte-Service Wupper | retail | BH | haushaltsgeraete | K | 4 + ремонт | ⚠ |
| sg_kabelsalat | Kabelsalat Technikzubehör | retail | GR | technik-zubehoer | K | 5 | ⚠ |
| sg_zweitakku | Refurbished-Laden Zweitakku | retail | MI | smartphones | K | 4 + `gebraucht` | ⚠ |

**5. Haus & Garten** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *wohnwerk* | *Wohnwerk Burg* | retail | BH | dekoration | K | — | — |
| sg_eichenstueck | Möbelwerkstatt Eichenstück | retail | GR | moebel | K | 4 | ✓ decken-kissen-sofa, set-schreibtisch-oben, set-sofaabend-decke |
| sg_gluehfaden | Leuchtenhaus Glühfaden | retail | MI | beleuchtung | K | 4 | ½ tischleuchte-knick-stahl, campinglampe-docht-laterne; ⚠ |
| sg_pfannenwerk | Küchenladen Pfannenwerk | retail | OAM | kueche | K | 5 | ✓ pfanne-feuer-gusseisen, braeter-sonntag-emaille, besteck-gerade-edelstahl, teekanne-bauch-steinzeug |
| sg_gruenspross | Gärtnerei Grünspross | retail | WA | garten-pflanzen | K | 5 | ⚠ растения |
| sg_vergissmeinnicht | Blumen Vergissmeinnicht | retail | GR | garten-pflanzen | A | 5 акций | ⚠ цветы |

**6. Beauty & Pflege** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *graefrather_markt* | *Salon am Gräfrather Markt* | friseur | GR | friseur | A | — | — |
| sg_messerscharf | Barbershop Messerscharf | friseur | OAM | friseur | K | 4 услуги | ✓ barber, barber-man, haircut |
| sg_rosenblatt | Kosmetikstudio Rosenblatt | other | MI | kosmetik | K | 4 услуги | ⚠ |
| sg_perlmutt | Nagelstudio Perlmutt | other | WA | naegel | K | 4 услуги | ⚠ |
| sg_ruhepol | Massagepraxis Ruhepol | other | BH | massage | K | 3 услуги (wellness, без лечебных обещаний) | ⚠ |
| sg_schaumkrone | Seifenmanufaktur Schaumkrone | retail | GR | pflegeprodukte | K | 5 с диетой vegan | ✓ seife-kohle-minze, seife-salzluft-stueck, seife-dusche-stueck, bartoel-kiefer-flakon, hair-oil |

**7. Gesundheit & Fitness** — было 1, станет 6 (аптеки нет, §9)

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *bergisch_fit* | *Bergisch Fit* | other | WA | fitness | K | — | — |
| sg_lotusblick | Yogaraum Lotusblick | other | GR | yoga | K | 3 услуги + 2 события (тема yoga/meditation) | ✓ yoga-studio, yoga-mat, yoga-nature |
| sg_bewegungsraum | Physiotherapie Bewegungsraum | other | MI | physiotherapie | K | 3 услуги (тексты без HWG-обещаний) | ⚠ |
| sg_scharfblick | Optik Scharfblick | retail | OAM | optik | K | 4 + Sehtest | ½ brille-licht, sub-brillen, mode-sonnenbrille-kueste |
| sg_lindenbluete | Reformhaus Lindenblüte | grocery | BH | gesundheitsprodukte | K | 5 (без health claims) | ✓ tee-feldrand-kraeuter, honig-lindenbluete-glas, ayurveda-spices |
| sg_wupperwelle | Day-Spa Wupperwelle | other | BH | wellness | K | 3 услуги | ⚠ |

**8. Freizeit & Erlebnisse** — было 0 основных, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| sg_lichtspiel | Programmkino Lichtspiel | events | WA | kino | K | 4 сеанса-события (+3…+30 дней) | ⚠ |
| sg_steilwand | Kletterhalle Steilwand | other | BH | sport | K | 2 услуги + 1 событие | ⚠ |
| sg_drehscheibe | Töpferwerkstatt Drehscheibe | events | GR | workshops | K | 3 курса-события + 3 товара | ½ vase-krug-steinzeug, becher-faust-steinzeug; ⚠ |
| sg_wupperpfad | Outdoor-Schule Wupperpfad | events | BH | outdoor | K | 3 события (тема natur → outdoor) | ✓ rucksack-grat-wandern, campfire-night, wanderstoecke-schritt-paar |
| sg_funkenschlag | Kulturkeller Funkenschlag | events | MI | events | K | 4 события | ⚠ |
| sg_abenteuerwiese | Familienhof Abenteuerwiese | events | OAM | familienausfluege | K | 3 события + акция | ½ bbq-family; ⚠ |

**9. Kinder & Familie** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *spielkiste* | *Spielkiste Gräfrath* | retail | GR | spielzeug | K | — | — |
| sg_wolke7 | Babyladen Wolke 7 | retail | OAM | babybedarf | K | 5 | ✓ mode-baby* |
| sg_purzelbaum | Kinderturnen Purzelbaum | other | WA | kinder-aktivitaeten | K | 3 услуги + событие | ⚠ |
| sg_kreisel | Spielwaren Kreisel | retail | MI | spielzeug | K | 5 | ⚠ |
| sg_leseratte | Kinderbuchladen Leseratte | retail | BH | kinder-aktivitaeten | K | 4 (книги; полка → `spielzeug`) + «Vorlesestunde» | ½ journal-book; ⚠ |
| sg_kinderkiste | Kinder-Secondhand Kinderkiste | retail | MI | babybedarf | K | 4 + `gebraucht` | ⚠ (`mode-kinder*` занят sg_puenktchen) |

**10. Auto & Mobilität** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *rad_und_tat* | *Rad & Tat Solingen* | retail | BH | fahrraeder | K | — | — |
| sg_kolbenring | Kfz-Meisterbetrieb Kolbenring | werkstatt | OAM | kfz-reparatur | K | 4 услуги + заявка с данными авто | ✓ car-repair, car-workshop, car-mechanic |
| sg_ventil | Autoteile Ventil | retail | WA | autoteile | K | 5 | ✓ car-parts, air-filter, antifreeze, motor-oil, brake-pad |
| sg_profil | Reifenservice Profil | werkstatt | GR | kfz-reparatur | K | 3 услуги | ½ tire-change; ⚠ |
| sg_wupperschleife | Radverleih Wupperschleife | other | BH | vermietung | K | 3 услуги аренды | ½ bike-tour; ⚠ |
| sg_klingenmobil | Mietwagen Klingenmobil | other | MI | vermietung | K | 3 услуги | ⚠ |

**11. Handwerk & Reparatur** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *elektro_schmitz* | *Elektro Schmitz* | handwerker | GR | elektriker | K | — | — |
| sg_wasserlauf | Sanitärtechnik Wasserlauf | handwerker | WA | sanitaer | K | 3 услуги + заявка | ✓ plumber-man, bathroom-renovation, modern-bathroom, tiles-bathroom |
| sg_farbenfroh | Malerbetrieb Farbenfroh | handwerker | OAM | bau | K | 3 + заявка | ✓ painter-wall, painting-room, painted-wall |
| sg_schraubgut | Montageservice Schraubgut | handwerker | MI | montage | K | 3 | ½ handyman-tools; ⚠ |
| sg_absatz | Schuh- & Schlüsseldienst Absatz | other | BH | reparatur | K | 4 услуги | ⚠ |
| sg_zeitwerk | Uhrmacher Zeitwerk | retail | MI | reparatur | K | 2 услуги + 3 товара | ⚠ (`ol-watch` закрыт) |

**12. Dienstleistungen** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *lichtblick* | *Fotostudio Lichtblick* | other | MI | fotografie | K | — | — |
| sg_netzknoten | IT-Service Netzknoten | other | OAM | it | K | 3 услуги | ⚠ |
| sg_waermewende | Energieberatung Wärmewende | other | WA | beratung | K | 3 услуги | ⚠ |
| sg_bluetenweiss | Textilreinigung Blütenweiß | other | MI | reinigung | K | 4 услуги | ⚠ |
| sg_papierflieger | Copyshop Papierflieger | retail | GR | bueroservice | K | 3 товара + 2 услуги | ✓ papeterie-buero-uebersicht, notizbuch-leinen-a5 |
| sg_nadeloehr | Änderungsschneiderei Nadelöhr | other | BH | weitere-dienstleistungen | K | 4 услуги | ⚠ |

**13. Reisen & Übernachten** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *brueckenblick* | *Pension Brückenblick* | hotel | BH | hotels | A | — | — |
| sg_alte_schmiede | Hotel Zur Alten Schmiede | hotel | MI | hotels | K | 3 номера + акция | ✓ hotel-room, hotel-bed, hotel-lobby, hotel-single-room |
| sg_fachwerkblick | Ferienwohnung Fachwerkblick | hotel | GR | ferienwohnungen | K | 2 юнита (категория — через Р-3) | ✓ apartment-living, apartment-kitchen |
| sg_klingenpfad | Stadtführungen Klingenpfad | tour_operator | MI | touren | K | 3 события-экскурсии | ✓ city-tour, tour-guide-woman, tour-guide-man |
| sg_bergland_ausflug | Ausflugsfahrten Bergland | tour_operator | BH | ausfluege | K | 3 события | ⚠ |
| sg_wupperaue | Landgasthof Wupperaue | hotel | OAM | hotels | K | 2 номера | ✓ family-hotel-room, hotel-bathroom, hotel-interior |

**14. Tiere & Tierbedarf** — было 1, станет 6; фото — целиком добор

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *pfotenglueck* | *Pfotenglück Wald* | retail | WA | tierzubehoer | K | — | — |
| sg_wuschelkopf | Hundesalon Wuschelkopf | other | OAM | grooming | K | 4 услуги | ⚠ |
| sg_leinenlos | Hundeschule Leinenlos | other | BH | tierdienstleistungen | K | 3 услуги + событие | ⚠ |
| sg_napfglueck | Futterhaus Napfglück | retail | MI | tierfutter | K | 5 | ⚠ |
| sg_wasserwelt | Aquaristik Wasserwelt | retail | GR | tierzubehoer | K | 4 | ⚠ |
| sg_pfotenpause | Tiersitting Pfotenpause | other | WA | tierdienstleistungen | A | 4 акции | ⚠ |

**15. Kunst & Geschenke** — было 1, станет 6

| ключ | название | тип | район | категория | проф. | состав | фото |
|---|---|---|---|---|---|---|---|
| *klingenwerk* | *Klingenwerk Solingen* | retail | MI | lokale-produkte | K | — | — |
| sg_weisswand | Galerie Weißwand | retail | GR | kunst | K | 4 принта | ⚠ |
| sg_schleifchen | Geschenkeladen Schleifchen | retail | OAM | geschenke | K | 5 | ✓ geschenkpapier-bogen-drei, kerze-zeder-salz, postkarten-kueste-set |
| sg_drechselspan | Holzkunst Drechselspan | retail | BH | handgemachtes | K | 4 + `handgemacht` | ✓ loeffel-drei-olivenholz, buersten-zubehoer-holz; ½ |
| sg_heimatgut | Bergischer Laden Heimatgut | retail | WA | lokale-produkte | K | 5 + `regional` | ½ (honey-*/tee-* заняты Золингеном) ⚠ |
| sg_federkiel | Papeterie Federkiel | retail | MI | geschenke | K | 4 | ✓ notizbuch-taschen-a6, bleistift-werkbank-set, skizzenbuch-grau-a4, radierer-spitzer-paar |

**Итого:**
- **79 новых** бизнесов, всего в Золингене **96**, по 6–9 на раздел.
- Районы среди новых: MI 19, BH 18, GR 14, WA 14, OAM 14. Точный баланс выравнивается в инкременте a, валидатор держит долю каждого района ≥ 12 %.
- **Все 76 категорий** получают хотя бы одного носителя. `ferienwohnungen` покрыт пока только карточкой бизнеса (до Р-3); `kino`/`sport`/`familienausfluege` — категорией бизнеса и акциями с явной `city_category`.
- Координаты: внутри bbox Золингена lat 51.12–51.23, lng 6.98–7.17 и внутри приблизительного прямоугольника района. Прямоугольники выведены из координат существующих китов: GR 51.195–51.225 / 7.05–7.10; WA 51.170–51.195 / 7.02–7.07; MI 51.158–51.180 / 7.06–7.10; BH 51.130–51.165 / 7.06–7.17; OAM 51.130–51.185 / 6.98–7.04. Их нужно перепроверить по карте в инкременте a.

---

## §3. Фото-инвентаризация

**Правила волны:**
- только реальные CC0/PDM кадры или тематический плейсхолдер; AI-генерация запрещена;
- новые кадры — в собственном пространстве ключей **`sg-<тема>-<предмет>`**;
- `ol-*` и `markt-*` недоступны (замки, §0.3), копии файлов запрещены md5-замком;
- **один файл — не больше чем у одного бизнеса Золингена** (на портале не должно быть двух карточек с одним кадром). Кадры китов из других городов (`mode-*`, кадры Weitwerk, retreat, catering) в Золингене переиспользовать можно, но только одним бизнесом;
- ключ даёт либо **точно свой файл**, либо **никакой файл**: никаких префиксных групп, псевдонимов и вариантов `{slug}-{lock}`.

**Фонд по темам:**
- **Хорошо закрыто:** еда и напитки (пицца, паста, супы, салаты, веган-линейка, кофе и чай Weitwerk, мясо, соки, пиво, вино, мёд), детская и взрослая одежда (`mode-*`), украшения, сумки, кухня и посуда, мебель и текстиль, отель и апартаменты, парикмахерская и барбер, авто (`car-*`, `air-filter`, `brake-pad`, `motor-oil`, `tire-change`), сантехника и малярные работы, йога и outdoor, канцелярия и подарки.
- **Пробелы (добор, инкремент f):**
  - животные: собака, кошка, груминг, аквариум, корм, поводок;
  - цветы и растения: букет, тюльпаны, горшечные растения, рассада;
  - красота: маникюр, лак для ногтей, уход за лицом, массаж, спа;
  - здоровье: физиотерапия, очки (частично);
  - досуг: кинозал, скалодром, гончарный круг, концерт, игровая площадка;
  - дети: деревянные игрушки, плюшевый мишка, кубики, коляска, детские книги;
  - электроника целиком (из-за `ol-*`): ноутбук, наушники, смартфон, телевизор, кабель, тостер, стиральная машина;
  - услуги: прачечная, швейная машинка, ключи, копировальный аппарат;
  - искусство: картина, галерея;
  - мобильность: аренда авто, велосипед крупным планом.
- **Запросы** к `scripts/fetch_cc0_photos.py` — короткие, 1–2 слова (урок AMP): `dog grooming`, `dog`, `cat`, `aquarium`, `dog food`, `bouquet`, `tulips`, `houseplant`, `seedlings`, `manicure`, `nail polish`, `facial`, `massage`, `spa`, `physiotherapy`, `eyeglasses`, `cinema`, `climbing wall`, `pottery wheel`, `concert`, `playground`, `wooden toy`, `teddy bear`, `building blocks`, `stroller`, `children books`, `laptop`, `headphones`, `smartphone`, `television`, `cable`, `toaster`, `washing machine`, `laundry`, `sewing`, `keys`, `photocopier`, `painting`, `art gallery`, `rental car`, `bicycle`.
- **Ожидание:** около 175 слотов, по прошлым волнам попадание 0–70 % (catering 2 из 15, outlet 171 из 249) → примерно 90–110 новых кадров. Остаток живёт на плейсхолдере.
- **Плейсхолдер обязан быть тематическим.** В `_EMOJI` (`demo_images.py:27`) добавить: 🐕 🐈 🐠 💐 🪴 💅 🧖 🎬 🧗 🏺 🧸 📚 💻 🎧 📺 🔌 🫧 🧺 🧵 🔑 🖨️ 🖼️ 🚗. Порядок подстрок важен: например, `uhr` ловится внутри других слов.
- **Приёмка кадра:** просмотр глазами, без узнаваемых лиц, без водяных знаков и чужой географии; webp ≤ 150 КБ; md5-дедуп; провенанс в `SOURCES.md`.
- **Опционально:** перевести 11 китов T-8.22 с несуществующих ключей на `sg-*` кадры.

---

## §4. Переводы

**Объём.** Около 28 уникальных строк на бизнес: hero, about, 1–2 полки, 3–6 позиций по название+описание, услуги, акции. Итого примерно **2200 строк × 4 локали ≈ 8800 записей**, минус ~15 % общих.
- Общие строки (часы, `USP`, меню, «Zu den Angeboten», группы акций) переводятся один раз, поэтому их держим **библиотеками** (`HOURS`, `USP`), а не свободным текстом.
- Названия заведений не переводятся: `measure()` и так относит `kit.label` к именам собственным (`demo_i18n_gap.py:329`). Вымышленные имена внутри позиций (например «Teller „Wupper“») — в `PROPER_NAMES` (`demo_i18n.py:52-82`) или в кавычках по правилу I18N-14.
- Identity-записи не пишем (замок `test_demo_kits.py:199-206`). Строки вроде «Espresso» и «Croissant» уходят в `PROPER_NAMES`, а не в словарь.

**Как держать покрытие ≥ 95 %:**
1. Перенести `Collector`/`measure` из `scripts/demo_i18n_gap.py` в модуль `apps/tenants/demo_i18n_measure.py`; скрипт его импортирует.
2. CI-замок `test_city_i18n`: для каждого кита с `origin="city:solingen"` строк без пути перевода = 0, покрытие en/ru/uk/tr ≥ 95 %. Работает без БД.
3. Перевод делается **в каждом батче b–e** — иначе замок красный. Батч-скрипт проверяет, что цены, проценты и числа совпадают с оригиналом (урок I18N-11), и что ни одна запись не равна оригиналу.
4. Инкремент g — сводный прогон по всей волне и по 17 существующим китам Золингена.

---

## §5. Сидинг, ops, производительность

1. **Время.** `create_business` ≈ 1 мин на тенанта (`seed_demo_tenants.py:33-34`). 79 новых последовательно — около 80–90 мин, пересоздание всех 96 — около 110 мин.
2. **`--jobs N`.** Каждый кит — отдельный подпроцесс `manage.py seed_demo_tenants --kit X` через `ThreadPoolExecutor(N)`. Подпроцесс, а не fork: свои соединения с БД, нет проблем с fork и Django; логи помечены префиксом кита; общая сводка в конце; `_ensure_city_portal` один раз в родителе. Ожидание при N=4: 79 китов за ~20–25 мин. Безопасное N подбирается на пилоте по CPU сервера.
3. **Идемпотентность — как сейчас:** без `--recreate` существующие пропускаются. Новые группы: `--group solingen-dcc`, `--group sg:<раздел>`. Пример: `seed_demo_tenants --group sg:tiere --recreate --jobs 3`.
4. **Цена деплоя (главный ops-риск).** `migrate_schemas` в `deploy.sh:68` идёт по всем схемам последовательно. На пилоте замерить холостой проход одной схемы; если он ≥ 2 с, около +3–5 мин на каждый деплой. Митигация — отдельное решение владельца (Р-4): `migrate_schemas --executor=multiprocessing` (поддержку django-tenants проверить на версии из `uv.lock`) или поднимать демо по необходимости.
5. **Шум Celery.** Сигналы ставят примерно 10 задач на кит; `reconcile_schema` делает ту же работу синхронно. Опция — контекст `aggregator.tasks.seeding()`, который гасит `_on_commit_sync` (`tasks.py:1163-1166`) на время сидинга. Не обязательно, задачи идемпотентны.
6. **Диск.** Замерить `pg_total_relation_size` по схемам пилота и умножить на 80; ожидаемо мало (пустые таблицы).
7. **Свежесть демо.** Акции с `ends="week"` продлеваются сами (`promotions/tasks.py:142-159`); события протухают. Генератор ставит события на +3…+60 дней. Опция i: команда `seed_demo_tenants --refresh-events`, которая сдвигает даты событий у `is_demo` и пересинхронизирует их.
8. **Кэш портала.** После сидинга листинги видны после TTL кэша страниц T-8.19. В инкременте h проверить ключ и TTL и при необходимости описать сброс.

---

## §6. Замки и тесты

**Новые, без сидинга:**
- `apps/tenants/tests/test_city_specs.py` — параметризация по всем `Biz`:
  1. `validate(biz) == []`. Проверяется: тип ∈ `BUSINESS_TYPES`; категория ∈ справочника и раздел категории = `SECTION` файла; район ∈ реестра; PLZ адреса ∈ `district.plz` (через `districts.suggest`); координаты в bbox и в прямоугольнике района; цены > 0 и `was > price` (UWG); телефон по формату и уникален; уникальны `key`/`subdomain`/`label` (и среди старых `KITS`); hostname валиден; признаки ⊆ `TAGS_BY_SECTION`; `profile=A` — без полок и с 4–6 акциями; `profile=K` — ≥ 3 позиции с фото и ценой; пресет часов известен; у еды заданы аллергены (LMIV) и `unit`/`content` у фасованного (PAngV).
  2. Улица ∈ `STREETS` — список вымышленных улиц, проверенный однажды.
- `test_city_photos.py` (логика `test_outlet_photos.py:100-131`, обобщённая):
  - ключ даёт собственный файл (stem == slug) или `None`;
  - нет файла вида `{slug}-<n>`;
  - плейсхолдер ≠ ✨/🍽️;
  - нет `ol-`/`markt-`;
  - **ни один файл не используется двумя бизнесами Золингена** (включая 17 существующих).
- `test_city_coverage.py` (расширяет `test_solingen_coverage.py:44-60`):
  - в каждом разделе ≥ 6 бизнесов Золингена;
  - каждая из 76 категорий есть в `predicted_categories()` хотя бы одного кита (предсказатель повторяет правила `_city_fields`);
  - каждый район ≥ 12 %.
- `test_city_i18n.py` (§4).
- `test_city_builder.py`:
  - текст часов совпадает со структурой;
  - меню включает все наполненные модули;
  - `ends` → `recurrence`/`no_end`;
  - SKU не «SG_-…»;
  - `subdomain` начинается с `sg-`.
- `test_seed_groups.py`: группы `solingen-dcc` и `sg:<раздел>`; `--jobs` (mock подпроцесса, ошибка одного кита не останавливает остальные).

**Новые, с БД (только образцы):**
- `test_city_sample_seed.py`: 3 представителя — K-магазин, K-услуги с событиями, A. `apply_kit` + `reconcile_schema` → фактические `AggregatorListing.city_category` совпадают с `predicted_categories()`. Это держит предсказатель честным; плюс `city_tags` у акции доходят до листинга.
- `_create_spec_promo`: `city_category`/`city_tags` из спеки нормализуются и сохраняются.

**Изменения существующих тестов:**
- `test_demo_lists.py:40` — параметризация `sorted(k for k, kit in KITS.items() if not kit.origin) + CITY_SAMPLE`. Полный прогон — маркер `@pytest.mark.demo_full`, вручную перед мержем волны (в CI не входит).
- Статические замки по всем китам (`test_demo_menus.py`, `test_demo_photo_report.py:100`, `test_inheritance_matrix.py:148`) оставить на полном наборе: около 80 × 8 дешёвых проверок, как бесплатные инварианты.

**Оценка CI:** статика +5–15 с, образцы +10–20 с. Без выборки `test_demo_lists` добавил бы ~2–4 мин.

---

## §7. Инкременты

| # | Содержание | Объём | Гейт |
|---|---|---|---|
| **a** | `demo_city/` (spec, builder, validate, photos, presets `HOURS`/`USP`/`STREETS`) + `DemoKit.origin` + `city_category`/`city_tags` в `_create_spec_promo` + группы и `--jobs` + `_ensure_city_portal` для всех городских + выборка в `test_demo_lists` + перенос `measure` + все замки §6 (сначала красные) + **2 пилота**: `sg_trattoria_lumetto` (K, товары) и `sg_wuschelkopf` (K, услуги, плейсхолдер) с переводами. Пилот на сервере: замер времени и диска. | L (1 сессия) | CI + замер |
| **b** | Lebensmittel, Essen, Mode (18) + переводы | M | CI |
| **c** | Elektronik, Haus, Beauty, Gesundheit (20; фото в основном ⚠, на плейсхолдерах) + переводы | M | CI |
| **d** | Freizeit, Kinder, Auto (16) + переводы | M | CI |
| **e** | Handwerk, Dienstleistungen, Reisen, Tiere, Kunst (25; можно e1/e2) + переводы | M–L | CI |
| **f** | Фото-добор: `sg-*`, контактные листы, просмотр, `SOURCES.md`, перевязка ключей, `_EMOJI` += темы; опционально кадры для T-8.22 | L (отдельная сессия) | CI + просмотр глазами |
| **g** | Сводный прогон переводов (вся волна + 17 старых), `PROPER_NAMES`, отчёт `demo_i18n_gap` | S–M | CI |
| **h** | Проверка названий на реальные фирмы; стенд Playwright портала (главная, 15 разделов, поиск, «рядом», 390/1440, de/ru); `docs/build-log.md`, `task-catalog.md` (семейство DCC), CLAUDE.md §3; ops-инструкция | M | стенд |
| i (опц.) | Р-3: категория номера; `--refresh-events`; гашение сигналов при сидинге | S | CI |

Миграций нет: все поля существуют. Переводы и фото добавляются в репозиторий в каждом батче.

---

## §8. Риски

- **Производительность портала.** ~96 бизнесов дают около 900–1100 листингов. Для Postgres это мало; `per_business`/`BLOCK_LIMIT` (`portal_home_blocks.py:27-28`, `:82`) не дают одному бизнесу занять блок; ротация «Lokale Unternehmen» по дням. pg_trgm-поиск (T-8.20) на таком объёме не заметен. Замер выполнить на стенде h.
- **Поиск.** Много похожих позиций (5 пицц у двух ресторанов). Ранжирование не меняем; проверить на стенде, что `?q=pizza` даёт оба бизнеса.
- **Кэш и featured.** Демо не featured, полоса «Anzeigen» остаётся пустой (`FEATURED_LIMIT=3`). Кэш — §5.8.
- **Деплой.** +80 схем на каждый `migrate_schemas` (§5.4) — главный долгосрочный риск. Решение Р-4.
- **Запуск портала.** При `show_demo=False` (T-8.15) все 96 демо исчезнут разом. Владельцу нужно ожидать на старте почти пустой портал.
- **Юридическое:**
  - телефоны: диапазон должен быть заведомо не принадлежащим реальным абонентам (Р-5; проверить список BNetzA с номерами для фильма и ТВ — есть ли там 0212; иначе номер без «Anrufen» или согласованный диапазон);
  - адреса: только вымышленные улицы;
  - названия: без «фамилия + ремесло», ручная проверка;
  - отзывы и Google-рейтинг у городских демо **не сеем** — фейковые отзывы рядом с настоящими на портале (UWG §5b);
  - тексты физиотерапии, массажа и реформхауса — без лечебных обещаний (HWG §3, HCVO);
  - Grundpreis у фасованных товаров (PAngV);
  - аллергены у еды (LMIV).
- **Фото.** Мало честных кадров в CC0 по технике и животным, большая доля плейсхолдеров в c/e до f. Замок «плейсхолдер тематический» не даст появиться ✨.
- **Цикл импорта** `demo_kits` ↔ `demo_city` — держит замок импорта (§1.2).
- **CI.** Выборка в `test_demo_lists` убирает полную проверку пустых списков по 79 китам → полный прогон `demo_full` перед мержем (h).

---

## §9. Что НЕ делаем

- AI-изображения, копии чужих кадров (`ol-*`, `markt-*`, md5-дубли), реальные лица.
- Аптеки (Apothekenpflicht, HWG/AMG), реальные бренды и фирмы, отзывы и рейтинги у городских демо.
- Листинги без тенанта (`AggregatorListing` без сайта): ссылки вели бы в 404, а демо должно быть живым сайтом.
- Новые модели и миграции. Р-3 — без миграции.
- Перевод 17 существующих китов на новый формат (возможно позже), изменение ранжирования портала, другие города, платные featured-демо.
- Новые разделы и категории справочника (замок «16 типов» и справочник не трогаем).

---

## Решения для владельца
- **Р-1.** Профиль по умолчанию — K (каталог/услуги идут в город), A — около 15 %. Нужно подтвердить: постановка «лёгкий + 3–8 товаров» технически противоречит `tasks.py:956`.
- **Р-2.** Число: 79 новых, по 6–9 на раздел (всего 96) — или ровно 5 новых на раздел (75)?
- **Р-3.** Категория номера из `tenant.city_category` (честная `ferienwohnungen`) — маленькая правка `tasks.py:87-88`.
- **Р-4.** Как жить с +80 схемами в деплое: мультипроцессный `migrate_schemas` или держать демо только на dev.
- **Р-5.** Диапазон телефонов и WhatsApp для демо.

## Ключевые файлы
- apps/core/city_categories.py
- apps/core/districts.py
- apps/tenants/demo_kits.py
- apps/tenants/demo_images.py
- apps/tenants/demo_i18n.py
- apps/tenants/management/commands/seed_demo_tenants.py
- apps/aggregator/tasks.py
- apps/aggregator/portal_home_blocks.py
- apps/tenants/tests/test_demo_lists.py
- apps/tenants/tests/test_solingen_coverage.py
- apps/tenants/tests/test_outlet_photos.py
- scripts/demo_i18n_gap.py
- scripts/fetch_cc0_photos.py
- scripts/deploy.sh
- docs/t8-22-solingen-demo-coverage-plan-2026-10-10.md

---

## §10. Решения по умолчанию (2026-10-15; владелец: «составь план, потом начни разработку автоматически»)

- **Р-1** — профиль K по умолчанию, A ≈ 15 % (как в плане). Постановка «лёгкий + товары» снята: товары идут в город только у K.
- **Р-2** — 79 новых (по 6–9 на раздел, всего 96).
- **Р-3** — да: категория номера из `tenant.city_category`, если она из раздела «Reisen & Übernachten» (без миграции).
- **Р-4** — демо-киты живут в репозитории, сидятся по группам; цена деплоя замеряется на пилоте и выносится владельцу отдельной строкой в ops (не блокирует).
- **Р-5** — тот же вымышленный формат, что у существующих китов Золингена (`+49 212 5550xxx` сквозной нумерацией, без пересечений); замена диапазона — одна константа в `builder.py`, если владелец даст другой.
- Порядок исполнения: после T-8.7 (код уже идёт) — инкременты a → b → … → h этого плана.
