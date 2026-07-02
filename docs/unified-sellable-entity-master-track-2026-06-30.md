# Единый слой продаваемой сущности + универсальный редактор + унифицированный заказ + канва акций — МАСТЕР-ТРЕК — 2026-06-30

> **Статус: DRAFT на согласование** (решение владельца 2026-06-30: полный единый слой;
> доменные модели раздельные + адаптер; оформить датированным треком). Конвенция: docs до кода.
> **Контекст:** капстоун серии «рынок ↔ функционал» — `docs/market-gap-synthesis-2026-06-30.md`
> (сквозные темы T1–T10, эпики E-1…E-15) + общий аудит `archetype-completeness-audit-2026-06-30.md`
> (D1–D10). Этот трек — архитектурный носитель, который **поглощает** E-1/T3/T6 и весь
> редакторный пласт, и добавляет три новых направления: унифицированный заказ (+Kanban+склад)
> и канву акций.

## 0. Цель (одной рамкой)

Все архетипы **кроме агрегатора** имеют главную продаваемую сущность — **товар или
услугу** (в широком смысле: товар / услуга-Termin / номер / событие / заявка-Auftrag).
Привести их к **единому ядру представления**: одинаковая структура детальной, листинга,
категорий, фасетов и блоков; **отличается только ценовой/опциональный блок** (buy-box),
выбираемый по `purchase_mode`. Тогда:
1. **шаблонизатор/визуальный редактор строится один раз** и работает на всех типах
   страниц и всех блоках (правка/добавление через сайт; исключение — внутренности
   сложных движков брони);
2. **заказ тоже унифицируется** → единая Kanban-доска управления + управление остатками/склад;
3. **акции получают визуальную канву** (Canva-like) поверх того же блочного движка.

**Принцип:** доменные модели (`Product`/`Service`/`StayUnit`/`Event`/`Job`/`Reservation`)
**НЕ сливаются** — каждая *реализует протокол представления* `SellableEntity`. Вьюхи,
шаблоны, редактор, отзывы, JSON-LD, фасеты работают с **протоколом**, не со знанием модели.
Прецедент проекции уже есть — `aggregator.AggregatorListing`.

## 1. Что уже заложено (строим поверх, не с нуля)

- `apps/core/archetypes.py` — реестр `primary_item` + **`PURCHASE_MODE`**
  (`cart|booking|reserve|request`) + `PURCHASE_LABELS` + **`DETAIL_ENTITIES`**
  (сейчас только `catalog.Product`/`stays.StayUnit`/`events.Event`).
- `storefront/detail.html` — единый каркас детальной (`gallery/aside/body/buybar`),
  наследуют product/stay/event/combo.
- `apps/core/modules.py` — `ModuleSpec` со storefront-полями + `NAV_GROUPS`.
- On-canvas редактор `storefront-onsite-editor-plan.md` (SE-1…SE-5), per-page раскладки,
  инлайн-правка (цена товара, `promotion_inline_edit` title/price), реестр секций.
- KDS-доска заказов (gastro) — прообраз Kanban; `stock_quantity`+anti-oversell+
  `jobs.commit_stock` (G11) — прообраз склада.

**Не закрыто (= этот трек):** `Service`/jobs не в `DETAIL_ENTITIES`; листинги/фасеты
пер-архетипны; реестр секций детальной пер-архетипный; заказ не унифицирован; склад-
леджер (M10) отложен; канвы акций нет.

## 2. Архитектура — протокол `SellableEntity`

Контракт представления, который реализует каждая доменная модель (адаптер, не модель):

```
SellableEntity (presentation protocol):
  identity:     entity_type, id, slug, detail_url
  head:         title_i18n, subtitle, badges[]
  gallery:      images[] (FileRef), video?
  purchase:     purchase_mode (cart|booking_date|booking_slot|request|reserve),
                price_display (from/ab, Grundpreis, VAT-note), buybox_component
  body:         description_i18n, attributes[] (typed key-value/группы: specs/опции/
                amenities/program), info_sections[] (FAQ/Ablauf/что входит)
  social:       reviews (per-item, T3), rating
  extras:       extra_sections[] (waiver/accommodation/checkin/vehicle — «доп-функции»)
  taxonomy:     category, subcategory, facet_values{}
  seo:          schema_type (Product/Service/Event/AutoRepair…), jsonld()
```

