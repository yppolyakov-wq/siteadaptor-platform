# План реализации T-8.8 «Машиночитаемость каталога города»

> Документ можно сохранить как `docs/t8-8-machine-readable-plan-2026-10-15.md`. Миграций нет. Будет один ops-шаг: пересинк листингов (§3, инкремент a).
> Источники: `t8-roadmap-2026-10-10.md:43`, `tz-siteadaptor-2-0-phase0-2026-10-10.md:35,63`, `t8-city-offers-portal-2026-10-09.md §3` (строки 78–87, 119), `t8-ai-layer-2026-10-09.md:17,39,124-126`.
> Тезис: каталог города — слой для людей и для агентов (данные · действия без оплаты · доверие). Все данные берутся только из БД через `AggregatorListing.objects.public()`.

---

## 0. Пять находок разведки, которые меняют объём

1. **Цена mystery-акции уже утекает на портал.** Это действующий дефект, и его надо закрыть до фида.
   - `AggregatorListing` не знает `discount_style`.
   - `tasks._snapshot` (`apps/aggregator/tasks.py:22-50`) копирует `promo.new_price`, `old_price` и `discount_percent` без проверки mystery.
   - Цену показывают `_cards.html:60-75`, `offer.html:43-46` и JSON-LD на странице предложения (`views.py:770-780`).
   - Прецедент SF-1.4 (`core/seo.py:155-157`) закрыл утечку только на витрине тенанта.
   - Фид размножил бы утечку на всех агентов. Отсюда инкремент **a**.
2. **У страницы предложения T-8.24 canonical указывает на страницу бизнеса** (`views.py:793`, решение «Стратегия А»). Если положить в sitemap URL, у которого canonical указывает на другой адрес, сигналы противоречат друг другу: Search Console пометит его «Alternate page with proper canonical». Предложение в sitemap портала поэтому требует решения владельца (Р-1).
3. **Scope `"portal-feed"` уже занят.** Это лимит частоты для некэшируемых рендеров главной портала: `FEED_RATE_LIMIT = 120`, `portal_views.py:30,131`. Для машинного фида нужен свой scope, иначе агент съест лимит людей, и наоборот.
4. **`cache_public_page` теряет заголовки.** `_pack` (`core/pagecache.py:119-123`) хранит только тело, Content-Type и Vary. ETag, Last-Modified и Cache-Control на кэш-хите пропадут, поэтому условный GET нужно навешивать снаружи кэша. `ConditionalGetMiddleware` в `MIDDLEWARE` нет (`config/settings/base.py:141+`).
5. **В разметке портала нет ни Impressum, ни Datenschutz** (`templates/aggregator/portal_base.html` — 0 совпадений). Ссылки в llms.txt и фиде строим на платформенные страницы основного домена (`urls_public.py:104-105`). Отсутствие Impressum на самом портале — правовой пробел по DDG §5. Записать в roadmap §Отложено (или закрыть строкой подвала в инкременте e).

---

## 1. Текущее состояние

### 1.1 JSON-LD на портале

| Поверхность | Есть | Нет |
|---|---|---|
| Главная портала / фасет / район (`portal_views.py:368`, `:501`) | `CollectionPage` + вложенный `ItemList` (name + `detail_url`) | — (для списков достаточно) |
| `/entdecken/<city>/` (`views.py:616`) | `ItemList` | — |
| Страница предложения `/angebot/<pk>/` (`views.py:760-794`) | Всегда `@type: Product`, `url = detail_url`, description, image, `Offer` с price/currency/`priceValidUntil` и `seller` только с `name` | Тип по виду: у Event нет `startDate`/`location`, у stay/service/business — свой тип. Нет `availability`, нет адреса/гео/часов у seller, нет `validFrom`. Цена mystery утекает. `priceValidUntil` считается через `.date()` от UTC: около полуночи сдвигается на день |
| Страница бизнеса `/unternehmen/<slug>/` (`reviews_views.py:44`) | `LocalBusiness` через `core.seo.localbusiness_ld` (адрес, телефон, гео, часы, рейтинг) | — |

