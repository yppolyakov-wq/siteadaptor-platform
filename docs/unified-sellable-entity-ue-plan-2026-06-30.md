# Волна U-E — детальный план подзадач (визуальная канва акций «Canva-like») — 2026-06-30

> Детализация фазы **U-E** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`
> (детализировано 2026-07-01). Все пути/поля/функции — **верифицированы разведкой + адверсариальной
> проверкой против кода** (3 Explore + Plan-агент + Workflow из 5 скептиков; сводка — §10). Формат —
> как U-A/U-B/U-C/U-D: подзадачи по файлам/критериям/тестам + партиция + пересечения + риски + решения.
> Каждая подзадача — вертикальный срез, отдельная ветка, CI-гейт. **Едет на блочном движке U-C** (реестр/
> `collect()`/`render_block`/visual-схема) + **промо-домене** (модели/`_promo_card`/`_price`/`PromotionSM`).
> **Самый фронтовой эпик; хранит layout как JSON поверх промо-моделей — без слома анти-оверселла акций.**
> Реализация — после волн U-A…U-D.

## 0. Ключевые уточнения дизайна (верифицировано; ⚠️ = поправка адверсариальной проверки)

1. **⚠️ РЕДАКТОР — СТРОГО ВЕРТИКАЛЬНЫЙ СТЕК. Свободного x/y НЕТ нигде.** Блоки рендерятся top→bottom
   из упорядоченного списка (`templates/storefront/home.html:13-24`); drag-on-canvas переупорядочивает
   по числовому `order_*` (`site_home.html ~1876-1968`, `drop` читает `clientY` лишь для before/after к
   середине цели, затем `moveBlock`+ре-нумерация `order`-инпутов), **НЕ по координатам**. Нет z-index/
   overlap/absolute-раскладки контента. Докстринг `siteconfig.py:2-6` прямо: «**сознательно НЕ
   drag-and-drop конструктор страниц — настройка блоков поверх фиксированных шаблонов**». → **Настоящая
   «свободная канва» (пиксельный drag/resize/наложение) — НОВАЯ способность, расходящаяся со всей
   архитектурой** (пер-элементная схема x/y/z/w/h, absolute-контейнер, новая drag-математика).
   **Прагматичная альтернатива — COMPOSABLE-SLOTS промо-блок** (бейдж-позиция пресетами top-left/
   top-right, оверлей-текст поверх фон-картинки, кнопка, богатые стиль-контролы: шрифты/цвета/размеры/
   радиус/тень), **переиспользующий стек + visual + `collect()`**. → **головное решение D1; рекомендуем
   slots-first, настоящую канву — опциональным поздним под-треком UE1-4 за D1.**

2. **Все 8 стилей вывода скидки УЖЕ существуют, но AD-HOC и ДУБЛИРОВАНЫ** между `_promo_card.html`
   (15-35) и `promotion_detail.html` (34-63): бейдж % / фолбэк −€ / зачёркнутая старая / жирная красная
   новая / scarcity «N left» / countdown / surprise-бейдж / valid-until. **`_price.html`** (6-9) —
   единственный уже-общий кусок (strikethrough + жирная красная новая), включается обеими точками.
   Центрального `_discount_display.html` **НЕТ** (glob пуст). «ab»/from-price есть на product/stay/event
   (`price_from`/`from_price_eur`), **но НЕ на promotions**. «Mystery»/hidden-until-reveal НЕТ (только
   surprise-ЛЕЙБЛ `is_surprise`). → **U-E2 — в основном КОНСОЛИДАЦИЯ** (общий компонент + селектор
   `discount_style`) + пара новых вариантов, **не рендер с нуля.**

3. **Секция акций — ФИКС-секция, DB-driven, НЕ C-блок.** `"promotions"` зарегистрирована в
   `BLOCK_TEMPLATES` (`siteui.py:20`), не в `CBLOCK_TEMPLATES`. Рендерит промо-карточки из queryset
   (`public_views.py:131` `Promotion.objects.filter(status="active")`, гейт `is_module_active`), не из
   `site_config` JSON. ⚠️ Обёртку `data-sf-section="promotions"` вешает **общий цикл `home.html:21-23`**,
   не сам `_promotions.html` (у него собственная обёртка `<section id="aktionen">`). **Спроектированный
   промо-БЛОК (U-E1/U-E4) — ДРУГАЯ сущность**, чем эта живая секция. Держим раздельно (§1; D2).

4. **`promotion_inline_edit` (`promotions/views.py:35-87`)** — `@login_required @require_POST`, правит
   ТОЛЬКО `title` (→ `title['de']`) + `price_override` (Decimal 0…1e6 + `bump_storefront_cache`), JSON
   `{pk,field,value}`, 204/400, строгий вайтлист (`_PROMOTION_INLINE_FIELDS={"title"}`, `:30`). Промо в
   `MODEL_EDIT_URLS` (`site_home.html:1681`); карточка — `data-edit-model="promotion" data-edit-field="title"`,
   цена — `data-price-field="price_override"`. **⚠️ ПРОБЕЛ: `MODEL_PHOTO_URLS` (`site_home.html:1684`) НЕ
   содержит `promotion`** (есть product/event/stay/service). Но ⚠️ **промо-фото УЖЕ управляется в
   кабинет-ФОРМЕ** (`_handle_promo_uploads`/`promotion_image_delete`/`primary`, `views.py:107+`) — не
   хватает только **on-canvas** фото-эдита. → **UE3-2 переиспользует существующий upload, не строит с нуля.**

5. **Блочный фундамент для переиспользования (из U-C, верифиц.):**
   - `REPEATABLE_BLOCKS = text/image/image_text/button/spacer` (`siteconfig.py:101`); санитайзеры
     `_clean_cblock_data` (105-122), `_clean_cblock` (133-147) → `{key,id,enabled,data,hidden_on,width,font}`.
   - Visual-схема `_clean_visual` radius/shadow/background/padding (464-517) + `effective_card_visual` +
     `site_defaults` + `FONTS` + `section_font_vars`; применяется CSS-переменными (`home.html:21-23`/`_base.html`).
   - `render_block` (`siteui.py:64-91`): C-блок → `CBLOCK_TEMPLATES[key]` с `block.data`; фикс-секция →
     `BLOCK_TEMPLATES[key]` с контекстом вьюхи. **Точка вставки промо-блока.**
   - `collect()` (`site_home.html:1211-1389`) → `site_preview_draft` → `home_builder_view` save (тот же
     3-сторонний round-trip, что U-C; C-блоки — по `cb_<id>` полям, 1223-1233).
   - **Прецедент «шаблонов»:** `block_templates` (SE-4a, `{id:{key,label,data}}`, `_MAX=50`,
     `normalize_block_templates` 191-206) + `page_templates` (SE-4b, `{id:{label,sections}}`, `_MAX=20`).
     → прецедент «шаблонов акций» (U-E4).

6. **Промо-домен (не трогать движки):** `Promotion.new_price/old_price/has_discount/discount_amount/
   discount_percent_display/primary_image/seconds_left/is_sold_out` — готовые свойства (`models.py:167-252`).
   `PromotionSM`/`ReservationSM`, `available_quantity` (F()-декремент лимита акции — **анти-оверселл,
   `services.py`**), revenue-хуки — **read-only для U-E**. Countdown = JS-тикер `data-countdown` ISO
   (`_base.html:329-334`). JSON-LD `offer_ld` (`seo.py:81`) в слот `structured_data` (`_base.html:26` —
   уже пуст, свободен), эмитит `promotion_detail.html:15`.

## 1. Партиция: что УНИФИЦИРУЕМ / что ПЛАГИН / что РАЗДЕЛЬНО

**УНИФИЦИРУЕМ (одна реализация):**
- **`_discount_display.html`** — единый компонент вывода скидки (поглощает дубли бейдж/−€/strikethrough/
  красная-новая/scarcity/countdown/surprise/valid-until из `_promo_card`+`promotion_detail`); вход
  `{promo, style, size}`. Переиспользует `_price.html`.
- **Промо-БЛОК** — новый C-подобный блок `promo` в U-C-движке (`REPEATABLE_BLOCKS`+`CBLOCK_TEMPLATES`+
  `_clean_cblock_data`+`render_block`); один слот/стиль-нормализатор; едет по тому же `collect()`.
- **Шаблоны акций** — через `block_templates` (реюз `normalize_block_templates`), НЕ новый реестр (D4).
- **Стиль-контролы** (шрифты/цвета/радиус/тень/паддинг) — реюз visual-схемы + `FONTS`+`section_font_vars`.
- **Инлайн-правка акции** — за тем же диспетчером/field-map (склейка с U-C UC2-4, D3).

**ПЛАГИН (пер-вариант за единым интерфейсом):** `discount_style ∈ {percent, strikethrough, festpreis,
countdown, badge, surprise, ab, mystery}` — выбирает под-рендер в `_discount_display`; badge-позиция
пресетами; слот-раскладка промо-блока (background+overlay-text+button+badge) пресетами.

**РАЗДЕЛЬНО (НЕ трогаем — код/движок/данные):**
- **Анти-оверселл / `available_quantity`-F()-декремент / `reserve` / `PromotionSM` / `ReservationSM` /
  revenue-хуки** — читаем свойства, никогда не пишем состояние/остаток.
- **DB-driven секция `_promotions.html`** (живой queryset) **vs спроектированный промо-БЛОК** (layout-JSON) —
  две сущности, не сливать (§0.3; D2).
- **`_price.html`** остаётся общим примитивом (компонент над ним, не вместо).
- **Настоящая свободная канва x/y/z** — за D1, отдельный опциональный под-трек (UE1-4), не в критпути.
- **i18n-оверлей `title`** (`title['de']`) — пишем только в `de`, как текущий inline.

## 2. Подзадачи U-E (сводка)

| ID | Фаза | Заголовок | Разм. | Мигр. | Зависит |
|---|---|---|:--:|:--:|---|
| **UE1-1** | U-E1 | Промо-БЛОК как тип C-блока: `promo` в `REPEATABLE_BLOCKS`+`CBLOCK_TEMPLATES`+`_clean_cblock_data`; слот/стиль-схема (background/overlay/button/badge-preset + visual/font); layout-JSON в `data` | L | — | UC2-1 (или мини-хост, §5) |
| **UE1-2** | U-E1 | Рендер `_block_promo.html`: absolute-composited слоты (background+overlay+badge-preset+button) на purge-safe пресетах; visual/font через CSS-vars | M | — | UE1-1 |
| **UE1-3** | U-E1 | On-canvas правка промо-блока: слот-инспектор + порядок слотов (стек/пресет, НЕ x/y); `collect()`-сериализация `cb_<id>_*`; live-preview паритет | L | — | UE1-2 |
| **UE1-4** | U-E1 | *(опц., за D1)* Настоящая свободная канва x/y/z/w/h: координатная схема + absolute-контейнер + drag/resize — **вне критпути** | L | возм. | D1=free-canvas |
| **UE2-1** | U-E2 | Единый `_discount_display.html`: извлечь 8 дублей из `_promo_card`+`promotion_detail` в один компонент `{promo,style,size}`; реюз `_price.html`; паритет | M | — | — |
| **UE2-2** | U-E2 | Поле `discount_style` (choices) + ветвление + новые варианты `festpreis`/`ab` (from-price для промо) | M | **да** | UE2-1 |
| **UE2-3** | U-E2 | *(опц.)* `mystery` hidden-until-reveal: пресет-стиль поверх surprise (скрыть цену/фото до раскрытия) — **презентация, бронь не трогаем** | S | возм. | UE2-2 |
| **UE3-1** | U-E3 | Расширить `promotion_inline_edit`: вайтлист +`discount_percent`/`compare_at_price`/`ends_at` (+ cache-bump); валидация; 204/400 | M | — | (D3) |
| **UE3-2** | U-E3 | Закрыть промо-фото-пробел: `promotion-photo-edit` view + `MODEL_PHOTO_URLS['promotion']`; `apply_gallery_op` поверх `promo.images` (реюз `_handle_promo_uploads`) | M | — | UE3-1 |
| **UE4-1** | U-E4 | Промо-шаблоны через `block_templates` (реюз `normalize_block_templates`, `key='promo'`) + вставка в другие места | M | — | UE1-3, UE2-2 |
| **UE4-2** | U-E4 | Применить промо-блок/шаблон к секциям/листингам/детали через U-C-движок (`render_block` на всех page_type); JSON-LD `offer_ld` в слот блока (только при LIVE) | M | — | UE4-1, UC2-2 |

**Старт = UE2-1** (извлечь `_discount_display`, без миграции, де-рискует и питает всё) **∥ UE1-1**
(схема промо-блока). **Миграции волны:** **UE2-2** (`Promotion.discount_style` — единственная
обязательная); возможно UE2-3 (mystery-флаг ∥ реюз `metadata`), UE1-4 (координатная схема — если
D1=free-canvas). **UE1/UE3/UE4 — без миграций** (layout-JSON в `block.data`; правки — существующие поля;
шаблоны — `block_templates`).

## 3. Подзадачи (детально: файлы/критерии/тесты)

### UE1-1 — Промо-БЛОК как тип C-блока · L · без миграции
Добавить `promo` в `REPEATABLE_BLOCKS` (`siteconfig.py:101`) + ветку в `_clean_cblock_data` (105-122),
санитизирующую слот/стиль-схему: `{background:{url|color}, overlay:{title,body,align}, button:{label,url},
badge:{preset∈top-left/top-right/…, style}, promo_pk?(D2), discount_style, visual{radius,shadow,bg,padding},
font}`. Layout — **JSON в `block.data`**, поверх промо-моделей, без схемной миграции.
`CBLOCK_TEMPLATES["promo"]` (`siteui.py:55-61`) → `_block_promo.html`.
- **Файлы:** `apps/tenants/siteconfig.py` (`REPEATABLE_BLOCKS`, `_clean_cblock_data`, при нужде
  `_clean_promo_slots`), `apps/tenants/templatetags/siteui.py` (`CBLOCK_TEMPLATES`).
- **Критерии:** `normalize()` санитайзит промо-блок (неизвестные ключи дропает; пресеты — из белого
  списка); `_MAX_CBLOCKS` соблюдён; legacy-конфиги — **байт-в-байт** (промо-ветка не трогает 5 типов);
  purge-safe (только пресет-значения).
- **Тесты:** `apps/core/tests/test_home_builder.py`, `test_siteconfig` (санитизация/паритет).

### UE1-2 — Рендер `_block_promo.html` · M · без миграции
Новый партиал `templates/storefront/sections/_block_promo.html`: композиция слотов **на absolute-позициях
ВНУТРИ карточки** (фикс-рамка блока, не свободная канва страницы): background-слой (img/color), overlay-text
(align-пресеты), badge по `badge.preset` (реюз позиций из `_promo_card` top-3/left-3), button. Стиль —
CSS-переменными visual/font. Скидку рендерит через `_discount_display` (UE2-1).
- **Файлы:** `_block_promo.html` (новый), реюз `_price.html`/`_discount_display.html`.
- **Критерии:** блок рендерится из `block.data` (D2: клон/LIVE); badge-пресеты покрывают углы; visual/font
  каскадят; purge-safe; мобайл-адаптив (overlay читаем на узком экране).
- **Тесты:** рендер-тест партиала (снапшот по пресетам), a11y-контраст (линт/ручное).

### UE1-3 — On-canvas правка промо-блока · L · без миграции (⚠️ горячее)
Слот-инспектор в билдере: background/overlay/button/badge-preset/discount_style/visual/font. Расширить
`collect()` (`site_home.html:1211-1389`): промо-блок несёт свои `cb_<id>_*`-поля — **добавить промо-поля
в список сериализуемых** (иначе выпадут из draft → «не появляется» в live-preview, ловушка комментария
1220-1222). Drag — **переупорядочивает СЛОТЫ в пресет-раскладке/стек, НЕ x/y** (D1). Round-trip
collect→`site_preview_draft`→save.
- **Файлы:** `templates/tenant/site_home.html` (`collect()`, слот-инспектор), `apps/core/views.py`
  (accept/normalize промо-полей, если вне generic C-путь).
- **Критерии:** новый промо-блок появляется в live-preview сразу; правка слота/стиля отражается под
  `?preview=1`; save персистит; home/остальное — без регрессии; анти-рекурсия `_SNAPSHOT_EXCLUDE`/`history`/
  `_draft` цела. **Мерж по diff.**
- **Тесты:** `test_home_builder`, `test_live_preview`, новый `test_promo_block_roundtrip`.

### UE1-4 — *(опц., за D1)* Настоящая свободная канва x/y/z/w/h · L · миграция возможна
**Только если D1=free-canvas.** Пер-элементная координатная схема (`x/y/z/w/h` на слот), absolute-контейнер
рендера, drag/resize-математика (новый JS-стек — НЕ `order_*`). **Явно вне критпути**; отдельным под-треком
после slots-first. ⚠️ Расходится со всей стек-архитектурой (§0.1) → a11y/мобайл/purge-safe-риски растут.
- **Критерии (если делаем):** координаты в JSON; absolute-рендер; responsive-фолбэк на стек на мобайле;
  клавиатурная доступность drag.
- **Тесты:** координатная сериализация + мобайл-фолбэк.

### UE2-1 — Единый `_discount_display.html` · M · без миграции
Извлечь 8 дублей из `_promo_card.html` (15-35) и `promotion_detail.html` (34-63) в компонент `{promo, style,
size}`: бейдж %/−€, strikethrough+красная-новая (реюз `_price`), scarcity «N left», countdown (`data-countdown`),
surprise-бейдж, valid-until. Обе точки включают компонент. **Паритет вывода — жёсткий гейт** (снапшот до/после).
- **Файлы:** `_discount_display.html` (новый), `_promo_card.html`, `promotion_detail.html` (inline→include),
  реюз `_price.html`.
- **Критерии:** карточка и деталь рендерят **идентично** текущему (снапшот-паритет); countdown работает
  (`_base.html:329`); `size` варьирует масштаб; один источник правды.
- **Тесты:** `promotions/test_public` (карточка+деталь снапшот), `test_price`.

### UE2-2 — Поле `discount_style` + новые варианты · M · **МИГРАЦИЯ**
`Promotion.discount_style = CharField(choices)` (`percent/strikethrough/festpreis/countdown/badge/surprise/
ab`), default сохраняет текущий вид. Нормализатор + `_discount_display` ветвит по стилю. Новые: **`festpreis`**
(только новая цена, без %/−€), **`ab`** (from-price для промо). Реюз в блоке (UE1-2)/карточке/детали.
- **Файлы:** `apps/promotions/models.py` (+field, +migration), `_discount_display.html`, `promotions/forms.py`
  (селектор в `PromotionForm`).
- **Критерии:** новый стиль меняет вывод во всех 3 местах; default = текущий вид (без регрессии legacy);
  миграция на TENANT-схемах (`deploy.sh single`, локально `--create-db`); **свойства цены/`has_discount`
  не тронуты** (анти-оверселл/price-логика цела).
- **Тесты:** `promotions/tests` (по стилю), `test_public`, миграция-smoke.

### UE2-3 — *(опц.)* `mystery` hidden-until-reveal · S · миграция возможна
Пресет-стиль поверх `is_surprise`: скрыть цену/картинку до клика-раскрытия (JS reveal). **Чистая презентация —
механику брони/`reserve`/остаток НЕ трогаем.** Флаг — новый bool ∥ реюз `metadata`/`discount_style='mystery'`
(без миграции).
- **Критерии:** до раскрытия скрыты цена+фото; после — обычный вид; бронь/остаток неизменны; a11y (раскрытие
  с клавиатуры).
- **Тесты:** `promotions/test_public` (reveal-состояния).

### UE3-1 — Расширить `promotion_inline_edit` · M · без миграции
Дополнить вайтлист (`promotions/views.py:30,55`): +`discount_percent` (0…100), +`compare_at_price` (Decimal≥0,
как `price_override`), +`ends_at` (ISO-парс, влияет на countdown). После правки — `bump_storefront_cache`.
Строгая валидация, 204/400. **Не расширять на поля движка** (`available_quantity`/`status` — только форма/SM).
D3: свой view или общий диспетчер (UC2-4).
- **Файлы:** `apps/promotions/views.py` (`promotion_inline_edit`), `site_home.html` (data-edit-* на новых полях).
- **Критерии:** каждое новое поле правится инлайн под `?preview=1`; невалид → 400; кэш сброшен → значение
  сразу публично; `title`/`price_override` — без регрессии; **`status`/`available_quantity` НЕ правятся** (гейт).
- **Тесты:** `promotions/test_inline_edit` (по полю + отказ невалида + анти-оверселл-поля закрыты).

### UE3-2 — Закрыть промо-фото-пробел · M · без миграции
Новый `promotion-photo-edit` view (образец `catalog`/`stays`/`events` + `apply_gallery_op` replace/add/remove
поверх `promo.images`) + `MODEL_PHOTO_URLS['promotion']` (`site_home.html:1684`). Реюз `save_product_image`/
`delete_stored_image` (импортированы `promotions/views.py:16`) и `_handle_promo_uploads`-логики.
- **Файлы:** `apps/promotions/views.py` (+view), `apps/promotions/urls.py` (+route), `site_home.html`
  (`MODEL_PHOTO_URLS`), `_promo_card`/`_block_promo` (data-photo-*).
- **Критерии:** фото акции меняется/добавляется/удаляется на канве; primary-логика (`is_primary`) цела;
  фолбэк на фото товара (`primary_image`) не сломан; multipart — вне `#home-form` (redirect+reload, как медиа U-C).
