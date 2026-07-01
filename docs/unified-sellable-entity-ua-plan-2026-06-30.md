# Волна U-A — детальный план подзадач (контракт + единая деталь) — 2026-06-30

> Детализация фазы **U-A** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`.
> Все пути/поля/тесты — **верифицированы разведкой против кода** (воркфлоу recon+design).
> Конвенция: docs до кода. Каждая подзадача — вертикальный срез, гейтится CI отдельной веткой.
> Закрывает **E-1** (деталь услуги A3/A7/A9) как первый отгружаемый инкремент.

## 0.0 Зафиксированные решения владельца (2026-06-30)

1. **Деталь услуги — СПЛИТ** (не рефактор одной страницы): отдельная SEO-страница описания
   услуги + слот-пикер как под-страница брони. → UA1-1 = **новая** `service_detail.html`+маршрут;
   `service_slots` остаётся booking-под-страницей, на которую ведёт CTA.
2. **A7/A9 primary-CTA — override**: primary-режим (`booking` vs `request`) настраивается на
   уровне тенанта (`site_config`, без миграции) + опц. per-Service поле. → UA3-1 (логика выбора) +
   поле `Service.primary_action` в миграции UA4-3.
3. **Отзывы — generic-модель сразу** (не адаптер): единый `Review` (`entity_kind`+`entity_id`) с
   **миграцией данных** из `catalog.ProductReview`. → UA4-4 разбит на **UA4-4a** (модель+data-
   migration+паритет product) и **UA4-4b** (Service/Stay/Event + per-entity JSON-LD).

Остальные решения (§5) — на дефолтах: JSON-LD `Service` для A3/A7 + `AutoRepair` для A9
(по `jobs_vehicle`); атрибуты услуги — free-form строки; combo — отложить (в U-A adapter-заглушка).

## 0. Ключевые уточнения дизайна (важно перед кодом)

1. **Деталь-сущность = `booking.Service`, НЕ `jobs.Job`.** Для A7/A9 просматриваемая
   продаваемая сущность — услуга (Leistung); оба кита сеют Services (`demo_kits.py:3721`),
   `archetypes.PRIMARY_SECTION['booking']='services'`. `jobs.Job`/Auftrag — индивидуальный
   Kostenvoranschlag (`/anfrage/`+`/angebot/<token>/`, `purchase_mode='request'`) —
   **транзакция под U-D**, НЕ деталь-сущность U-A. В детали услуги A7/A9 «запрос сметы» —
   CTA по override (решение 2), не отдельная сущность.
2. **E-1 = НОВАЯ страница-деталь (сплит, решение 1).** Добавляем `service_detail.html`
   (extends `detail.html`) на новом маршруте `storefront-service-detail`
   (`/leistung/<uuid:pk>/`): галерея/описание/атрибуты/FAQ/отзывы + primary-CTA + вторичная
   «Anfrage» (A7/A9). Существующий `service_slots` (`storefront-service-slots`) остаётся
   под-страницей брони (buy-box, mode=booking-by-slot), на которую ведёт CTA. Карточки
   `service_index` перелинковываем на деталь. В `DETAIL_ENTITIES` регистрируем деталь, не slots.
3. **`detail.html` — 6 пустых блоков:** `detail_back`, `detail_gallery`, `detail_aside`,
   `detail_body`, `detail_wide`, `detail_buybar`. `product_detail.html` **standalone** (НЕ
   наследует `detail.html`) — его вписывание = крупнейшая зона регрессии. `stay_detail`/
   `event_detail` уже наследуют; `combo_detail` — обходит каркас.
4. **Опции/варианты/модификаторы/комбо — это buy-box (U-A3), НЕ атрибуты (U-A4).**
5. Инлайн-правка/фото услуги уже подключены (`MODEL_EDIT_URLS`/`MODEL_PHOTO_URLS`,
   `site_home.html:1681-1684`) → на новой детали `data-edit-model='service'` заработает без нового кода.

## 1. Подзадачи (сводка)

| ID | Фаза | Заголовок | Размер | Миграция | Зависит |
|---|---|---|:--:|:--:|---|
| **UA1-1** | U-A1 | Новая `service_detail.html` (сплит) + маршрут/вьюха (**E-1, старт**) | M | — | — |
| **UA1-2** | U-A1 | Регистрация `Service`-детали в `DETAIL_ENTITIES` + превью редактора | S | — | UA1-1 |
| **UA1-3** | U-A1 | Контракт `SellableEntity` (протокол-адаптер) + 5 адаптеров | M | — | UA1-2 |
| **UA2-1** | U-A2 | Единый шаблон детали через контракт; **вписать `product_detail` в каркас** | L | — | UA1-3 |
| **UA3-1** | U-A3 | Pluggable buy-box по `purchase_mode` + **override primary-CTA (реш. 2)** | L | — | UA2-1 |
| **UA3-2** | U-A3 | Двухшаговый buy-box (booking-slot услуга + booking-date номер) | L | — | UA3-1 |
| **UA4-1** | U-A4 | Единый реестр секций детали (KEYS+LABELS вместе; ключи Service+Stay) | L | — | UA2-1 |
| **UA4-2** | U-A4 | Data-driven цикл рендера секций вместо per-template if/elif | L | — | UA4-1 |
| **UA4-3** | U-A4 | **Атрибуты+FAQ услуги** + поле `primary_action` (богатая карточка A3/A7/A9) | M | **да** | UA4-2 |
| **UA4-4a** | U-A4 | **Generic `Review`-модель** (entity_kind+id) + миграция данных из `ProductReview` + паритет product | L | **да** | UA4-3 |
| **UA4-4b** | U-A4 | Per-entity JSON-LD + отзывы на Service/Stay/Event через generic-модель | L | — | UA4-4a |

**Первый отгружаемый инкремент = UA1-1** (закрывает «деталь услуги»), **без миграции**.
Миграции волны: **UA4-3** (атрибуты/FAQ + `primary_action` на `Service`), **UA4-4a**
(generic `Review` + миграция данных из `ProductReview`).

## 2. Подзадачи (детально)

### UA1-1 — Новая `service_detail.html` (сплит) + маршрут/вьюха (E-1) · M · без миграции
Создать НОВУЮ страницу-деталь услуги на каркасе: маршрут `storefront-service-detail`
(`/leistung/<uuid:pk>/`) → вьюха `service_detail` → шаблон `service_detail.html` (extends
`detail.html`). Блоки: `detail_back`→`storefront-termin`; `detail_gallery`→`_media_gallery.html`/
`service.image_url`; `detail_aside`→карточка `#buchen` (h1 `data-edit`, длит./цена, **primary-CTA
«Termin buchen»** → `storefront-service-slots`, **вторичная «Anfrage senden»** → `storefront-anfrage`
при `jobs_active`); `detail_body`→описание (атрибуты/FAQ — UA4-3); `detail_buybar`→`_detail_buybar.html`
anchor=`#buchen` module=`booking`. **`service_slots` не трогаем** — остаётся под-страницей брони.
Карточки `service_index.html` перелинковать с `storefront-service-slots` на `storefront-service-detail`.
- **Файлы:** `templates/storefront/service_detail.html` (новый), `apps/booking/public_views.py`
  (вьюха `service_detail`), `config/urls_tenant.py` (маршрут), `templates/storefront/service_index.html`
  (ссылка карточки), `templates/storefront/detail.html`.
