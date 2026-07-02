# Волна U-C — детальный план подзадач (универсальный визуальный редактор на всех страницах/блоках) — 2026-06-30

> Детализация фазы **U-C** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`
> (детализировано 2026-07-01). Все пути/поля/функции — **верифицированы разведкой против кода**
> (3 Explore-агента + Plan-агент). Формат — как U-A/U-B: подзадачи по файлам/критериям/тестам +
> **сравнение** + **пересечения**. Каждая подзадача — вертикальный срез, отдельная ветка, CI-гейт.
> Переиспользуем всё из U-A/U-B; без big-bang. Реализация — после волн U-A/U-B.
> Зависит от **U-A** (UA1-3 `SellableEntity`, UA2-1 product-на-каркасе, UA4-1 единый реестр
> секций детальной, UA4-4a generic `Review`) и **U-B** (UB1-2 `_sellable_card.html`, UB2-1 `FacetProvider`).

## 0. Контекст и «хребет», который U-C обобщает (верифицировано)

Главная мотивация мастер-трека: **шаблонизатор/визуальный редактор строится ОДИН раз и работает
на всех типах страниц и всех блоках**. Сегодня редактор мощный (SE-1…SE-9), но «прошит» под
ГЛАВНУЮ: полный реестр секций + on-canvas правка/добавление/перенос есть только для home;
листинг/деталь/инфо — частично (пер-страничная раскладка + инлайн-тексты), правовые — только текст.

Редактор — это **трёхсторонний round-trip, завязанный на константы `apps/tenants/siteconfig.py`**.
Любой редактируемый блок обязан присутствовать во всех трёх, иначе молча теряется:
1. **`collect()`** (`templates/tenant/site_home.html:1211-1389`) — форма → draft-JSON.
2. **`site_preview_draft`** (`apps/core/views.py`, ~1393+) — JSON → сессия `site_preview_draft`,
   ре-нормализация, рендер под `?preview=1` через контекст-процессор `apps/core/context.py:119-129`
   (page-agnostic наложение на ЛЮБОЙ странице).
3. **`home_builder_view` POST** (`apps/core/views.py:669-1044`) — форма → `siteconfig.normalize` →
   ОДИН blob `Tenant.site_config`; история через `push_history` (кап 8), автосейв `_draft`.

Инспектор-контекст строится на `views.py:1103-1191` (home `sections`, `event_sections`,
`product_sections`). Переключение области — `applyPageScope`/`SCOPE_PAGE_KEY` (`site_home.html:1629-1674`),
тумблит группы `[data-scope]`/`[data-page-key]` по странице. **Это самая горячая поверхность в
кодовой базе** — каждая подзадача ниже гейтится тестами паритета round-trip и мержится по diff.

## 1. Сравнение состояния редактора по типам страниц (что «прошито» под home)

| Аспект | Главная (home) | Листинг (catalog/events/stays/services) | Деталь (product/stay/event/service) | Инфо/Правовое |
|---|---|---|---|---|
| Реестр секций | **полный** `SECTIONS` (~21) + C-блоки | нет (только раскладка страницы) | **фрагментарно**: event 14 кл. (order+hidden), product 4 кл. (hidden), stay/service — **нет** | нет (`group='text'`) |
| On-canvas add/move | **да** (`+`/drag, только `/`) | нет | нет | нет |
| Инспектор-группы | **да** (`sections`) | пер-страничная раскладка на вкладке Pages | event/product — да; stay/service — нет | нет |
| Инлайн-правка | текст+цена+фото (5 моделей) | карточки (инлайн) | да (`data-edit-model`) | тексты сайта (`data-edit`) |
| Реестр в коде | `SECTIONS`/`GRID_*`/`_SECTION_ICONS` | `catalog_layout`/… | `EVENT_/PRODUCT_DETAIL_SECTION_KEYS` | `preview_pages` `views.py:1091-1099` |

**Инлайн-правка — 6 РАЗДЕЛЬНЫХ эндпоинтов** (`@login_required`, 204/400): promotion (`promotions/views.py:35-87`),
product (`catalog/views.py:459-518` + фото 523-562), category (422-449), service (`booking/views.py:410-456` +
фото 461-486). ⚠️ service — **плоские строки, без i18n**; остальные — i18n `de`. Фото: product/stay/event —
список (`apply_gallery_op` replace/add/remove), **service — одиночный dict, только replace**.

## 2. Пересечения / партиция (что унифицируем vs провайдеры vs раздельно)

**УНИФИЦИРУЕМ (одна реализация на все типы страниц):**
- **Реестр секций/блоков** — `PAGE_SECTION_REGISTRY` по ключу `(page_type, section)`, поглощает
  `SECTIONS` + `EVENT_/PRODUCT_DETAIL_SECTION_KEYS` + `_SECTION_ICONS` + `_*_SECTION_LABELS` (UC1).
- **Draft-схема + round-trip** — `collect()`/`site_preview_draft`/save-цикл делят ОДИН page-scoped
  сериализатор по реестру (UC2-1). Page-agnostic `?preview=1` (`context.py`) уже работает на любой
  странице — расширяем, не форкаем.
- **Layout-движок** — `normalize_layout`/`grid_class_string`/`effective_card_visual`/`site_defaults`
  (переиспользуем как есть, purge-safe таблицы).
- **Микрошаблоны/темы/пер-девайс** — один аппликатор каскадит на все типы страниц (UC3).
- **Undo/redo/drag/inserter** — один JS-стек, параметризован page-type (UC2-2).
- **Отзывы + JSON-LD + галерея** — по одному блоку, питаются от `SellableEntity` (UC4).
- **Инлайн-правка** — один диспетчер за field-map адаптера (UC2-4).

**ПРОВАЙДЕР (пер-страница/пер-kind за единым интерфейсом):** доступные блоки на page_type (сам реестр
= провайдер); маппинг карточки (`SellableEntity`→`_sellable_card`); фасеты (`FacetProvider`, U-B);
верификация отзывов / `@type` JSON-LD / форма галереи — пер-kind адаптеры.

**РАЗДЕЛЬНО (НЕ канва — форма/код):** внутренности buy-box (календарь дат/слоты/multi-room/line-items,
UC5); анти-оверселл/availability/движки брони; иерархия категорий (только catalog); i18n-оверлей
(`localize`/`_deep_overlay`).

## 3. Подзадачи U-C (сводка)

| ID | Фаза | Заголовок | Разм. | Мигр. | Зависит |
|---|---|---|:--:|:--:|---|
| **UC1-1** | U-C1 | Универсальный `PAGE_SECTION_REGISTRY` — одна модель `(page_type, section)`, обобщает `SECTIONS`+`*_DETAIL_SECTION_KEYS`; один нормализатор/order/hidden на page_type | L | — | UA4-1 |
| **UC1-2** | U-C1 | Наполнить реестр недостающими page-type: `stay_detail`, `service_detail`, `listing`, `info`/`legal` | M | — | UC1-1 |
| **UC1-3** | U-C1 | Свести `_SECTION_ICONS`+`_EVENT/_PRODUCT_SECTION_LABELS` в реестр (KEYS+LABELS+ICONS вместе); переписать сборку инспектор-контекста на `page_inspector()` | M | — | UC1-2 |
| **UC2-1** | U-C2 | Обобщить `collect()`/`site_preview_draft`/save в один page-scoped draft-модуль (`config["pages"][page_type]`) с back-compat шимами | L | — | UC1-3 |
| **UC2-2** | U-C2 | On-canvas add/move для деталь/листинг/инфо: расширить `+`/`moveBlock` за пределы home; `data-sf-section` drop-targets на всех страницах | L | — | UC2-1 |
| **UC2-3** | U-C2 | Пер-страничные инспектор-группы для всех page-type (`applyPageScope` из реестра); C-блоки разрешить на деталь/инфо | M | — | UC2-2 |
| **UC2-4** | U-C2 | Один диспетчер инлайн-правки (обобщить 6 пер-модельных эндпоинтов за field-map `SellableEntity`) | M | — | UC2-1, UA1-3 |
| **UC3-1** | U-C3 | Тема/микрошаблоны на ВЕСЬ сайт: `MICRO_TEMPLATES`+`site_defaults` каскадят на все page-type разом (не только грид главной) | M | — | UC2-1 |
| **UC3-2** | U-C3 | Пер-девайс (`hidden_on`)+`width` на секциях ВСЕХ page-type (деталь/листинг) | S | — | UC3-1 |
| **UC4-1** | U-C4 | Единый `_reviews_block.html` из generic `Review` (UA4-4a); секция отзывов/рейтинг на всех деталях (закрывает **T3**) | M | — | UA4-4a, UC1-2 |
| **UC4-2** | U-C4 | Единый JSON-LD-блок `entity_ld(sellable)` в слот `structured_data` на event/stay/product/service деталях (закрывает **T6**) | M | — | UA4-4b, UC4-1 |
| **UC4-3** | U-C4 | Единая галерея через адаптер: нормализовать Service single-image → список, чтобы `_media_gallery.html` покрыл все 5 kind | M | **возм.** | UA1-3, UC4-1 |
| **UC5-1** | U-C5 | Граница: внутренности buy-box (календарь/слоты/multi-room/line-items) — **форма**, не канва; реестр метит `configurable=form` | S | — | UA3-1, UC2-3 |

**Первый отгружаемый инкремент = UC1-1** (единый реестр — закрывает отложенный «реестр секций
детальной»), без миграции. **Миграции в волне: не гарантированы** — только UC4-3 *возможно* (если
`Service.image` поднимать из dict в список; решение D4). Все схемные/дата-миграции, на которые U-C
опирается (generic `Review` и атрибуты), уже приземляются в **U-A** (UA4-3/UA4-4a).

## 4. Последовательность (что что разблокирует)

```
UA4-1 ─┐
       UC1-1 → UC1-2 → UC1-3 → UC2-1 ─┬─ UC2-2 → UC2-3 → UC5-1
                                      ├─ UC2-4        (UC2-3)
                                      └─ UC3-1 → UC3-2
