# DL-11 — «Volle Reihen»: ряды плиток заполнены на всех шаблонах и ширинах

**Дата:** 2026-09-02 · **Запрос владельца (скриншот категорий aktionsmarkt, 5 плиток в
4 колонках):** «старайся, чтоб ряд был полностью заполнен… либо 4 уже делать, или 8, но
проверяй в зависимости от типа вывода, чтоб были заполнены ряды. Проверь все шаблоны и с
зумом, и измени, чтоб было красиво». Порядок работ (решение владельца 2026-09-02):
**DL-11 (выравнивание) → DL-12 (анализ композиций) → DL-13 (шесть новых дизайнов на все
страницы)**.

## 1. Диагноз (разведка 2026-09-02 + сканер стенда)

Сканер `scratchpad/orphan_scan.mjs` (Playwright, считает колонки по computed
`grid-template-columns` с учётом `col-span`, остаток последнего ряда) по aktionsmarkt на
6 ширинах (1440/1180/1024/820/640/390):

| Страница / секция | 1440–1024 | 820–640 | 390 |
|---|---|---|---|
| Главная · Kategorien (compact, 3 кол.) | 5 → **+2** | 2 кол.: 5 → **+1** | — |
| Главная · Aktionen (spotlight + сетка 3) | 3+11 → **+2** | — | — |
| Главная · Produkte (limit 8, cols4) | 8 = 2×4 ✓ | **sm = 3 кол.: 8 → +2** | 2 кол. ✓ |
| /aktionen/ группы (3 кол.) | 4 → +1 · 8 → +2 · 2 → (<N) | «Dauertiefpreis» 3 → +1 | 3 → +1 |
| /sortiment/ плитки категорий (cols4) + товары (cols3, 16 шт.) | 5 → +1 · 16 → **+1** | 3 кол.: 5 → +2 | 5 → +1 |
| deal_frisch (плитки cols4) | 5 → +1 | 3 кол.: +2 | +1 |

Системные причины (факты — file:line):

1. **Нет механизма кратности.** Лимит секции (`GRID_SECTION_LIMITS`, siteconfig.py:895) и
   колонки (`normalize_layout`, :935) нормализуются независимо (`_section_entry` :2262-2268);
   секции promotions/services/stay_rooms/team/testimonials/gallery/archetypes выводят ВСЁ без
   среза (public_views.py:173, :234, :273). Grep `nth-child|orphan` по css/html/js — 0.
2. **Планшетный шаг ломает даже «правильные» числа.** `_SM_FROM_COLS = {4:3, 5:3, 6:3, 3:2}`
   (:925): десктопные 4/5/6 колонок на 640–1023 px становятся тремя → 8 товаров = 3+3+2.
   Именно это владелец видит «с зумом» (зум браузера = меньшая CSS-ширина = другой брейкпоинт).
3. **Стили с жёсткими сетками** игнорируют раскладку: categories compact `sm:2 lg:3`
   (`_categories.html:18`), promotions spotlight `lg:grid-cols-3` (`_promotions.html:41`),
   team duo, gallery large, trust compact, usp pillars, faq twocol, process.
4. **Листинги вне движка** — ~25 хардкодов (`promotions_list.html:57,65`, `_combo_grid.html`,
   lookbook, blog_index, booking_index, related `product_detail.html:233`, `_stay_similar`).
   Размер страницы каталога 24 (public_views.py:815) кратен 2/3/4/6, но не 5.
5. Единственная смежная механика — DS-5 `balance` (центрирует неполный ряд, expert-чекбокс,
   выкл по умолчанию, без медиазапросов, app.css:627-634) и ручной комментарий в ките
   restaurant «promo_count=4 — сетка кратна 2».

## 2. Решение — три слоя

Принцип: **ряд либо полный, либо его нет.** Заполненность обеспечивается на КАЖДОМ
брейкпоинте чистым CSS (данные не знают ширину экрана), а данные демо подгоняются под
колонки, чтобы на витринах-образцах ничего не пряталось.

### 2.1 Движок: маркеры колонок + режим «хвоста» ряда

- `normalize_layout` += ключ `tail` ∈ {`""` (по умолчанию — **обрезать**), `"show"`
  (показать всё, прежнее поведение), `"fill"` (добить ряд плиткой-подсказкой)}.
  Presence-minimal: хранится только `show`/`fill` → golden целы. Приоритет режимов
  рендера как у DS-5: `scroll` > `balance` > `tail`.
