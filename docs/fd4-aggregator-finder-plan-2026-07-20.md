# FD-4 «Finder агрегатора» — план (2026-07-20)

ТЗ D5: «найди бизнес под задачу» на городских страницах /entdecken —
платформенная петля. Разведка (Explore, 2026-07-20): тенантский
`apps/core/finder.py` НЕ переносится напрямую (тенант-схема, display_fields,
M2M) — нужен ОТДЕЛЬНЫЙ лёгкий движок в public-схеме над денормализованными
`AggregatorListing` (title/teaser/business_type/city/category/new_price есть
в пуле). Без миграций (дерево — код-пресет: у агрегатора нет site_config).

## §1 v1 — серверные шаги (зеркало тенантского /finder/)

- НОВЫЙ `apps/aggregator/finder.py`: `PLATFORM_TREE` — 2 вопроса:
  1) «Was suchst du?» — чипы вертикалей (живые `_distinct_types()`; для events
     опц. ветка category);
  2) «Wo?» — чипы городов (`_distinct_cities()`).
  `resolve_public(answers)` — контракт как у core.finder.resolve
  ({question,step,total} | {results,fallback}); выдача = 3 БИЗНЕСА через
  существующий `listings_for(business_type, city)` + attach_ratings +
  open_status (реюз карточек _cards.html); пусто → фолбэк «сейчас популярно»
  (ending_soon/новейшие) с честной подписью.
- Вьюха `/entdecken/finder/` (urls_public; портальный дубль — по паттерну
  featured-click, опц. v1.1) — UX `?a=q.chip,…` как finder_page; шаги не
  кэшируются (query → мимо cache_public_page).
- CTA-вход: секция на `/entdecken/` index.html («Finde das passende Angebot»)
  с чипами первого вопроса → шаг 2.

## §2 UWG §5a — featured-нейтральность (главный риск)

Выдача Finder — ОРГАНИЧЕСКАЯ (сортировка рейтинг/новизна). Никакого
«Unser Vorschlag» для платных позиций: featured в тройке допустим ТОЛЬКО с
существующей меткой «★ Anzeige» (замок test_featured), середина НЕ
переприоритизируется платно. НОВЫЙ замок: средний слот без «Anzeige»-платного.

## §3 Замки

- Шаги/выдача/фолбэк (по образцу test_finder страничных тестов);
- featured-нейтральность; существующие test_featured/reconcile/search целы;
- тенантский finder (17 тестов) не тронут (движок отдельный).

## §4 Инкременты

1. finder.py + вьюха + маршрут + шаблон шагов/выдачи + тесты.
2. CTA-секция на index + докблок (ТЗ D5 ✅ — ОЧЕРЕДЬ ТЗ ИСЧЕРПАНА) + i18n.