UA4-4a ──────────────────────────────── UC4-1 → UC4-2
UA1-3 ─────────────────────────────────── UC4-1 → UC4-3
```
Критический путь: `UC1-1→UC1-2→UC1-3` (реестр) → `UC2-1` (обобщение draft-схемы) — второй гейт, на
котором висит остальное. `UC4-*` — параллельная ветка (другие файлы, питается от generic Review/адаптера
из U-A). `UC5-1` — последним (только затягивает границу, которую реестр уже выражает).

## 5. Детали ключевых подзадач (файлы/критерии/тесты)

- **UC1-1** (L) — новый `PAGE_SECTION_REGISTRY` в `siteconfig.py`: обобщить `_section_entry`/
  `normalize_sections`/`section_layout`; `SECTIONS`/`EVENT_/PRODUCT_DETAIL_SECTION_KEYS` оставить
  как производные view (back-compat). *Критерии:* `page_sections(config, page_type)` даёт упорядоченные
  видимые ключи для любого page_type; `normalize()` — **байт-в-байт** для существующих home/event/product
  конфигов (жёсткий гейт); `test_sections_cover` цел. *Тесты:* `test_siteconfig`, `test_home_builder`,
  `test_live_preview`, `test_sections_cover`.
- **UC1-2** (M) — реестр для page-type без реестра: `stay_detail` (amenities/факты/галерея/отзывы/related),
  `service_detail` (описание/атрибуты/FAQ/отзывы/related — ключи из UA4-1/UA4-3), `listing` (header/facets/
  grid/pagination — слоты U-B), first-class `info`/`legal` (about/impressum/datenschutz/widerruf — сейчас
  `group='text'`, `views.py:1091-1099`). *Критерии:* stay/service деталь получают order+hidden (был статик);
  round-trip через save И live-preview. *Тесты:* `stays/test_public`, `booking/test_public`, `test_preview_pages`.
- **UC1-3** (M) — свести `_SECTION_ICONS` (`views.py:632-655`), `_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS`
  (`views.py:1643/1661`) в реестр (KEYS+LABELS+ICONS вместе). Переписать сборку инспектора (`views.py:1103-1191`)
  на generic `page_inspector(config, page_type)` вместо трёх ручных списков. *Критерии:* инспектор строится
  одним циклом по реестру для активного page_type; вывод для home/event/product не меняется (снапшот-паритет);
  иконки появляются у секций детали в рейле. *Тесты:* `test_home_builder`.
- **UC2-1** (L, ⚠️ горячее) — `config["pages"][page_type]={"sections":[…]}` рядом с legacy `config["sections"]`
  + шимы; вынести serialize/accept/normalize в общие хелперы по реестру. *Критерии:* секция детали/инфо
  переживает collect→accept→save без потерь; `?preview=1` показывает её на нужной странице; legacy home —
  байт-в-байт; анти-рекурсия `_SNAPSHOT_EXCLUDE`/`history`/`_draft` цела. *Тесты:* `test_live_preview`,
  `test_home_builder`, новый `test_draft_schema`. **Мерж по diff.**
- **UC2-2** (L) — расширить инсертер `+` (`showInserter`/`submitInsert`/`submitInsertTemplate`, `site_home.html:1545-1579`)
  и drag (`moveBlock`, `1593-1604`) на деталь/листинг/инфо; `add_block`/`_insert_after_section` (`views.py:702-711`)
  получают `page_type`. *Критерии:* C-блок добавляется/переносится на детали/инфо; drop-line/`focus-on` работают;
  home не меняется. *Тесты:* `test_home_builder`, `test_preview_pages`.
- **UC2-3** (M) — `applyPageScope`/`SCOPE_PAGE_KEY` (`site_home.html:1629`) → реестр-driven: каждый page-type
  из переключателя (`#home-prev-page`, включая stay_detail/service_detail/info/legal) получает инспектор-группу;
  C-блоки на деталь/инфо. *Критерии:* переключение показывает только блоки страницы; carry-forward скрытых
  скоупов (как `existing_fixed`, `views.py:821-836`). *Тесты:* `test_preview_pages`, `test_home_builder`.
