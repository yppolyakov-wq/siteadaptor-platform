# DL-13 — Шесть новых дизайнов (V6–V11) на все страницы, в РАЗНЫХ композициях

**Дата:** 2026-09-02 · **Решения владельца:** канвас «Neue Design-Richtungen» (V6 Monochrom ·
V7 Pastell · V8 Retro · V9 Nobel · V10 Foto · V11 Bauhaus) — «внедряй с учётом всех страниц,
но только после выравнивания» (DL-11 ✅); анализ DL-12 утверждён: привязка §4.1 · лимит акций
на главной **9** · Grundpreis на карточке акции — в этой волне. Ультиматум DL-12: дизайны
отличаются **композицией**, а не только кожей.

## 0. Что уже есть (реюз без правок)

- Кожа = `LOOK_FAMILIES` (шрифт/типографика/хром карточек/page_bg/theme) × `ARCHETYPE_LOOK_ACCENTS`
  (15 типов, позиционные колонки) → `apply_look`, превью `?preview=1&look=`, body `data-sf-look`.
- Композиция = сборка `BUNDLES` (оси `_apply_bundle_axes`: hero_style · nav_style · nav_cta ·
  hero_widget · card_style · media_shape · catalog_layout · section_styles · section_layouts (DL-11)
  · sections_on/off · sections_order · page_presets) → `apply_bundle`, превью `?bundle=`, карточки
  на `/dashboard/design/` и в мастере, демо-переключатель «Design testen».
- Охват страниц (DL-6): `--sf-*`/`--accent`/`--accent-ink`, sf-card на второстепенных страницах,
  тёмная карта app.css, section_row на /galerie/ /team/ /ueber-uns/.
- Фирменный CSS-слой по `[data-sf-look="…"]` (DL-8b) — бейджи/цены/полосы.

## 1. Шесть Look-семейств (кожа)

| Look | Шрифт заголовков (self-hosted, OFL) | Тело | Хром карточек | page_bg | theme | Фирменные детали CSS |
|---|---|---|---|---|---|---|
| **monochrom** | Archivo 700 (uppercase, letter-spacing) | system | `line`, radius 0, без тени | #ffffff | light | **фото ч/б** (`filter: grayscale(1)`, цвет по hover), цвет только у цены/бейджа (акцент), чёрные кнопки |
| **pastell** | Quicksand 700 | system | `hairline`? нет → мягкий: radius 22, тень, card_bg #fff | #fbf6f8 | light | бейдж — белая пилюля с акцентом, чипы-таблетки пастель, цены зелёные (#2b6e52) |
| **retro** | Alfa Slab One 400 | system | `hard` (рамка 2px + жёсткая тень), radius 6 | #f6efe1 | light | бейдж — наклонный «штамп» с двойной обводкой, охра/кирпич, заголовки секций с подчёркиванием-полосой |
| **nobel** | Cormorant Garamond 600 | system (light) | `hairline` gold, radius 0 | #12100e | **dark** | золотая волосяная рамка карточек, цены serif золото, uppercase-трекинг у подписей |
| **foto** | Manrope 800 | system | без рамок, radius 22 | #ffffff | light | «стеклянные» плашки на фото (backdrop-blur), overlay-карточки (card_style overlay), белые пилюли-бейджи |
| **bauhaus** | Archivo Black 400 | system | `hard` черный 3px, radius 0, без тени | #f4f1ea | light | бейдж — круг, три чистых цвета (красный/синий/жёлтый) у плиток/бейджей по позиции, чёрные разделители |