- НОВЫЙ тег `{% grid_attrs site 'key' %}` (siteui) → `data-sf-cols="<base>/<sm>/<lg>"
  data-sf-tail="trim|show|fill"` — рядом с существующим `{% grid_classes %}`; строка
  Tailwind-классов **не меняется** (характеризационные замки test_layout/test_grid_controls
  целы; замок на новый тег — отдельный). Хардкоженным сеткам атрибуты ставятся руками
  (`data-sf-cols="1/2/3"` у categories compact, `2/2/3` у промо-листинга и т.д.).
- Общий хелпер `siteconfig.grid_cols_triplet(layout) -> (base, sm, lg)` — единственный
  источник чисел для тега и для аудита демо (§2.3); при `scroll`/`balance` тег отдаёт
  пустую строку (режимы несовместимы).

### 2.2 CSS: quantity queries по брейкпоинтам

Генератор `scripts/gen_fill_rows_css.py` пишет блок в `static/src/app.css` между маркерами
`/* DL-11 fill-rows: generated */ … /* /DL-11 */` (правки — только через генератор), затем
`npm run build:css`. Для каждого N ∈ 2..6 и трёх окон (`max-width:639.98px`,
`640–1023.98px`, `min-width:1024px`) — атрибутные селекторы по позиции числа в
`data-sf-cols` (`^="N/"`, `*="/N/"`, `$="/N"`):

```css
/* trim: первый элемент НЕПОЛНОГО последнего ряда и всё за ним — скрыть;
   :not(:first-child) — единственный неполный ряд (count < N) остаётся виден */
[data-sf-tail="trim"][data-sf-cols$="/4"] > :nth-child(4n+1):nth-last-child(-n+3):not(:first-child),
[data-sf-tail="trim"][data-sf-cols$="/4"] > :nth-child(4n+1):nth-last-child(-n+3):not(:first-child) ~ * { display: none; }
/* fill: плитка-подсказка (.sf-filler — всегда последний ребёнок) растягивается на остаток
   ряда; если ряд и так полный — прячется */
[data-sf-cols$="/4"] > .sf-filler:nth-child(4n+2) { grid-column: span 3; }
[data-sf-cols$="/4"] > .sf-filler:nth-child(4n+3) { grid-column: span 2; }
[data-sf-cols$="/4"] > .sf-filler:nth-child(4n+1) { display: none; }
```

Исключения (в CSS): `[data-grid].is-list` (посетительский «список» < 768 px — 1 колонка,
прятать нечего) и `[data-density]` (KAT-4: на ≥1024 колонки задаёт посетитель — правила
trim/fill пишутся ещё и по `[data-density="N"]`, а `data-sf-cols$=` для них гейтится
`:not([data-density])`). Инвариант разметки: **прямые дети сетки — только плитки**
(`:nth-child` считает и скрытые элементы) — замок на стенде + ревью каждого шаблона.

### 2.3 Где какой режим

| Поверхность | Режим | Почему |
|---|---|---|
| Секции-превью главной (categories/products/promotions-хвост/events/tours/blog/services/stay_rooms/team/testimonials/reviews/gallery) | **trim** (дефолт), в Studio — «Alle zeigen» / «Ausgleichen» | у каждой есть «Alle …» (SECTION_VIEWALL_KEYS + страницы ST-8 /team/ /galerie/ /bewertungen/) |
| Секция archetypes (ретрит-направления) | show | скрыть направление = потерять смысл секции |
| Листинги: /sortiment/ (товары, плитки категорий, подкатегории), /aktionen/ группы, /kombi/ + полоса наборов, related на детали | **fill** — `storefront/_grid_filler.html` | контент листинга прятать нельзя; плитка-подсказка = CTA (акции/Newsletter/Merkzettel/Kontakt по гейтам модулей, `apps/core/grid_filler.py::filler_for`) |
| Спотлайт/баннер акций, stats, hero-плитки | без изменений | всегда полные по построению |
| FAQ/process/usp/trust/before_after (контент-секции с фикс-сетками) | без изменений | это не плитки товара; 2 колонки FAQ с нечётным числом — норма |
| Прайс-виды (Kacheln `data-plv`) | v2 | своя сетка md/xl + кап «Zeilen» считает элементы, не ряды — отдельный инкремент |

Размер страницы каталога: 24 → `page_size = 24 if cols != 5 else 20` (кратен колонкам lg и sm).

### 2.4 Studio