- **buy-box остаётся изолированным компонентом на `purchase_mode`** (5 разных движков:
  cart+остаток / booking-по-датам+availability+тарифы / booking-по-слотам+ресурс+депозит /
  request+line-items / reserve). Унифицируем оболочку вокруг него, не сам движок.
- **Агрегатор** — отдельно (cross-tenant), но **потребляет тот же контракт** → карточки
  листинга агрегатора рендерятся единообразно как побочный плюс.

## 3. Фазы (эпики U-*) с зависимостями

### Phase U-A — Контракт + единая деталь (фундамент; поглощает E-1)
| # | Эпик | Размер | Закрывает |
|---|---|:--:|---|
| U-A1 | Протокол `SellableEntity` + расширить `DETAIL_ENTITIES` до 5 сущностей (product/service/stay/event/job) | M | T1 фундамент |
| U-A2 | Единая деталь: `Service`(A3) и job(A7/A9) через `detail.html`+адаптер | M | **E-1 деталь услуги** (A3/A7/A9) |
| U-A3 | Pluggable buy-box по `purchase_mode` (5 компонентов, единый внешний контракт) | M | основа |
| U-A4 | Единая схема **атрибутов/опций** + info-секции + **FAQ услуги** | M | D2 «описание услуг как FAQ» |

### Phase U-B — Листинг / категории / фасеты
| # | Эпик | Размер | Закрывает |
|---|---|:--:|---|
| U-B1 | Единый листинг-каркас (свести products/stay_index/event_index/service_index) | M | унификация витрины |
| U-B2 | **Facet-framework** + per-entity провайдеры (diet/amenities/date/category/price/rating) | M | T9 фасеты, A1/A2 D2, A4 |
| U-B3 | Единые категории/подкатегории/«коллекции» поверх сущностей | M | A7/A9 каталог Leistungen (D8) |

### Phase U-C — Универсальный визуальный редактор (главная мотивация)
| # | Эпик | Размер | Закрывает |
|---|---|:--:|---|
| U-C1 | **Единый реестр секций/блоков** для ВСЕХ страниц (главная/листинг/деталь/инфо/правовые), не пер-архетипно | L | реестр секций детальной (был «отложен») |
| U-C2 | On-canvas редактор на всех типах страниц (расширить SE-1…SE-5): добавить/править/переместить **любой** блок через сайт | L | «максимум правок через сайт» |
| U-C3 | Микрошаблоны/темы/устройства — раскладки/визуализации применяются ко **всем** архетипам разом | M | разнообразные шаблоны на все архетипы |
| U-C4 | Унифиц. блоки **отзывы + JSON-LD + галерея** (через адаптер) | M | **T3 отзывы per-item**, **T6 JSON-LD** |
| U-C5 | Исключения: внутренности сложных buy-box (календарь дат/слоты/multi-room) — настраиваются формой, не свободной канвой | — | граница редактора |

### Phase U-D — Унифицированный ЗАКАЗ + Kanban + склад (новое; Stage 3 поднимаем)
| # | Эпик | Размер | Закрывает |
|---|---|:--:|---|
| U-D1 | **Единая транзакционная абстракция** (проекция Order/Booking/StayBooking/Ticket/Job/Reservation) для управления и ЛК | L | унификация заказа |
| U-D2 | **Kanban-доска** управления (статус-pipeline по типам: Anfrage→Angebot→Auftrag, new→ready→picked, pending→confirmed→fulfilled) в кабинете | L | управление заказами/заявками/бронями |
| U-D3 | **Управление остатками / склад-леджер** (M10: движения/приёмки/корректировки/low-stock/инвентаризация) — поднять из отложенного Stage 3 | L | остатки «по-настоящему» |
| U-D4 | Унифиц. статусы/уведомления (repair-статус A9 K6, ready-письма, SMS-канал) | M | A9 K6, T8 |

