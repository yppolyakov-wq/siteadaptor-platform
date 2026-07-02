# Волна U-D — детальный план подзадач (унифицированный заказ + Kanban + склад-леджер + статусы/уведомления) — 2026-06-30

> Детализация фазы **U-D** мастер-трека `docs/unified-sellable-entity-master-track-2026-06-30.md`
> (детализировано 2026-07-01). Все пути/поля/функции — **верифицированы разведкой + адверсариальной
> проверкой против кода** (3 Explore + Plan-агент + Workflow из 7 скептиков; сводка — §10). Формат —
> как U-A/U-B/U-C: подзадачи по файлам/критериям/тестам + партиция + пересечения + риски + решения.
> Каждая подзадача — вертикальный срез, отдельная ветка, CI-гейт. Зависит концептуально от **U-A**
> (прецедент `SellableEntity` — тот же адаптерный подход) и от ЛК-проекции `apps/account/account_data.py`.
> Практически **независима от U-B/U-C** (другие файлы). **Самая крупная волна: модели + миграции** — том сам по себе.

## 0. Ключевые уточнения дизайна (верифицировано; ⚠️ = поправка адверсариальной проверки)

1. **6 транзакций делят инфраструктуру.** Все extends `TimestampedModel` (UUID PK, `apps/core/models.py:20-28`),
   FK `promotions.Customer` on_delete=PROTECT, unique 12-симв. `reference_code` (`O-`/`S-`/`E-`/`T-`/`R-`/`A-`),
   снимок цены, Stripe PI, у каждой — свой `StateMachine`-подкласс. ✅ верифицировано на всех 6.
2. **⚠️ Статус двигается ПРЕИМУЩЕСТВЕННО через `apps/core/fsm.py::StateMachine.apply()`, но НЕ исключительно.**
   Проверка нашла **3 боевых обхода FSM** (прямое `.status=`): `StayBooking` в `apps/events/public_views.py:624`
   и `apps/events/views.py:321` (отмена связанной брони при отмене билета), `Ticket` в `apps/events/views.py:309`
   (намеренный fallback, если `TicketSM().apply` бросил). Докстринги (`fsm.py`, `promotions/models.py`) объявляют
   прямое присваивание запрещённым — это признанные девиации, не санкционированный путь. **Следствие:**
   **read-проекция U-D1 читает ПОЛЕ `status` и не зависит от способа записи → не блокируется.** Но **U-D2 (запись
   перехода с доски) обязана идти через `SM().apply()` и НЕ полагаться на инвариант «только FSM»** (риск R1);
   опц. по ходу — вычистить 3 обхода (мелкий рефактор, не входит в U-D критпуть).
3. **Все денежные/складские side-effects — на `on_transition`-хуках 6 FSM** (верифицировано: revenue в
   `orders:37-60`/`stays:29-41`/`events:63-75`/`booking:28-40`/`promotions:82-94`). Проекция/доска **вызывают
   тот же `SM().apply()`** — никакой параллельной логики переходов. → U-D1/U-D2 в основном **проекция+UI без миграций.**
4. **⚠️ ЛК уже агрегирует транзакции — но шире, чем «6».** `apps/account/account_data.py::sections_for()`
   (путь `apps/account/`, единственное число): **9 модуль-гейтов / 12 билдеров разделов**, каждый через `_safe()`
   (try/except → None), LIMIT=10 по свежести. Транзакционных из них — 6 (orders/booking/stays/tickets/jobs/
   reservations), остальные — loyalty/vouchers/passes/invoices/inbox. Deep-link: reference_code для основных, но
   **jobs/messages — `public_token`**, часть (passes/invoices/vouchers/loyalty) — без ссылки. → U-D1-2 обобщает
   **только 6 транзакционных разделов** на протокол; нетранзакционные остаются как есть.
5. **KDS-доска = единственный прообраз Kanban** — `apps/orders/views.py:82-125` (`kitchen`/`kitchen_board`/
   `kitchen_action`) + `templates/orders/_kitchen_board.html` (HTMX-колонки, `hx-post`→`OrderSM().apply`, поллинг).
   Остальные (jobs/booking/stays/finance) — плоские списки с самодельными кнопками. ⚠️ **jobs/orders-detail/finance**
   рисуют кнопки из `SM.allowed_targets()`, а **booking/stays — из хардкод-сравнений** `{% if b.status == 'pending' %}`
   (`templates/stays/calendar.html:82-94`, `booking/calendar.html`). → UD2-1 при обобщении **конвертирует
   booking/stays на `allowed_targets`**.