- **Критерии:** `storefront-service-detail` рендерит `service_detail.html` extends `detail.html` со
  всеми 6 блоками; primary-CTA ведёт на `storefront-service-slots` (без изменения его вьюхи/полей);
  вторичная «Anfrage» видна только при активном `jobs`; `service_index` карточки ведут на деталь;
  `data-edit-model='service'`/`data-photo-edit` на детали работают; buybar показывает `Jetzt buchen`;
  без миграции; ruff чисто; тесты booking зелёные.
- **Тесты:** `apps/booking/tests/test_public.py`, `apps/core/tests/test_inline_edit.py`.

### UA1-2 — Регистрация `Service`-детали в `DETAIL_ENTITIES` + превью редактора · S · без миграции
Добавить в `archetypes.DETAIL_ENTITIES`: `('booking','booking.Service','storefront-service-detail',
_('Service page'), {'is_active':True}, ('-created_at',))`. Добавить `booking_detail` в
`SCOPE_PAGE_KEY` (`site_home.html:1629`) — пока без per-page инспектора (fallthrough к «правь на
канве», как `stays_detail`; per-page инспектор — UA4-1).
- **Файлы:** `apps/core/archetypes.py`, `templates/tenant/site_home.html`, `apps/core/tests/test_preview_pages.py`.
- **Критерии:** `example_detail_pages(tenant)` отдаёт `group='booking_detail'`,
  `url=reverse('storefront-service-detail', args=[service.pk])` при активном booking + ≥1 активном
  Service (guard `is_module_active`+`NoReverseMatch`); опция в `<select id='home-prev-page'>`;
  тест-локи обновлены (каждый detail-group `endswith '_detail'`).