- **Тесты:** `promotions/test_photo_edit` (gallery-ops), паритет `_handle_promo_uploads`.

### UE4-1 — Промо-шаблоны через `block_templates` · M · без миграции
`normalize_block_templates` (`siteconfig.py:191-206`) гейтит `REPEATABLE_BLOCKS` → промо войдёт из UE1-1
**автоматически**. Сохранить настроенный промо-блок как шаблон (реюз SE-4a UI, `views.py:725-749`) + вставка
(инсертер `submitInsertTemplate`, `site_home.html:1545-1579`). **Реюз, НЕ новый реестр** (D4).
- **Файлы:** `apps/tenants/siteconfig.py` (проверить санитизацию промо-`data` в шаблоне), `apps/core/views.py`
  (block_templates save — уже generic), `site_home.html` (инсертер).
- **Критерии:** промо-блок сохраняется как block_template (`_MAX=50`); вставляется в другие места/страницы;
  `data` санитизируется как при `_clean_cblock`; legacy block_templates целы.
- **Тесты:** `test_home_builder` (block_templates для `key='promo'`), `test_siteconfig`.

### UE4-2 — Применить к секциям/листингам/детали + JSON-LD · M · без миграции
Промо-блок доступен как C-блок на всех page_type через U-C-инсертер (`UC2-2` on-canvas add на деталь/листинг/
инфо). Спроектированный блок эмитит `offer_ld` (`seo.py:81`) в слот `structured_data` (`_base.html:26`) —
**только если блок несёт LIVE-промо (D2)**. Если D2=клон — JSON-LD только у DB-driven секции/детали (иначе
фантом-оффер).
- **Файлы:** `_block_promo.html` (структур-данные условно), реюз `render_block` (`siteui.py`), зависит от `UC2-2`.
- **Критерии:** промо-блок вставляется на деталь/листинг/инфо (если U-C готов); валидный `offer_ld` только
  при LIVE; нет дубля/фантом-оффера при клоне; purge-safe.