Акценты `ARCHETYPE_LOOK_ACCENTS` += 6 колонок на каждый из 15 типов (замок «ровно 16»):
monochrom — один насыщенный цвет типа (у grocery — красный) · pastell — приглушённый тон типа ·
retro — охра/кирпич/оливка · nobel — золото/бронза/шампань · foto — тёмный нейтральный (#17181c)
или тон типа · bauhaus — красный #d62828 / синий #1d3f9e (чередование по типу).

Шрифты: `static/fonts/` += archivo-{latin,latin-ext}-700, archivo-black-{latin,latin-ext}-400,
quicksand-{latin,latin-ext}-700, alfa-slab-one-{latin,latin-ext}-400, cormorant-garamond-
{latin,latin-ext,cyrillic}-600, manrope-{latin,latin-ext,cyrillic}-800 (≈209 КБ, fonts.gstatic,
OFL; SOURCES.md) + `@font-face` в app.css + `FONTS` += archivo/archivo_black/quicksand/alfaslab/
cormorant/manrope (кириллицы нет у 4 — системный фолбэк, как в DL-1).

## 2. Композиционные примитивы (код)

| # | Примитив | Где | Детали |
|---|---|---|---|
| C1 | `hero_style = "fullscreen"` | `_hero.html` + `HERO_STYLES` + билдер (селект стиля hero) + live-draft | full-bleed фото (hero_image / heroes[0]) высотой ~86 vh (мобайл 70 vh), градиент-оверлей, заголовок/текст/CTA слева снизу, справа снизу «стеклянная» карточка первой активной акции (если модуль promotions и акция есть — иначе без карточки); без фото → фолбэк `accent` (честно, не пусто) |
| C2 | `hero_style = "bento"` | там же | мозаика 2×3 (десктоп) / 1 колонка (мобайл): [акция дня 2 ряда] [категория с фото] [часы·адрес] [Newsletter] [★ рейтинг]; источник данных — `hero_tiles`-реестр + первая акция + первая категория с фото + opening_hours + trust; плитки без данных выпадают (сетка самоуплотняется) |
| C3 | Страница акций «по времени» | `promotion_list` + `promotions_list.html` + normalize (`promo_grouping` presence-minimal: `"time"`) + панель на /promotions/ кабинета | группы: «Endet heute» · «Diese Woche» (starts_at ≤ сегодня) · «Ab <Wochentag, d.m.>» по будущим `starts_at` · «Nächste Woche» · «Dauerhaft» (без ends_at); внутри — прежний порядок; чипы/фильтры прежние; MIN_GROUP_SECTION как у тем |
| C4 | Лимит акций на главной = 9 | `GRID_SECTION_LIMITS["promotions"] = 9` + `_section_entry` (limit материализуется → **golden-регенерация осознанно**, 4 эталона) + `storefront_home` срез `[:limit]` + ссылка «Alle Aktionen» (SECTION_VIEWALL_KEYS += promotions) | spotlight/banner берут featured из того же среза; «Endet bald»-полоса — из полной выборки (как было) |
| C5 | Grundpreis на акции | `_discount_display.html` part=price (после цены), деталь акции | реюз `product.grundpreis` с промо-ценой: `pricing.grundpreis(promo_price, unit, content_amount)`; у акций без товара — нет |
| C6 | Слайдер `heroes` | `_hero.html` JS | пауза при hover/focus, стоп после клика по точке, **без автопрокрутки при `matchMedia(max-width:767px)`** и при `prefers-reduced-motion` |

## 3. Шесть сборок (композиция, `recommended_for=()` — видны всем типам)

| Сборка | Look | Композиция (DL-12) | sections_order (главная) | Стили/оси |
|---|---|---|---|---|
| `deal_monochrom` «Monochrom» | monochrom | **H3 Sortiment-first** | categories → promotions(rows) → usp_bar → trust(compact) → contact | hero off, nav minimal, nav_cta, categories cols3 square, catalog `cols4`, media_shape "" |
| `deal_pastell` «Pastell» | pastell | **H6 Bento** | hero(bento) → categories → promotions(spotlight) → testimonials → contact | nav classic, categories cols4 wide, media_shape round, page_presets info=geschichte |
| `deal_retro` «Retro» | retro | **H2 Prospekt по времени** | hero(accent) → promotions(spotlight) → categories(compact) → process → usp_bar → contact | `promo_grouping=time` (страница акций), catalog preisliste_foto, media_shape wide |
| `deal_nobel` «Nobel» | nobel | **H4 Magazin** | hero(split, фото) → about(accent) → promotions(banner) → gallery → testimonials(quotes) → contact(split) | nav centered, categories cols3 tall, page_presets info=geschichte |
| `deal_foto` «Foto» | foto | **H5 Vollbild** | hero(fullscreen) → usp_bar(plain) → promotions("" сетка overlay) → cta → contact | card_style overlay, media_shape "" |
| `deal_bauhaus` «Bauhaus» | bauhaus | **H6 Bento-geo** | hero(bento) → categories → promotions(rows) → process(row) → contact | categories cols4 square, catalog cols4, media_shape "" |

Замок DL-9 «попарно разные композиции» должен пройти для всех 11 дил-сборок.
Карточка сборки на `/dashboard/design/` и в мастере получает подпись композиции
(`composition` = ключ H1…H7 + человеческая метка) и «настроение» (P7).

## 4. Охват всех страниц (DL-6-паттерн)

Стенд Playwright: 6 сборок × страницы (главная · /sortiment/ · категория · деталь товара ·
/aktionen/ · деталь акции · /ueber-uns/ · корзина · /kontakt-якорь) × 1440/820/390 + `orphan_scan`.
Ожидаемые правки: тёмная карта для nobel на второстепенных страницах; ч/б-фильтр monochrom не
должен трогать QR (`sf-qr`) и логотипы платёжных систем; bauhaus-рамки на формах чекаута.

## 5. Инкременты (батч-режим, каждый — локальные гейты → отдельный коммит; CI на верхушке)

1. **DL-13.1** шрифты + 6 семейств + акценты 15×16 + фирменный CSS + замки test_looks (10→16).
2. **DL-13.2** примитивы C1–C6 (+ golden-регенерация для C4, замки).
3. **DL-13.3** 6 сборок + подписи композиций + демо-переключатель.
4. **DL-13.4** стенд всех страниц, фиксы, доки, мерж.

Гейты: `ruff check .`/`format --check .` целиком, pytest tenants/promotions/core-builder,
`test_template_comments`, `i18n_quickcheck` + `i18n_untranslated --check`, **`npm run build:css`
последним шагом** (урок DL-11).

## 6. Вне объёма

Левый рейл фасетов (L3), PDF-проспект, «лента только на телефоне» (P4) — отдельными
инкрементами по спросу. Демо-кит под каждый новый дизайн не заводим: все шесть — универсальные
сборки, проверяются на aktionsmarkt через превью/«Design testen».