### Phase U-E — Канва акций (Canva-like; новое)
| # | Эпик | Размер | Закрывает |
|---|---|:--:|---|
| U-E1 | **Свободная канва промо-карточки**: drag элементов (кнопки/текст/бейдж/фон), шрифты, цвета, размеры — прямо на сайте | L | визуальная настройка акции |
| U-E2 | **Виды вывода скидки** как стили (%/durchgestrichen/Festpreis/countdown/badge/surprise/«ab») | M | разнообразие отображения скидок |
| U-E3 | Прямо-на-сайте настройка акции (расширить `promotion_inline_edit`) | M | «двигая кнопки, меняя шрифты/цвета» |
| U-E4 | Шаблоны акций + применение к секциям/листингам/детальной (через блочный движок U-C) | M | переиспользование |

### Phase U-F — Сшивка с market-gap бэклогом (садится на единый слой)
Этот трек **несёт** E-1 (U-A2), T3+T6 (U-C4), весь редактор. Остальные эпики анализа
**садятся на унифицированный слой** и идут параллельно/после:
- **E-2 правовой пакет** (AGB+§312j+PAngV+засев) — как унифицированные инфо/правовые страницы (U-C1).
- **E-7 платёжный микс DACH** (PayPal/Klarna/SEPA + `Order.payment_method`) — на унифицированный заказ (U-D1).
- **E-6 языковой модуль** (L1–L4) — `I18nMixin` на stays/events ложится в адаптер (title/desc/attributes i18n).
- **E-8 SMS/WhatsApp** — в U-D4. **E-5 reuse-пачка** — естественно внутри адаптера.
- Вертикальные **E-9…E-15** (A9 retention, A4 gastro, A8 монетизация, A5/A6/A1/A2/A3) — поверх готового слоя.

## 4. Рекомендованный порядок (обновлён 2026-07-01 по `…-priority-review-2026-07-01.md`)

0. **Волна L (МУЛЬТИЯЗЫЧНОСТЬ, приоритет — зависимость U-A):** **L1→L2 ДО кода U-A** (рантайм-локали +
   кабинет «Sprachen», без миграции), **L3 ПАРАЛЛЕЛЬНО U-A** (i18n-поля Service/Stay + миграция → адаптер
   locale-clean). N локалей, не хардкод DE/EN; витрина+кабинет. План — `docs/multilanguage-wave-L-plan-2026-07-01.md`.
1. **Волна U1 (фундамент):** U-A1→U-A2 (деталь услуги, проверяет протокол) → U-A3 → U-A4.
   Малый старт = вписать `Service` в `detail.html`+`DETAIL_ENTITIES` (это и есть E-1). **UA4-4a (generic Review) —
   параллельно UA4-3 (P4).** Адаптер UA1-3 читает i18n для 5 kind (после L3).
2. **Волна U2 (витрина+редактор):** U-B1→U-B2→U-B3, затем U-C1→U-C2→U-C3→U-C4. **UB3-2 — M2M `Collection`
   (B-3), мини-разведка до UB3-1 (P5). E-2 правовой засев — явный инкремент в U-C (P3), сходится с L5.**
3. **Волна U3 (заказ):** U-D1→U-D2→U-D3→U-D4. **`Order.payment_method` в scope UD1-1 + параллельный трек
   E-7 (платёжный микс DACH: PayPal/Klarna/SEPA) во время U-D (PR-2/P2). UD3-1-схема — параллельно UD1-1 (P6).**
   SMS (UD4-1) — отложено (B-2).
4. **Волна U4 (акции):** U-E1→U-E2→U-E3→U-E4 (slots-first, B-1).
5. **Параллельно/после:** L4 (хром/письма)→L5 (правовое i18n, с E-2), E-8 SMS+WhatsApp, вертикальные E-9…E-15, L6 (URL, опц.).

> Инкрементально, **за существующим каркасом**, без big-bang: каждый эпик — отдельная
> ветка → CI зелёный → чекпоинт. Деталь/листинг — горячие поверхности, гейтить тестами.

