# FB-3 «Вариант B» — ПОЛНОЦЕННЫЕ пользовательские статусы (через роли)

**Дата:** 2026-07-12 · **Ветка:** `claude/admin-simplification-handoff-dfawis`
**ID:** FB-3 Вариант B (расширение FB-3; Вариант A уже в проде)
**Статус:** DRAFT — план полной реализации. Решение владельца: «делать полноценно».

Источник истины по связям: разведка 2026-07-12 (исчерпывающая карта литеральных
завязок; см. чат). Вариант A (скрытие переходов поверх фикс-набора) — `docs/fb3-status-
engine-plan-2026-07-12.md`. Здесь — как снять ограничение «фикс-набор» БЕЗОПАСНО.

---

## 1. Что значит «полноценно» и почему это большой рефактор

«Полноценно» = владелец может **создать СВОЙ статус** (напр. «Beim Lieferanten»,
«In QK», «Wartet auf Kunde»), поставить его между существующими, дать имя, и заказ/бронь
реально в нём живёт. Проблема: статус в коде — не ярлык, а узел, к которому привязаны:

- **Деньги** — `record_revenue`/`record_reversal` (VAT 19% booking/event, 7% stay);
  идемпотентность по `source_ref` (у возврата `f"{id}:return"`).
- **Склад** — `_restore_stock`+inventory-леджер (order cancel/returned), `commit_stock`
  (job done), promo `available_quantity` (reservation).
- **Ваучеры** — `unredeem_voucher` (cancel).
- **Anti-oversell** — `ACTIVE_STATUSES` читается ЛИТЕРАЛЬНЫМ кортежем ВНУТРИ атомарных
  guard'ов: `booking/services.py:78`, `stays/availability.py:40`, `events/services.py:127`.
  Ошибка в роли custom-статуса → **двойное бронирование** или фантомная занятость.
- **Стадия доски** — `pipeline.PIPELINE[kind][status]→stage`; неизвестный → молча `intake`.
- **Отображение** — `get_status_display` (Reservation/Promotion без choices!), бейджи в
  ~25 шаблонах, `_status_display` в редакторе.
- **Beat/дашборды/отчёты** — десятки `.filter(status="confirmed"/"active"/…)` в
  `*/tasks.py`, `core/digest.py`, `stays/reports.py` (`_COUNTED` считает `fulfilled`, а
  `ACTIVE_STATUSES` — нет → **ДВЕ ортогональные оси**).

**Критические асимметрии (почему одного enum ролей мало):**
1. `Ticket.attended` — «done», НО занимает место (в `ACTIVE_STATUSES`); `booking/stay.fulfilled`
   — «done» и ОСВОБОЖДАЕТ. → нужен отдельный флаг `blocks_capacity`, независимый от стадии.
2. Отчёт занятости считает `fulfilled` (прошедшие), oversell — нет. → флаг `counts_in_reports`
   ≠ `blocks_capacity`.
3. `returned` делает reversal (выручка была списана на picked_up), `cancelled` — нет
   (до выдачи выручки не было). → «отменять ли выручку» зависит от того, был ли ПОКИНУТЫЙ
   статус revenue-recognized.

**Вывод:** одного `role`-enum недостаточно. Дескриптор статуса = **роль + 3-4 ортогональных
флага**. Полноценный B = перевести все литеральные завязки на дескриптор-производные
множества, СОХРАНИВ поведение встроенных статусов байт-в-байт, и только потом впустить
кастом-статусы в ту же машинерию.

## 2. Модель дескриптора статуса

Для КАЖДОГО (kind, status) — встроенного и кастомного — дескриптор:

```
StatusDescriptor:
  code: str                 # "confirmed", "beim_lieferanten"
  role: str                 # intake | active | done | cancelled   (семантика побочек)
  stage: str                # intake | in_progress | done | terminal (колонка доски)
  blocks_capacity: bool     # входит в ACTIVE_STATUSES (anti-oversell)
  counts_in_reports: bool   # входит в _COUNTED (отчёты занятости/выручки)
  is_danger: bool           # красная кнопка + не прячется в Вариант A
  builtin: bool             # встроенный (нельзя удалить) vs кастом
```

Роль → побочки при ВХОДЕ в статус (дефолты, наследуются кастомом):
- `intake` — ничего;
- `active` — блокирует ёмкость, письмо «подтверждено», без выручки;
- `done` — `record_revenue` (VAT/сумма — per-kind резолвер) + commit_stock (goods/parts),
  `blocks_capacity`/`counts_in_reports` по флагам;
- `cancelled` — restore stock + unredeem voucher + `record_reversal` ЕСЛИ покидаемый статус
  был revenue-recognized (reuse точного `source_ref`), исключение из отзывов.

Реестр встроенных дескрипторов **выводится из текущих констант** (PIPELINE + ACTIVE_STATUSES
+ DANGER_TARGETS + `_COUNTED`) — так, чтобы Phase 0 доказала эквивалентность.

## 3. Фазы (каждая — отдельный инкремент с замками; риск нарастает — чекпоинты владельца)

### Phase 0 — фундамент + ЗАМКИ ПАРИТЕТА (без изменения поведения) ⬅ старт
- `apps/core/status_registry.py`: `StatusDescriptor` + `BUILTIN[kind][status]` для всех 6
  kind (+ reservation/promotion), заполнены ТОЧНО под текущие PIPELINE/ACTIVE/DANGER/_COUNTED.
