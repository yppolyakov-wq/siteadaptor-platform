# Execution-plan: витрина/UX + «анти-Битрикс» (Спринты A–F)

> **Назначение:** пошаговый план реализации выводов рыночного анализа
> (`docs/archetype-market-analysis.md` + отчёты `docs/market-analysis/*`). Это
> **source of truth по текущему этапу**: новые сессии идут строго по этому файлу,
> ничего не упуская. Конвенция: один инкремент = ветка/коммит → CI зелёный →
> чекпоинт → отметка статуса здесь + строка в `build-log.md`.
>
> **Статусы:** ☐ не начато · 🚧 в работе · ✅ готово (CI зелёный, в ветке/`main`).
> Дата старта плана: 2026-06-25. Ветка этапа: `claude/archetype-analysis-market-gaps-dkwo87`.

## Принципы реализации (держать в голове весь этап)
- **Эволюция JSON-секций, без новых моделей**, где возможно. Стек — HTMX/Alpine/
  Tailwind, server-rendered, НЕ SPA.
- **Гардрейлы вместо свободы:** раскладки — только пресеты (`LAYOUT_PRESETS`), цвет —
  акцент-токен, шрифты — `FONTS` (системные, без веб-шрифтов, GDPR).
- **Покрытие тестами** каждого инкремента (django-tenants: вьюхи через RequestFactory,
  Tenant через TenantFactory `auto_create_schema=False`; рендер партиалов — через
  `render_to_string`).
- **Перед коммитом с шаблонами:** `npm run build:css` (CI гейтит свежесть
  `static/css/app.css`). Раздельно `ruff check .` и `ruff format --check .`.
- **Демо:** новые блоки засевать в соответствующие киты `apps/tenants/demo_kits.py`
  (по нескольку примеров на фичу), чтобы фича была видна в showcase.
- **Завершая инкремент:** дописать строку в `docs/build-log.md`, отметить статус здесь.

---

## Спринт A — сквозные витринные блоки (дёшево, бьют по многим архетипам)

### A.1 — Блок «Leistungen & Preise» (services) для A3 ✅
**Цель:** primary-секция архетипа `booking` на главной (Friseur/Massage/Werkstatt).
**Файлы:** `apps/tenants/siteconfig.py` (SECTIONS + GRID_SECTION_DEFAULTS + TITLE/
VIEWALL keys), `apps/core/archetypes.py` (`PRIMARY_SECTION["booking"]="services"`,
`booking` в `_PRIORITY` выше `catalog`), `apps/promotions/public_views.py`
(`services_preview`), `templates/storefront/home.html` (ветка), новый
`templates/storefront/sections/_services.html`, тесты `test_services_section.py` +
`test_archetypes.py`.
**Критерии:** services в реестре (выкл по умолчанию); booking→services; рендер карточек
с ценой/длительностью + CTA «Jetzt buchen»; пустой список → пусто. ✅ тесты зелёные.
**Осталось (минор):** богатая карточка услуги (фото/«что входит») — нужна доработка
модели `Service` (поля `description`/`image`) → вынесено в A.1b (опц., размер S–M).

### A.2 — Блок отзывов на витрине: включить в киты + обогатить ✅
**Контекст:** блок `reviews` (партиал `_reviews.html`, тег `storefront_reviews`) **уже
существует** и читает SHARED `BusinessReview`. Реальный пробел — он не включён/не
засеян в friseur/werkstatt/restaurant и подача беднее ретрита (без фото/города).
**Шаги:**
- Засеять `reviews_seed` + включить секцию `reviews` в китах FRISEUR, WERKSTATT,
  RESTAURANT, PRANASY, SHOP (у hotel/retreat уже есть).
- (опц. A.2b) Обогатить `_reviews.html`: аватар-инициал/фото, город — выровнять с
  ретрит-стилем R13 (без новой модели: поля уже есть в BusinessReview? проверить).
**Файлы:** `apps/tenants/demo_kits.py`, опц. `_reviews.html`, тег `storefront_reviews`.
**Критерии:** демо friseur/werkstatt/restaurant показывают отзывы; тест на наличие
секции в ките.

