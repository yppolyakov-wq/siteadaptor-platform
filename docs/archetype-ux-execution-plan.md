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

### A.2 — Блок отзывов на витрине: включить в киты + обогатить ☐
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

### A.4 — Лайтбокс-галерея везде (переиспользование) ☐
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

### B.1 — Демо-контент внутри мастера онбординга ☐  (S, быстрая победа)
Шаг «Beispiel-Inhalte? Ja/Nein» в `/dashboard/setup/` → `demo.load_demo(tenant)`
(идемпотентно, обратимо `clear_demo`). **Файлы:** `apps/tenants/onboarding.py`,
`apps/core/views.py::setup_view`, `templates/tenant/setup.html`.

### B.2 — Тема-пикер внутри мастера (визуальные карточки) ☐  (S)
Шаг «Stil & Farbe»: 5 шаблонов `sitetemplates.TEMPLATES` как превью-карточки +
акцент. **Файлы:** мастер + миниатюры шаблонов.

### B.3 — Загрузчик картинки в hero/баннеры (файл вместо URL) ☐  (M)
Использовать `catalog.images.save_product_image`. **Файлы:** `site_view`/builder,
форма hero, шаблон.

### B.4 — Линейный онбординг `/willkommen/` (HTMX-фрагменты, ≤10 шагов) ☐  (M)
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

### C.1 — Widerrufs-Flow для покупателя ☐  (M)
Кнопка/форма отзыва заказа на витрине (по `Order`), статус `returned` уже есть → дать
потребительский флоу + письмо. **Файлы:** `apps/orders/` (views/public), шаблоны.

### C.2 — Rechtstexte-Wizard (авто Impressum/Datenschutz/AGB/Widerruf) ☐  (M)
Генерация юр-текстов из данных бизнеса; проверка DDG/TDDDG (не TMG/TTDSG). **Файлы:**
`apps/tenants/` (legal-генератор), `templates/storefront/legal.html`.

### C.3 — (опц.) PayPal / Kauf auf Rechnung ☐  (L, гейт владельца)
Минимум 1 бесплатный способ оплаты. Зависит от решения по провайдеру. **Отложить** до
решения владельца.

---

## Спринт D — «анти-Битрикс» Phase 2 «Реестр блоков» (разблокиратор)

### D.1 — Диспетчер секций `{% render_block %}` вместо if/elif ☐  (M)
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

### E.1 — Undo/Redo (стек снимков в сессии) ☐  (S, быстрая победа)
`session["site_preview_history"]` (N=20), Ctrl+Z/кнопка. **Файлы:** preview-вьюхи, JS.

### E.2 — Click-to-edit блока → попап настроек (postMessage + hx-get) ☐  (M)
`data-block` на каждый блок в превью; клик → попап формы. Зависит от D.1. **Файлы:**
preview iframe, Alpine-обёртка, партиалы форм.

### E.3 — Инсертер «+» с библиотекой блоков-миниатюр ☐  (M)
Зона «+» между блоками → библиотека (SVG-эскизы) → hx-post в draft → swap. Зависит от
D.1/D.2.

### E.4 — Drag-on-canvas (SortableJS в iframe) ☐  (M)
Перетаскивание секций на самом превью. Зависит от D.1.

---

## Спринт F — глубина по архетипам (по приоритету владельца)

> Полные списки — в отчётах `docs/market-analysis/*`. Здесь — крупные пункты; детальный
> план каждого заводим отдельным план-доком перед стартом (конвенция docs до кода).

### F-A6 Ретрит (визуальный трек, см. `retreat-archetype-plan.md` §6)
- RV2 agenda-timeline (S–M) · RV3 грид-обложки + countdown (S–M) · RV4 лайтбокс (S,
  пересекается с A.4) · RV1 2-шаговый чекаут (M) · RT1 QR-билет + check-in (M) ·
  RT2 онлайн/Zoom (S–M) · RT3 recurring-серии (M) · RT4 блог (M, общий).

### F-A5 Отель
- Визуальный календарь наличия (M–L, сильнейший рычаг) · полноэкранный лайтбокс (S,
  ⊂ A.4) · разбивка цены PAngV + рейтинг на странице номера (S–M) · extras с фото (S–M).
- Отложено: реальные OTA-API (нужны партнёрские ключи владельца), метапоиск-фид Google FBL.

### F-A4 Gastro
- Food-hero пресет (S) · видимость Kombo/Tagesgericht (S) · диет-иконки/фильтр (S–M) ·
  гибкий депозит за стол + no-show (M) · виджет брони стола + reminder (M) · слоты
  доставки + Trinkgeld для QR (M). Демо: засеять комбо/QR-столы/брони/депозит.

### F-A1/A2 Retail
- Trust-Leiste (⊂ A.3) · галерея товара + лайтбокс (⊂ A.4) · отзывы о товаре (M, нужна
  модель отзыва на Product) · featured-products блок (S).

### F-A3 Termin
- Богатая карточка услуги (A.1b) · профили мастеров ↔ Resource (M) · визуальный
  календарь слотов (M) · SMS-Erinnerung (M, провайдер) · выбор мастера/skill-matrix (M) ·
  multi-service-Buchung (L) · Gutscheine на услуги (M).

### F-A9 Werkstatt
- Прайс-блок Festpreis (⊂ A.1) · отзывы (⊂ A.2) · структурные данные авто
  (Kennzeichen/HSN-TSN) (M) · Repair-Status трекинг + письмо (S–M) · TÜV/Service-Reminder
  (M) · Reifeneinlagerung (M–L).

### F-A7 Handwerker
- **Отдельный Handwerker-кит** (Maler/Elektriker/SHK, generic без авто) (M) ·
  Referenzen/before-after-галерея (M) · Notdienst-CTA с tel (S) · Meister/Innung-значки
  (⊂ A.3) · PLZ/Einzugsgebiet (M) · Rückruf-Anfrage (S) · авто-запрос отзыва (S–M).

### F-A8 Aggregator
- Фасетные фильтры + сортировка + автоподсказки (M) · богатая карточка бизнеса (S–M) ·
  карта как режим (M) · полный JSON-LD для Map Pack/AI (S–M) · self-serve Featured через
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
Спринт F (по приоритету). Демо-обогащения — параллельно по ходу.
