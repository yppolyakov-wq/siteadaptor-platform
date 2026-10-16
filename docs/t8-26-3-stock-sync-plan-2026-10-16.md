# T-8.26 п.3 — снимок остатка после массовых `.update()` + плановая сверка (2026-10-16)

План агента planner по пункту 3 `docs/t8-26-audit-fixes-plan-2026-10-16.md`; факты сверены с
`main`. Цикл: замки ДО кода → django-reviewer + security-reviewer → зелёный CI → FF в `main`.
Миграций НЕТ: поле `AggregatorListing.availability` уже есть (`models.py:140`).

## Факты
- Снимок товара берёт `Product.in_stock` (`aggregator/tasks.py:925-930`) — тот же источник,
  что витрина; хуки — только `post_save` (`apps.py:29-99`), ключ дедупа `agg-product:{id}:
  {updated_at}`; массовый `.update()` не меняет `updated_at` и не шлёт сигнал.
- Остаток мимо `save()` меняют 4 места — отмена заказа (`orders/state_machine.py:117-140`),
  `jobs/services.release_stock`, опции-трекеры (`core/option_trackers.py:161-220`), возврат
  резерва акции (`promotions/services.py:213-231`); КАЖДОЕ в той же atomic пишет
  `StockMovement` (`record_movement` → create/get_or_create → `post_save(created=True)`).
  Шум: переносы между локациями (`transfer_out/in`, сумма 0).
- Лимит акции (`available_quantity`) меняется ТОЛЬКО через `.update()` (8 мест: `price_layer`
  claim/return, `promotions/services.py:130,272,458`, `state_machine.py:80`,
  `core/status_effects.py:184`, `orders/state_machine.py:161`); `_snapshot` акции
  `availability` не пишет; `Promotion.is_sold_out` есть (`models.py:453`).
- События: `_event_snapshot` без `availability`; `Event.is_sold_out` (ёмкость + тиры) есть;
  хука на `Ticket` нет. Групповая запись тура/серии — по ближайшему заезду.
- Потребители: JSON-LD пустое → `InStock` (`structured.py:20-36`); поиск «только доступное»
  и блоки главной «Produkte»/«Neu» исключают `sold_out`.
- Плановой сверки нет: `reconcile_schema` зовут только команда `sync_aggregator` и возврат
  бизнеса в каталог; beat агрегатора — roll-event-group, purge_search_log, Folgen.

## Решения
- **Р-1** хук остатка — ОДНА точка: `post_save StockMovement` (`created`, не transfer) →
  `touch_products` → `sync_aggregator_product` с ключом `agg-stock:{schema}:{pid}:{bucket}`
  и `countdown` = окно 30 с (как категории). Не трогаем 4 места по отдельности: пятое
  забудут; скан-замок «каждый `stock_quantity=F(` живёт в функции с `record_movement`».
- **Р-2** лимит акции — хелпер `touch_promotion(schema, pk)` рядом с каждым `.update()`
  `available_quantity`; скан-замок правила.
- **Р-3** билеты — `post_save/post_delete Ticket` → синк события (группа делегируется сама).
- **Р-4** доступность акции/события считается при синке через `is_sold_out` (mystery — тоже:
  скрыта цена, не распроданность); группа — `sold_out` только если распроданы ВСЕ будущие
  опубликованные заезды. Отвергнуто: считать при чтении (обход схем на рендер), поле
  `seats_left` (миграция SHARED ради цифры, которую не показываем — v2).
- **Р-5** ночная сверка `reconcile_aggregator_nightly`: раз в сутки по всем тенантам без
  public, `reconcile_aggregator_schema` с ключом `agg-nightly:{schema}:{date}` и
  `countdown = i × SPREAD` (env `AGG_RECONCILE_SPREAD_S`, 20 с); полная, не инкрементальная
  (надёжного признака «тенант менялся» нет — дрейф как раз там, где `updated_at` не тронут).