### 1.2 Sitemap и robots
- `portal_sitemap_xml` (`portal_views.py:510-530`) отдаёт корень, страницы свободной оси `/<facet>/` и районы `/stadtteil/<slug>/`. Нет `lastmod`, нет страниц бизнеса `/unternehmen/<slug>/` (они self-canonical), нет страниц предложений.
- `portal_robots_txt` (`:533-536`) отдаёт `Allow: /` и Sitemap. Технические GET-пути не закрыты: `/klick/<pk>/` (`featured_click` без `require_POST` — бот накручивает клики), `/konto/`, `/melden/`, `/tg/`, `/sprache/`.
- На основном домене (`views.py:637-677`; `urls_public.py:94-96`) sitemap отдаёт `/`, `/branchen/*`, `/entdecken/`, города и связки «город/тип».

### 1.3 llms.txt
- У портала и у основного домена его нет.
- У тенанта есть: `promotions/public_views.py:2980-3015` (имя, описание, город, разделы по модулям, ошибки гасятся). Этот паттерн переиспользуем.

### 1.4 Открытый фид
- Нет. Есть только Google Merchant RSS тенанта (`public_views.py:3018`) — это другая задача.
- Атрибуция каналов нормализует любой `?ch=` (`promotions/channels.py:19-22`: `[a-z0-9_-]`, до 30 символов). Значит, канал `feed` допустим без реестра: строка «feed» появится в воронке акции сама.

---

## 2. Решения (рекомендация отмечена ✅)

### Р-1. Страницы предложений в sitemap
- **(A) ✅ Сохраняем Стратегию А** (canonical на бизнес, решение владельца в T-8.24): страницы предложений в sitemap портала не кладём.
  - Их и так покрывают sitemap витрин тенантов: `detail_url` — URL витрины.
  - Агентам они достаются через фид и llms.txt.
  - Замок: «в sitemap нет URL, у которого canonical указывает на другой адрес».
- **(B)** Self-canonical для страниц предложений (отказ от Стратегии А) и `/angebot/<pk>/` в sitemap с `lastmod`. Тогда портал конкурирует в выдаче с сайтом бизнеса — это противоречит тезису «трафик в магазин». Только решением владельца.
- Независимо от Р-1 в sitemap добавляем страницы бизнеса `/unternehmen/<slug>/` (self-canonical, LocalBusiness) и `lastmod`.

### Р-2. JSON-LD на странице предложения
Нужен тип по виду, `availability`, `seller` = полный `LocalBusiness`. В списках остаётся `ItemList` ссылками: полный Offer есть только на странице предложения, иначе страница разрастается.

| `listing_kind` | `@type` | Offer / доп. поля |
|---|---|---|
| promotion | `Product` | `Offer`: price, `validFrom` = starts_at, `priceValidUntil` = localdate(ends_at), availability |
| product | `Product` | `Offer` + availability из склада |
| menu | `Product` | `Offer` + `priceSpecification` `UnitPriceSpecification` (`unitText: "Person"` при `price_per_person`), `eligibleQuantity.minValue = min_persons` |
| stay | `HotelRoom` + `containedInPlace` = seller (LodgingBusiness) | `Offer` + `UnitPriceSpecification` `unitCode: "DAY"` («ab … pro Nacht») |
| service | `Service` (`provider` = seller) | `Offer` при наличии цены |
| event | `Event` | startDate/endDate, `eventStatus: EventScheduled`, `eventAttendanceMode: Offline`, `location` = `Place` (business_name + `PostalAddress` addressLocality/район), `organizer` = seller, `Offer` |
| business | `LocalBusiness` (`localbusiness_data(tenant)`) | без Offer |

- **availability:**
  - `sold_out` → `https://schema.org/SoldOut`;
  - `on_request` → `https://schema.org/MadeToOrder` (✅ точнее, чем PreOrder: PreOrder значит «ещё не вышло»);
  - `""` → `InStock` у product/promotion/menu/event; у stay/service/business — не указываем.