В блоке настроек секции-сетки (`site_home.html:491`) вместо одинокого чекбокса
«Ausgleichen»: селект «Reihen» — *Abschneiden* (дефолт) · *Alle zeigen* · *Ausgleichen*
(= balance) · *Scrollen* (= scroll). Save (`views.py:1588`) пишет `tail` presence-minimal;
чекбоксы balance/scroll остаются в POST-контракте (замки DS-5 целы), селект лишь отдаёт те
же поля. Live-draft: атрибуты берутся с сервера при перерисовке канвы (draft-канал уже
пересобирает секции).

### 2.5 Демо-киты — «4 или 8, но по типу вывода»

Аудит статикой: `scripts/demo_rows_audit.py` печатает по каждому из 17 китов таблицу
«секция → элементов → колонки base/sm/lg → остаток», беря колонки из
`GRID_SECTION_DEFAULTS` + `kit.section_layouts` + оси сборки; тест
`test_demo_kits_rows_full` фиксирует: **на lg и sm остаток 0** (либо count < N) у всех
секций-превью всех китов. Исправления по таблице (первый проход, уточняется аудитом):

- **aktionsmarkt:** 5 → **6 категорий × 4 товара = 24** (+ «Molkerei & Eier»: Gouda,
  Butter, Eier 10er, Bergkäse; +Vollkornbrötchen в Backwaren, +Shampoo в Haushalt,
  +2 Retter-Tüten) — 6 кратно 2/3/6 (compact 3 кол., плитки cols3), 24 = ровно страница
  каталога при 2/3/4/6 колонках. Индексы `promotions_spec.product` перенумеровать
  (плоский список по порядку категорий), проверка «акция ↔ товар по названию».
- Сборки `deal_*` получают ось `section_layouts` (новая, аналог `section_styles`):
  categories `cols3` (6 плиток = 2 полных ряда, фото крупнее).
- Прочие киты — по аудиту: hotel 4 номера → `stay_rooms cols2`; restaurant 4 события →
  `events cols2`; werkstatt/handwerker 5 услуг → 6-я услуга; retreat 3 услуги → `services
  cols3`; stadtfuehrung 3 тура → `tours cols3`; testimonials 3 при cols2 → стиль
  quotes/список или 4-й отзыв. Мобильный (2 кол.) — чётные числа там, где дёшево.

## 3. Инкременты и замки

| # | Что | Замки |
|---|---|---|
| DL-11b.1 ✅ | `normalize_layout.tail` + `grid_cols_triplet` + тег `grid_attrs` + атрибуты у 13 секций и 5 листингов | presence-minimal · golden байт-в-байт · тег отдаёт триплет для cols2..6/tablet · scroll/balance → пусто |
| DL-11b.2 ✅ | генератор CSS + блок в app.css + пересборка | замок «блок в app.css совпадает с выводом генератора» |
| DL-11b.3 ✅ | `_grid_filler.html` + `grid_filler.filler_for` + вставка в 5 листингов + page_size 20 при cols5 | filler последний ребёнок · гейты модулей fail-safe (contact всегда) · паритет-замки листингов (`test_listing_parity`, `test_promotions_parity`) целы или переписаны осознанно |
| DL-11b.4 ✅ | Studio: селект «Reihen» + Save + префилл | round-trip trim/show/fill · balance/scroll как прежде |
| DL-11c ✅ | аудит-скрипт + правки китов + ось `section_layouts` у сборок | `test_demo_kits_rows_full` (17 китов) · кит aktionsmarkt 24 товара/6 категорий · акция↔товар |
| DL-11c-стенд ✅ | `orphan_scan.mjs` по aktionsmarkt (+5 сборок) + hotel/catering/friseur/bakery на 6 ширинах | «OK: неполных рядов нет» |
| DL-11d | адверсариальное ревью (после сброса лимита субагентов), доки, мерж | — |

Гейты перед пушем: `ruff check .` (весь репо), `ruff format --check .`, pytest затронутых
(tenants/promotions/catalog/core), `test_template_comments`, `scripts/i18n_quickcheck.py`
(новые msgid: «Reihen», «Abschneiden», «Alle zeigen», тексты filler), `npm run build:css`.

## 4. Вне объёма (зафиксировано)

- Kacheln-прайс (`data-plv`): кап «Zeilen» считает элементы, md/xl-сетка — отдельный инкремент.
- `balance` без медиазапросов (DS-5) — не трогаем; при выборе «Ausgleichen» trim не действует.
- Страницы /galerie/ и /team/ (последний ряд полного списка без CTA-плитки) — v2.
- Лимит для секции акций на главной (сейчас — все активные) — кандидат, требует
  golden-регенерации (прецедент DS-5 categories).
- Режим `fill` для секций главной (плитка «Alle N ansehen →») — v2, CSS уже готов.