### A.3 — Trust/USP-bar блок (типизированные значки) ✅
**Контекст:** секция `trust` существует, но это свободный текст «since/marks». Рынок
ждёт **типизированные значки** (платёжные иконки, «Versand ab X €», «14 Tage Widerruf»,
Meisterbetrieb/Innung).
**Шаги:**
- Ввести лёгкий блок `usp_bar` (или расширить `trust`) с набором **предустановленных
  значков-токенов** (иконка+подпись) + произвольные пары. Хранение — в `site_config`.
- Партиал `_usp_bar.html` с иконками (inline-SVG, без внешних ресурсов).
- Реестр значков (платёж/доставка/Widerruf/Meister/Bio/Regional/Familienbetrieb).
- Билдер: чекбоксы значков + порядок (как pairs).
**Файлы:** `siteconfig.py` (новая секция/нормализация значков), `home.html`, новый
`_usp_bar.html`, `site_*.html` (контролы), демо-киты.
**Критерии:** значки рендерятся из токенов; выключено по умолчанию; тест нормализации
+ рендер. Закрывает A1/A2/A4/A7/A9.

### A.4 — Лайтбокс-галерея везде (переиспользование) ✅
**Контекст:** полноэкранный лайтбокс уже есть у номеров отеля/ретрита. Перенести на
карточку товара, услуги, блюда, Referenzen.
**Шаги:** выделить общий Alpine-компонент лайтбокса в партиал/`siteui`-include;
подключить на `detail.html` (товар), `_media_gallery.html`, страницы услуг.
**Файлы:** общий партиал лайтбокса, `templates/storefront/detail.html`,
`_media_gallery.html`, `_product_card.html` (опц.).
**Критерии:** клик по фото товара → полноэкранный просмотр; нет внешних ресурсов
(GDPR); тест присутствия атрибутов компонента. Закрывает A1/A4/A5/A7.

---

## Спринт B — «анти-Битрикс» Phase 1 «Сайт не пустой» (главный рычаг)

> Детали и обоснование — `docs/market-analysis/z-anti-bitrix-builder.md` §«≤10-step
> onboarding» и §Roadmap Phase 1. Кирпичи уже есть (`sitetemplates`, `demo.load_demo`,
> `presets`) — их нужно сшить в линейный поток.

### B.1 — Демо-контент внутри мастера онбординга ✅  (S, быстрая победа)
Шаг «Beispiel-Inhalte? Ja/Nein» в `/dashboard/setup/` → `demo.load_demo(tenant)`
(идемпотентно, обратимо `clear_demo`). **Файлы:** `apps/tenants/onboarding.py`,
`apps/core/views.py::setup_view`, `templates/tenant/setup.html`.

### B.2 — Тема-пикер внутри мастера (визуальные карточки) ✅  (S)
Шаг «Stil & Farbe»: 5 шаблонов `sitetemplates.TEMPLATES` как превью-карточки +
акцент. **Файлы:** мастер + миниатюры шаблонов.

### B.3 — Загрузчик картинки в hero/баннеры (файл вместо URL) ✅  (M)
Использовать `catalog.images.save_product_image`. **Файлы:** `site_view`/builder,
форма hero, шаблон.

### B.4 — Линейный онбординг `/willkommen/` (7 шагов) ✅  (M)
Объединить signup + setup в один линейный URL; шаги — hx-swap; состояние в
`site_config["onboarding"]`. Финал — «вот твой готовый сайт». **Файлы:**
`apps/tenants/views.py`, `forms.py` (упростить signup: слаг авто), urls, шаблоны.
**Критерии всего B:** новый тенант после мастера имеет наполненный сайт (демо + тема +
контакты); путь ≤10 экранов; тесты потока (минимум: демо-загрузка из мастера, выбор
шаблона применяется).

---

## Спринт C — правовой долг L1 (Widerruf + Rechtstexte) для A1/A2

> Обоснование/срочность — `docs/market-analysis/a1a2-retail-online-shop.md` §Technical.
> Widerrufsbutton обязателен с 19.06.2026 (в силе). Риск Abmahnung для живых retail.

### C.1 — Widerrufs-Flow для покупателя ✅  (M)
Кнопка/форма отзыва заказа на витрине (по `Order`), статус `returned` уже есть → дать
потребительский флоу + письмо. **Файлы:** `apps/orders/` (views/public), шаблоны.