- **mystery:** Offer без цены. После инкремента a `new_price` у mystery равен `None`, поэтому правило выполняется автоматически, и ветку держит отдельный замок.
- **featured:** в JSON-LD ничего особого. `sponsored` — не свойство schema.org, разметка остаётся честной: тот же Offer.
- **StrikethroughPrice** (old_price): ✅ в JSON-LD v1 **не** отдаём. У листинга нет «низшей цены за 30 дней» (§11 PAngV), а машинный «зачёркнутый» ценник — тот же анонс снижения. В фиде `old_price` идёт как сырые данные бизнеса.
- **seller:** `Tenant.objects.filter(schema_name=...).first()` — одна строка в public-схеме, +1 запрос только на странице предложения. Берём только публичные данные бизнеса: адрес, `public_phone`, гео, часы, лого. Нет тенанта (сирота) — фолбэк `{"@type":"LocalBusiness","name": business_name, "address":{"addressLocality": city}}`.
- `url` в JSON-LD остаётся `detail_url` (согласовано с canonical при Р-1 A). `aggregateRating` у seller в v1 не добавляем.

### Р-3. llms.txt портала
✅ v1: только `/llms.txt`, `/llms-full.txt` не делаем (полный список отдаёт фид).

Содержимое:
- заголовок портала + tagline/intro;
- город, районы с предложениями (ссылки `/stadtteil/<slug>/`);
- **только непустые** разделы справочника (`city_categories.SECTIONS`, ссылки `/?kat=<section>`). Пустой раздел — мёртвая ссылка;
- блок «Daten für Assistenten»:
  - фид JSON/Atom с перечнем фильтров `?kind ?kat ?merkmal ?stadtteil ?limit`;
  - sitemap;
  - формат страницы предложения;
  - заметка «keine Online-Zahlung; Reservieren/Coupon/Anfrage beim Anbieter»;
  - «Anzeigen sind als sponsored markiert»;
  - «Preise ohne Gewähr»;
- ссылки на Impressum/Datenschutz платформы.

Персональных данных нет. Кэш через `@cache_public_page`. Язык — по запросу: тексты через gettext с немецкими msgid, около 25 msgid × 5 каталогов.

Основной домен: ✅ маленький `/llms.txt` той же функцией без портала — описание платформы, ссылка на `/entdecken/` и фид, список активных порталов (`AggregatorPortal.objects.filter(is_active=True)`, ≤12).

### Р-4. Открытый фид
✅ **JSON Feed 1.1 (`/feed.json`) и Atom (`/feed.xml`) из одного набора элементов.** Atom собираем штатным `django.utils.feedgenerator.Atom1Feed`: экранирование и даты он делает сам.

- **Состав:** `listings_for(...)` → `objects.public()`. По умолчанию — `OFFER_KINDS` (promotion/stay/event/menu).
  - `?kind=` — product/service/business и прочие, проверка по `dict(KINDS)`, мусор → 400 или игнор;
  - `?kat=` / `?merkmal=` — `category_facets.selected`;
  - `?stadtteil=` — `districts.normalize(city, value)`.
- **Порядок и лимит:** `-created_at` (featured не поднимаем — UWG §5a, как в `_render_home`). `?limit=` от 1 до 100, по умолчанию 100. `next_url` — курсором `apps.core.pagination.paginate(order_field="created_at")`: дёшево, а курсорные URL идут мимо кэша под лимит частоты.
- **Поля элемента JSON Feed:**
  - `id`: tag-URI `tag:<host>,2026:listing:<pk>` (pk стабилен, синк обновляет ту же строку благодаря unique-constraint);
  - `url`: страница предложения на этом хосте (`reverse("aggregator-offer")`);
  - `external_url`: `listing.with_channel("feed")` — сайт бизнеса с `?ch=feed`. ✅ Атрибуция живёт здесь, потому что `offer_page` канал не ловит (публичный хост, сессии нет);
  - `title`, `summary` (teaser), `image` (absolute), `date_published` = created_at, `date_modified` = updated_at;
  - `_siteadaptor`: `{kind, price, old_price, discount_percent, currency, price_unit: person|night|None, valid_from, valid_until, availability, is_new, category, category_label, tags, district, district_name, city, lat, lng, business:{name, page: <portal /unternehmen/slug/>, website: <origin detail_url>}, sponsored: is_featured_now, demo?}`.
  - Цена, old_price и процент отдаются только если `new_price is not None` (mystery → все `None`).
- **Верх фида:** `version: "https://jsonfeed.org/version/1.1"`, `title`, `home_page_url`, `feed_url`, `language`, `_siteadaptor: {city, license, terms_url, impressum, datenschutz, preview}`.
  - Строка лицензии — **на владельце** (черновик: «Daten der Anbieter; Nutzung für Verzeichnisse und Assistenten mit Quellenangabe erlaubt; Preise ohne Gewähr»).