> **Детальные план-доки по фазам (подзадачи + сравнение + пересечения, docs до кода) — СЕРИЯ ЗАКРЫТА:**
> U-A — `docs/unified-sellable-entity-ua-plan-2026-06-30.md`; U-B —
> `docs/unified-sellable-entity-ub-plan-2026-06-30.md`; U-C —
> `docs/unified-sellable-entity-uc-plan-2026-06-30.md` (реестр страниц + редактор на всех типах +
> отзывы/JSON-LD/галерея; 13 подзадач UC1-1…UC5-1); U-D —
> `docs/unified-sellable-entity-ud-plan-2026-06-30.md` (проекция `Transaction` + Kanban-доска +
> склад-леджер M10 + SMS-канал; 11 подзадач UD1-1…UD4-2); **U-E —
> `docs/unified-sellable-entity-ue-plan-2026-06-30.md`** (канва акций: промо-блок на движке U-C +
> единый `_discount_display` + расширенный inline-edit + промо-шаблоны; 11 подзадач UE1-1…UE4-2).
> U-D/U-E — несущие утверждения адверсариально верифицированы Workflow-скептиками. Все 5 фаз готовы к реализации.
> **Волна L (мультиязычность) — `docs/multilanguage-wave-L-plan-2026-07-01.md`** (L1-L6, N локалей, витрина+кабинет;
> L1-L3 до/∥ U-A). **Ревью структуры/приоритетов/гэпов — `docs/unified-sellable-entity-priority-review-2026-07-01.md`.**
> **Решения — `docs/unified-sellable-entity-decisions-2026-06-30.md`.**

## 5. Риски / границы
- **Buy-box сложных движков** (availability/слоты/даты/multi-room/line-items) остаётся
  кодом, настраивается формой/настройками — НЕ свободной канвой (U-C5). Канва правит
  презентацию вокруг и порядок/видимость блоков.
- **Схема атрибутов** должна быть гибкой (typed блоки), иначе specs товара и amenities
  номера не лягут в одну форму редактора (U-A4).
- **Склад-леджер (U-D3)** и **унифицированный заказ (U-D1)** — крупные, с миграциями;
  это подъём отложенного Stage 3 (M10/M14) — планировать как отдельную волну.
- **Канва акций (U-E)** — самый «фронтовой» эпик (drag/resize/шрифты/цвета); хранить
  layout как JSON поверх существующих промо-моделей, без слома анти-оверселла акций.
- Миграции: протокол — без миграций (адаптеры/реестр); атрибуты/заказ-проекция/склад/
  промо-canvas — с миграциями (после мержа — деплой `./scripts/deploy.sh single`).

## 6. Связанные
`docs/market-gap-synthesis-2026-06-30.md` (T1–T10/E-1…E-15) · `archetype-completeness-audit-2026-06-30.md`
(D1–D10) · `market-gap-<a1a2…a9>-2026-06-30.md` (пер-архетипные гэпы) ·
`apps/core/archetypes.py` (primary_item/PURCHASE_MODE/DETAIL_ENTITIES) ·
`m20-site-builder-plan.md` / `m20-retreat-pages-plan.md` / `storefront-onsite-editor-plan.md`
(SE-1…SE-5) / `archetype-entities-plan.md` (H0) · master-plan.md §M10/M14 (склад/маркетплейс — Stage 3).

---

## 7. Дополнения по итогам аудита 2026-07-01 («что недостаёт», привязано к очереди волн §4)

> Источник — `docs/audit-2026-07-01.md` (ре-проверка план↔факт + рынок A1–A9, адверсариально
> верифицировано против кода). Ниже — пробелы, которые НЕ должны потеряться, разложенные по
> той же очереди волн 0→4. `[остаток]` = недоделано внутри уже «закрытой» волны; `[доб.]` =
> новый пункт из рыночного анализа. Каждый пункт с уликой/размером.

### 7.0 Волна L (L1→L2 ✅ ДО U-A · L3 ✅ ∥ U-A) — остаток
- **`[остаток]` L3-ввод + демо (S/M):** per-locale инпут-виджет форм (N колонок по `active_locales`)
  отсутствует (`catalog/forms.py` — хардкод пар `de/en`; у `Service`/`StayUnit` форм i18n нет вовсе);
  мультиязычный демо-засев есть только у `pranasy` (`demo_kits.py` не пишет `name_i18n`/`description_i18n`).
- **`[остаток]` combo i18n (S):** адаптер `SellableEntity` читает i18n для 4/5 kind — `combo`
  (`catalog.Combo`) без `*_i18n`, `sellable.py:110` берёт плоские DE. Сходится с U-A.
