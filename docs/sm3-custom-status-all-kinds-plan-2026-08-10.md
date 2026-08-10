# SM-3: кастом-статусы (FB-3 Вариант B) на всех шести направлениях (план)

Решение владельца (2026-08-10, «делаем»): распространить создание СВОИХ статусов
с order/booking/stay на job/ticket/reservation — «свой статус работает везде
одинаково». Второй шаг SM-2b (см. `sm-single-mode-plan-2026-08-10.md §SM-2`).

## 0. Главная находка разведки: дверь уже открыта

SM-2b расширил `_STATUS_LABEL_KINDS` до шести kind, а через этот словарь живут
не только имена/переходы, но и **весь трубопровод кастом-статусов**:

- `siteconfig.normalize_status_defs` / `normalize_status_edges` итерируют
  `_STATUS_LABEL_KINDS` → хранилище УЖЕ принимает дефы/рёбра для
  job/ticket/reservation (комментарии «kind ∈ order/booking/stay» устарели);
- вьюхи `status_manager`/`status_manager_save` гейтятся
  `status_label_statuses(kind) is None` → редактор УЖЕ отвечает 200;
- вход «🏷️ Eigene Status verwalten» на Abläufe рендерится с `kind=active_kind`
  → ссылка УЖЕ видна для всех шести вкладок;
- реестр (`status_registry.BUILTIN` — все 6 kind, включая асимметрию
  `ticket.attended` blocks_capacity), эффекты (`status_effects` — все 6, у job
  выручка осознанно нет: invoice-флоу), FSM (`kind` проставлен у всех шести SM,
  включая Ticket/Job/ReservationSM) — были готовы с Phase 0–6.

То есть владелец МОЖЕТ создать статус для Tickets уже сегодня — но корректность
для новых kind никто не гарантировал. Инкремент = закрыть найденные дыры +
замки, а не «включить фичу».

## 1. Дыры (найдены разведкой, каждая сверена с кодом)

### 1.1 Anti-oversell билетов: кастом-статус освобождает место (КРИТИЧНО)

Занятость мест события считается ЛИТЕРАЛЬНЫМ `Ticket.ACTIVE_STATUSES` в 4
местах: `events/models.py:201` (tier_sold_map), `:265` (seats_sold),
`events/services.py:127` (guard ёмкости), `:145` (guard тира). Билет,
переведённый владельцем в кастом-статус (роль active, blocks_capacity=True),
из этих сумм ВЫПАДАЕТ → guard продаёт его место второй раз.

Фикс: все 4 места → `status_registry.active_statuses_for("ticket")` (built-in ∪
кастом-active текущего тенанта; для booking/stay это уже сделано в PMS-волне).
`Ticket.ACTIVE_STATUSES` остаётся (журнал/др. читатели), но guard'ы и счётчики
идут через реестр.

### 1.2 Двойной возврат склада/лимита на рёбрах cancel↔cancel (дыра ЖИВЫХ kind тоже)

`on_transition` диспатчит по `t.dst` → кастом-ребро в builtin `cancelled`
СРАБАТЫВАЕТ встроенными побочками. Возвраты НЕ идемпотентны (`_restore_stock` —
F()+qty; `return_units`/possible reservation `available_quantity` — F()+qty;
докстринг `return_units` прямо говорит: «идемпотентность — на вызывающем FSM:
терминальный статус не перезаходится» — кастом-рёбра этот инвариант ломают).

Сценарии двойного возврата:
- `pending → мой_отказ (роль cancelled: эффекты вернули限 лимит/склад) →
  cancelled (builtin: on_transition вернул ВТОРОЙ раз)`;
- `cancelled (builtin: вернул) → мой_отказ (apply_custom_effects вернул второй)`.

Фикс двухслойный (лечит и уже сохранённые конфиги, и все 6 kind разом).
**Усилен после адверсариальной сверки воркфлоу**, которая нашла обход первой
версии («оба конца cancelled»): двухшаговый путь `cancelled → кастом-active
(un-cancel, счётчики НЕ ре-декрементятся) → cancelled` возвращал лимит второй
раз. Итоговое правило проще и сильнее:
- **слой чтения** `status_registry.custom_edges`: рёбер ИЗ cancelled-роли НЕ
  БЫВАЕТ — терминальный статус терминален, ровно как в builtin-графе (из
  cancelled/returned/no_show выходов нет и не было). Закрывает и cancel→cancel,
  и un-cancel-обход одним правилом;
- **эффекты** `apply_custom_effects`: cancel-блок (restore+unredeem+reversal)
  пропускать, если `src_desc` тоже cancelled-роли (пояс+подтяжки для прямых
  вызовов);
- **редактор** `status_manager`: sources/targets раздельно — отменённые не
  предлагаются источником, у кастом-отмены нет блока «Führt zu» (молчаливо-
  мёртвая галочка хуже отсутствующей); save-эндпоинт тоже не хранит такие рёбра.

