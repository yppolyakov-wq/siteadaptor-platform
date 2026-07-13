# FB-3 + FB-4b — движок статусов заказа/услуги/брони с правилами переходов

**Дата:** 2026-07-12 · **Ветка:** `claude/admin-simplification-handoff-dfawis`
**ID:** FB-3 (правила переходов) + FB-4b (переименование статусов service/stay — расширение FB-4a)
**Статус:** DRAFT на согласование (нужно решение владельца по развилке §3)

Источник: ТЗ `docs/cabinet-feedback-tz-2026-07-10.md`. Разведка кода — проведена
(отчёт в чате 2026-07-12): FSM — код, не данные; побочки привязаны к КОНКРЕТНЫМ кодам
статуса; anti-oversell зависит от `ACTIVE_STATUSES=(pending,confirmed)`.

---

## 1. Что уже есть (не переделываем)

- **FB-4a (готово, в main):** переименование ОТОБРАЖАЕМЫХ имён статусов заказа —
  `site_config["status_labels"]["order"]`, тег `{% status_label obj kind %}`,
  панель «⚙️ Status-Namen anpassen» в списке заказов, presence-minimal + golden-паритет.
- **W5 (готово):** переименование/порядок/скрытие КОЛОНОК доски
  (`site_config["board"]`, `pipeline.resolve_columns`) — стадии intake/in_progress/done/terminal.
- **FSM (`apps/core/fsm.py`):** `StateMachine.apply()` — единственная точка смены статуса;
  `transitions` — class-level список `Transition(src,dst,event)`; `allowed_targets(src)`.
  6 машин: order / booking(Termin) / stay / event+ticket / job / reservation.

## 2. Ключевой факт разведки (почему нельзя «свободный редактор»)

Побочные эффекты в `on_transition` каждой машины ветвятся по ЛИТЕРАЛЬНЫМ кодам dst:
- `cancelled`/`returned` → возврат склада (`_restore_stock` + inventory-леджер) + un-redeem ваучера;
- `fulfilled`/`picked_up`/`shipped` → `record_revenue` (VAT 19% booking/event, 7% stay);
- `done` (job) → `commit_stock` (расход деталей); `quoted` → письмо-Angebot; и т.д.

Плюс **anti-oversell** читает `ACTIVE_STATUSES=(pending,confirmed)` напрямую в запросах
доступности (`booking/availability.py`, `stays/public_views.py`). И `pipeline.PIPELINE`
жёстко маппит каждый статус → стадию доски.

**Вывод:** новый/переназначенный статус в свободном редакторе → молча пропущенные или
неверно сработавшие финансовые/складские эффекты, либо oversell. Свободный граф —
большой рискованный рефактор (развязать побочки от кодов статуса на «семантические роли»).

## 3. РАЗВИЛКА ДЛЯ ВЛАДЕЛЬЦА (нужно решение)

Владелец в чате спрашивал про «полноценные НОВЫЕ статусы… создание и управление
статусами». Два варианта реализации:

### Вариант A — «правила поверх фиксированного набора» (РЕКОМЕНДУЮ, безопасно)
Набор статусов остаётся кодовым (менять нельзя), но владелец управляет:
1. **Именами** статусов (FB-4a — расширить на service/booking + stay = FB-4b).
2. **Правилами переходов** — какие из УЖЕ-ЛЕГАЛЬНЫХ переходов показывать/прятать и в
   каком порядке (напр. скрыть «no_show», оставить только «confirmed→fulfilled»).
   Опасные/терминальные (cancel) — не прячем (чтобы не запереть карточку).
3. **Именами колонок** доски (W5, уже есть).

Хранение: `site_config["transitions"] = {kind: {src: [подмножество dst]}}`, нормируется
против реального `allowed_targets` FSM (что не легально — отбрасываем). `apply()`
по-прежнему сверяется с FSM → «протухшее» правило безвредно. Побочки не трогаем ВООБЩЕ.

**Плюс:** даёт запрошенный UX «настроить, какой статус в какой может перейти» без риска.
**Минус:** нельзя ДОБАВИТЬ свой промежуточный статус (напр. «Beim Lieferanten»).

### Вариант B — «настоящие свои статусы» (риск, большой объём — отдельная волна)
Владелец добавляет свой статус, но ОБЯЗАН назначить ему «семантическую роль»
(active / cancelled / fulfilled / neutral) — по ней срабатывают побочки и маппинг на
стадию. Требует: развязать все `on_transition` от литералов на роли, поле роли на
каждой машине, миграции конфигурации, аккуратные замки на каждую побочку (склад,
выручка, ваучеры, oversell). Оценка — самостоятельная волна, НЕ в этот инкремент.