- **Atom:** `id`, `updated` (= max updated_at выборки), `published`, `link` alternate (страница предложения) и related (external_url), `summary`, `<category term="<city_category>">`, `<category term="sponsored" label="Anzeige">` у featured. Цен в Atom нет (стандартных полей нет): цена идёт строкой в summary, если видима.
- **HTTP:**
  - Content-Type: `application/feed+json; charset=utf-8` и `application/atom+xml; charset=utf-8`;
  - без query: `@cache_public_page` (TTL 120 с);
  - с query: `ratelimit.hit("open-feed", ip, limit=OPEN_FEED_RATE_LIMIT=60, window=60)` → 429. **Новый scope**, а не `portal-feed`;
  - снаружи кэша: `decorator_from_middleware(ConditionalGetMiddleware)` — ETag по хешу тела и 304 по If-None-Match, работает и на кэш-хите. Last-Modified не ставим: max(updated_at) не меняется при скрытии или истечении листинга, был бы ложный 304;
  - `patch_cache_control(public=True, max_age=PUBLIC_PAGE_CACHE_TTL)`.
- **Демо:**
  - настоящий портал → `include_demo=portal.show_demo`, то есть демо нет вовсе;
  - превью-портал (`show_demo=True`) → элементы с `demo: true` и `_siteadaptor.preview: true` сверху;
  - основной домен → всегда `include_demo=False`. ✅ Агент не должен принять демо за реальность, хотя `/entdecken/` демо показывает.
- **Discoverability:** `<link rel="alternate" type="application/feed+json">` и `type="application/atom+xml"` в `<head>` `portal_base.html` (строки 8-14) и `aggregator/_base.html`.

### Р-5. Основной домен
✅ Да: `/entdecken/feed.json` и `/entdecken/feed.xml` с `?city=`. Одна функция, две точки входа. Без `?city=` — общий пул платформы (лимит тот же). Роуты ставятся выше `entdecken/<str:city>/` (`urls_public.py:81`).

### Р-6. Robots
✅ Портал и основной домен: `Allow: /` остаётся, AI-краулеры разрешены (портал открыт по замыслу), плюс `Disallow:` на технические GET-пути:
- портал: `/klick/`, `/melden/`, `/konto/`, `/tg/`, `/sprache/`;
- основной домен: `/entdecken/klick/`, `/entdecken/melden/`, `/entdecken/merkliste/`.

Строка `Sitemap:` остаётся.

---

## 3. Инкременты (один батч, ветка `claude/t8-8-machine-readable`)

### a) Подготовка и фикс утечки
1. `apps/aggregator/tasks.py:22-50` `_snapshot`: при `promo.discount_style == "mystery"` ставить `new_price`, `old_price` и `discount_percent` в `None`. Сравнение со строкой — как в `seo.py:157`.
2. `apps/aggregator/models.py:228-237`: новый метод `def with_channel(self, ch: str) -> str`. `portal_url` становится `return self.with_channel("portal")`, поведение байт-в-байт.
3. Новый модуль `apps/aggregator/platform_links.py`: `def platform_url(name: str) -> str`. Это `reverse(name, urlconf="config.urls_public")` поверх `f"{_scheme()}://{settings.TENANT_DOMAIN_BASE}"` — для Impressum/Datenschutz с хоста портала.
4. Robots (Р-6): `portal_views.py:533`, `views.py:674`.
5. **Ops после деплоя:** `python manage.py sync_aggregator` (пересинк всех схем, `management/commands/sync_aggregator.py`) — затирает уже лежащие mystery-цены.

### b) JSON-LD страницы предложения
1. `apps/core/seo.py:51-138`: выделить `def localbusiness_data(tenant, *, url, aggregate_rating=None, price_range="", image="", schema_type="") -> dict`. `localbusiness_ld` превращается в `_dumps(localbusiness_data(...))` — паритет, существующие тесты должны остаться зелёными.
2. Новый модуль `apps/aggregator/structured.py`:
   ```python
   AVAILABILITY = {"sold_out": "https://schema.org/SoldOut", "on_request": "https://schema.org/MadeToOrder"}
   def availability_iri(listing) -> str | None
   def price_visible(listing) -> bool          # new_price is not None
   def seller_data(listing, tenant, *, request) -> dict
   def offer_data(listing, *, url: str) -> dict | None
   def listing_ld(listing, *, request, tenant=None) -> dict   # диспатч по listing_kind (таблица Р-2)
   ```
   Даты — `timezone.localdate(ends_at)`.
