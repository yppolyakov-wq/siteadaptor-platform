# Волна U-B — детальный план подзадач (листинг + категории + фасеты) — 2026-06-30

> Детализация фазы **U-B** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`.
> Все пути/поля — **верифицированы разведкой против кода**. Формат — как U-A: подзадачи по
> файлам/критериям/тестам + **сравнение архетипов** + **пересечения** (что унифицируем vs провайдеры).
> Реализация — после волны U-A (зависит от UA1-3 `SellableEntity` + UA2-1 product-на-каркасе).

## 0. Context

U-A унифицировал ДЕТАЛЬНУЮ страницу (`detail.html` + контракт `SellableEntity`). U-B делает то же
для **ЛИСТИНГА/категорий/фасетов**: свести 4 разрозненных листинга (товар/номер/событие/услуга) к
единому каркасу с pluggable фасет- и card-провайдерами; добавить недостающие на витрине
**поиск/сорт/фасеты** (сквозные гэпы A1/A2 D1, A4 O5, T9); обобщить категории/подкатегории.

## 1. Сравнение архетипов (текущее состояние листинга)

**Почему 4 колонки, а не 9.** Единый слой охватывает ПРОСМАТРИВАЕМЫЕ продаваемые сущности; 9
бизнес-архетипов (A1–A9) отображаются всего на **4 различные модели листинга** — несколько
архетипов делят одну сущность (дедупликация, не пропуск):

| Архетип | Модель листинга (колонка матрицы) |
|---|---|
| **A1/A2 Retail, A4 Gastro** | `catalog.Product` (товар; меню/комбо — та же catalog-семья) |
| **A3 Friseur, A7 Handwerker, A9 Werkstatt** | `booking.Service` (услуга) — одна колонка на 3 архетипа |
| **A5 Hotel** | `stays.StayUnit` (номер) |
| **A6 Event/Retreat** | `events.Event` (событие) |
| **A8 Aggregator** | **вне U-B** — cross-tenant портал, *потребляет* контракт, не входит в единый слой витрины тенанта |
| _акции_ | `promotions.Promotion` (режим `reserve`) — инлайн/на главной; визуальная настройка — фаза **U-E** (канва акций) |
| _заявка/Auftrag (A7/A9)_ | `jobs.Job` — не листинг, а транзакция → фаза **U-D** |

Реализация идёт по 4 моделям (Product/Service/Stay/Event); combo рендерится тизером в каталоге
(catalog-семья), у него отдельный `combos.html`. Матрица ниже — по этим 4 моделям.

| Аспект | Товар (catalog) | Номер (stays) | Событие (events) | Услуга (booking) |
|---|---|---|---|---|
| Вьюха | `product_list` (`apps/promotions/public_views.py:269-350`) | `unterkunft_index` (`apps/stays/public_views.py:114-180`) | `veranstaltung_index` (`apps/events/public_views.py:34-95`) | `termin_index` (`apps/booking/public_views.py:79-98`) |
| Шаблон | `products.html` | `stay_index.html` | `event_index.html` | `service_index.html` |
| Раскладка | `catalog_layout` (cols3) | `stay_index_layout` (cols3/m1) | `events_index_layout` (list) | **нет** (хардкод cols2) |
| Фасеты | категории+подкат.+diet (2) | date-search von/bis/guests | **7** (cat/level/lang/city/dur/month/teacher) | **0** |
| Карточка | **партиал** `_product_card.html` | инлайн (+ home `sections/_stay_rooms.html`) | инлайн ×2 (+ `sections/_events.html`) | инлайн (+ `sections/_services.html`) |
| Пагинация | **cursor** (24, `core/pagination.py`) | нет | нет | нет |
| `data-sf-section` | `catalog` | `stay_rooms` | `events` | **нет** |
| Категория | **Category self-FK** (подкат., `apps/catalog/models.py:14-45`) | flat (только `type`) | flat taxonomy (`apps/events/taxonomy.py`) | flat |

## 2. Пересечения (что унифицируем / провайдеры / раздельно)

- **ОБЩИЙ каркас (→ `listing.html`, по образцу `detail.html`):** заголовок (H1+intro+втор.CTA) ·
  слот фасет-бара · грид/лист-контейнер с пресетом раскладки (`normalize_layout`/`grid_class_string`,
  `siteconfig.py:209-363`) + `data-sf-section` · унифиц. карточка · пагинация (cursor,
  `core/pagination.py:1-57`) · empty-state.
- **Per-entity ПРОВАЙДЕРЫ (различия за единым интерфейсом):** набор фасетов (facet-provider);
  date-search(stays)/slot-precondition; маппинг данных карточки (через `SellableEntity`);
  QuerySet (`is_active` vs `status=published`).
- **Раздельно (НЕ унифицируем):** движки брони/анти-оверселла (даты/слоты/места/остаток);
  иерархия категорий — только у catalog.
- **Максимум переиспользования:** унифиц. карточка `_sellable_card.html` покрывает СРАЗУ и home-
  секции (`sections/_*`), и грид листинга; sort/rating-паттерны из агрегатора
  (`aggregator/views.py:76-121` `_LISTING_SORTS`/`_RATING_THRESHOLDS`) — адаптировать на per-tenant витрину.

## 3. Недостаёт на витрине (цель U-B)

Поиск по витрине (`?q=`) — есть только в агрегаторе/кабинете; user-facing **сорт**; фасеты
**цена / наличие(`Product.in_stock`) / Bio-Regional-Herkunft(`Product.origin`) / рейтинг** (рейтинг —
после UA4-4). См. сквозную тему T9.

## 4. Подзадачи U-B

| ID | Заголовок | Разм. | Мигр. | Зависит |
|---|---|:--:|:--:|---|
| **UB1-1** | Каркас `listing.html` (header/facets/grid/pagination/empty) + перевод услуг + `service_index_layout` | M | — | UA1-3 |
| **UB1-2** | Унифиц. карточка `_sellable_card.html` из контракта `SellableEntity` (услуга+номер: инлайн→партиал; покрывает и home-секции) | M | — | UB1-1 |
| **UB1-3** | Свести `products.html`/`event_index.html`/`stay_index.html` на `listing.html` | L | — | UB1-2 |
| **UB2-1** | Протокол `FacetProvider` + резолвер в `apps/core` (обобщить `_event_facets`/catalog-in-view/aggregator) | M | — | UB1-3 |
| **UB2-2** | **Поиск `?q=` на витрине** (name/description icontains, per-tenant) + **user-facing SORT** (reuse `_LISTING_SORTS`) | M | — | UB2-1 |
| **UB2-3** | Фасеты **цена / наличие / Bio-Regional-Herkunft / рейтинг** (reuse `_RATING_THRESHOLDS`) | M | — | UB2-2 (рейтинг — UA4-4) |
| **UB3-1** | Подкатегории-первыми (M20U-3) в единый каркас (catalog) | S | — | UB1-3 |
| **UB3-2** | Плоская таксономия/коллекция для услуг/номеров (по образцу `events.category`) — опц. группировка | M | **да** | UB3-1 |

### Детали (файлы/критерии/тесты)

- **UB1-1** — новый `templates/storefront/listing.html` (блоки `listing_header/listing_facets/
  listing_grid/listing_pagination/listing_empty`); `service_index.html extends listing.html`; добавить
  `service_index_layout` в `siteconfig.py` (~1244-1268) + селектор в on-canvas редакторе
  (`site_home.html:1334-1338`). *Критерии:* услуги через каркас, раскладка настраивается,
  `data-sf-section="services"`; без регресса. *Тесты:* `apps/booking/tests/test_public.py`.
- **UB1-2** — `templates/storefront/_sellable_card.html` из полей контракта (kind/image_url/title/
  price_display/badges/detail_url/purchase_label). Заменить инлайн-карточки услуги/номера (листинг +
  `sections/_services.html`/`sections/_stay_rooms.html`). *Критерии:* карточка едина для листинга и home-
  секции; CSS `sf-card` переиспользован; inline-edit/`data-sf-section` сохранены. *Тесты:*
  `apps/catalog/tests/test_storefront.py`, `apps/core/tests/test_sections_cover.py`.
- **UB1-3** — крупнейший по риску (как product_detail в UA2-1): свести 3 листинга на каркас, каждый
  отдаёт facets-слот и карточку. *Критерии:* грид/сорт/фасеты паритетны; снапшот-паритет event
  list/grid; cursor-пагинация каталога сохранена. *Тесты:* `apps/catalog/tests/test_storefront.py`,
  `apps/events/tests/test_public.py`, `apps/stays/tests/test_public.py`.
- **UB2-1** — `apps/core/facets.py`: `FacetProvider` (kind→доступные фасеты + `apply(qs, params)` +
  present-values); провайдеры catalog(category/diet)/events(taxonomy)/stays(date)/booking(none).
  *Тесты:* новый `apps/core/tests/test_facets.py`.
- **UB2-2** — `?q=` в резолвере (name/description i18n icontains) + бокс поиска в `listing.html`;
  SORT-контрол (`_LISTING_SORTS`-стиль: newest/price/rating/relevance). *Критерии:* поиск/сорт на всех
  листингах; keyset-safe. *Тесты:* `test_facets`, `test_storefront`.
- **UB2-3** — провайдеры price-range/in-stock/origin/rating; рейтинг из generic Review (UA4-4).
  *Тесты:* `test_facets`.
- **UB3-1** — перенести M20U-3 подкатегории-первыми (`public_views.py:298-303`) в каркас. *Тесты:*
  `apps/catalog/tests/test_storefront.py`.
- **UB3-2** — ⚠️ решение владельца (см. §6): группировка услуг/номеров. Рекоменд.: плоское поле
  `category` (как `events`), миграция на `StayUnit`/`Service`; НЕ self-FK на каждую модель.
  *Тесты:* модельные + `test_public`.

## 5. Риски U-B
1. **UB1-3** — свод 3 листингов = крупнейшая регрессия (event list/grid, cursor-пагинация каталога,
   date-search stays) → снапшот-паритет обязателен.
2. **Карточка ×2 контекста** (листинг + home-секция) — унификация не должна сломать home
   (`sections/_*` покрыты `test_sections_cover`).
3. **UB2-2 поиск** — v1 = icontains (per-tenant, без индекса); Postgres FTS/trigram — отдельно (§6).
4. **UB3-2** — миграция таксономии; `--create-db` локально.
5. Зависимость от UA1-3/UA2-1 — U-B стартует после них.

## 6. Открытые решения U-B — ✅ ЗАФИКСИРОВАНО (2026-07-01, см. `…-decisions-2026-06-30.md`)
1. **Группировка услуг/номеров (UB3-2):** ⚠️ **M2M-коллекция** (выбор владельца, НЕ плоское поле `category`). →
   **UB3-2 переписать: M2M `Collection`-модель** (услуги/номера ↔ коллекции) + миграция + резолвер/фасет
   группировки; размер **L**. Перед UB3-2 — мини-разведка модели `Collection` (имя/иерархия/i18n/пер-архетип охват).
2. **Бэкенд поиска (UB2-2):** ✅ **icontains v1** (реком.). Postgres FTS/trigram — отдельно позже.
3. **Охват карточки (UB1-2):** ✅ **листинг + home-секции сразу** (реком.).

## 7. Верификация U-B (end-to-end)
- `uv run ruff check .` + `ruff format --check`; `uv run pytest apps/catalog apps/booking apps/stays
  apps/events apps/core -k "listing or facet or storefront or public" --reuse-db` (при UB3-2 — `--create-db`).
- Браузер: `seed_demo_tenants --recreate`; каталог/номера/события/услуги — единый вид, работают
  поиск/сорт/фасеты, раскладка настраивается на канве; home-секции не сломаны.
- CI зелёный по батчу; чекпоинт перед фазой U-C.

## 8. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` · `docs/unified-sellable-entity-ua-plan-2026-06-30.md`
(зависимость: UA1-3 контракт, UA2-1 product-на-каркасе) · `docs/market-gap-synthesis-2026-06-30.md` (T9) ·
`apps/core/archetypes.py`, `apps/core/pagination.py`, `apps/tenants/siteconfig.py`, `apps/aggregator/views.py`.

## 9. Дополнения по аудиту 2026-07-01 (см. master-track §7.2)
В U-B добавить из рыночного анализа: **поиск по витрине `?q=`+autosuggest** (A1/A2, A4, A8 — сейчас
`q` только в кабинете/агрегаторе); **sort-оси rating/price + price-фасет** для портала (A8, `_LISTING_SORTS`
= только neueste/name); **чипы «Kostenlose Stornierung»/рейтинг на карточках номеров + визуальный
range-picker** поиска (A5 — сейчас `<date>`-инпуты). ⚠️ UC2-4-асимметрия «service — плоские строки»
**снята L3** — учесть в фасет-провайдерах/инлайне. Детали и % — `docs/audit-2026-07-01.md §3`.