- **В-1 (дефолт)** распроданная акция на главной портала видна с плашкой; **В-2 (дефолт)**
  86400 с от старта beat, как остальные суточные задачи.

## Инкременты
- **3a** `apps/aggregator/stock_sync.py` (touch_products + обработчик), подключение в `apps.py`,
  скан-замок леджера.
- **3b** `availability` у акции/события/группы в снимке; `touch_promotion` в местах Р-2; хук
  `Ticket`; плашка «Ausverkauft» на карточке портала для всех видов (проверить партиал).
- **3c** beat `reconcile-aggregator-nightly` + задача с разбросом.

## Замки ДО кода
`test_stock_sync.py`: отмена заказа / release_stock / опция / возврат резерва ставят синк
товара с countdown; всплеск в одном окне — один ключ; transfer не ставит; интеграционный
sold_out→"" после отмены; скан-замок леджера. `test_snapshot_availability.py`: акция
`available_quantity=0` → sold_out, None → ""; mystery sold_out; событие по ёмкости и по тирам;
группа sold_out только при всех распроданных; claim/return ставят синк акции; Ticket ставит
синк события; JSON-LD SoldOut. `test_nightly_reconcile.py`: запись beat; fan-out с
countdown 0,S,2S без public, ключ с датой; сверка чинит дрейф после голого `.update()`.
Изоляция xdist: `.delay`/`.apply_async` через mock, uuid-id, `django_capture_on_commit_callbacks`,
время окна — patch `time.time`.
**Переписываются осознанно:** матрица `availability`→IRI в `test_machine_readable` (+2 строки).

## Риски / Ops
Нагрузка: один отложенный синк на товар за окно (импорт 500 позиций = 500 лёгких задач);
двойной синк на save-путях безвреден (идемпотентен). Ночная сверка: ~80 задач на 79 демо,
замерить `time sync_aggregator`; >10 мин на схему → v2 батч снимка. Ops: beat подхватит
запись при рестарте; один раз `python manage.py sync_aggregator` после деплоя, чтобы выровнять
акции/события по новому полю, не дожидаясь ночи.

## Ревью перед мержем (django · security · database)
- **django (HIGH):** окно дедупа считалось в момент правки, задача ставилась при коммите —
  длинная транзакция из конца окна, закоммиченная после старта первой задачи, упиралась в
  её lock и терялась до ночной сверки → окно считается ПРИ КОММИТЕ (и у хука категории —
  тот же класс); срез `[:50]` у группы заездов давал бы ложное «Ausverkauft» длинной серии
  → без среза, `all()` останавливается на первом свободном; lock суточной сверки был 1 ч
  (рестарт beat гонял бы все схемы заново) → `lock_timeout=86400`; потолок countdown 3300 с
  (visibility_timeout Redis).
- **security (MEDIUM):** брокер получал по сообщению на каждую строку заказа/билет, дедуп
  только при исполнении → `cache.add` при постановке (fail-open, как lock). X-Forwarded-For
  доверяется первому значению (pre-existing, зависит от Caddy) — не трогал.
- **database (HIGH):** ночная сверка переписывала бы КАЖДУЮ строку снимка, сдвигая
  `updated_at` (lastmod sitemap, даты фида, порядок «новые») и плодя мёртвые кортежи с
  перестройкой GIN → единый `_upsert_listing` с гардом «все поля равны — не пишем» на 8
  мест; сверка событий по группе один раз (было K раз на K заездов); `select_related("tour")`.
  Отложено в roadmap §Отложено: прокинуть `tenant` в `sync_*_listing` (−2 запроса на объект),
  батч-снимок товара (варианты/категории одним запросом), partial-индекс под `public()`
  после замера, кэш `withheld_schemas` на запрос. Миграция `tenants/0037` — fast-default
  PG11+, без переписи таблицы, индекс не нужен (подтверждено).