- **UC2-4** (M) — диспетчер `sellable-inline-edit`, резолвит модель+поле через адаптер (UA1-3); 6 URL
  оставить тонкими алиасами. ⚠️ service — плоские строки, остальные i18n `de` → адаптер несёт i18n-ность
  пер-kind, fail-closed на рассинхроне. *Тесты:* `test_inline_edit`, `booking/test_public`, `catalog/test_storefront`.
- **UC3-1** (M) — контрол «тема на все архетипы разом»: `MICRO_TEMPLATES` (`siteconfig.py:227-262`) +
  `site_defaults`/`effective_card_visual` (`488-517`) каскадят на карточки листинга/детали всех page-type;
  распаковка на фронте (как SE-3a). *Критерии:* тема обновляет вид на home+листинг+деталь live; purge-safe;
  пустые дефолты = текущий вид. *Тесты:* `test_live_preview`, `test_siteconfig`.
- **UC3-2** (S) — `hidden_on` (`_clean_hidden_on`) + `width` (`_LAYOUT_WIDTHS`) на секциях детали/листинга
  через реестр. *Критерии:* секция детали скрывается пер-девайс/делается full-bleed; back-compat. *Тесты:*
  `test_siteconfig`, `test_home_builder`.
- **UC4-1** (M) — `_reviews_block.html` из generic `Review` (UA4-4a, `entity_kind`+`entity_id`), pluggable
  пер-kind, как секция реестра на ВСЕХ деталях → закрывает **T3** для event/stay/service (сейчас отзывов нет;
  есть только `catalog.ProductReview` + business-wide `BusinessReview`). Верификация пер-kind (fail-closed).
  *Критерии:* event/stay/service деталь рендерят отзывы+рейтинг из generic Review; product-паритет; секция
  скрываема/сортируема через реестр. *Тесты:* `catalog/test_product_reviews`, `reviews/tests`, `*/test_public`.
