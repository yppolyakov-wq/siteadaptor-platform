# Волна U-A — детальный план подзадач (контракт + единая деталь) — 2026-06-30

> Детализация фазы **U-A** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`.
> Все пути/поля/тесты — **верифицированы разведкой против кода** (воркфлоу recon+design).
> Конвенция: docs до кода. Каждая подзадача — вертикальный срез, гейтится CI отдельной веткой.
> Закрывает **E-1** (деталь услуги A3/A7/A9) как первый отгружаемый инкремент.

## 0. Ключевые уточнения дизайна (важно перед кодом)

1. **Деталь-сущность = `booking.Service`, НЕ `jobs.Job`.** Для A7/A9 просматриваемая
   продаваемая сущность — услуга (Leistung); оба кита сеют Services (`demo_kits.py:3721`),
   `archetypes.PRIMARY_SECTION['booking']='services'`, `purchase_mode('booking')='booking'`.
   `jobs.Job`/Auftrag — индивидуальный Kostenvoranschlag (`/anfrage/`+`/angebot/<token>/`,
   `purchase_mode='request'`) — **транзакция под U-D**, НЕ деталь-сущность U-A. В детали
   услуги A7/A9 «запрос сметы» — **вторичная CTA** (ссылка на `/anfrage/`), не primary buy-box.
2. **E-1 = рефактор, не новая страница.** Единственная публичная страница услуги —
   `storefront-service-slots` (`service_slots.html`), которая уже де-факто «деталь+слот-
   пикер». Переводим её на каркас `detail.html` и регистрируем в `DETAIL_ENTITIES` — второй
   URL не плодим (slots-пикер и есть buy-box услуги, mode=booking-by-slot).
3. **`detail.html` — 6 пустых блоков:** `detail_back`, `detail_gallery`, `detail_aside`,
   `detail_body`, `detail_wide`, `detail_buybar`. `product_detail.html` **standalone** (НЕ
   наследует `detail.html`) — его вписывание = крупнейшая зона регрессии. `stay_detail`/
   `event_detail` уже наследуют; `combo_detail` — обходит каркас.
4. **Опции/варианты/модификаторы/комбо — это buy-box (U-A3), НЕ атрибуты (U-A4).** U-A4
   (атрибуты/характеристики/FAQ) их сознательно исключает.
5. Инлайн-правка/фото услуги уже подключены (`MODEL_EDIT_URLS`/`MODEL_PHOTO_URLS`,
   `site_home.html:1681-1684`) → после перевода на каркас on-canvas-правка заработает без нового кода.

## 1. Подзадачи (сводка)

| ID | Фаза | Заголовок | Размер | Миграция | Зависит |
|---|---|---|:--:|:--:|---|
| **UA1-1** | U-A1 | Деталь услуги на каркасе `detail.html` (**E-1, первый срез**) | M | — | — |
| **UA1-2** | U-A1 | Регистрация `Service` в `DETAIL_ENTITIES` + переключатель превью редактора | S | — | UA1-1 |
| **UA1-3** | U-A1 | Контракт `SellableEntity` (протокол-адаптер) + 5 адаптеров | M | — | UA1-2 |
| **UA2-1** | U-A2 | Единый шаблон детали через контракт; **вписать `product_detail` в каркас** | L | — | UA1-3 |
| **UA3-1** | U-A3 | Pluggable buy-box include по `purchase_mode` (одношаговые: cart/reserve/request) | L | — | UA2-1 |
| **UA3-2** | U-A3 | Двухшаговый buy-box (booking-slot услуга + booking-date номер) | L | — | UA3-1 |
| **UA4-1** | U-A4 | Единый реестр секций детали (KEYS+LABELS вместе; ключи Service+Stay) | L | — | UA2-1 |
| **UA4-2** | U-A4 | Data-driven цикл рендера секций вместо per-template if/elif | L | — | UA4-1 |
| **UA4-3** | U-A4 | **Атрибуты/характеристики + FAQ услуги** (богатая карточка A3/A7/A9) | M | **да** | UA4-2 |
| **UA4-4** | U-A4 | Per-entity JSON-LD эмиттер + верифиц. отзывы обобщены на Service | L | — | UA4-3 |

**Первый отгружаемый инкремент = UA1-1** (закрывает прямое требование «деталь услуги»).
Волна без миграций до **UA4-3** (единственная миграция — атрибуты/FAQ на `Service`).

## 2. Подзадачи (детально)

### UA1-1 — Деталь услуги на каркасе `detail.html` (E-1) · M · без миграции
Перевести `service_slots.html` (сейчас `extends _base.html`) на `extends storefront/detail.html`,
заполнив 6 блоков: `detail_back`→`storefront-termin`; `detail_gallery`→`_media_gallery.html`/
`service.image_url`; `detail_aside`→карточка `#buchen` (h1 `data-edit`, длит./цена, выбор мастера,
депозит); `detail_body`→описание + слот-пикер + форма брони (перенести из текущего body);
`detail_buybar`→`_detail_buybar.html` anchor=`#buchen` module=`booking`. **Вьюху/URL/модель не
трогаем** — тот же `service_slots` view/context.
- **Файлы:** `templates/storefront/service_slots.html`, `templates/storefront/detail.html`.
- **Критерии:** весь прежний контент рендерится без регресса; POST на `storefront-service-book`
  с теми же полями (`start/resource/website/name/email/phone/note/pass_code/extras`); GET-ссылки
  слотов (`?tag/?slot/?resource`) не меняются; `data-edit-model='service'`/`data-photo-edit`
  сохранены; buybar показывает `purchase_label('booking')='Jetzt buchen'`.