6. **⚠️ Склад — голый счётчик, леджера НЕТ (M10 не построен, grep пуст).** `Product.stock_quantity`/
   `ProductVariant.stock_quantity` = nullable IntegerField (`catalog/models.py:81,210`), `Product.in_stock` (150-155).
   `finance.RevenueEntry` — revenue-only, не склад. → **UD3-1 — единственная подзадача с обязательной новой
   моделью+схемной миграцией.** (мелочь: флаг `stock_committed` — в `jobs/models.py:70`, не в services.)
7. **⚠️ Только 2 из 5 анти-оверселл движков реально двигают СКЛАДСКОЙ счётчик товара:**
   - **orders** — `select_for_update`+декремент `Product/ProductVariant.stock_quantity` (`orders/services.py:36-60`) — **это склад**;
   - **jobs.commit_stock** (`jobs/services.py:109-141`, G11) — декремент того же counter при →done — **это склад**.

   Остальные 3 **склад не трогают**: **promotions** декрементит `Promotion.available_quantity` (**лимит акции, НЕ инвентарь**,
   `F()`-UPDATE `promotions/services.py:94-100`); **stays** — счёт по-ночной занятости `StayBooking` vs `StayUnit.quantity`
   (`availability.py:54-58`); **events** — `Sum(ticket.quantity)` vs `Event.capacity` под lock-строки; **booking** — overlap
   слота vs `Resource.capacity`. → **UD3-2 логирует движения ТОЛЬКО у orders(sale/restore) + jobs(commit).**
   **promotions/stays/events/booking — вне складского леджера** (их истина — свои движки, не catalog-stock).
   Append-only-леджер пишется **в той же `@transaction.atomic`**, что и списание, **не меняя** атомарный декремент.

## 1. Партиция: что УНИФИЦИРУЕМ / что ПЛАГИН / что РАЗДЕЛЬНО

**УНИФИЦИРУЕМ (одна реализация на все kind):**
- **Протокол `Transaction`** (`apps/core/transactions.py`) — нормализует Order/StayBooking/Ticket/Booking/
  Reservation/Job к `{kind, pk, reference_code, customer, title, subtotal_display, currency, status, status_label,
  pipeline_stage, created_at, detail_url_customer, manage_url, allowed_actions[]}`. Адаптер, **модели не сливаются**.
- **Единый pipeline-маппинг** — `stage ∈ {intake, in_progress, done, terminal}` из общего фрейма.
- **Переиспуемая Kanban-доска** `_kanban_board.html` (обобщение KDS) + generic `kanban_action`.
- **Партиал `_status_actions.html`** из `SM.allowed_targets()` (заменяет per-app inline-кнопки, включая хардкод booking/stays).
- **Один склад-леджер** `StockMovement` (append-only) — на движения orders+jobs (см. §0.7).
- **Один SMS-адаптер** за существующим `_SENDERS`-диспетчером notifications.

**ПЛАГИН (per-kind за единым интерфейсом):** статус→колонка маппинг · форма line-item (OrderItem int / JobLine Decimal /
embedded rooms|quantity / slot без позиций) · шаблон уведомления · availability-движок (за buy-box, U-D не трогает).

**РАЗДЕЛЬНО (НЕ унифицируем — код/движок):** 5 анти-оверселл атомарных путей · availability-математика · запись выручки
`finance.record_revenue`/`record_reversal` на FSM-хуках (**не дублировать, не трогать**) · пер-app booking-календари ·
`_restore_stock`/`commit_stock`/`F()`-возврат side-effects (леджер их **логирует**, не заменяет).

## 2. Подзадачи U-D (сводка)