- **Тесты:** `promotions/test_seo` (offer_ld live vs клон), `test_preview_pages`.

## 4. Последовательность (критический путь)

```
UE2-1 ──────────────── UE2-2 ── UE2-3(опц.)
   │                      │
UE1-1 → UE1-2 → UE1-3 ────┴── UE4-1 → UE4-2
   └───────────── UE1-4 (опц., за D1, ВНЕ критпути)
UE3-1 → UE3-2            (параллельная ветка — инлайн-правка/фото)
```
Критпуть: **`UE2-1 → UE1-2 → UE1-3 → UE4-1 → UE4-2`** (общий компонент скидки → рендер блока → on-canvas →
шаблоны → применение везде). **`UE1-1`** параллелен `UE2-1`. **`UE3-*`** — независимая ветка. **`UE1-4`/`UE2-3`** —
опциональные, вне критпути. **Старт — `UE2-1`** (де-рискует консолидацией без миграции) **∥ `UE1-1`** (схема блока).

## 5. Пересечения с U-C / U-D / U-A / U-B
- **U-C — несущее пересечение.** U-E **едет на U-C-движке**: `render_block`/`CBLOCK_TEMPLATES`/`collect()`/
  visual-схема/`block_templates`/инсертер. Промо-блок = ещё один тип C-блока. **Если U-C слипает (UC2-1/UC2-2
  не готовы), U-E несёт МИНИ-ХОСТ сам**: промо-блок регистрируется в home-only C-блок-пути (уже существует),
  расширение на не-home (UE4-2) ждёт `UC2-2`. Инлайн-правка (UE3-1) **сходится с UC2-4** — D3.