- **UC4-2** (M) — закрывает **T6**. `entity_ld(sellable)` (из UA4-4b, `apps/core/seo.py`) в слот
  `structured_data` (`_base.html:26` уже пуст) на всех деталях; `@type` = `SellableEntity.schema_type`
  (Product/Service/Event/LodgingBusiness; Service→AutoRepair при `jobs_vehicle`) + AggregateRating.
  `localbusiness_ld`/`offer_ld` не трогаем. *Критерии:* каждая деталь эмитит корректный `@type`; нет дубля
  LocalBusiness; валидный JSON. *Тесты:* `promotions/test_seo`, `*/test_public`.
- **UC4-3** (M, миграция возможна) — адаптер (UA1-3) отдаёт `images[]` для всех kind, чтобы
  `_media_gallery.html` покрыл Service (сейчас single-dict → нет галереи). Либо шим dict→[dict] (без миграции,
  replace-only), либо поле-список (миграция, D4). *Критерии:* service-деталь показывает общую галерею;
  replace/add/remove работают при поднятии поля; прочие kind не тронуты. *Тесты:* `booking/test_public`,
  `catalog/test_storefront`.
- **UC5-1** (S) — реестр метит buy-box `configurable="form"` → инспектор рисует форму (не drag/inserter);
  канва правит презентацию ВОКРУГ (`_buybox.html` из UA3-1). Движки дат/слотов/multi-room не трогаем.
  *Критерии:* buy-box нельзя перетащить/удалить на канве; настройки — форма; окружение — правится канвой.
  *Тесты:* `test_home_builder`, `booking/test_public`, `stays/test_public`.