### C.2 — Widerrufsbelehrung für Waren (авто) ✅  (M; полный Rechtstexte-Wizard — позже)
Генерация юр-текстов из данных бизнеса; проверка DDG/TDDDG (не TMG/TTDSG). **Файлы:**
`apps/tenants/` (legal-генератор), `templates/storefront/legal.html`.

### C.3 — (опц.) PayPal / Kauf auf Rechnung ☐  (L, гейт владельца)
Минимум 1 бесплатный способ оплаты. Зависит от решения по провайдеру. **Отложить** до
решения владельца.

---

## Спринт D — «анти-Битрикс» Phase 2 «Реестр блоков» (разблокиратор)

### D.1 — Диспетчер секций render_block вместо if/elif ✅  (M)
Заменить хардкод в `home.html` на inclusion-tag с картой `BLOCK_TEMPLATES = {key:
partial}`. Рефактор без регрессии (тот же вывод). **Разблокиратор для D.2/E.***.
**Файлы:** новый templatetag, `home.html`, `siteui.py`.

### D.2 — C-блоки `text`/`image`/`image_text`/`button`/`spacer`/`embed` ☐  (L)
Множественные блоки с `id` (uuid) поверх `site_config["sections"]`. Расширить
`normalize` на `REPEATABLE_BLOCKS`. Партиалы + контролы. **Файлы:** `siteconfig.py`,
партиалы, билдер.

### D.3 — Единый builder-экран (свести 6 → 1 + Menu отдельно) ☐  (M)
UX-консолидация Site/Home/Sections/Pages в один экран. **Файлы:** `apps/core/views.py`,
`templates/tenant/site*.html`.

---

## Спринт E — «анти-Битрикс» Phase 3 «On-canvas»

### E.1 — Undo/Redo ✅  (S, быстрая победа)
Реализовано **клиентским** стеком снимков состояния редактора (карта name→value/
checked, N=20) — снимок восстанавливает поля формы и обновляет live-preview, поэтому
«Отменить» влияет и на Сохранение (не только на превью). Кнопки ↶/↷ в тулбаре превью +
Ctrl+Z / Ctrl+Shift+Z (в текстовых полях — нативная отмена). **Файлы:**
`templates/tenant/site_home.html` (JS), тест `test_home_builder_get_renders_undo_redo`.

### E.2 — Click-to-edit блока → попап настроек ✅  (M)
Клик по блоку в live-preview (`data-sf-section`) открывает плавающую карточку у превью,
в которую **переносится реальный control-row блока** (фикс-секции — `.home-block`,
C-блоки — `.cb-row[data-cb-id]`). Попап живёт ВНУТРИ `#home-form`, поэтому правки в нём
идут в live-preview/сабмит/историю (E.1) без дублирования состояния. Закрытие (✕/Esc)
возвращает строку на место (anchor-комментарий). Фолбэк — прежняя прокрутка к контролам.
**Файлы:** `templates/tenant/site_home.html`, тест `test_home_builder_get_renders_block_popup`.

### E.3 — Инсертер «+» с библиотекой блоков ✅  (M)
Зоны «+» инъектируются между блоками live-preview; клик → плавающая библиотека блоков
(`#bld-inserter`, типы из `block_types`) → выбор типа POST-ит `add_block` с новым
параметром **`add_after`** (ключ фикс-секции / id C-блока) → блок вставляется СРАЗУ
ПОСЛЕ него (не в конец), страница перерисовывается. Бэк: `home_builder_view` add_block
читает `add_after` (insert по индексу, `normalize` сохраняет порядок). **Файлы:**
`apps/core/views.py`, `templates/tenant/site_home.html`, тесты
`test_add_block_after_inserts_at_position` + `test_home_builder_get_renders_inserter`.

### E.4 — Drag-on-canvas ✅  (M)
На каждый блок live-preview инъектируется ручка ⠿ (native HTML5 DnD, без библиотек —
GDPR/no-SPA). Перетаскивание блока вычисляет before/after по Y-середине цели и через
`moveBlock` переносит соответствующий `.home-block` в редакторе к новой позиции +
перенумеровывает `order-input` → общий путь с live-preview/Сохранением/историей (E.1).
Обёртки `display:contents` не дают drag-бокс → ручка крепится к первому элементу секции
(position:relative при static). **Файлы:** `templates/tenant/site_home.html`, тест
`test_home_builder_get_renders_canvas_drag`. **Спринт E закрыт (E.1–E.4).**