- **`[остаток]` L4 хром/письма (M):** `locale/` = только `.gitkeep`; нет `compilemessages` в CI;
  письма — захардкоженный DE. ⚠️ Хром витрины уже частично в `{% trans %}` с **английскими** `msgid`
  при пустых `.mo` → DE-посетитель видит английский хром (`_base.html`/`stay_detail.html`).
- **`[остаток]` L5 правовое (M, миграция):** нет модели `LegalDoc` (S-2b), маршрута `/agb/`, i18n
  правового; правовое не засеяно (placeholder). **Сходится с E-2** (§7.2).
- **`[остаток]` L6 URL-локаль (L, опц.).**
- **Актуализация L-плана:** §4 L3 всё ещё говорит «бэкфилл `{de:…}`» — фактически overlay-семантика;
  §1 «хром не в `{% trans %}`» устарел (частично уже в trans).

### 7.1 Волна U-A (UA1-1 ✅) — остаток ВНУТРИ «закрытой» волны
> ⚠️ Формулировка «Волна U-A (UA1–UA4) закрыта» неточна. Решение: доделать остаток ИЛИ переписать статус.
- **`[остаток]` UA3-1 слайс 2 (L):** единый `templates/storefront/_buybox.html` с диспатчем по
  `purchase_mode` (`cart/reserve/request/booking`) — **не существует**; сделан только override
  primary-CTA (резолвер `archetypes.primary_service_action` + свап кнопок). `buybox_context` в
  `SellableEntity` — пустая заглушка.
- **`[остаток]` UA3-2 (L):** двухшаговый buy-box (`select_url`/`submit_url` в контракте + рендер
  селектор→POST, провести `stay_detail` и `service_slots`) — **не начат** (поля есть только в план-доке).
- **`[остаток]` UA4-4b AutoRepair (S):** плановый дефолт `Service→AutoRepair` для `jobs_vehicle` не
  реализован — `entity_jsonld` (`templatetags/seo.py:129`) не пробрасывает `schema_type`, услуга всегда
  `@type=Service`. `entity_ld` параметр поддерживает — правка ~1 строка тега.
- **`[остаток]` UA4-3 демо A9 (S):** rich-карточка (attributes/faq/primary_action) засеяна только у
  handwerker (A7); werkstatt (A9) — плоские кортежи (`demo_kits.py:2322`). План требовал A7+A9.
- **`[доб.]` reviews-email wiring (S/M):** движок generic-отзывов готов, но **ни одно письмо не ведёт
  на форму `/…/bewerten/`** — у события `ticket_post_event` ведёт на корень витрины, у номера
  `_review_url` на портал, у услуги письма нет. Замкнуть post-visit рассылки на generic-форму отзыва.
- **`[остаток]` тесты:** live-preview round-trip для `service_detail`/`stay_detail`
  (`test_live_preview.py` — только event); рендер-тест L3c для stays; сквозной POST инлайн-правки услуги.

### 7.2 Волна U-B → U-C — добавить/подтвердить
- **U-B `[доб.]`:** поиск по витрине `?q=`+autosuggest (A1/A2, A4, A8) — UB2; sort-оси rating/price +
  price-фасет для портала (A8) — UB2; чипы «Kostenlose Stornierung»/рейтинг на карточках номеров +
  визуальный range-picker поиска (A5) — UB1/UB2. ⚠️ Устаревшее в UC-плане: **UC2-4** держит спец-случай
  «service — плоские строки, i18n-асимметрия, fail-closed» — **снят L3** (упростить диспетчер инлайна).
- **U-C `[доб.]` E-2 правовой пакет DACH — явным инкрементом:** AGB через `LegalDoc` (сходится с L5) +
  §312j-кнопка «Zahlungspflichtig bestellen» (сейчас «Place order», `cart.html:162`) + PAngV-ноты
  «inkl. MwSt., zzgl. Versand»/`Lieferzeit` на товаре/в корзине + Zusatzstoffe/E-Nummern (A4) + засев
  Impressum/Datenschutz/AGB во все 9 китов (сейчас placeholder). Плюс **правовое ОПЕРАТОРА портала**
  (Impressum/Datenschutz/AGB на `/entdecken`, A8) + UWG-лейбл «Anzeige» вместо «Empfohlen» + фикс
  **404 бизнес-страницы/отзывов на главном `/entdecken`** (рейтинги ведут в никуда).