## 6. Пересечения с U-A / U-B
- **UC1 реестр детали сидит на блоках `detail.html` (U-A):** UA4-1 уже свёл event+product за одним
  нормализатором, UA4-2 сделал тела data-driven — UC1 поднимает это на ВСЕ page-type включая home. Если
  UA4-1 сдвинется, UC1-1 сам делает свод детали (крупнее).
- **UC2-4** нужен `SellableEntity` (UA1-3) — field-map адаптера = ось диспетчера.
- **UC4-1** едет на UA4-4a generic `Review`+дата-миграция (решение UA-плана §0.0.3 — Review в U-A) → тогда
  UC4-1 = чистая проводка, без модели/миграции здесь. **UC4-2** на UA4-4b `entity_ld`.
- **UC4-3 + `_sellable_card` (UB1-2):** карточка уже ест `image_url`; UC4-3 расширяет адаптер до `images[]`.
- **UC3** каскадит тему в `_sellable_card` (и home-секции, и листинги — гейт `test_sections_cover`).
- **UC2-3 листинг-скоуп** нужен `listing.html` (UB1-1).

## 7. Риски U-C
1. **Редактор — самая горячая поверхность.** `collect()`/`site_preview_draft`/`normalize`/`push_history`/
   undo/drag/inserter тесно связаны → регрессия ломает весь билдер. Каждая UC2 — гейт паритетом round-trip,
   мерж по diff.
2. **Page-agnostic draft.** `context.py:119-129` накладывает черновик на ЛЮБУЮ страницу под `?preview=1`;
   `config["pages"][page_type]` не должен «протекать» с одной страницы на другую; анти-рекурсия цела.
3. **Purge-safe Tailwind.** UC3-тема эмитит только из статических таблиц/inline-CSS-переменных — никогда
   динамические классы (purge вырежет); уже кусалось (`siteconfig.py:~294`).