- **Тесты:** `apps/booking/tests/test_public.py`, `apps/core/tests/test_inline_edit.py`.

### UA1-2 — Регистрация `Service` в `DETAIL_ENTITIES` + превью редактора · S · без миграции
Добавить в `archetypes.DETAIL_ENTITIES`: `('booking','booking.Service','storefront-service-slots',
_('Service page'), {'is_active':True}, ('-created_at',))`. Добавить `booking_detail` в
`SCOPE_PAGE_KEY` (`site_home.html:1629`) — пока без per-page инспектора (fallthrough к «правь на
канве», как `stays_detail`; per-page инспектор — UA4-1).
- **Файлы:** `apps/core/archetypes.py`, `templates/tenant/site_home.html`, `apps/core/tests/test_preview_pages.py`.
- **Критерии:** `example_detail_pages(tenant)` отдаёт `group='booking_detail'` при активном
  booking + ≥1 активном Service (guard `is_module_active`+`NoReverseMatch`); опция в
  `<select id='home-prev-page'>`; тест-локи обновлены (каждый detail-group `endswith '_detail'`).
- **Тесты:** `apps/core/tests/test_preview_pages.py`, `apps/core/tests/test_archetypes.py`.

### UA1-3 — Контракт `SellableEntity` (адаптер) + 5 адаптеров · M · без миграции
Ввести лёгкий протокол представления в `apps/core` (напр. `sellable.py`): нормализует любую
просматриваемую сущность к общему виду `{kind, pk, name, description, image/gallery,
price_display, purchase_mode, purchase_label, detail_url, buybox_context, attributes, info_sections}`.
Per-kind адаптеры (product/service/stay/event/combo), модели — лениво (`django_apps.get_model`,
как в `archetypes.py`). Адаптеры **делегируют** цены/наличие существующим движкам, модели НЕ сливают.
Это шов, на котором строятся U-A3 и U-A4. Пока без правки шаблонов — чистый Python + юниты.
- **Файлы:** `apps/core/archetypes.py` (+ новый `apps/core/sellable.py`), `apps/core/views.py`.
- **Критерии:** резолвер `sellable_for(kind, obj)` + kind→mode/label **переиспользует**
  `archetypes.purchase_mode/purchase_label` (без дублей таблиц); адаптеры для 5 kinds; combo→`cart`;
  jobs **явно НЕ адаптер** (документирован как U-D); импорт `apps.core` не тянет catalog/stays/
  events/booking на загрузке.