- Характеризационные замки: для каждого kind
  `{s: d.stage} == PIPELINE[kind]`,
  `{s: d.blocks_capacity} ⇒ set == ACTIVE_STATUSES`,
  `{s: d.is_danger} ⇒ ∩ DANGER_TARGETS`,
  stays `counts_in_reports ⇒ == _COUNTED`.
  → доказывает, что дескриптор описывает текущий мир 1:1. **Полностью безопасно/реверсивно.**

### Phase 1 — перевод ЧТЕНИЯ на дескриптор-производные (эквивалентно, built-in only)
- Аксессоры `status_registry.active_statuses(kind, tenant=None)`,
  `stage_of(kind, status)`, `is_danger(status)`, `counted_statuses(kind)`.
- Заменить литералы: `Booking/StayBooking/Ticket.ACTIVE_STATUSES` → property/функция,
  `pipeline.stage_for`/`PIPELINE` → реестр, `pipeline.DANGER_TARGETS`/`is_danger` → реестр,
  `stays/reports._COUNTED` → реестр. Все ~10 oversell-запросов зовут `active_statuses(kind)`.
- Built-in поведение байт-в-байт (Phase 0 замки + существующие FSM/oversell тесты — зелёные).
  Кастом-статусов ещё НЕТ (tenant=None). **Риск средний (широкая замена), но чистая
  эквивалентность под замками.** Чекпоинт владельца после Phase 1.

### Phase 2 — диспетчеризация ПОБОЧЕК по роли (built-in only, эквивалентно)
- `on_transition` каждой машины: вместо `if t.dst == "fulfilled"` → по роли ВХОДИМОГО
  статуса + role покидаемого (для reversal). Per-kind резолвер выручки (VAT+сумма+source_ref)
  и склада вынести в таблицу. Reversal reuse `source_ref`.
- Замки эффект-паритета: для каждого легального перехода каждого kind — тот же набор
  побочек, что сегодня (revenue/reversal/stock/voucher/email вызваны с теми же аргументами).
  Существующие state_machine-тесты + новые. **Риск ВЫСОКИЙ (деньги/склад) — но built-in
  граф неизменен, только путь диспетчеризации.** Чекпоинт владельца.

### Phase 3 — хранение кастом-определений + впуск в ёмкость
- `site_config["status_defs"][kind] = [{code,label,role,stage,blocks_capacity,
  counts_in_reports,after}]` + `normalize_status_defs` (whitelist role/stage; slug code;
  запрет коллизий с built-in; presence-minimal → golden-паритет).
- `active_statuses(kind, tenant)` = built-in ∪ кастом-active-коды тенанта → oversell-guard'ы
  видят кастом. `stage_of`/`is_danger`/`counted` учитывают кастом. Кастом ещё без своих
  переходов (узел существует, но недостижим) — безопасно.

### Phase 4 — кастом-ПЕРЕХОДЫ (граф тенанта поверх FSM)
- `site_config["status_transitions"][kind]` — рёбра к/от кастом-узлов, заданные владельцем.
  `apply()` сверяется с ОБЪЕДИНЁННЫМ графом (built-in FSM ∪ tenant-рёбра). Валидация: кастом
  можно вставлять только МЕЖДУ узлами так, что побочки роли согласованы (нельзя «перепрыгнуть»
  revenue/cancel-семантику). Побочки — по роли ВХОДИМОГО узла (Phase 2).
- Замки: apply legality с кастом-рёбрами; НЕЛЬЗЯ обойти oversell/revenue. **Самый тонкий узел
  (apply был «жёстким полом»).** Чекпоинт владельца.

### Phase 5 — кабинетный редактор
- Менеджер статусов на экране (заказ/бронь/услуга): создать статус (имя+роль+стадия+позиция),
  редактор переходов расширен на кастом-узлы (Вариант A UI переиспользуется). Guard'ы UWG/…
  не при чём.

### Phase 6 — отображение и периферия
- `get_status_display`-фолбэк для кастом (в т.ч. Reservation/Promotion без choices),
  бейджи в шаблонах через тег (роль→цвет), стадия доски, beat-задачи (reminders/post-visit/
  expire) — фильтры по РОЛИ, дашборды/отчёты — по дескриптор-множествам.

## 4. Что НЕ трогаем / гарантии
- Встроенные статусы, их коды, FSM-граф, суммы/VAT — поведение байт-в-байт (Phase 0/2 замки).
- `record_revenue` идемпотентность (source_ref) — кастом-cancel reuse точный ref.
- Каждая oversell-точка (§1) — под замком «до/после рефактора одинаковое множество».

## 5. Оценка и порядок
6 фаз, зависимые → строго последовательно. Phase 0-1 — фундамент/эквивалентный рефактор
(безопасно, реверсивно). Phase 2 — деньги (высокий риск, максимум замков). Phase 3-4 —
впуск кастома. Phase 5-6 — UI/периферия. **Чекпоинты владельца после 1, 2, 4.** Миграций
НЕТ (всё в site_config + код). Старт — Phase 0 (чистая добавка).

## 6. Альтернатива (если объём/риск не устроит на чекпоинте)
«B-lite» — кастом-статус ТОЛЬКО как промежуточный, приколотый к роли соседнего узла
(наследует его флаги, НЕ порождает новых побочек). Даёт «Beim Lieferanten» безопасно за
~2 фазы вместо 6. Полноценный граф с произвольными ролями — это фазы 2-4 выше.