4. **Вложенность multipart-форм.** Загрузчики медиа — отдельные формы (нельзя вкладывать в `#home-form`);
   UC2-2 на деталях: композиция — через JSON-draft, медиа-операции — вне формы (redirect+reload).
5. **Back-compat — жёсткий гейт.** Тысячи legacy `site_config` должны нормализоваться байт-в-байт после
   UC1-1/UC2-1 (`normalize` дропает неизвестное / дописывает недостающее — инвариант сохранить).
6. **i18n-асимметрия инлайна (UC2-4).** service — плоские строки, остальные i18n `de`; диспетчер не должен
   писать плоскую строку в i18n-поле (порча данных) — fail-closed.
7. **Carry-forward скоупа.** `home_builder_view` несёт вперёд секции скрытых архетипов (`existing_fixed`,
   `views.py:821-836`); расширение скоупа на деталь/инфо/правовое обязано повторить это пер-page_type,
   иначе частичный POST затрёт блоки другой страницы.

## 8. Открытые решения U-C — ✅ ЗАФИКСИРОВАНО (2026-07-01, см. `…-decisions-2026-06-30.md`)
- **D1 — обобщение 6 инлайн-эндпоинтов (UC2-4):** ✅ **(a) один диспетчер за адаптером, 6 URL — тонкие
  алиасы** (C-1; JS не трогаем; промо-inline — свой view сейчас, мигрирует в диспетчер позже).
- **D2 — generic `Review`:** ✅ **в U-A (UA4-4a)** — подтверждено (A-3); UC4-1 = чистая проводка без миграции здесь.
- **D3 — `legal`/`info` first-class page-type:** ✅ **сейчас (B-4)** — UC1-2/UC2-3 включают `info`/`legal`;
  **тянет E-2 (правовой пакет DACH) в волну U-C** (засев AGB/§312j/PAngV — отдельным инкрементом внутри/сразу после).
- **D4 — галерея Service:** ✅ **(a) шим dict→[dict] сейчас (без миграции)** (C-2); поле-список — позже при нужде reorder.

## 9. Верификация U-C (end-to-end)
- `uv run ruff check .` + `ruff format --check`; `uv run pytest apps/core apps/tenants apps/catalog apps/booking
  apps/stays apps/events -k "home_builder or live_preview or sections or draft or inline or preview or seo or
  review" --reuse-db` (при UC4-3(b) — `--create-db`).
- Браузер: `seed_demo_tenants --recreate`; в редакторе переключить страницу (Home/Каталог/События/Номера/
  Услуги/Деталь/Инфо), убедиться: добавление/перенос/правка блока работает на КАЖДОМ типе; тема применяется
  ко всем разом; отзывы+JSON-LD на всех деталях; buy-box правится формой; home не сломан; legacy-конфиг цел.
- CI зелёный по батчу подзадач; чекпоинт с владельцем перед фазой U-D.

## 10. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` · `docs/unified-sellable-entity-ua-plan-2026-06-30.md`
(UA1-3/UA2-1/UA4-1/UA4-4a) · `docs/unified-sellable-entity-ub-plan-2026-06-30.md` (UB1-2/UB2-1) ·
`docs/storefront-onsite-editor-plan.md` (SE-1…SE-9) · `apps/tenants/siteconfig.py` · `apps/core/views.py` ·
`apps/core/context.py` · `templates/tenant/site_home.html` · `templates/storefront/detail.html` · `apps/core/seo.py`.

## §11 РЕВИЗИЯ 2026-07-02 (после закрытия U-A целиком, U-B целиком, E-7 внутр.) — АКТУАЛЬНАЯ ОЧЕРЕДЬ

> Верифицировано против кода 2026-07-02. План выше писался ДО завершения U-A/U-B — часть
> подзадач уже закрыта другими волнами. Source of truth очереди U-C — ЭТА секция.

**Закрыто предыдущими волнами (из плана U-C делать НЕ нужно):**
- **UC4-1 (отзывы)** ✅ — UA4-4a/4-4b: generic `reviews.Review` + верифиц. отзывы и рейтинг на
  всех деталях (`_entity_reviews.html`), демо засеяно, post-visit письма замкнуты (2026-07-02).