---

## Спринт F — глубина по архетипам (по приоритету владельца)

> Полные списки — в отчётах `docs/market-analysis/*`. Здесь — крупные пункты; детальный
> план каждого заводим отдельным план-доком перед стартом (конвенция docs до кода).

### F-A6 Ретрит (визуальный трек, см. `retreat-archetype-plan.md` §6)
- ✅ **RV3 грид-обложки + countdown** — индекс событий в grid-режиме рендерит крупные
  карточки-обложки (фото 4:3 сверху, бейджи категории/sold-out/countdown оверлеем, мета
  снизу) вместо горизонтальных строк; urgency-пилюля «Heute/Morgen/In N Tagen» (≤14 дн)
  на гриде и в списке. Бэк: `veranstaltung_index` размечает `starts_soon`/`countdown_label`
  по календарной разнице дат. Демо: retreat/pranasy events-страница = `cols2`. Тесты
  `test_index_grid_layout_*` / `test_index_list_layout_*`.
- ✅ **RV2 agenda-timeline** — `program` (плоский список строк) рендерится как тайм-лайн
  день-за-днём: рельса слева + точки, ведущий маркер времени/дня (до тире) выделен,
  остаток — описание; строки без тире — обычным текстом. Парсер `_parse_agenda` в
  `veranstaltung_detail` (generic, любой формат). Тест `test_detail_program_renders_agenda_timeline`.
- ✅ **RT2 онлайн/Zoom-события** — поля `Event.is_online`/`online_url` (миграция
  `events/0017`); витрина показывает «🖥 Online» (детальная/индекс-бейдж), скрывает
  адрес/карту; ссылка доступа — только участнику ПОСЛЕ брони (страница подтверждения +
  письма confirmed/reminder). Форма кабинета + демо retreat (Zoom-Morgen-Meditation). Тесты
  `test_detail_online_*` / `test_index_online_*` / `test_confirmation_online_*` + demo.
- ✅ **RT1 QR-билет + Check-in** — `Ticket.checked_in_at` (миграция `events/0018`), публичный
  QR `/e/<code>/qr.svg` (→ ссылка Check-in) на странице подтверждения; кабинет
  `/dashboard/events/checkin/<code>/` (login) — гость + «Einchecken» (status→attended +
  timestamp), идемпотентно. Тесты `test_cabinet` (checkin) + `test_storefront` (QR).
- ✅ **RV1 2-шаговый чекаут** — форма брони разбита на Schritt 1 (тариф/места/проживание/
  Extras) → Schritt 2 (контакты/анкета/Voucher/Waiver) + обзор выбора; прогрессивное улучшение
  (vanilla JS, без JS — обычная форма), бэкенд не тронут. Тесты `test_storefront` (структура +
  регрессия единого POST).
- ✅ **RT3 recurring-серии** — `Event.series_id` (миграция `events/0019`) + сервис
  `create_series(source, interval, count)`: клон события (поля+JSON+M2M, билеты — нет) со
  сдвигом дат (weekly/biweekly/monthly, month-end-safe), общий series_id, atomic, потолок 52.
  Кабинет: форма «Repeat this event». Тесты `test_cabinet` (сдвиги/m2m/view).
- ✅ **RT4 блог/новости** — модель `events.BlogPost` (миграция `events/0020`): публичные
  `/blog/` (список) + `/blog/<slug>/` (деталь), кабинет CRUD (`/dashboard/events/blog/`,
  авто-слаг/обложка/публикация/удаление). Демо retreat: 2 записи + пункт меню. Тесты
  `test_blog.py`. **A6 (остаток) закрыт.**

### F-A5 Отель
- ✅ **Разбивка цены PAngV** на странице номера — Gesamtpreis сопровождается разбивкой
  «Nachtpreis × Nächte × Zimmer = Übernachtung», строкой Kurtaxe (если есть) и пометкой
  «inkl. MwSt.» (PAngV §). Бэк: `unterkunft_unit` отдаёт `quote.nightly_eur`/`accommodation_eur`.
  Тест `test_detail_shows_pangv_price_breakdown`.
- ✅ **Рейтинг на странице номера** — под названием номера ★ + среднее + число отзывов
  (тег `business_rating` из `BusinessRating`-агрегата; показывается только при наличии
  отзывов). Тест `test_detail_shows_business_rating_badge`.