- **Тесты:** `apps/core/tests/test_archetypes.py`, `apps/booking/tests/test_services.py`.

### UA2-1 — Единый шаблон детали через контракт; вписать `product_detail` · L · без миграции
Свести общий «хром» detail-страниц (back-label, галерея, title/price-header, buybar-module) на
чтение из `SellableEntity` там, где тривиально, чтобы product/stay/event/service рендерили общую
оболочку одним путём, сохраняя mode-специфичные тела. **`product_detail.html` вписать в каркас**
(сейчас standalone). Формы/якоря каждой сущности — байт-в-байт, чтобы не регрессить; унифицируем
только оболочку.
- **Файлы:** `templates/storefront/product_detail.html`, `detail.html`, `service_slots.html`.
- **Критерии:** `product_detail.html extends detail.html` с паритетом раскладки (категория/badge/
  h1/summary/цена+grundpreis/LMIV/add-to-cart/отзывы/related); все 4 detail-страницы делят 2-кол.
  grid+sticky aside+buybar; POST/поля/anchor-id (`#kaufen`/`#buchen`)/inline-attr — без изменений.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/booking/tests/test_public.py`,
  `apps/promotions/tests/test_public.py`.
- ⚠️ **Наибольшая зона регрессии** — снапшот-паритет обязателен, мержить по внимательному diff.

### UA3-1 — Pluggable buy-box include (одношаговые режимы) · L · без миграции
Вынести buy-box в data-driven include `storefront/_buybox.html`, диспатч по
`SellableEntity.purchase_mode`: `cart`(`_add_to_cart_form.html`), `reserve`(промо-форма),
`request`(ссылка `/anfrage/`), и одношаговый booking. Detail-шаблоны зовут
`{% include 'storefront/_buybox.html' with entity=... %}` в `detail_aside` вместо инлайна.
Сохранить общий контракт (csrf, honeypot `website`, `name(req)/email/phone/note`, sold_out→waitlist).
Двухшаговые (stay/service) — UA3-2.
- **Файлы:** `_detail_buybar.html`, `_add_to_cart_form.html`, `product_detail.html`, `archetypes.py`.
- **Критерии:** `_buybox.html` рендерит верную per-mode форму/CTA только из `entity.purchase_mode`+
  `purchase_label` (без per-template if/elif по архетипу); product(cart)/promotion(reserve)/
  Service-с-Anfrage-CTA(request вторичн. у A7/A9) — через общий include, POST/поля неизменны;
  sold-out→waitlist где режим поддерживает.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/promotions/tests/test_public.py`.

### UA3-2 — Двухшаговый buy-box (booking-slot услуга + booking-date номер) · L · без миграции
Смоделировать «выбери-потом-купи» для stay (GET quote по датам/гостям/комнатам) и service (GET
выбор слота): `SellableEntity` даёт `select_url`(GET) отдельно от `submit_url`(POST) + признак
готовности; `_buybox.html` рендерит селектор, а POST-форму — только при валидном выборе
(`quote.available`/выбранный слот). Провести stay_detail и service через этот путь, сохранив
rate_options/kurtaxe/extras/deposit (stay) и resource/pass_code/extras/deposit (service).
Анти-оверселл — на сервере.
- **Файлы:** `stay_detail.html`, `service_slots.html`, `apps/stays/public_views.py`,
  `apps/booking/public_views.py`.
- **Критерии:** поля `storefront-unterkunft-book`/`storefront-service-book` неизменны; POST-форма
  только при выборе; сервер ре-валидирует наличие (`book_stay`/`booking.services.book` не трогаем).
- **Тесты:** `apps/stays/tests/test_public.py`, `apps/booking/tests/test_public.py`.