3. `apps/aggregator/views.py:760-781`: заменить сборку `ld` на `listing_ld(listing, request=request, tenant=_tenant_for(listing))`. Это +1 запрос `Tenant.objects.filter(schema_name=...).only(...)`. Страница предложения кэшируется, поэтому цена запроса мала.

### c) Sitemap
`portal_views.py:510-530` разбить на `_sitemap_urls(request, portal) -> list[tuple[str, datetime|None]]` и рендер:
- корень с `lastmod` = `pool.aggregate(Max("updated_at"))` (1 запрос);
- фасеты и районы — как сейчас;
- **+** `/unternehmen/<slug>/` по `pool.values_list("tenant_slug").distinct()` (1 запрос) с lastmod = Max per slug (`values("tenant_slug").annotate(Max)`);
- при Р-1 B — `/angebot/<pk>/` по `pool.values_list("pk","updated_at")`.
- Query-URL (`?kat=`) не включаем.
- Кап `SITEMAP_MAX_URLS = 45_000` + `logger.warning` при обрезке. Sitemap-index — когда упрёмся (roadmap §Отложено).
- `@cache_public_page` на sitemap и robots (сейчас нет).

### d) Открытый фид
1. Новый модуль `apps/aggregator/open_feed.py`:
   ```python
   OPEN_FEED_RATE_LIMIT = 60
   MAX_ITEMS = 100
   @dataclass(frozen=True)
   class FeedParams: kinds: tuple[str, ...]; kat: str; tag: str; district: str; limit: int; cursor: str | None
   def parse_params(request, *, city: str) -> FeedParams            # мусор → дефолты, не 500
   def feed_pool(*, city, business_type, include_demo, params) -> QuerySet  # listings_for(...).defer("search_vector","search_text")
   def feed_item(listing, *, request, preview: bool) -> dict
   def json_feed(request, *, title, home_url, city, items, next_url, preview) -> dict
   def atom_feed(request, *, title, home_url, items) -> str          # feedgenerator.Atom1Feed
   def machine_resource(view)  # ConditionalGetMiddleware + Cache-Control, снаружи cache_public_page
   ```
2. Вьюхи: `portal_views.portal_feed_json`, `portal_feed_atom` (портал → `city=portal.city`, `business_type=portal.business_type`, `include_demo=portal.show_demo`); `views.discover_feed_json`, `discover_feed_atom` (`?city=`, `include_demo=False`). Порядок декораторов: `@machine_resource` → `@cache_public_page` → view. Лимит частоты внутри view при `request.GET`.
3. Роуты:
   - `config/urls_portal.py` после `robots.txt` (строка 28): `feed.json` (`portal-feed-json`), `feed.xml` (`portal-feed-atom`);
   - `config/urls_public.py` выше строки 81: `entdecken/feed.json`, `entdecken/feed.xml`.
4. `<link rel="alternate">` в `portal_base.html` и `aggregator/_base.html`.
5. **Бюджет запросов:** 1 запрос выборки (подзапрос `withheld_schemas` встроен, `visibility.py:29-40`) + 1 на курсор. Без N+1: имя бизнеса, slug и город денормализованы в листинге, Tenant не читаем. Подписи категорий и районов — из реестров в памяти.

### e) llms.txt
`portal_views.portal_llms_txt(request)` и `views.llms_txt(request)` — общий построитель `apps/aggregator/llms.py::build(request, portal=None) -> str`:
- секции через `pool.exclude(city_category="").values_list("city_category", flat=True).distinct()` → маппинг на разделы (1 запрос);
- районы — `_district_choices` (1 запрос);
- около 3 запросов на промах кэша.

Роуты `llms.txt` на обоих urlconf (портал — рядом с `sitemap.xml`). Опционально — строка Impressum/Datenschutz в подвале `portal_base.html` (находка 5).