- **U-D — практически нет.** U-D правит транзакции/Kanban/склад в **кабинете**; U-E — презентацию акции на
  **витрине**. Разные поверхности/файлы. Общая граница — **не трогать `PromotionSM`/`available_quantity`/revenue**.
- **U-A — идеи цены, не деталь.** Промо **НЕ `SellableEntity`-деталь** (свой `promotion_detail`/`reserve`),
  но делит `_price`/discount/`price_from`(`ab`). UE2-2 `ab` — паритет product/stay на промо-свойствах.
- **U-B — нет прямого** (фасеты/листинг не про акции); косвенно discount-идеи общие.

## 6. Риски U-E
1. **⚠️ НЕ сломать анти-оверселл акций.** `available_quantity`-F()-декремент (`services.py`), `PromotionSM`/
   `ReservationSM`, revenue-хуки — **read-only**. U-E пишет только презентацию (`block.data`, `title['de']`,
   `price_override`/`discount_percent`/`compare_at_price`/`ends_at`, `images`). Гейт: инлайн-вайтлист НЕ содержит
   `status`/`available_quantity`; параллельные анти-оверселл-тесты промо остаются зелёными.
2. **Свободная канва vs стек (D1).** Настоящий x/y расходится со всей стек-архитектурой (§0.1) → a11y/мобайл/
   purge-safe-риски. **Рекомендация: slots-first**, x/y — опц. UE1-4 вне критпути.