- 🚧 **Визуальный календарь наличия (M–L, сильнейший рычаг)** — план-док
  `docs/hotel-availability-calendar-plan.md`. **C1 ✅** данные (`month_availability`).
  **C2 ✅** вьюха `…/kalender/` + партиал `_stay_calendar.html` (server-render месяца,
  перелистывание ‹ › vanilla-fetch, без htmx; свободные ночи кликабельны `data-date`,
  занятые/прошлые — нет). **C3 ✅** встроен в `stay_detail.html` (общий хелпер
  `_calendar_context`, начальный месяц = месяц заезда) + **выбор диапазона кликом**
  (1-й клик заезд → 2-й выезд → заполняет `von/bis` и сабмитит форму; vanilla, делегировано).
  **C4 ✅** демо: брони HOTEL уже наполняют календарь; добавлен `UnitBlock` (Wartung/Sperrung —
  «belegt» без брони) + embed сохраняет `&embed=1` в nav. **Календарь наличия (C1–C4) закрыт.**
- Дальше: полноэкранный лайтбокс (S, ⊂ A.4 ✅) · extras с фото (S–M).
- Отложено: реальные OTA-API (нужны партнёрские ключи владельца), метапоиск-фид Google FBL.

### F-A4 Gastro
- ✅ **Аллергены на карточке меню (LMIV)** — карточка товара показывает компактную строку
  аллергенов (`product.allergen_labels`), если они заданы; для retail-товаров без аллергенов
  строки нет (не зашумляет). Тесты `test_storefront_card_shows_allergens_inline` / `_no_*`.
- ✅ **Видимость Kombo/Tagesgericht** — на меню (`products.html`) вверху тизер-карточки
  комбо (до 3, имя/описание/цена/CTA) вместо одной текст-ссылки; только на 1-й странице без
  выбранной категории (в категории — прежняя ссылка). Бэк: `product_list` отдаёт `combos_teaser`.
  Тесты `test_product_list_shows_combos_teaser` / `_hidden_in_category`.
- food-hero пресет — по факту покрыт существующим фото-hero (full-bleed фото + оверлей + CTA),
  отдельный пресет не нужен.
- ✅ **Диет-иконки + фильтр меню** — поле `Product.diets` (миграция `catalog/0009`) + реестр
  `food.DIETS` (vegan/vegetarisch/glutenfrei/laktosefrei/halal/bio + иконки). Иконки на карточке
  меню; фасет-чипы на `/sortiment/?diet=…` (только встречающиеся диеты, keyset-совместимо);
  форма кабинета (чекбоксы) + демо restaurant. Тесты `test_card_shows_diet_icons` /
  `_diet_filter` / `_invalid_diet_ignored` + helper/property.
- Дальше: гибкий депозит за стол + no-show (M) · виджет брони стола + reminder (M) · слоты
  доставки + Trinkgeld для QR (M).

### F-A1/A2 Retail
- ✅ **Отзывы о товаре (только верифиц. покупатели)** — модель `ProductReview` (TENANT,
  миграция `catalog/0010`); оставить может лишь тот, у кого есть заказ с товаром по email
  (`reviews.has_purchased`, orders выкл → fail-closed). Деталь: звёзды-бейдж + секция
  «Bewertungen» (список + форма в `<details>`), POST `/sortiment/<pk>/bewerten/` (рейтлимит,
  `update_or_create`). Демо shop-кит сеет 3 отзыва. Тесты `test_product_reviews.py` (12).
- Дальше: Trust-Leiste (⊂ A.3 ✅) · галерея товара + лайтбокс (⊂ A.4 ✅) · featured-products блок (S) ·
  рейтинг на карточке каталога (S, агрегат-аннотация).

### F-A3 Termin
- ✅ **Богатая карточка услуги — фото** (`Service.image`, миграция `booking/0009`): миниатюра
  в секции «Leistungen», обложка+описание на `/termin/`, hero-фото на детали `/t/<service>/`;
  загрузка/удаление фото в кабинете `/dashboard/booking/leistungen/` (reuse `catalog.images`).
  Демо Friseur: услуги с описанием+фото. Тесты `test_services.py` (image_url/деталь/кабинет) +
  `test_services_section` (фото/регрессия).
