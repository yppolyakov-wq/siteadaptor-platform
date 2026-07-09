# S6 — реальные архетипы через миграцию (план, 2026-07-09)

Продолжение программы упрощения кабинета «анти-Битрикс v2». S1–S5 закрыты и в `main`
(S5 = `db412ed`). Источник ТЗ — `docs/admin-simplification-handoff-2026-07-08.md §4` +
`docs/admin-simplification-exec-plan-2026-07-08.md §S6`. Решение владельца: добавить
`friseur/handwerker/werkstatt/events` к текущим 10 типам (НЕ заменять).

## Разбивка (снижение риска на миграции SHARED-модели)
- **S6a** (этот батч, ⚠️ миграция → деплой): `Tenant.BUSINESS_TYPES += 4` + миграция
  `tenants/0024` (AlterField choices) + проводка `recommended_for`/`suited_for` (пресеты
  модулей на архетип) + маппинг демо-китов (`business_type` вместо `"other"`) + тесты.
  Делает архетипы «настоящими»: выбираемы в онбординге/мастере, дают осмысленный
  стартовый набор модулей, демо помечены типом.
- **S6b** (следующий батч, БЕЗ миграции): в Простом режиме (S5) прятать нерелевантные
  ХАБЫ по `business_type` (Friseur без Sortiment/Lager; Hotel без корзины). Поверх
  `recommended_for` + `is_simple`. Отдельно — трогает механику скрытия хабов (catalog —
  core, гейтить сложнее).

## Пресеты модулей (S6a) — что ВКЛ по умолчанию на новый архетип
Core всегда: dashboard, board, catalog, settings, billing. Ниже — `recommended_for`
(default-ON, влияет на `default_disabled_for`) и `suited_for` (не вкл, только подсказка
«geeignet für» + без предупреждения при ручном включении).

| Модуль | friseur | handwerker | werkstatt | events(bt) |
|---|---|---|---|---|
| booking (Termin) | **rec** | suited | **rec** | — |
| jobs (Angebote) | — | **rec** | **rec** | — |
| events (Tickets) | — | — | — | **rec** |
| promotions | **rec** | suited | suited | **rec** |
| loyalty | **rec** | — | — | — |
| orders | suited | — | suited | — |
| crm | suited | suited | suited | suited |
| reviews | **rec** | **rec** | **rec** | **rec** |
| gift | **rec** | **rec** | **rec** | **rec** |
| blog | **rec** | **rec** | **rec** | **rec** |
| inbox | **rec** | **rec** | **rec** | **rec** |
| customer_account | **rec** | **rec** | **rec** | **rec** |

Primary-товар витрины (`archetypes.PRIMARY_SECTION`/`_PRIORITY`) выводится по активному
модулю, НЕ по business_type → работает автоматически: friseur→services (booking),
werkstatt→services (booking выше jobs в `_PRIORITY`), events→events. ⚠️ handwerker: jobs
НЕ в `_PRIORITY` → primary падает на catalog (core). Пре-существующий нюанс (сегодня
handwerker = «other» ведёт себя так же); поднять jobs в реестр архетипов — отдельный
follow-up (риск для существующих «other»+jobs), в S6a НЕ трогаем.

## Замки (уже в дереве) — держать зелёными
- `test_blog.py:116` — `blog.recommended_for == ВСЕ business_types` → добавить 4 в blog. ✓
- `test_modules.py::test_suited_label` — `promotions == "Für alle Geschäftstypen"` →
  promotions должен покрыть все 14 (rec friseur/events + suited handwerker/werkstatt). ✓
- `test_default_disabled_for_vertical` — параметризован ТОЛЬКО существующими типами →
  правки затрагивают лишь новые типы, существующие пресеты не меняются. ✓
- jobs: `recommended_for=(handwerker,werkstatt)` + `suited_for=(restaurant,cafe,other)`
  (сохранить catering-Anfrage у RESTAURANT/PRANASY-демо без предупреждения). suited_for НЕ
  влияет на `default_disabled_for` (тот читает только recommended) → jobs остаётся выкл по
  умолчанию у существующих. ✓

## Новые тесты (S6a)
- 4 новых типа присутствуют в `Tenant.BUSINESS_TYPES`.
- `default_disabled_for("friseur")` НЕ содержит booking (primary вкл); handwerker/werkstatt
  НЕ содержат jobs; events НЕ содержит events-модуль.
- Демо-киты FRISEUR/WERKSTATT/HANDWERKER/RETREAT → business_type = новый тип.
- Миграция `0024` применяется (django-tenants: SHARED/public).

## Гейт (ТЗ §5)
`uv run pytest apps/core apps/tenants apps/events -p no:cacheprovider --reuse-db --create-db`
(миграция изменилась → `--create-db`), ruff check/format. Затем push → CI. Merge+deploy —
после чекпоинта владельца (миграция SHARED Tenant.choices).