### UA4-1 — Единый реестр секций детали · L · без миграции
Обобщить два ad-hoc реестра (`EVENT_DETAIL_SECTION_KEYS` order+hide, `PRODUCT_DETAIL_SECTION_KEYS`
hide-only) в одну модель `(archetype,section)`→`{orderable,hideable}`, config
`['<module>_detail']={order,hidden}` за одним нормализатором. Совместить KEYS с LABELS (сейчас
LABELS в `core/views.py` `_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS`, отдельно от ключей).
Добавить `SERVICE_DETAIL_SECTION_KEYS` (description/attributes/faq/related) и
`STAY_DETAIL_SECTION_KEYS` (amenities/facts/related). Round-trip через save (`home_builder_view`)
и live-preview (`accept_preview_draft`).
- **Файлы:** `apps/tenants/siteconfig.py`, `apps/core/views.py`, `templates/tenant/site_home.html`.
- **Критерии:** один нормализатор + `*_detail_order(config, module)` на catalog/events/stays/booking;
  `SCOPE_PAGE_KEY` получает `booking_detail`/`stays_detail`; config round-trip'ит через POST И
  live-preview без потерь; **бэк-компат** (существующий event/product-config нормализуется идентично).
- **Тесты:** `apps/core/tests/test_home_builder.py`, `apps/core/tests/test_live_preview.py`.