3. **Purge-safe Tailwind.** Промо-блок/бейдж-пресеты эмитят **только статические утилиты/inline-CSS-переменные**,
   никогда динамические классы (purge вырежет; уже кусалось `siteconfig.py:~294`; `_promotions.html:20` держит
   `<span class="hidden grid-cols-1 grid-cols-2">` как purge-guard).
4. **3-сторонний `collect()`/draft/save — горячий.** Промо-блок обязан быть во всех трёх (иначе молча теряется,
   комментарий `site_home.html:1220-1222`). UE1-3 — гейт паритетом round-trip, мерж по diff.
5. **i18n `title` как JSON `de`.** Инлайн пишет только `title['de']` — не портить i18n-словарь (fail-closed,
   как текущий `:79-86`).
6. **LIVE vs клон в блоке (D2).** Клон-цена → риск **устаревшей цены**; LIVE (`promo_pk`) → риск фантома при
   удалённой/завершённой акции (фолбэк — скрыть блок). D2 фиксирует; JSON-LD (UE4-2) — **только при LIVE**.
7. **A11y/мобайл overlay.** Overlay поверх фон-картинки — контраст/читаемость на узком экране; badge-пресеты не
   перекрывают текст. Гейт — контраст-линт + мобайл-снапшот.
8. **Миграция `discount_style` (UE2-2).** Единственная обязательная — default сохраняет вид legacy-акций;
   TENANT-схемы (`deploy.sh single`, локально `--create-db`).