- **UC4-2 (JSON-LD)** ✅ в основной части — UA4-4b: `entity_jsonld` в `detail.html` на всех
  деталях, @type Product/Service/Event/LodgingBusiness + AutoRepair (A9) + AggregateRating.
  Остаток — доводка §Дополнений: `Offer`+`BreadcrumbList`, Event `startDate/location/offers`.
- **UC1 в части ДЕТАЛИ** ✅ — UA4-1/4-2: реестр `apps/core/detail_sections.py` (KEYS+LABELS,
  event/product/service/stay), `EVENT_/PRODUCT_DETAIL_SECTION_KEYS` уже производные от него,
  скрытие секций end-to-end, тела data-driven. Остаток UC1 — обобщение до (page_type, section)
  ВКЛЮЧАЯ home/listing/info/legal.
- **Граница buy-box** ✅ фактически — UA3-1/3-2: единый `_buybox.html` (диспатч по purchase_mode,
  двухшаговый гейт), POST-движки за формой. UC5-1 остаётся только пометкой `configurable=form`.
- **UC2-4 упрощён** — i18n-асимметрия service снята L3 (плоская база + оверлей у всех kind).

**Остаток волны U-C (актуальная очередь, порядок исполнения):**
1. **UC1-1′ ✅ (2026-07-02)** — фасад `page_types`/`page_section_keys`/`page_section_labels`/
   `page_sections(config, page_type)` в `siteconfig.py` (`PAGE_DETAIL_MODULES`). Осознанное
   отклонение: реестры (SECTIONS + detail_sections) остаются первичными, фасад — над ними
   (единый API тот же, normalize() не тронут). Golden-замки normalize (байт-в-байт,
   `test_normalize_golden` + `golden/*.json`) — постоянный гейт волны; регенерация эталонов —
   только осознанным решением. 527 passed.
2. **UC1-2′ ✅ (2026-07-02)** — реестр += `listing` (слоты каркаса U-B) / `info` / `legal`
   (fixed-order мета; конфиг-управление — UC2-3/UC3-2; AGB-ключ добавится с E-2/L5).
3. **UC1-3 ✅ (2026-07-02)** — `SECTION_ICONS`+`page_section_icons` в siteconfig;
   `page_inspector(config, page_type)` — 4 ручные сборки инспектора деталей в
   home_builder_view заменены вызовами реестра (паритет структур).
4. **UC2-1 ✅ (2026-07-02, слайсы A+B; свод save → UC2-4)** — page-scoped draft-модуль:
   решение «виртуальный фасад» (`PAGE_CONFIG_KEYS`+`apply_page_payload`, хранение плоское) —
   план-док `docs/uc2-1-page-draft-plan-2026-07-02.md`.
5. **UC2-2 ✅ (2026-07-02, слайсы 1+2; слайс 3 C-блоков — за решением владельца, план-док)** (L) — on-canvas add/move (`+`/drag) на деталь/листинг/инфо.
6. **UC2-3** (M) — инспектор-группы всех page-type (`applyPageScope` из реестра); C-блоки на деталь/инфо.
7. **UC2-4** (S, было M — упрощён L3) — единый инлайн-диспетчер, 6 эндпоинтов → тонкие алиасы (D1a).
8. **UC3-1/3-2** (M+S) — тема/микрошаблоны каскадом на все page-type (частично есть: sf-card на
   листингах с UB1-2); `hidden_on`+`width` на секциях детали/листинга.
9. **UC4-3 ✅ (2026-07-02)** — галерея Service: шим dict→[dict] (D4a, БЕЗ миграции) → `_media_gallery` на 5 kind.
10. **UC4-2-доводка ✅ (2026-07-02)** — Offer+BreadcrumbList; Event-поля startDate/location.
11. **UC5-1 ✅ (2026-07-02)** — пометка `BUYBOX_CONFIGURABLE="form"` + замок границы.
12. **E-2 правовой пакет DACH** — явный инкремент внутри волны (D3, §Дополнения ниже):
    §312j-кнопка + PAngV-ноты + AGB через `LegalDoc` (сходится с L5) + засев права в 9 китов +
    UWG «Anzeige» + фикс 404 `/entdecken`. Может идти параллельно UC2 (другие файлы).