- ✅ **Профили мастеров** (`Resource.title/bio/photo`, миграция `booking/0010`): пикер
  специалиста на `/t/<service>/` показывает аватар+должность, под ним — био выбранного мастера;
  кабинет `/dashboard/booking/ressourcen/` — форма профиля для `type=staff` (должность/био/
  фото upload+remove). Демо Friseur: Lea/Jonas с должностью/био/фото. Тесты `test_services.py`
  (photo_url/пикер) + `test_cabinet` (profile). **A3 закрыт.**

- ✅ **Богатая карточка услуги (A.1b)** — поле `Service.description` (миграция `booking/0008`):
  описание «что входит» на карточке блока услуг (line-clamp) + на странице выбора времени;
  редактирование в кабинете `/dashboard/booking/services/` (create+inline-update); демо Werkstatt
  с описаниями. Тест `test_services_section_shows_description`. Осталось A3b: фото услуги (image
  + загрузка) — отдельным инкрементом.
- Дальше: профили мастеров ↔ Resource (M) · визуальный календарь слотов (M) · SMS-Erinnerung
  (M, провайдер) · выбор мастера/skill-matrix (M) · multi-service-Buchung (L) · Gutscheine (M).

### F-A9 Werkstatt
- ✅ **Прайс-блок Festpreis** — в блоке услуг у платной услуги пометка «Festpreis», когда
  активен модуль `jobs` (Werkstatt/Handwerker; у Friseur — нет). Флаг `services_festpreis`
  в `storefront_home`. Тесты `test_services_section_shows_festpreis_for_trades` / `_no_*`.
- ✅ **Структурные данные авто (Kennzeichen/HSN-TSN)** — поля `Job.vehicle_plate/hsn/tsn`
  (миграция `jobs/0008`) + флаг витрины `site_config.jobs_vehicle`: Anfrage показывает
  структурные поля авто + schema.org `AutoRepair` JSON-LD; кабинет-деталь заявки выводит
  Kennzeichen+HSN/TSN. Демо Werkstatt: флаг on + Kostenvoranschläge со структурой. Тесты
  `test_public` (поля/LD/сохранение) + `test_seo` (schema_type) + Werkstatt-кит.
- Дальше: Repair-Status трекинг + письмо (S–M) · TÜV/Service-Reminder
  (M) · Reifeneinlagerung (M–L).

### F-A7 Handwerker
- ✅ **Отдельный Handwerker-кит** `handwerker` (Meisterbetrieb Krause — Maler/Elektro/SHK,
  generic без авто): ядро `jobs` (Angebot/Festpreis-Anfrage) + `booking`-Leistungen с
  Festpreisen и бесплатной Vor-Ort-Beratung, без shop; Referenzen-галерея, Notdienst-/
  Meister-/Innung-/Festpreis-USP-бар (⊂ A.3), отзывы, 2 демо-Angebote (Maler/Bad). Демо:
  `seed_demo_tenants --kit handwerker` (→ `handwerker.<base>`). Тест
  `test_apply_handwerker_kit_jobs_services_no_shop`.
- ✅ **before/after-слайдер** — секция `before_after` (интерактивный слайдер сравнения:
  перетаскивание мышь/тач + range для клавиатуры, vanilla JS/GDPR). Данные —
  `site_config.before_after` [{before, after, text}], якорь `#referenzen`. Handwerker-кит
  сеет 2 кейса. Тесты `test_before_after_section_renders_slider` / `_normalize_*`.
- Осталось (опц.): PLZ/Einzugsgebiet, Rückruf-Anfrage, авто-запрос отзыва.

### F-A8 Aggregator
- ✅ **Сортировка выдачи** — на городской странице дропдаун «Neueste / Name (A–Z)»
  (`?sort=`, keyset-совместимо: поля `created_at`/`business_name`; featured остаются
  закреплены сверху, `sort` переносится в «Show more»). Тесты
  `test_city_listing_sort_by_name_orders_az` / `_default_sort_is_newest`.
- ✅ **Фасетные фильтры рейтинг + «Jetzt geöffnet»** — на городской странице select минимального
  рейтинга (3/4/5★, из денорм `BusinessRating`) и чекбокс «Jetzt geöffnet» (live-статус по
  `Tenant.opening_hours_structured`). Оба сводятся к `tenant_schema__in` (keyset-пагинация цела,
  без миграции); непустые параметры проносятся в «Show more». Тесты `test_city_listing_rating_facet_*`
  / `_open_now_facet_*`.