## 7. Открытые решения U-E — ✅ ЗАФИКСИРОВАНО (2026-07-01, см. `…-decisions-2026-06-30.md`)
- **D1 (головное) — канва:** ✅ **(a) composable-slots** (B-1; slots-first). **UE1-4 (свободная канва x/y) — снят/отложен.**
- **D2 — данные промо-блока:** ✅ **(a) LIVE (`promo_pk`) с fail-safe скрытием** (C-8; JSON-LD только при LIVE).
- **D3 — расширение `promotion_inline_edit`:** ✅ **(a) свой view сейчас** (+`discount_percent`/`compare_at_price`/`ends_at`
  + промо-фото-edit), мигрирует в общий диспетчер `sellable-inline-edit` (UC2-4/C-1) позже. **НЕ добавлять `status`/`available_quantity`**.
- **D4 — промо-шаблоны:** ✅ **(a) через `block_templates` (`key='promo'`)** (C-9; реюз, 0 нового реестра).

## 8. Верификация U-E (end-to-end)
- `uv run ruff check .` + `ruff format --check`; `uv run pytest apps/promotions apps/tenants apps/core -k "promo
  or discount or inline or block or home_builder or live_preview or seo or photo" --reuse-db` (UE2-2 — `--create-db`).
- **Обязательно:** параллельный анти-оверселл-тест акций (`available_quantity`-декремент, `TransactionTestCase`)
  **зелёный** после UE2/UE3.