- **Тесты:** `apps/core/tests/test_preview_pages.py`, `apps/core/tests/test_archetypes.py`.

### UA1-3 — Контракт `SellableEntity` (адаптер) + 5 адаптеров · M · без миграции
Ввести лёгкий протокол представления в `apps/core` (`sellable.py`): нормализует любую
просматриваемую сущность к `{kind, pk, name, description, image/gallery, price_display,
purchase_mode, purchase_label, detail_url, buybox_context, attributes, info_sections}`. Per-kind
адаптеры (product/service/stay/event/combo), модели — лениво (`django_apps.get_model`). Адаптеры
**делегируют** цены/наличие существующим движкам, модели НЕ сливают. Шов для U-A3/U-A4. Пока без
правки шаблонов — чистый Python + юниты.
- **Файлы:** `apps/core/sellable.py` (новый), `apps/core/archetypes.py`, `apps/core/views.py`.
- **Критерии:** `sellable_for(kind, obj)` + kind→mode/label **переиспользует**
  `archetypes.purchase_mode/purchase_label` (без дублей); адаптеры для 5 kinds; combo→`cart`;
  jobs **явно НЕ адаптер** (документирован как U-D); импорт `apps.core` не тянет catalog/stays/
  events/booking на загрузке.
- **Тесты:** `apps/core/tests/test_archetypes.py`, `apps/booking/tests/test_services.py`.

### UA2-1 — Единый шаблон детали через контракт; вписать `product_detail` · L · без миграции
Свести общий «хром» detail-страниц (back-label, галерея, title/price-header, buybar-module) на
чтение из `SellableEntity`. **`product_detail.html` вписать в каркас** (сейчас standalone). Формы/
якоря каждой сущности — байт-в-байт.
- **Файлы:** `templates/storefront/product_detail.html`, `detail.html`, `service_detail.html`.
- **Критерии:** `product_detail.html extends detail.html` с паритетом раскладки (категория/badge/h1/
  summary/цена+grundpreis/LMIV/add-to-cart/отзывы/related); все detail-страницы делят 2-кол.
  grid+sticky aside+buybar; POST/поля/anchor-id/inline-attr — без изменений.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/booking/tests/test_public.py`,
  `apps/promotions/tests/test_public.py`.
- ⚠️ **Наибольшая зона регрессии** — снапшот-паритет обязателен, мержить по diff.

### UA3-1 — Pluggable buy-box (одношаговые) + override primary-CTA · L · без миграции
Вынести buy-box в `storefront/_buybox.html`, диспатч по `purchase_mode`: `cart`
(`_add_to_cart_form.html`), `reserve` (промо-форма), `request` (ссылка `/anfrage/`), одношаговый
booking. **Override primary-CTA (реш. 2):** резолвер `primary_action(service, tenant)` =
`Service.primary_action` (поле из UA4-3) ∥ `site_config['primary_service_cta']` ∥
`purchase_mode('booking')`; на детали услуги (UA1-1) primary/secondary кнопки меняются местами по
резолверу (booking↔request). Общий контракт (csrf, honeypot `website`, `name(req)/email/phone/note`,
sold_out→waitlist). Двухшаговые — UA3-2.
- **Файлы:** `templates/storefront/_buybox.html` (новый), `_detail_buybar.html`, `service_detail.html`,
  `product_detail.html`, `apps/core/archetypes.py` (резолвер primary_action).
- **Критерии:** `_buybox.html` рендерит верную per-mode форму/CTA только из контракта (без per-template
  if/elif по архетипу); primary/secondary на детали услуги следуют override (tenant-default пока без
  миграции; per-service поле — UA4-3); product(cart)/promotion(reserve) — через include, POST неизменны;
  sold-out→waitlist где режим поддерживает.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/promotions/tests/test_public.py`,
  `apps/booking/tests/test_public.py`.

### UA3-2 — Двухшаговый buy-box (booking-slot услуга + booking-date номер) · L · без миграции
`SellableEntity` даёт `select_url`(GET) отдельно от `submit_url`(POST) + признак готовности;
`_buybox.html` рендерит селектор, POST-форму — только при валидном выборе (`quote.available`/
выбранный слот). Провести stay (`stay_detail`) и услугу (booking-под-страница `service_slots`) через
этот путь, сохранив rate_options/kurtaxe/extras/deposit (stay) и resource/pass_code/extras/deposit
(service). Анти-оверселл — на сервере.
- **Файлы:** `stay_detail.html`, `service_slots.html`, `apps/stays/public_views.py`,
  `apps/booking/public_views.py`.