- Дальше: автоподсказки поиска (M) · богатая карточка
  бизнеса (S–M) · карта как режим (M) · полный JSON-LD для Map Pack/AI (S–M) · self-serve Featured через
  Stripe (M, монетизация без комиссии). Развилка: Stadtgutschein/единая корзина — только
  white-label с фикс-платой (не комиссия), решение владельца.

---

## Текущий статус (обновлять каждый инкремент)
- ✅ Рыночный анализ (9 отчётов + сводка) — запушен.
- ✅ **A.1** services-блок (+ фикс видимости в демо через `_kit_sections`) — запушен.
- ✅ **A.2** отзывы на витрине в китах — запушен.
- ✅ **A.3** Trust/USP-bar блок — готов, ждёт CI/чекпоинт.
- ☐ Дальше: **A.4** (лайтбокс) → Спринт B → C → D → E → F.

**Рекомендованный порядок (подтверждён владельцем «все по очереди», 2026-06-25):**
Спринт A (A.1✅ → A.2 → A.3 → A.4) → Спринт B → Спринт C → Спринт D → Спринт E →
Спринт F (по приоритету) → **Спринт G** (анти-Битрикс кабинет/онбординг, ниже). Демо-
обогащения — параллельно по ходу.

---

## Спринт G — «настоящий анти-Битрикс»: кабинет/админка + онбординг (фидбэк владельца 2026-06-26)
> ⬇️ ИДЁТ ПОСЛЕ остатка Спринта F. Отдельный трек UX кабинета/онбординга (не витрина).
> Полный план — **`docs/anti-bitrix-admin-plan.md`**. Цель: «чтобы ребёнок собрал и вёл
> магазин». Фундамент есть (реестр `ModuleSpec`, мастер `/willkommen/`, живое превью) —
> переписываем подачу, не модели.
- ✅ **AB1** меню кабинета — группировка по задачам (Mein Geschäft / Verkaufen / Kunden & Marketing /
  Einstellungen): `modules.NAV_GROUPS` + `grouped_active_modules` → `context.nav_groups`; сайдбар
  рисует заголовки групп + «➕ Funktion hinzufügen» → «Module». Поиск сохранён. Без миграций.
  Тесты `test_modules` (группировка) + `test_cabinet_nav` (рендер групп).
- ✅ **AB2** страница «Module» v2 — 3 секции в языке задач: «Für Ihr Geschäft empfohlen»
  (core+подходящие вертикали) / «Weitere Funktionen» / «Premium» (бейдж тарифа, скрыта без
  premium-модулей); карточка несёт иконку/описание/«Geeignet für»/Recommended/Premium-бейдж.
  `modules_view` → rows/other_rows/premium_rows. Тест `test_modules` (секции). Без миграций.
- **AB3** мастер онбординга v2 — прогресс, демо-дефолты на шагах, живое превью, язык задач (M).
- **AB4** чек-лист готовности сайта на дашборде («zu X% fertig» + пункты-ссылки) (S–M).
- **AB5** связать регистрацию → мастер (M, HIGH-RISK signup/provisioning, последним, гейт владельца).
Порядок AB1→AB5; AB1–AB4 низкий риск (UI/контекст/хелперы), AB5 — отдельно с тестами.

### Остаток Спринта F (закрыть перед G)
Готово в этой сессии: A7 before/after-галерея ✅ · A8 фасетные фильтры (рейтинг/«offen jetzt») ✅ ·
A1/A2 отзывы о товаре (ProductReview, верифиц. покупатели) ✅ · A3 богатая карточка услуги (фото) ✅ ·
A3 профили мастеров ✅ · A9 структурные данные авто (Kennzeichen/HSN-TSN) ✅
(A4 диет-иконки/фильтр — уже было ✅). **A3, A9 закрыты.**
**Спринт F закрыт** (A6: RT1 QR ✅, RV1 2-шаг ✅, RT3 recurring ✅, RT4 блог ✅). **Дальше — Спринт G** (анти-Битрикс кабинет/онбординг, AB1–AB5).
Затем Спринт G. Идём по убыванию
ценности/без-миграций-первыми.