- Браузер: `seed_demo_tenants --recreate`; добавить промо-блок, подвигать слоты/сменить стиль скидки/шрифты/
  цвета/бейдж-позицию live; сохранить промо-шаблон и вставить в другую секцию/деталь; инлайн-править
  `discount_percent`/`ends_at`/фото акции на канве; проверить: цена/остаток/countdown корректны, home не сломан,
  legacy-акции как раньше, JSON-LD валиден только у LIVE.
- CI зелёный по батчу; чекпоинт с владельцем (D1/D2/D3/D4) — **D1 блокирует объём UE1-\***.

## 9. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` (U-E §3, §5) · `docs/unified-sellable-entity-uc-plan-2026-06-30.md`
(реестр/`collect()`/`render_block`/block_templates — несущее пересечение) · `docs/unified-sellable-entity-ud-plan-2026-06-30.md`
(граница: не трогать `PromotionSM`/revenue) · `docs/storefront-onsite-editor-plan.md` (SE-3a/SE-4a visual/шаблоны) ·
`docs/references/patterns/anti-oversell.md` · `apps/promotions/models.py` · `apps/promotions/views.py`
(`promotion_inline_edit`) · `apps/tenants/siteconfig.py` (`REPEATABLE_BLOCKS`/`_clean_cblock_data`/`_clean_visual`/
`block_templates`) · `apps/tenants/templatetags/siteui.py` (`render_block`/`CBLOCK_TEMPLATES`) · `templates/tenant/site_home.html`
(`collect()`/`MODEL_EDIT_URLS`/`MODEL_PHOTO_URLS`) · `templates/storefront/_promo_card.html` / `promotion_detail.html` /
`_price.html` · `apps/core/seo.py` (`offer_ld`).