- **Критерии:** поля `storefront-unterkunft-book`/`storefront-service-book` неизменны; POST-форма
  только при выборе; сервер ре-валидирует наличие (`book_stay`/`booking.services.book` не трогаем).
- **Тесты:** `apps/stays/tests/test_public.py`, `apps/booking/tests/test_public.py`.

### UA4-1 — Единый реестр секций детали · L · без миграции
Обобщить `EVENT_DETAIL_SECTION_KEYS`(order+hide)/`PRODUCT_DETAIL_SECTION_KEYS`(hide-only) в одну
модель `(archetype,section)`→`{orderable,hideable}`, config `['<module>_detail']={order,hidden}` за
одним нормализатором. Совместить KEYS с LABELS (сейчас LABELS в `core/views.py`). Добавить
`SERVICE_DETAIL_SECTION_KEYS` (description/attributes/faq/related), `STAY_DETAIL_SECTION_KEYS`
(amenities/facts/related). Round-trip через save (`home_builder_view`) и live-preview (`accept_preview_draft`).
- **Файлы:** `apps/tenants/siteconfig.py`, `apps/core/views.py`, `templates/tenant/site_home.html`.
- **Критерии:** один нормализатор + `*_detail_order(config, module)`; `SCOPE_PAGE_KEY` получает
  `booking_detail`/`stays_detail`; round-trip через POST И live-preview без потерь; **бэк-компат**
  (существующий event/product-config нормализуется идентично).
- **Тесты:** `apps/core/tests/test_home_builder.py`, `apps/core/tests/test_live_preview.py`.

### UA4-2 — Data-driven цикл рендера секций · L · без миграции
Заменить if/elif в `_event_thematic.html` и инлайн-guard'ы `product_detail.html` одним
`{% for section in detail_order %}{% include %}` из реестра UA4-1. Service/stay тела — через тот же цикл.
- **Файлы:** `_event_thematic.html`, `product_detail.html`, `stay_detail.html`, `service_detail.html`.
- **Критерии:** тела product/event/stay/service — один цикл по `detail_order`; скрытые опущены; порядок
  соблюдён; каждая секция несёт `data-sf-section`; снапшот event-вывода неизменен.
- **Тесты:** `apps/catalog/tests/test_storefront.py`, `apps/core/tests/test_home_builder.py`,
  `apps/stays/tests/test_public.py`.

### UA4-3 — Атрибуты+FAQ услуги + поле `primary_action` · M · **МИГРАЦИЯ**
Дать `Service`: `attributes` (JSONField list — free-form строки, реш. §5), `faq` (JSONField list of
`{q,a}`), `primary_action` (choices `booking|request`, для override реш. 2). Валидатор по образцу
`events/details.py _SCHEMA` (garbage→ничего, без краша). Рендер атрибутов/FAQ как унифицированные
секции (цикл UA4-2). Засеять пару атрибутов+FAQ в werkstatt/handwerker демо. **Закрывает E-1/D1/D2
полностью.**
- **Файлы:** `apps/booking/models.py`, `service_detail.html`, `apps/tenants/demo_kits.py`.
- **Критерии:** `Service.attributes/faq/primary_action` + normalize/validate; секции attributes/FAQ
  (hideable/orderable через UA4-1); демо A7/A9 сеют атрибуты+FAQ; `primary_action` читается резолвером
  UA3-1. **Миграция booking.Service; локально `--create-db`.**
- **Тесты:** `apps/booking/tests/test_services.py`, `apps/booking/tests/test_public.py`.

### UA4-4a — Generic `Review`-модель + миграция данных из `ProductReview` · L · **МИГРАЦИЯ**
Ввести единую модель отзыва (`apps/reviews` или `apps/core`): `entity_kind` + `entity_id` + rating +
author/email + comment + verified + is_published + timestamps (по образцу `ProductReview`). **Data-
migration**: перенести существующие `catalog.ProductReview` строки в generic-модель (`entity_kind='product'`),
сохранив опубликованность/верификацию. Product-деталь переключить на чтение generic-модели (паритет
рендера/summary). Per-kind verification-адаптер (Product→OrderItem), **fail-closed**.
- **Файлы:** `apps/reviews/models.py`+`migrations/` (новый app) или `apps/core`, `apps/catalog/reviews.py`,
  `apps/promotions/public_views.py` (product_review_submit/summary), `templates/storefront/product_detail.html`.