| ID | Фаза | Заголовок | Разм. | Мигр. | Зависит |
|---|---|---|:--:|:--:|---|
| **UD1-1** | U-D1 | Протокол `Transaction` + 6 адаптеров (`apps/core/transactions.py`), чистый Python + юниты | M | — | — |
| **UD1-2** | U-D1 | Обобщить `account_data.sections_for` (6 транзакц. разделов) на протокол; паритет ЛК | M | — | UD1-1 |
| **UD1-3** | U-D1 | Кабинетный резолвер «все транзакции по активным sell-модулям» (`manage_sections_for`) | M | — | UD1-1 |
| **UD2-1** | U-D2 | Pipeline-фрейм `PIPELINE` + `_status_actions.html` из `allowed_targets`; вписать orders/jobs/**booking/stays** detail | M | — | UD1-1 |
| **UD2-2** | U-D2 | Переиспуемая `_kanban_board.html` (обобщение KDS) + generic `kanban_action`; KDS переводится (паритет) | L | — | UD2-1 |
| **UD2-3** | U-D2 | Кабинетная Kanban-страница `/dashboard/board/` (выбор kind, колонки из pipeline, HTMX-advance) + nav | L | — | UD2-2, UD1-3 |
| **UD3-1** | U-D3 | Модель `StockMovement` (append-only) + миграция + идемпотентный `record_movement` | L | **да** | — |
| **UD3-2** | U-D3 | Врезка логирования **только в orders(sale/restore)+jobs(commit)** (движение рядом со списанием, НЕ вместо) | M | — | UD3-1 |
| **UD3-3** | U-D3 | Кабинет склада `/dashboard/stock/`: приёмки/корректировки/low-stock/инвентаризация + реконсиляция леджер↔счётчик | L | возм. | UD3-2 |
| **UD4-1** | U-D4 | SMS-канал: адаптер `_send_sms` + choice `sms` (миграция alter-choices) + per-tenant opt-in/провайдер | M | **да** | — |
| **UD4-2** | U-D4 | Унифиц. статус-уведомления (A9 K6 + ready) + выбор канала (email∥sms∥telegram) per-событие | M | возм. | UD4-1 |

**Старт = UD1-1** (протокол `Transaction`, чистый Python, без миграции). **Миграции волны:** **UD3-1**
(`StockMovement` — обязательная новая таблица), **UD4-1** (alter `Notification.channel` choices + tenant SMS-конфиг),
возможно UD3-3 (`low_stock_threshold`) и UD4-2 (per-событие channel-prefs). **UD1/UD2 — без миграций.**

## 3. Подзадачи (детально)

### UD1-1 — Протокол `Transaction` + 6 адаптеров · M · без миграции
`apps/core/transactions.py`: нормализует любую из 6 к контракту (§1); per-kind адаптеры, модели лениво
(`django_apps.get_model`, как `sellable.py` в UA1-3). Адаптеры **делегируют** метку `instance.get_status_display()`,
`allowed_actions` = `SM().allowed_targets(status)`; **читают, никогда не пишут** статус. Чистый Python + юниты.
**⚠️ PR-2/P2 (2026-07-01): контракт `Transaction` несёт `payment_method`** (read-only из модели/null) — фундамент
E-7 (платёжный микс DACH). Поле `Order.payment_method` (choices) + пикер/Stripe `payment_method_types` — **параллельный
трек E-7 во время U-D**, миграция в U-D (не после). UD1-1 только ВЫСТАВЛЯЕТ поле в проекции, UI выбора не строит.
- **Файлы:** `apps/core/transactions.py` (новый); reuse префиксов/URL из `apps/account/account_data.py`, per-app `state_machine.py`.
- **Критерии:** `transaction_for(kind, obj)` + `TRANSACTION_KINDS`; 6 адаптеров; `allowed_actions`=`allowed_targets`
  (без дубля переходов); `payment_method` в контракте (null-safe); импорт `apps.core` не тянет orders/stays/… на загрузке (lazy).
- **Тесты:** `apps/core/tests/test_transactions.py` (новый) — по адаптеру на kind + guard «не пишет статус» + `payment_method` в проекции.

### UD1-2 — Обобщить ЛК на протокол · M · без миграции
Переписать **6 транзакционных** билдеров `account_data.py` (`_orders/_bookings/_stays/_tickets/_jobs/_reservations`)
на `transaction_for`; **loyalty/passes/vouchers/invoices/inbox остаются как есть** (§0.4). **Паритет вывода**
(title/sub/status/url + reorder/cancel-токены; ⚠️ jobs/messages deep-link — `public_token`, сохранить per-kind в адаптере).
- **Файлы:** `apps/account/account_data.py`, `apps/core/transactions.py`.
- **Критерии:** те же разделы рендерятся идентично (снапшот-паритет); reference_code/public_token-ссылки корректны per-kind;
  `_safe()`-обёртка цела (сбой раздела не рушит ЛК).
- **Тесты:** существующие ЛК-тесты `apps/account/tests/`, гейт паритета.

### UD1-3 — Кабинетный резолвер транзакций · M · без миграции
`manage_sections_for(tenant)` — активные транзакции по активным `NAV_GROUPS['sell']`-модулям с `manage_url`
(dashboard-детали) + `allowed_actions` + счётчик по стадиям. Фундамент доски/inbox. Чистый Python (UI — UD2-3).
- **Файлы:** `apps/core/transactions.py`, reuse `apps/core/modules.py::is_module_active`.
- **Критерии:** фильтр по sell-модулям; `manage_url`=per-app dashboard detail; «последние N + счётчик по стадиям».
- **Тесты:** `apps/core/tests/test_transactions.py`.

### UD2-1 — Pipeline-фрейм + `_status_actions.html` · M · без миграции
`apps/core/pipeline.py::PIPELINE` — per-kind статус→`stage ∈ {intake,in_progress,done,terminal}` + метки колонок.
Партиал `templates/core/_status_actions.html` из `SM.allowed_targets(status)` + per-kind labels, `hx-post` на
per-app action-view (view не меняем). Вписать в `orders/order_detail.html`, `jobs/detail.html`, **и конвертировать
хардкод-кнопки `stays/calendar.html`/`booking/calendar.html` на `allowed_targets`** (§0.5).
- **Файлы:** `apps/core/pipeline.py` (новый), `templates/core/_status_actions.html` (новый), `apps/core/transactions.py`
  (pipeline_stage из PIPELINE), `templates/orders/order_detail.html`, `templates/jobs/detail.html`,
  `templates/stays/calendar.html`, `templates/booking/calendar.html`.
- **Критерии:** `pipeline_for(kind)` → упорядоч. стадии+статусы; кнопки только из `allowed_targets` (без per-app if/elif
  и без хардкод-сравнений); orders/jobs/booking/stays показывают те же действия (паритет), POST-endpoints неизменны.
- **Тесты:** `apps/orders/tests/`, `apps/jobs/tests/`, `apps/stays/tests/`, `apps/booking/tests/`, новый `test_pipeline.py`.

### UD2-2 — Переиспуемая Kanban-доска + generic `kanban_action` · L · без миграции
`templates/core/_kanban_board.html` (обобщение `_kitchen_board.html`): колонки из `pipeline_for(kind)`, карточки из
`Transaction`. Generic `apps/core/views.py::kanban_action(request, kind, pk)` — резолвит модель+SM, **`SM().apply(instance,
dst, actor=user)`** (тот же путь, что KDS — revenue/notifications/stock едут на FSM-хуках, **не дублируются**).
**KDS переводится на новую доску** (kind=order) — паритет обязателен (живая gastro-поверхность).
- **Файлы:** `templates/core/_kanban_board.html` (новый), `apps/core/views.py` (`kanban_action`+`kanban_board`),
  `apps/orders/views.py` (kitchen* → делегируют), `templates/orders/kitchen.html`.
- **Критерии:** доска рендерит колонки/карточки для любого kind; `kanban_action` двигает статус **только через
  `SM().apply`** (IllegalTransition→тихая перерисовка); KDS-вывод/поллинг/HTMX паритетны; **revenue не дублируется**
  (гейт: `RevenueEntry.count()` не растёт от перерисовки/повтора apply — верифиц. `fsm.py:44-45` src==dst → no-op).
- **Тесты:** `apps/orders/tests/` (KDS-паритет), новый `apps/core/tests/test_kanban.py`.
- ⚠️ **Зона регрессии:** KDS — живая поверхность; снапшот-паритет + гейт «apply один раз».

### UD2-3 — Кабинетная Kanban-страница + nav · L · без миграции
`/dashboard/board/`: выбор kind (табы по активным sell-модулям из UD1-3), колонки из pipeline, advance через UD2-2.
Пункт в nav. **Per-app страницы ОСТАЮТСЯ** (доска — дополнение, не замена — D2).
- **Файлы:** `config/urls_tenant.py` (`dashboard/board/`), `apps/core/views.py` (`board_view`), `templates/core/board.html`
  (новый), `apps/core/modules.py` (nav), dashboard-nav шаблон.
- **Критерии:** доска по активным модулям (гейтинг как per-app); переключение kind меняет колонки; advance двигает FSM+перерисовка.
- **Тесты:** `apps/core/tests/test_board.py` (новый) + гейтинг-тест.

### UD3-1 — Модель `StockMovement` + миграция + сервис · L · **МИГРАЦИЯ**
Новый app `apps/inventory` (или в `apps/catalog`): `StockMovement(TimestampedModel)` — `product` FK / `variant` FK(null) /
`kind ∈ {receipt, sale, adjustment, return, stocktake, commit}` / `delta` int (знаковый) / `source` / `source_ref` /
`note` / `actor`(null) / индексы `(product, created_at)`, `(source, source_ref)`. Сервис `record_movement(...)` —
**идемпотентный по `(source, source_ref, kind)`** для событийных движений (get_or_create + UNIQUE, образец
`finance.record_revenue`), свободный для ручных. **НЕ трогает счётчик** в v1 (D1 — леджер ALONGSIDE счётчика).
- **Файлы:** `apps/inventory/models.py`+`migrations/0001`, `apps/inventory/services.py`, регистрация в `TENANT_APPS` (base.py).
- **Критерии:** таблица создана схемной миграцией (TENANT-схема); `record_movement` идемпотентен по source_ref для
  событийных kind (тест дубль→no-op); ручные — без дедупа; **счётчик не меняется** (append-only).
- **Тесты:** `apps/inventory/tests/test_movement.py` (новый); идемпотентность по образцу `finance/tests`.
- ⚠️ **Единственная обязательная схемная миграция** — деплой на tenant-схемах (`./scripts/deploy.sh single`); локально `--create-db`.

### UD3-2 — Врезка логирования в orders+jobs · M · без миграции
Дописать `record_movement(...)` **рядом** со списанием/возвратом **только** в: `orders/services.py` (kind=sale) +
`orders/state_machine.py::_restore_stock` (kind=return); `jobs/services.py::commit_stock` (kind=commit).
**⚠️ promotions/stays/events/booking — НЕ логируем** (склад-счётчик товара не трогают, §0.7). **Списание остаётся
атомарным как есть — movement в той же транзакции, НЕ заменяет декремент.**
- **Файлы:** `apps/orders/services.py`, `apps/orders/state_machine.py`, `apps/jobs/services.py`, `apps/inventory/services.py`.
- **Критерии:** каждое списание/возврат catalog-товара пишет movement в той же транзакции; **атомарность декремента цела**
  (движок не изменён); `sum(delta)` по товару = изменение счётчика (реконсиляция — UD3-3); идемпотентно по source_ref.
- **Тесты:** параллельный анти-оверселл тест orders (`TransactionTestCase`+`ThreadPoolExecutor`, DoD `anti-oversell.md`)
  **остаётся зелёным**; `test_movement` на паритет delta↔счётчик.
- ⚠️ **Correctness-critical:** трогает горячий путь списания orders/jobs — гейт параллельным тестом.

### UD3-3 — Кабинет склада + реконсиляция · L · возможна миграция
`/dashboard/stock/`: приёмки (receipt +N), корректировки (adjustment ±N), low-stock (`stock_quantity ≤ threshold`),
инвентаризация (stocktake→adjustment на разницу). **Ручные приёмки/корректировки — единственный путь, где movement
меняет счётчик** (в одной транзакции). Реконсиляция: `sum(delta)` vs `stock_quantity` (алерт при расхождении).
Опц. `Product.low_stock_threshold` (миграция) ∥ tenant-глобальный порог (без миграции — D-склад).
- **Файлы:** `config/urls_tenant.py`, `apps/inventory/views.py`, `templates/inventory/stock.html`, `apps/inventory/services.py`,
  `apps/catalog/models.py` (опц. threshold).
- **Критерии:** приёмка/корректировка пишет movement + двигает счётчик атомарно; low-stock из счётчика/порога; stocktake→adjustment;
  реконсиляция показывает расхождения.
- **Тесты:** `apps/inventory/tests/test_stock_cabinet.py`; тест реконсиляции.

### UD4-1 — SMS-канал · M · **МИГРАЦИЯ**
`_send_sms(notification)` в `apps/notifications/adapters.py::_SENDERS` (провайдер за настройкой — Twilio/MessageBird/Vonage;
креды в tenant-конфиге/env, как email/telegram). Choice `sms` в `Notification.CHANNELS` (**миграция alter-choices**, как
`0002_alter_notification_channel`). Per-tenant opt-in + `Customer.phone`-consent (DSGVO). Через `notify(channel="sms")`+`NotificationSM`.
- **Файлы:** `apps/notifications/adapters.py`, `models.py`+`migrations/0003`, `services.py` (routing цел), tenant-конфиг, `sms.py` (клиент).
- **Критерии:** `channel="sms"` через `_send_sms`; ошибка→`NotificationSM`→failed→retry (как telegram); opt-in-гейт; нет кред→failed (не краш).
- **Тесты:** `apps/notifications/tests/test_send.py` (mock-провайдер) + opt-in-гейт.
- ⚠️ **Новая внешняя интеграция** — стоимость/opt-in/DSGVO (риски + D3); за фичефлагом, дефолт-выкл (как `whatsapp`-choice без адаптера).

### UD4-2 — Унифиц. статус-уведомления · M · возможна миграция
Repair-статус A9 (K6) + ready-for-pickup — на FSM-хуках. Обобщить **выбор канала per-событие**: `notify(channel=...)`
из tenant/customer-prefs (fallback email); dedupe-путь `{kind}:{id}:{event}:{role}` цел. Опц. per-событие channel-prefs (миграция) ∥ tenant-глобально.
- **Файлы:** per-app `notifications.py` (`channel=`), `apps/notifications/services.py`, tenant/customer prefs.
- **Критерии:** переход шлёт по выбранному каналу (email по умолч.); ready/repair — существующий dedupe (без задвоения);
  SMS только при opt-in; **revenue/side-effects на хуках не трогаются**.
- **Тесты:** `apps/orders/tests/`, `apps/jobs/tests/`, `apps/notifications/tests/`.

## 4. Последовательность (критический путь)

```
UD1-1 ─┬─ UD1-2 (ЛК)
       ├─ UD1-3 ───────────────── UD2-3
       └─ UD2-1 → UD2-2 → UD2-3
UD3-1 → UD3-2 → UD3-3        (параллельная ветка — новый app)
UD4-1 → UD4-2               (параллельная ветка — notifications)
```
Критпуть: **`UD1-1 → UD2-1 → UD2-2`** (протокол → pipeline → доска). **UD3-*** и **UD4-*** — независимые ветки
(другие файлы; только UD3-2 трогает горячий путь orders/jobs → гейт параллельным тестом). Три параллельных потока,
сходятся в дашборд-nav. **Старт — UD1-1** (де-рискует всё, окупается в ЛК UD1-2).

## 5. Пересечения с U-A / U-B / U-C
- **U-A прецедент (`SellableEntity`, UA1-3):** `Transaction` — тот же адаптерный подход (lazy `get_model`, модели не сливаются).
  U-A унифицирует **просматриваемую** сущность, U-D — **транзакцию** над ней. `jobs.Job` в U-A **явно НЕ деталь-адаптер**
  (документирован как «транзакция под U-D») → U-D1 подхватывает Job. Границы чистые, файлы разные.
- **ЛК-проекция (`account_data.py`):** UD1-2 обобщает 6 транзакционных разделов; живой прецедент «6 kinds за одним циклом».
- **Kanban — в КАБИНЕТЕ, не в U-C storefront-редакторе.** U-C правит витрину (`site_config`-round-trip, `site_home.html`);
  U-D2 — management (`/dashboard/board/`). **Не пересекаются** (разные поверхности/файлы). U-D не трогает `collect()/normalize`.
- **Склад ↔ catalog (U-B листит):** U-B наличие-фасет `Product.in_stock` (UB2-3). Леджер UD3 стоит **за** тем же счётчиком →
  `in_stock`/фасет остаются истиной; UB2-3 работает без изменений.
- **Уведомления:** U-A/U-B/U-C не трогают notifications; U-D4 — изолированная ветка; E-8 (SMS/WhatsApp) сходится сюда.

## 6. Риски U-D (correctness-critical — деньги + склад + анти-оверселл)
1. **⚠️ FSM не исключителен (R1).** Есть 3 боевых прямых `.status=` (§0.2). U-D1 read-проекция не зависит. **U-D2 `kanban_action`
   обязана идти через `SM().apply()`**; не строить инвариант «status всегда валиден по FSM-переходам». Опц. вычистить 3 обхода.
2. **Не задвоить выручку.** `record_revenue`/`record_reversal` на FSM-хуках; доска зовёт `SM().apply()`; `fsm.py:44-45`
   src==dst→no-op; дедуп по `(source, source_ref)` (⚠️ доска должна писать ту же сущность тем же ключом — не менять source/format).
   Гейт UD2-2: перерисовка не растит `RevenueEntry`.
3. **Не сломать 5 анти-оверселл.** UD3-2 добавляет movement **рядом** (та же транзакция), атомарный UPDATE/select_for_update
   не меняется, и **только у orders/jobs** (§0.7). Гейт: параллельные тесты остаются зелёными.
4. **Леджер реконсилирует со счётчиком.** D1: append-alongside (счётчик — истина, реконсиляция-вью) vs counter-derived
   (риск переписать горячий путь). v1 — alongside. Гейт `sum(delta)==Δcounter`.
5. **Миграции на tenant-схемах.** UD3-1 (новая таблица) + UD4-1 (alter choices); `./scripts/deploy.sh single`; локально `--create-db`.
6. **SMS = внешняя интеграция.** Стоимость, **opt-in обязателен** (DSGVO), креды per-tenant; за фичефлагом, дефолт-выкл.
7. **KDS-паритет (UD2-2).** Живая gastro-поверхность (поллинг/HTMX) — снапшот-паритет + гейт «apply один раз».
8. **line-item асимметрия (D4).** OrderItem int vs JobLine Decimal; stays/events embedded; booking/reservation без позиций.
   `Transaction` отдаёт `title`+готовый `subtotal_display`, **не** нормализует позиции в v1 → без int/Decimal-конфликта.

## 7. Открытые решения U-D — ✅ ЗАФИКСИРОВАНО (2026-07-01, см. `…-decisions-2026-06-30.md`)
- **D1 — Склад-леджер:** ✅ **(a) append-only лог РЯДОМ со счётчиком** (C-5; счётчик — истина, реконсиляция-вью).
- **D2 — Кабинет:** ✅ **(a) per-app страницы + общая доска `/dashboard/board/`** (C-6).
- **D3 — SMS:** ⏸️ **ОТЛОЖИТЬ** (B-2) — **UD4-1 снят из волны U-D**, поднять вместе с WhatsApp позже. Остаётся UD4-2
  (выбор канала email/telegram per-событие). Провайдер (Twilio/MessageBird/Vonage) — решать при подъёме SMS.
- **D4 — Унификация line-items:** ✅ **(a) НЕ унифицировать** (C-7; проекция отдаёт `title`+`subtotal_display`).

## 8. Верификация U-D (end-to-end)
- `uv run ruff check .` + `ruff format --check`; `uv run pytest apps/core apps/orders apps/jobs apps/booking apps/stays
  apps/events apps/promotions apps/inventory apps/notifications apps/account -k "transaction or pipeline or kanban or board
  or movement or stock or sms or notif" --create-db` (UD3-1/UD4-1 — схемные миграции).
- **Обязательно:** параллельные анти-оверселл тесты (orders/promotions/stays/events/booking, `TransactionTestCase`+`ThreadPoolExecutor`)
  **зелёные** после UD3-2 (движки не деградировали).
- Браузер: `seed_demo_tenants --recreate`; доска `/dashboard/board/` двигает заказ/бронь/заявку (FSM, письмо/выручка один раз);
  склад `/dashboard/stock/` — приёмка/корректировка/low-stock/инвентаризация, реконсиляция сходится; KDS не сломан; ЛК — те же разделы;
  SMS (opt-in+креды) доставляется, иначе email-fallback.
- CI зелёный по батчу; чекпоинт с владельцем (D1/D2/D3/D4) перед фазой U-E.

## 9. Связанные
`docs/unified-sellable-entity-master-track-2026-06-30.md` (U-D §3, §5 M10) · `docs/unified-sellable-entity-ua-plan-2026-06-30.md`
(UA1-3 `SellableEntity`-прецедент) · `docs/references/patterns/anti-oversell.md` (DoD параллельных тестов) ·
`docs/references/patterns/notification-dedupe.md` · `docs/references/patterns/state-machine.md` · `apps/core/fsm.py` ·
`apps/core/transactions.py` (новый) · `apps/account/account_data.py` · `apps/notifications/` · `apps/inventory/` (новый) ·
`apps/finance/services.py` (образец идемпотентности по `source_ref`) · `master-plan.md §M10`.

## 10. Верификация утверждений (адверсариальная проверка против кода, 2026-07-01)
Workflow из 7 скептиков (refute-by-default) проверил несущие технические утверждения плана:

| Утверждение | Вердикт | Что уточнено (уже вложено в план) |
|---|---|---|
| 6 сущностей делят инфраструктуру + FSM | **partial** | База/Customer FK/reference_code/FSM ✅. **«Статус только через FSM.apply()» — неверно:** 3 боевых обхода (§0.2, R1). Read-проекция не блокируется. |
| Леджера склада нет (M10) | **confirmed** | ✅ (флаг `stock_committed` — в `jobs/models.py:70`). |
| Выручка идемпотентна по source_ref | **confirmed** | ✅; дедуп по паре `(source, source_ref)` — доска пишет ту же сущность тем же ключом (R2). |
| 5 анти-оверселл независимы; леджер рядом | **partial** | Леджер рядом в atomic ✅. **Склад двигают только 2 из 5 (orders+jobs); promotions=лимит акции, stays/events/booking=счёт vs капасити** → UD3-2 сужен (§0.7). |
| ЛК уже проецирует | **partial** | Путь `apps/account/` ✅. **9 гейтов/12 билдеров, не «6»;** jobs/messages — `public_token`. Обобщаем только 6 транзакц. разделов. |
| KDS — единственный Kanban | **confirmed** | ✅; **booking/stays кнопки — хардкод `{% if status %}`** → UD2-1 конвертирует на `allowed_targets`. |
| Уведомления канал-агностичны, SMS нет | **confirmed** | ✅ SMS = новый адаптер, не новая инфраструктура. |

## Дополнения по аудиту 2026-07-01 (см. master-track §7.3)
- **E-7 платёжный микс DACH — ПРИОРИТЕТ №1 (сквозной блокер, вне волн):** `Order.payment_method` в
  UD1-1 (сейчас только `payment_state`) + PayPal / Klarna Kauf-auf-Rechnung / SEPA / Vorkasse +
  `payment_method_types` в Stripe Checkout (`billing/connect.py:145` без них). Внутр. часть
  (`payment_method`+Vorkasse) — до/в начале U-D; PayPal/Klarna — по `external-integrations-backlog`.
- **A7/A9 финансы:** online-оплата финального счёта (сейчас только депозит на Angebot) + E-Rechnung
  (XRechnung/ZUGFeRD, B2B must 2025) — отдельный трек E-Invoice.
- **A7 отзыв по Auftrag:** kind `job` в `reviews.Review` + `has_completed_job` (fail-closed) +
  письмо `job_done` → форма `/bewerten/` (сейчас ведёт на портал).
- **`[правка аудита]` A9:** repair-статус + «fertig»-письмо (K6) и HU/AU-reminder (K7) **уже реализованы**
  (`jobs/state_machine.py:29-43`, `Job.service_due_date`+beat) — из бэклога снять. Остаётся
  **serviced-vehicle история** (мультивизит) + **Reifeneinlagerung**. Детали — `docs/audit-2026-07-01.md §3/§5`.