## 10. Верификация утверждений (адверсариальная проверка против кода, 2026-07-01)
Workflow из 5 скептиков (refute-by-default) проверил несущие технические утверждения плана:

| Утверждение | Вердикт | Что уточнено (вложено в план) |
|---|---|---|
| Всё — вертикальный стек, x/y-drag нет нигде | **confirmed** | Докстринг `siteconfig.py:2-6`: «**сознательно НЕ drag-and-drop конструктор**». `drop` читает `clientY` лишь для before/after; редакторные `absolute`/`z-index` — только хром, не контент. → free-canvas U-E1 = новая способность (D1). |
| 8 стилей скидки есть, ad-hoc/дублируются | **confirmed** | Только `_price.html` общий; центрального `_discount_display.html` нет (glob пуст); «ab»/mystery на акциях нет. → U-E2 = консолидация + селектор. |
| Акции — фикс-секция; `inline_edit` только title+price; промо-фото-эдита нет | **partial** | Фикс-секция/DB-driven/вайтлист ✅. ⚠️ `data-sf-section` вешает **общий цикл `home.html:21-23`**, не сам `_promotions.html` (`<section id="aktionen">`). ⚠️ Промо-фото **УЖЕ есть в кабинет-форме** (`_handle_promo_uploads`) → UE3-2 переиспользует, не строит с нуля. |
| block/page-templates (SE-4a/b) — прецедент промо-шаблонов | **confirmed** | ✅ → U-E4 реюзит `block_templates` (D4=a). |
| У `Promotion` есть все нужные поля/свойства | **confirmed** | ✅ (title/description i18n, discount_percent, price_override, compare_at_price, images, available_quantity, show_countdown, strikethrough_old_price, is_surprise, ends_at + computed). |