**Моя рекомендация:** делаем **A** сейчас (закрывает 90% запроса «управление статусами
и переходами»), **B** — отдельным треком, если после A владельцу всё ещё нужны
собственные промежуточные статусы.

## 4. План реализации Варианта A (по инкрементам)

### A-0. FB-4b: переименование статусов на service/booking + stay (быстро)
- Расширить `_STATUS_LABEL_KINDS` в `siteconfig.py`: добавить `booking` (pending/confirmed/
  fulfilled/cancelled/no_show) и `stay` (те же). `normalize_status_labels` уже generic по kind.
- Тег `{% status_label obj "booking" %}` / `"stay"` — уже generic, только вызвать в шаблонах:
  `booking/calendar.html`, `stays/calendar.html`, `stays/booking_detail.html`.
- Панель переименования — вынести из `orders/order_list.html` в переиспользуемый партиал
  `tenant/_status_labels_panel.html` (kind-параметр); показать в booking/stays хабах.
- Замки: паритет-тест normalize (golden), сохранение/рендер/сброс на 3 kind.

### A-1. Хранение правил переходов
- `siteconfig.py`: `_TRANSITION_KINDS` (order/booking/stay — те, что видит владелец на доске),
  `normalize_transitions(raw, sm_map)` — для каждого (kind,src) оставить только dst ∈
  `SM.allowed_targets(src)`; отбросить пустые/неизвестные; presence-minimal (ключ
  `transitions` только когда непусто). Wire в `normalize()`.
- Golden-паритет: `test_normalize_golden` — новый ключ не должен ломать байт-в-байт
  (materialize только при непустом). Идемпотентность.

### A-2. Применение правил в отображении переходов
- `apps/core/transactions.py::allowed_actions_for(kind, status)` — добавить опц.
  `tenant`/config; пересечь `SM.allowed_targets` с подмножеством из конфига (для показа),
  сохранив порядок конфига; НЕ трогать danger/terminal (всегда показывать cancel).
- `apps/core/templatetags/workflow.py::status_actions` — прокинуть tenant из контекста.
- `orders/views.py::order_detail` — bespoke-кнопки заказа (в шаблоне) фильтровать тем же
  подмножеством (или свести на generic партиал — отдельная микро-задача).
- `apply()`/`kanban_action`/FSM — НЕ меняем (жёсткий пол).

### A-3. Кабинетный UI редактора правил
- Партиал `tenant/_status_rules_panel.html`: на kind — строки «из статуса X можно в: [чекбоксы
  легальных Y] + порядок». Дефолт = все легальные включены (= текущее поведение).
- Вьюха-писатель `save_transitions(tenant, request, kind)` — targeted-write
  `site_config["transitions"][kind]`, presence-minimal; сброс к дефолту = удалить ключ.
- Разместить рядом с панелью имён статусов (тот же экран настроек kind).
- Замки: сохранение/рендер/сброс; «скрытое правило не показывает кнопку, но apply всё равно
  разрешает легальный переход» (безопасность); «cancel не прячется».

## 5. Файлы (A)
- `apps/tenants/siteconfig.py` (normalize_status_labels расширить kinds; +normalize_transitions).
- `apps/core/transactions.py` (allowed_actions_for + config).
- `apps/core/templatetags/workflow.py`, `apps/core/templatetags/cabinet.py` (status_label уже готов).
- Вьюхи-писатели: `apps/orders/views.py` (есть save_status_labels — обобщить), booking/stays.
- Шаблоны: партиалы `_status_labels_panel.html`, `_status_rules_panel.html`; хабы booking/stays/orders.
- Замки: `apps/tenants/tests/test_normalize_golden.py`, `apps/core/tests/test_status_actions.py`,
  `apps/orders/tests/test_cabinet.py` (+ booking/stays аналоги).

## 6. НЕ трогаем (гарантия безопасности A)
Все `apps/*/state_machine.py` (`transitions`, `on_transition`); `ACTIVE_STATUSES`
(booking/stays/events models); `apps/core/pipeline.py` `PIPELINE`/`STAGES`;
`kanban_action`/`apply()` легальность.

## 7. Порядок / объём
A-0 (FB-4b) — маленький, самодостаточный, можно первым. A-1..A-3 — связный вертикальный
срез (хранение→показ→UI), один батч. Без миграций (всё в site_config). B — отдельная волна
по отдельному решению.