Деньги двойного не боятся уже сейчас: `record_revenue/reversal` идемпотентны по
`(source, source_ref)` — фикс касается только склада/лимита/ваучера.

### 1.3 PII-purge резервов: литерал вместо реестра

`promotions/tasks.py:204` держит активных клиентов по литералу
`["pending","confirmed"]` — клиент, чей единственный резерв стоит в кастом-
active статусе, считался бы неактивным → PII вычищен при живой сделке. Строкой
ниже stays уже на `active_statuses_for("stay")`. Фикс: →
`active_statuses_for("reservation")`.

### 1.4 Сырые коды встроенных статусов Reservation в панелях

У `Reservation.status` НЕТ choices; читаемые подписи живут в
`transactions._RESERVATION_STATUS_LABELS` (используются только в билдере
транзакций). Оба панельных фолбэка — `label_of` в `status_manager`
(`getattr(model, "STATUSES", [])`) и `transition_rules._status_display` — для
reservation отдадут сырые `pending`/`fulfilled`.

Фикс: хелпер `transactions.builtin_status_labels(kind)` (dict STATUSES, для
reservation — `_RESERVATION_STATUS_LABELS`) + оба фолбэка через него.

### 1.5 Устаревшие комментарии

`normalize_status_defs`/`normalize_status_edges` («kind ∈ order/booking/stay»),
докстринг `status_manager` («(order/booking/stay)») — привести к факту.

## 1b. Дополнения воркфлоу-разведки (6 разведчиков + адверсариальная сверка)

### 1.6 Зеркала эффектов job/ticket (паритет с builtin-путём)

- **job**: `commit_stock` висит на литерале `t.dst == "done"` → кастом done-роль
  («QK bestanden») закрыла бы заявку БЕЗ списания Teile. Фикс: в
  `apply_custom_effects` вход в done-роль для job зовёт `jobs.services.commit_stock`
  (он идемпотентен — гард `stock_committed`; повторный builtin-done безопасен).
  Возврат склада при cancel НЕ делаем — builtin-отмена job его тоже не делает
  (обратной функции нет; паритет).
- **ticket**: builtin-отмена стопит рассрочку (R10e, `InstallmentPlan`) — кастом-
  cancel должен тоже (иначе beat продолжит списания отменённого билета). Фикс:
  ветка ticket в cancel-блоке эффектов (идемпотентно: гард STATUS_ACTIVE).

### 1.7 Роль done у ticket освобождала бы место (асимметрия attended)

`ROLE_DEFAULT_FLAGS["done"]` не даёт blocks_capacity, а builtin `attended` —
done, но место ДЕРЖИТ. Свой «завершённый» статус билета вёл бы к перепродаже.
Фикс: `def_from_role` получает `kind`; ticket+done → blocks_capacity=True.

### 1.8 Re-save редактора терял продвинутые флаги

`status_manager_save` пересобирает КАЖДЫЙ деф через `def_from_role` → флаги,
выставленные через site_config API (`counts_in_reports` у отеля — PMS-кейс),
слетали при любом сохранении редактора. Фикс: для существующего кода с
НЕИЗМЕНЁННОЙ ролью — сохранять сохранённый деф (обновляя label), не дефолты роли.

### 1.9 varchar(20) на ВСЕХ шести моделях vs код ≤40 в normalize

Кастом-код длиннее 20 символов («warten_auf_ersatzteile») сохранялся в конфиг,
рисовался на доске, а `apply()` падал DataError 500. Дыра пред-существует у всех
kind. Фикс БЕЗ миграции: кламп кода до 20 в `normalize_status_defs`,
`normalize_status_edges._code` и `_slug` редактора (согласованно — рёбра
продолжают матчиться с дефами).

### 1.10 Ещё литералы «активных» (та же дыра, что 1.1/1.3)

- `promotions/services.py` max_per_customer: резервы клиента считаются по
  литералу pending/confirmed → кастом-active обходит лимит на клиента;
- витринно-кабинетные СЧЁТЧИКИ: `digest.py` (bookings_today/arrivals_today),
  `dashboard.py` (_stays_today), `sales_page.py` (Anreisen/Termine heute) —
  фильтруют `Model.ACTIVE_STATUSES` → сделка в кастом-статусе выпадает из
  «Heute»/дайджеста. Меняем ТОЛЬКО места с ACTIVE_STATUSES-литералом; фильтры
  по одиночному STATUS_CONFIRMED (Abreisen/Im Haus) — семантика, не occupancy.
- верификация отзывов has_booked/has_stayed/has_ticket: исключение отменённых —
  литеральные наборы → билет в кастом-cancel статусе оставался «верифицированным
  покупателем». Новый хелпер `cancelled_statuses_for(kind)` (builtin danger ∪
  кастом-cancel) + три файла reviews.

### 1.11 Правила переходов (Вариант A) прятали кастом-кнопки

