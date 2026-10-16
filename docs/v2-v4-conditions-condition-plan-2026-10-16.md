# В2 «условные цены» + В4 «состояние товара» — план (2026-10-16)

План — агент planner (разведка по коду, факты сверены вручную). Решения владельца:
`backlog-portal-direction-2026-10-16.md` §9 (В2 «делаем», В4 «ок, одной миграцией с В2»).
Кода в документе нет.

## 1. Факты

**В2 — механики «условия» в коде нет.** Условие живёт только в заголовке акции;
`Promotion.new_price` (`promotions/models.py:394`) = обычная цена × (100 − %). Поэтому
«Pizza-Abend: zweite Pizza −50 %» (`demo_city/solingen/essen.py:119`), «Kabel-Dienstag:
2 für 1» (`elektronik.py:337`), «zweite Fassung zum halben Preis» (`gesundheit.py:199`)
публикуются в каталог города как ЦЕНА ОДНОЙ ШТУКИ × 0,5 (`aggregator/tasks.py:25–62`).

**Тот же дефект касается денег на витрине бизнеса:** `price_layer.promo_line_price`
(:121) и `product_promo_map` (:187, по `lowers_price`) применяют `new_price` к КАЖДОЙ
строке корзины — при включённых заказах каждая пицца уходит за полцены (SF-4b «показано =
списано»). Аналогично услуга (`price_layer.py:202–234`). Прочие потребители `new_price`:
`core/seo.py:180`, `promotions/flyer.py:49`, `promotions/facets.py:56`,
`public_views.py:2556`, `services.py:310`, `core/transactions.py:254`.

**В4.** `Product.condition`/`condition_note`/`condition_note_i18n`
(`catalog/models.py:211–222`, 7 кодов, подписи переведены) в листинг не попадает;
портал знает только «Neu im Sortiment» (`is_new`). Карта schema.org уже есть —
`core/sellable.py:93 ITEM_CONDITION`.

**Снимок.** Единая точка записи `_upsert_listing` (`tasks.py:151`) пишет только при
изменении полей из `defaults` → новые поля обязаны быть в `defaults` ВСЕХ построителей
(акция, товар, stay, событие, группа событий, меню, услуга, бизнес). Прецеденты нового
поля: `price_reference` (SF-8, `0028`), `variant_terms` (T-8.26 п.5c).

## 2. Миграция `aggregator/0029` (SHARED, аддитивная, fast default)

| поле | тип | default | смысл |
|---|---|---|---|
| `price_condition` | JSONField | `{}` | В2: `{kind, n, pay, percent, note}`; `{}` = цена за штуку честная |
| `item_condition` | CharField(20), без choices | `""` | В4: код `Product.CONDITION_CHOICES` |
| `item_condition_note` | JSONField | `{}` | В4: `{locale: text}` |

Индексов и бэкфилла нет — заполнит `sync_aggregator`/ночная сверка.

**Условие у акции — без тенантской миграции:** `Promotion.metadata["price_condition"]`
(прецедент `response`/`perishable`):
`{"kind": "nth"|"x_for_y"|"min_qty"|"other", "n", "pay", "note": {loc: text}}`.
`nth` («каждая n-я −p %», n 2..10), `x_for_y` («n за pay»), `min_qty` («от n штук −p %»,
n 2..99), `other` (заметка ≤ 80). Мусор → «условия нет» (fail-safe).

Новый модуль `apps/core/price_conditions.py`: `normalize`, `snapshot(promo)`,
`label(cond, locale)`.

## 3. Правила

**В2:** есть условие → в снимке `new_price = old_price = discount_percent = None`,
`price_reference = ""`, `price_condition = snapshot`. Отсюда сами собой честные: фильтры
цены, `Offer.price` в JSON-LD, цены в фиде, письма-сводки, «ab»/минимум группы.
Mystery сильнее условия (условие раскрыло бы скидку).

**Тенант (деньги):** `lowers_price`/`has_discount`/`discount_percent_display` → нет при
условии (гасит корзину, баннер товара, фасет «−N %+»); `service_promos` и кандидат
промо номера пропускают условные; отклик BUY для условной недоступен + приёмник
`/kaufen/` отбивает. Показ — новая ветка `_discount_display.html` (бейдж-подпись
условия + обычная цена), seo без цены, флаер с подписью.

**Ввод:** поле формы акции «Preis gilt nur unter Bedingung» (вид + n/pay + заметка),
сентинел `price_condition_present` (W0); при `nth`/`min_qty` обязателен процент,
`price_override` с условием запрещён. Быстрый ассистент в v1 не трогаем.

**В4:** `item_condition`/`item_condition_note` у листинга товара и у акции с
товаром-целью; остальные виды пишут явный сброс (общий словарь нейтральных полей).
Бейдж состояния на карточке/странице предложения, отдельный от «Neu im Sortiment»;
`itemCondition` в JSON-LD только при непустом коде (пусто = «keine Angabe», не
«новое»); поля в фиде; подписи состояния в индексе поиска (вес C) — «gebraucht»,
«Retoure» находятся. Фасета `?zustand=` в v1 нет.

## 4. Замки до кода

- `core/tests/test_price_conditions.py` — normalize, подписи всех видов de/ru, `%%`.
- `promotions/tests/test_price_condition_promo.py` — корзина не дешевеет, нет % и
  бейджа снижения, нет BUY, `/kaufen/` отбивает, услуга пропускает, W0-сентинел формы,
  запрет `price_override`, бейдж витрины.
- `aggregator/tests/test_v2_v4_snapshot.py` — условная акция без цен, mystery сильнее,
  смена условия обновляет строку, состояние+оверлей заметки, акция на б/у товар,
  **каждый построитель пишет три поля**, неизменённая строка не переписывается.
- `aggregator/tests/test_v2_v4_render.py` — карточка/страница/JSON-LD (параметризация
  по всем `CONDITION_CHOICES`)/фид/фильтр цены/сводка/поиск «gebraucht»/бейдж ≠ «Neu».
- `tenants/tests/test_city_specs.py` — заголовок со словами «zweite / 2 für 1 / ab N
  Stück / halben Preis» обязан нести условие (ловит пиццу, кабель, очки).

## 5. Риски

Забытое поле в построителе = строка не обновится никогда (замок). JSON сравнивать
нормализованным (int, только непустые локали), иначе ночная сверка будет переписывать
строки. Старые строки до `sync_aggregator` показывают прежнее (без регрессии). Смена
состояния товара доходит до листинга его акции через ночную сверку (≤ 1 сутки) либо
синком активных акций товара в `resync_on_product_save` (+5 строк, берём).
Витрина при пустом состоянии пишет NewCondition — расхождение с порталом осознанное,
выравнивание — в roadmap §Отложено.

## 6. Инкременты

1. **В2-0** (тенант, без миграции): `price_conditions` + гейты денег/показа + форма +
   витрина + замки. Первым — снимает риск в корзине.
2. **В2/В4-1** миграция `0029` + построители + замки снимка.
3. **В2/В4-2** вывод на портале/фиде/JSON-LD/сводке/поиске + переводы (≈12 msgid × 5).
4. **В2/В4-3** демо (условия в спеках essen/elektronik/gesundheit и др.) + стенд.

2–3 одним батчем. Перед мержем: django-reviewer + security-reviewer + database-reviewer.

## 7. Ops после деплоя

`./scripts/deploy.sh single` → `python manage.py sync_aggregator` →
`seed_demo_tenants --group solingen-dcc --recreate` (+ `--kit outlet --recreate`) →
`python manage.py migration_state`. `rebuild_search_index` не нужен.