### f) Доки
`build-log.md`, `task-catalog.md` (T-8.8 ✅), `CLAUDE.md` §3, roadmap §Отложено (sitemap-index, `/llms-full.txt`, StrikethroughPrice после §11-данных, Impressum портала — если не закрыт в e).

**Гейт батча:** `ruff check .`, `ruff format --check .`, `pytest apps/aggregator apps/core/tests/test_seo_meta.py apps/promotions/tests/test_seo.py --reuse-db`, `scripts/i18n_quickcheck.py` и `i18n_gap` (новые msgid), `test_template_comments.py` (правка head-шаблонов).

---

## 4. Тесты — `apps/aggregator/tests/test_machine_readable.py`
Паттерн `test_portal_seo.py`: RequestFactory, `req.portal`, `override_settings(ROOT_URLCONF="config.urls_portal")`.

**JSON-LD** (парсить `<script type="application/ld+json">` → `json.loads`):
- тип по каждому из 7 видов (параметризованно);
- у Event есть `startDate` и `location.address.addressLocality`;
- stay → `UnitPriceSpecification` `unitCode: "DAY"`;
- маппинг availability: sold_out / on_request / "" × вид;
- `priceValidUntil` = localdate (ends_at 23:30 UTC → следующий день по Berlin);
- seller с адресом и телефоном, при этом **e-mail владельца и `contact_email` не в теле** (грепом по строке);
- сирота без Tenant → фолбэк без 500;
- mystery-листинг (после синка) → нет `offers`, нет цены в HTML;
- featured → JSON-LD идентичен не-featured (кроме данных).

**Синк mystery:** `sync_listing` у mystery-акции даёт `new_price/old_price/discount_percent is None` (замок прецедента SF-1.4).

**Sitemap:**
- содержит `/unternehmen/<slug>/` и районы с `<lastmod>`;
- не содержит скрытых (`hidden_at`), истёкших (`ends_at` в прошлом), демо (на портале с `show_demo=False`), бизнесов из `withheld_schemas`, query-URL;
- при Р-1 A — нет `/angebot/`; замок «каждый URL sitemap — self-canonical» (рендер и сверка `<link rel=canonical>` для выборки).

**Robots:** Disallow `/klick/` и прочих технических путей; `Sitemap:` есть; AI-краулеры не заблокированы.

**llms.txt:**
- 200, `text/plain; charset=utf-8`;
- содержит заголовок портала, только непустые разделы (пустой раздел отсутствует), районы, ссылки на фид/sitemap/Impressum/Datenschutz;
- все относительные ссылки резолвятся через `resolve()` в urlconf портала;
- нет e-mail и телефонов.

**Фид:**
- только `public()`: hidden, expired, withheld, демо на настоящем портале — не попадают;
- по умолчанию только `OFFER_KINDS`, `?kind=product` → товары;
- фильтры `?kat=`, `?merkmal=`, `?stadtteil=`; мусорные `?kind`/`?limit=abc`/`?limit=10000` → дефолт или кламп, не 500;
- лимит ≤ 100, `next_url` ведёт на следующую страницу без пересечений;
- порядок `-created_at`, featured не поднимается, но у него `sponsored: true` и Atom-категория `sponsored`;
- mystery без цены;
- `url` = `/angebot/<pk>/` текущего хоста, `external_url` содержит `ch=feed`, а при уже имеющемся `?ch=` в `detail_url` — не дублирует;
- валидность JSON Feed: `version`, `title`, `items[*].id`, плюс `content_text` или `summary` (обязательно хотя бы одно по спецификации — отдаём `content_text` = teaser или title);
- Atom: `xml.etree` парсит, у feed и каждого entry есть `id`/`updated`;
- ETag присутствует, повторный запрос с `If-None-Match` → 304, в том числе на кэш-хите (`override_settings(PUBLIC_PAGE_CACHE_TTL=60)` + locmem-кэш, как `test_storefront_cache`);
- без query кэшируется (второй вызов не идёт во вьюху — mock);
- с query срабатывает лимит частоты `open-feed` (429), и он **не** расходует `portal-feed`;
- превью-портал: `demo: true` и `preview: true`;
- `/entdecken/feed.json` никогда не отдаёт демо и фильтрует по `?city=`.