Критический путь не изменился: UC1-1′→UC1-2′→UC1-3→UC2-1 — на нём висит остальное; UC4-3/UC4-2-
доводка/E-2 — параллельные ветки. Первый инкремент **UC1-1′**, без миграций. Риски §7 в силе
(горячая поверхность редактора, back-compat конфигов байт-в-байт, purge-safe, carry-forward).

**Втянуто из U-E (анализ 2026-07-02, ✅ ОДОБРЕНО владельцем 2026-07-02):** две ветки U-E НЕ зависят от
критпути U-C (другие файлы — `apps/promotions/*`, `_promo_card`/`promotion_detail`) и дают
видимую ценность сразу — тянем в волну U-C параллельными пакетами:
13. **Пакет «Стили скидки» (U-E2) — ✅ ЗАКРЫТ ЦЕЛИКОМ (2026-07-02, вкл. UE2-3):** UE2-1 единый `_discount_display.html` (консолидация 8
    ad-hoc дублей карточка/деталь, снапшот-паритет — наш приём `_buybox`) → UE2-2
    `Promotion.discount_style` (селектор вида: percent/strikethrough/festpreis/countdown/badge/
    surprise/ab; ⚠️ единственная миграция) → опц. UE2-3 `mystery` (через `discount_style`, без
    миграции). Клиенту: владелец сам выбирает, КАК показать скидку — сердце «канвы» без канвы.
14. **Пакет «Промо на канве» (U-E3) — ✅ ЗАКРЫТ ЦЕЛИКОМ (2026-07-02):** UE3-1 инлайн-правка `discount_percent`/`compare_at_price`/
    `ends_at` (D3a: свой view, позже мигрирует в UC2-4-диспетчер) + UE3-2 промо-фото on-canvas
    (`MODEL_PHOTO_URLS['promotion']` — единственная модель без фото-эдита; реюз
    `_handle_promo_uploads`). Закрывает несогласованность редактора — точно в духе U-C.
НЕ втягиваем: **UE1 промо-БЛОК** (потребитель UC2-1/UC2-2 — делать ПОСЛЕ движка, иначе строим
мини-хост и переделываем), **UE4 шаблоны/применение везде** (зависят от UE1+UC2-2), **UE1-4
свободная канва** (снята решением D1: slots-first). Анти-оверселл/SM/available_quantity —
read-only граница (риск №1 U-E) — действует и для втянутых пакетов.

## Дополнения по аудиту 2026-07-01 (см. master-track §7.2)
E-2 правовой пакет DACH — **явным инкрементом в U-C:** §312j-кнопка «Zahlungspflichtig bestellen»
(сейчас «Place order», `cart.html:162`) + PAngV-ноты «inkl. MwSt., zzgl. Versand»/`Lieferzeit` +
Zusatzstoffe/E-Nummern (A4) + AGB через `LegalDoc` (сходится с L5) + **засев Impressum/Datenschutz/AGB
во все 9 китов** (сейчас placeholder) + **правовое оператора портала** (A8, `/entdecken`) + UWG-лейбл
«Anzeige» вместо «Empfohlen» + фикс **404 бизнес-страницы/отзывов на главном `/entdecken`**.
UC4 JSON-LD-доводка: `Offer`+`BreadcrumbList` в `entity_ld`; Event-поля `startDate/location/offers` (A6);
`AutoRepair` @type для `jobs_vehicle` (A9). ⚠️ UC2-4 i18n-асимметрия «service — плоские строки» **снята
L3** — диспетчер инлайна упростить. Детали — `docs/audit-2026-07-01.md §3/§4`.