- **Критерии:** generic `Review` создан; **data-migration переносит все ProductReview без потерь**
  (тест на количество/поля/verified); product-деталь рендерит отзывы+summary из generic-модели с
  прежним видом; verification fail-closed при выкл. модуле. **Миграция схемы + данных; `--create-db`.**
- **Тесты:** `apps/catalog/tests/test_product_reviews.py`, новый `apps/reviews/tests/`.
- ⚠️ **Data-migration существующих отзывов** — гейт: тест на равенство до/после.

### UA4-4b — Per-entity JSON-LD + отзывы на Service/Stay/Event · L · без миграции
Обобщить сабмит/рендер отзыва на Service/Stay/Event через generic-модель (per-kind verification:
Service→Booking-by-email, Stay→StayBooking, Event→Ticket; fail-closed). Kind-aware JSON-LD эмиттер в
`apps/core/seo.py` (`entity_ld` из нормализованного дикта контракта, не привязанного к Promotion) →
schema.org Product/Service/Event/LodgingBusiness + Offer + AggregateRating/Review из generic-summary;
Service → `AutoRepair` при `jobs_vehicle`, иначе `Service` (реш. §5). Через per-page `structured_data`.
- **Файлы:** `apps/core/seo.py`, `apps/booking/public_views.py` (service review submit + jsonld),
  `apps/stays/public_views.py`, `apps/events/public_views.py`, detail-шаблоны.
- **Критерии:** Service/Stay/Event-деталь принимают верифиц. отзыв (per-kind, fail-closed) и рендерят
  блок+summary из generic-модели; entity-JSON-LD с верным `@type` per kind + AggregateRating;
  `offer_ld`/`localbusiness_ld` не трогаем.
- **Тесты:** `apps/promotions/tests/test_seo.py`, `apps/booking/tests/test_services.py`,
  `apps/stays/tests/test_public.py`, `apps/events/tests/test_public.py`.

## 3. Порядок / первый инкремент

`UA1-1 (E-1) → UA1-2 → UA1-3 → UA2-1 → {UA3-1→UA3-2} ∥ {UA4-1→UA4-2→UA4-3→UA4-4a→UA4-4b}`.
**Старт — UA1-1**: новая страница-деталь услуги (сплит) — закрывает прямое требование «деталь
услуги» без миграций/смены существующих эндпоинтов. UA3-* и UA4-* после UA2-1 можно вести
параллельными ветками (разные файлы).

## 4. Риски (из разведки + правки по решениям)
1. **Сплит (реш.1):** новая деталь + существующий slots — следить, что карточки/ссылки/`DETAIL_ENTITIES`
   ведут на деталь, а primary-CTA — на slots; не сломать GET-флоу слотов. Гейт `test_public.py`.
2. `product_detail.html` standalone → вписывание (UA2-1) = наибольшая визуальная регрессия →
   снапшот-паритет обязателен.
3. Buy-box — 5 режимов с тонкими контрактами → унифицируем только template/context, вьюхи/services не трогаем.
4. UA4-1 меняет нормализацию, общую для save И live-preview → бэк-компат — жёсткий гейт.
5. **UA4-3 и UA4-4a — миграции** (Service attrs/faq/primary_action; generic Review + **data-migration**).
   Локально `--create-db`; для UA4-4a — тест равенства перенесённых отзывов до/после.
6. До UA4-1 у `stays_detail`/`booking_detail` нет per-page инспектора → только «правь на канве» (интерим).

## 5. Открытые решения — статус
1. ✅ **Форма детали услуги:** СПЛИТ (описание + бронь) — зафиксировано.
2. ✅ **A7/A9 primary CTA:** per-tenant/service override — зафиксировано (UA3-1 + `Service.primary_action`).
3. ✅ **Отзывы per-item:** generic review-модель сразу — зафиксировано (UA4-4a data-migration).
4. **JSON-LD @type услуги:** `Service` (A3/A7) + `AutoRepair` (A9 по `jobs_vehicle`) — *дефолт (UA4-4b)*.
5. **Словарь атрибутов услуги:** free-form строки — *дефолт (UA4-3)*; vocab с icon/i18n — позже.
6. **Combo:** отложить (в U-A только adapter-заглушка UA1-3) — *дефолт*.
> Пункты 4–6 — на дефолтах; можно уточнить при подходе к UA4-3/UA4-4b.

## 6. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` · `docs/market-gap-synthesis-2026-06-30.md`
(E-1/T3/T6) · `docs/archetype-completeness-audit-2026-06-30.md` (D1/D2) ·
`apps/core/archetypes.py` · `templates/storefront/detail.html` · `apps/booking` · `apps/tenants/siteconfig.py`.