**Паритет:** `localbusiness_ld` после рефакторинга байт-в-байт (существующие тесты). Обновить `test_offer_page.py::test_offer_page_renders_with_cta_canonical_and_jsonld` (там ожидается `Product` — сверить тип по виду).

**Изоляция:** ключи `rl:*` переживают прогоны (грабля из CLAUDE.md) — у каждого теста лимита свой IP.

---

## 5. Риски
- **Ложный 304.** Last-Modified по max(updated_at) не видит скрытия и истечения → используем только ETag по телу.
- **Демо-утечки агентам.** Закрыто тремя точками: `include_demo` на портале, `False` на основном домене, замок.
- **Атрибуция `?ch=feed`.** Попадает в воронку только через переход на сайт бизнеса. Страница предложения портала канал не несёт (v1). Если нужно — отдельно: прокинуть `?ch=` в CTA страницы предложения (влияет на кэш, потому что query идёт мимо него).
- **Scraping конкурентами.** Данные и так публичны; спасают лимит частоты, кэш и строка лицензии. Юридическая формулировка — на владельце.
- **Размер sitemap и фида** при росте товаров (T-8.11): кап и предупреждение, sitemap-index — по факту.
- **i18n.** Новые строки llms.txt и фида — через gettext. Гейты `i18n_gap` и `i18n_untranslated` (f-строки с `_()` запрещены).
- **Пересинк mystery** — ops-шаг. Без него старые листинги держат цену до следующей правки акции.

## 6. Что НЕ делаем
MCP-приложение (T-8.10f), подписка на запрос (T-8.10d), аналитика «агентских» переходов владельцу, Merchant Center / локальное наличие Google (идёт через магазин), индексация товаров тенантов вне каталога города (`hide_in_city`/непригодное к показу не попадает — правило T-8.11), `/llms-full.txt`, sitemap-index, StrikethroughPrice в JSON-LD, отказ от Стратегии А без решения владельца (Р-1 B).

## 7. Вопросы владельцу
1. **Р-1:** оставляем Стратегию А (предложения не в sitemap портала) или переводим страницы предложений на self-canonical?
2. **Формулировка лицензии / условий использования фида.**
3. **Impressum и Datenschutz на самом портале:** закрыть строкой подвала в этом батче (рекомендация) или отдельной задачей?

---

### Ключевые точки изменения (файл:строка)
- `apps/aggregator/tasks.py:22-50` — mystery в `_snapshot`
- `apps/aggregator/models.py:228-237` — `with_channel`
- `apps/core/seo.py:51-138` — `localbusiness_data`
- `apps/aggregator/views.py:760-781` (JSON-LD), `:637-677` (sitemap/robots основного домена)
- `apps/aggregator/portal_views.py:30` (не трогать `portal-feed`), `:510-536` (sitemap/robots)
- `config/urls_portal.py:26-28` (+feed/llms), `config/urls_public.py:79-96` (+feed/llms выше `entdecken/<city>/`)
- `templates/aggregator/portal_base.html:8-14`, `templates/aggregator/_base.html:8-14` — `rel=alternate`
- новые модули: `apps/aggregator/structured.py`, `open_feed.py`, `llms.py`, `platform_links.py`
- новый тест: `apps/aggregator/tests/test_machine_readable.py`; правка `test_offer_page.py`

---

## 8. Решения владельца (2026-10-15)

- **Р-1 → A.** Стратегия А остаётся: canonical страницы предложения указывает на бизнес,
  предложения в sitemap портала не кладём (короткоживущие URL, портал не конкурирует с сайтами
  бизнесов; машинам хватает фида/JSON-LD/llms.txt). Переход на self-canonical — после пилота,
  если понадобится.
- **Лицензия фида** (черновик, показать юристу перед пилотом): «Daten der jeweiligen Anbieter.
  Nutzung in Verzeichnissen, Suchdiensten und Assistenten mit Quellenangabe und Link erlaubt.
  Keine Vervielfältigung des gesamten Datenbestands. Preise und Verfügbarkeit ohne Gewähr.»
- **Impressum/Datenschutz на портале — в этом батче** (инкремент e): строка подвала
  `portal_base.html` со ссылками на платформенные страницы (`platform_links.platform_url`).