### UA4-2 — Data-driven цикл рендера секций · L · без миграции
Заменить гигантский if/elif в `_event_thematic.html` и инлайн-guard'ы `product_detail.html` одним
`{% for section in detail_order %}{% include %}` по архетипу, из реестра UA4-1. Service/stay тела —
через тот же цикл. Тела детали становятся конфигурируемыми и консистентными, вид сохраняется.
- **Файлы:** `_event_thematic.html`, `product_detail.html`, `stay_detail.html`, `service_slots.html`.
- **Критерии:** тела product/event/stay/service — один цикл по `detail_order`; скрытые секции
  опущены; порядок соблюдён; каждая секция несёт `data-sf-section` (паритет с event); снапшот
  event-вывода неизменен.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/core/tests/test_home_builder.py`,
  `apps/stays/tests/test_public.py`.

### UA4-3 — Атрибуты/характеристики + FAQ услуги · M · **МИГРАЦИЯ**
Дать `Service` структурные атрибуты + FAQ, чтобы A3/A7/A9 получили «богатую карточку» (что входит/
особенности + FAQ) — закрывает E-1/D1/D2 полностью. Хранить JSON на `Service` (`attributes` list +
`faq` list of `{q,a}`), валидатор по образцу `events/details.py _SCHEMA` (scalar|list|record). Рендер
как унифицированные секции (через цикл UA4-2). Засеять пару атрибутов+FAQ в werkstatt/handwerker демо.
- **Файлы:** `apps/booking/models.py`, `service_slots.html`, `apps/tenants/demo_kits.py`.
- **Критерии:** `Service.attributes`/`faq` (JSONField) + normalize/validate (garbage→ничего, без
  краша); секции attributes/FAQ (hideable/orderable через UA4-1); демо A7/A9 сеют атрибуты+FAQ;
  резолвер code→label — generic (переиспользован, не копипаст). **Миграция booking.Service;
  локально `--create-db`.**
- **Тесты:** `apps/booking/tests/test_services.py`, `apps/booking/tests/test_public.py`.

### UA4-4 — Per-entity JSON-LD + верифиц. отзывы на Service · L · без миграции
Добавить kind-aware JSON-LD эмиттер в `apps/core/seo.py` (`product_ld`/`service_ld` из
нормализованного дикта контракта, не привязанного к Promotion-атрибутам как `offer_ld`) — schema.org
Product/Service/Event/LodgingBusiness + Offer + опц. AggregateRating/Review, через per-page
`structured_data` context-var. Обобщить верифиц.-отзывы на Service: `has_purchased`-диспатч через
per-kind verification-адаптер (Product→OrderItem; Service→Booking-by-email), **fail-closed**.
`ProductReview` и `BusinessReview` держим раздельно (без смены FK в этом срезе → без миграции).
- **Файлы:** `apps/core/seo.py`, `apps/catalog/reviews.py`, `apps/booking/public_views.py`.
- **Критерии:** entity-эмиттер из нормализованного дикта → верный `@type` per kind (`offer_ld`/
  `localbusiness_ld` не трогаем); Service-деталь эмитит Service (или AutoRepair для A9 по
  `jobs_vehicle`); product-деталь — Product JSON-LD с AggregateRating из ProductReview summary;
  `has_purchased` за per-kind адаптером (fail-closed при выкл. модуле).
- **Тесты:** `apps/promotions/tests/test_seo.py`, `apps/catalog/tests/test_product_reviews.py`,
  `apps/booking/tests/test_services.py`.

## 3. Порядок / первый инкремент

`UA1-1 (E-1) → UA1-2 → UA1-3 → UA2-1 → {UA3-1→UA3-2} ∥ {UA4-1→UA4-2→UA4-3→UA4-4}`.
**Старт — UA1-1**: закрывает прямое требование «деталь страницы услуги» одним рефактором шаблона,
без миграций/новых эндпоинтов, и на нём валидируется контракт. UA3-* и UA4-* после UA2-1 можно
вести параллельными ветками (разные файлы).

## 4. Риски (из разведки)
1. `service_slots.html` — и деталь, и слот-пикер: рефактор рискует GET-флоу `?tag/?slot/?resource`
   и ветками deposit/pass_code/extras → гейт `test_public.py` до мержа.
2. `product_detail.html` standalone → вписывание (UA2-1) = наибольшая визуальная регрессия →
   снапшот-паритет обязателен, аккуратный diff.
3. Buy-box — 5 режимов с тонкими контрактами (session-cart vs DB, two-phase, form_token-
   идемпотентность reserve, multipart-upload) → унифицируем только template/context, вьюхи/services не трогаем.
4. UA4-1 меняет нормализацию, общую для save И live-preview → бэк-компат существующего
   event/product-config — жёсткий гейт (иначе тихо портит сохранённый config тенантов).
5. UA4-3 — единственная миграция волны → локально `--create-db` (иначе ложный зелёный).
6. До UA4-1 у `stays_detail`/`booking_detail` нет per-page инспектора → только «правь на канве»
   (приемлемый интерим).

## 5. Открытые решения (нужно согласовать; в скобках — рекоменд. дефолт)
1. **A7/A9 primary CTA:** «Jetzt buchen» (слот) primary + «Anfrage senden» secondary *(реком.)*,
   или quote-first (Anfrage primary)? Нужен ли per-Service/per-tenant override primary-режима?
2. **URL детали услуги:** один маршрут (деталь == слот-пикер) *(реком., UA1)*, или сплит
   (SEO-описание + отдельная суб-страница брони)?
3. **Отзывы на Service:** адаптер-над-`ProductReview` без миграции *(реком., меньше)*, или сразу
   generic review-модель (`entity_kind+id`/GenericFK — миграция, крупнее, чище на будущее)?
4. **JSON-LD @type услуги:** generic `Service` для A3/A7 + `AutoRepair` для A9 (по `jobs_vehicle`)
   *(реком.)*, или всегда `Service`?
5. **Словарь атрибутов услуги (UA4-3):** контролируемый vocab (как `food.py`/`AMENITIES`) с
   icon/i18n, или free-form строки *(проще для широты Handwerker/Werkstatt, но без icon/i18n)*?
6. **Combo:** вписать в каркас в U-A, или отложить (в UA1-3 только adapter-заглушка) *(реком. отложить)*?

## 6. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` · `docs/market-gap-synthesis-2026-06-30.md`
(E-1/T3/T6) · `docs/archetype-completeness-audit-2026-06-30.md` (D1/D2) ·
`apps/core/archetypes.py` · `templates/storefront/detail.html` · `apps/booking` · `apps/tenants/siteconfig.py`.