- **U-C4 `[доб.]` JSON-LD-доводка:** `Offer`(price/availability)+`BreadcrumbList` в `entity_ld`
  (rich-snippet с ценой для всех архетипов; `seo.py` уже отдаёт name/desc/image/rating);
  Event-поля `startDate/endDate/location/offers` (A6 → Google Event rich results);
  `AutoRepair` sitewide (A9, сходится с §7.1).

### 7.3 Волна U-D + параллельный трек E-7 — добавить
- **`[доб.]` E-7 платёжный микс DACH — ПРИОРИТЕТ №1:** `Order.payment_method` в UD1-1 + PayPal /
  Klarna Kauf-auf-Rechnung / SEPA / Vorkasse-Überweisung + `payment_method_types` в Stripe Checkout
  (`billing/connect.py:145` сейчас без них). Сквозной блокер конверсии A1/A2, A4, A5, A6, A7, A9 —
  **не покрыт ни одной волной**. Внутреннюю часть (`payment_method`+Vorkasse) заложить до/в начале U-D.
- **`[доб.]` A7/A9 финансы:** online-оплата финального счёта (сейчас только депозит на Angebot) +
  **E-Rechnung XRechnung/ZUGFeRD** (B2B must с 2025) — отдельный трек E-Invoice.
- **`[доб.]` A7 отзыв по Auftrag:** добавить kind `job` в `reviews.Review` + `has_completed_job`
  (fail-closed) + переключить письмо `job_done` с портала на форму `/bewerten/` — транзакция под U-D.
- **`[правка аудита]` A9:** repair-статус клиенту + «fertig»-письмо (K6) и HU/AU-reminder (K7)
  **уже реализованы** (`jobs/state_machine.py:29-43`, `Job.service_due_date`+beat) — из бэклога снять.
  Остаётся **serviced-vehicle история/сущность** (мультивизит) + **Reifeneinlagerung** (сезонный доход).
- SMS (E-8/UD4) — **отложен** (внешний провайдер, `external-integrations-backlog.md`).

### 7.4 Волна U-E — из аудита новых блокеров нет (канва акций покрыта планом U-E).

### 7.5 Вертикальные «недостаёт» (E-9…E-15, поверх готового слоя — вне U-A…U-E)
| Архетип | Недостающее (мой приоритет) | Размер | Куда |
|---|---|:--:|---|
| A5 Hotel | cross-type multi-room (семья); qty+лимит у upsell; кнопка самоотмены/переноса в ЛК гостя | M-L / S / S | E-12 (multi-room — stay-спец.), upsell-лимит → U-D склад |
| A6 Event | per-attendee roster (именной список + QR на каждого); `.ics` в письмо; DSGVO-purge health-данных; авто-early-bird (reuse G4 stays) | M / S / S / M | E-13 |
| A8 Portal | claim-your-business + owner-аналитика/лиды (вся воронка монетизации) | L | E-11 (отдельный A8-трек, вне U-волн) |
| A3 Termin | клиентский Umbuchung по self-service ссылке (`move()` уже атомарен); skill-matrix Service↔Resource; Pufferzeit; `.ics`/карта на подтверждении; gift-сертификат услуги | M / M / S / S / M | E-15 |
| A4 Gastro | слот предзаказа в checkout (`pickup_slot` уже в модели); Mittagstisch по расписанию; pay-at-table+Trinkgeld | M / M / L | E-10 |
| A7 Handwerker | портфолио проектов; типизир. trust-бейджи (Meister/Innung/HWK); auto-ack клиенту + SLA; e-подпись акцепта; Notdienst-флаг | M / M / S / S / S | E-9-смежное |
| A9 Werkstatt | засев WERKSTATT demo (reviews/attributes/faq/Extra); trust-бейджи (Kfz-Innung/Bosch) | S / M | E-9 |

> **Сквозной вывод аудита:** приоритет №1 после багфиксов — **E-7 платёжный микс DACH** (6 архетипов,
> вне волн). №2 — правовая тройка §312j/PAngV/AGB (частью дёшево сейчас, частью L5/U-C). Детали и % —
> `docs/audit-2026-07-01.md`.