Правило, сохранённое ДО создания кастом-статуса, — whitelist целей из src; новая
кастом-цель в него не входит → кнопка скрыта. Хуже: `normalize_transitions`
валидирует по builtin-кортежу и ВЫЧИЩАЛ кастом-код из правила при каждом
сохранении настроек (класс W7a). Фикс — разграничение слоёв: правила Варианта A
управляют ТОЛЬКО builtin-целями; кастом-цели всегда видимы (их курирует сам
status-manager). `keep_target(kind=...)` пропускает кастомы; `editor_rows`/
`save` панели правил не предлагают/не хранят кастом-цели. Danger-флаг кнопки —
из дескриптора (`resolve`), кастом-отмена красная (pipeline.DANGER_TARGETS
заморожен на импорте и кастомов не знает).

### 1.12 Per-app экраны: сырые слаги статусов

`jobs/list`, `jobs/detail`, тикеты в `events/event_detail`,
`promotions/reservation_list` печатали `get_status_display`/`r.status` — для
кастома это сырой слаг, у Reservation и для builtin. Переведены на тег
`{% status_label %}`; тег получил фолбэк `builtin_status_labels` (Reservation
без choices). Кнопки-действия per-app экранов НЕ трогаем (§2: поверхность
действий — доска/Verkäufe, W10).

## 2. Осознанные квирки (документируем, НЕ трогаем)

- **beat-протухание резервов** (`expire_stale`) фильтрует builtin
  `pending/confirmed` — кастом-статус = ручной флоу владельца, авто-expire к
  нему не применяется (и НЕ должен: `apply(...,"expired")` из кастом-src без
  ребра владельца — IllegalTransition).
- **un-cancel рёбра** (builtin cancelled → кастом-active) не запрещаем: для
  jobs легитимно («переоткрыть»), у order/reservation склад/лимит при этом НЕ
  ре-декрементится — пред-существующее поведение живых kind (у booking/stay/
  ticket ёмкость динамическая — там корректно). Отдельное решение владельца,
  если понадобится.
- **post-event/`attended`-литералы** (письма отзывов, drip-напоминания,
  post-visit): кастом-статусы из цепочек выпадают — письма идут по builtin-пути.
- **job без выручки по статусу** — соответствует builtin (invoice-флоу); подпись
  роли «Abgeschlossen (Umsatz)» для job формально обещает лишнее — generic-метка.
- **per-app поверхности** (карточка заявки jobs, действия резервов в кабинете
  promotions) перечисляют builtin-кнопки литерально — из кастом-статуса действия
  доступны с доски/Verkäufe (W10: единая поверхность продаж); сервисные
  `cancel/expire` резервов из кастом-статуса — no-op (не двойной возврат).
- **публичный акцепт сметы** гейтится `status == quoted` — заявка, уведённая
  владельцем в кастом-статус до решения клиента, публично не принимается
  (владелец сам увёл её «с витрины»).
- **builtin-отмена билета НЕ сторнирует выручку, кастом-cancel — сторнирует**
  (если покинутый статус был revenue) — документированная семантика Варианта B
  («чистая ролевая» для кастомов, квирки builtin сохранены), как у живых kind.

## 3. Замки (характеризационные — ДО правок guard'ов)

1. Билет в кастом-active статусе ДЕРЖИТ место: capacity-guard даёт SoldOut;
   `seats_sold`/tier-суммы его считают (до фикса — красный).
2. Purge не выпиливает клиента с кастом-active резервом (до фикса — красный).
3. `custom_edges` дропает cancel↔cancel рёбра (все 3 конфигурации:
   custom→builtin-danger, builtin-danger→custom, custom→custom).
4. `apply_custom_effects` с src cancelled-роли НЕ зовёт restore/unredeem
   (monkeypatch-юнит; revenue-ветка не затронута).
5. Редактор: 200 + save для job/ticket/reservation; у reservation подписи
   встроенных статусов читаемые (не `pending`).
6. e2e job: new → кастом (через отредактированные рёбра) → done через
   `apply()` — путь доски; эффекты по роли.
7. Golden-эталоны normalize БЕЗ изменений (ключи те же, SM-2b уже расширил).

## 4. Порядок

Один инкремент, БЕЗ миграций: замки (красные там, где дыры) → фиксы 1.1–1.5 →
локальный гейт (ruff целиком + apps/core+events+promotions+jobs + golden +
i18n_gap) → стенд Playwright (создать статус для Tickets из Abläufe, увидеть
на доске, перевести карточку) → push → зелёный CI → FF-мерж. Новых msgid не
ожидается (ROLE_LABELS/редактор generic уже переведены) — проверить i18n_gap.

## 5. Ссылки

FB-3 B: `fb3-variant-b-full-plan-2026-07-12.md` (модель дескриптора §2).
SM-2b: `sm-single-mode-plan-2026-08-10.md`. PMS-переводы guard'ов на
`counted_statuses_for`: build-log 2026-07-27/28.
