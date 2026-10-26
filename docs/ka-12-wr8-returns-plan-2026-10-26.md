# KA-12 WR-8 (E1.5) · Rücksendung pro Position (2026-10-26)

Сценарий B8 (`ka-5a-waren-2026-10-23.md`): клиент вернул часть заказа (одна футболка из трёх,
вторая с дефектом). Сегодня есть только статус `returned` на ВЕСЬ заказ: весь остаток назад на
склад, вся выручка сторно. Поштучного возврата нет.

## Решение
- `OrderItem.returned_qty` / `restocked_qty` (PositiveInteger, default 0) — ⚠️ `orders/0026`,
  аддитивная; там же индекс `Order(pickup_slot, status)` из ревью WR-7.
- `apps/orders/returns.py::return_items(order, lines, method, tenant, user)`:
  1. Только выданный/отправленный заказ (`picked_up`/`shipped`).
  2. Товар: условный UPDATE `returned_qty` (ожидаемое значение из формы → двойной клик/гонка
     = «уже»), «wieder verkaufbar» — склад `+qty` через F() + леджер `kind=return`
     (source_ref `<item>:ret:<накопл.>`) + FEFO, `restocked_qty`. Повреждённое — без склада.
     Наборы (combo) — без склада (состав — снимок).
  3. Деньги — ТЕМ ЖЕ путём, что «Preisminderung» на карточке (`refunds.refund_partial`,
     reason=minderung): часть платежа картой или вручную, скидка сделки растёт, выручка
     сторнируется, выставленный счёт получает Rechnungskorrektur. Сумма = Σ цена штуки × qty.
     Без права `geld.korrektur` или «ohne Erstattung» — только товар (деньги вручную позже).
  4. Товар фиксируется ДО денег (физически вернулся); отказ/сбой денег — честное сообщение.
- `_restore_stock` (полный `returned`/отмена) возвращает только `qty − returned_qty`: уже
  обработанные штуки не попадут на склад второй раз, повреждённые — вообще.
- UI: форма «↩ Rücksendung» на карточке заказа (кол-во по строкам, чекбокс «wieder
  verkaufbar», способ возврата из того же набора, что форма возврата).

## Не делаем (v1)
Статус `delivered` (6 реестров статусов — отдельно), НДС возврата по ставке СТРОКИ (Minderung
распределяет по ставкам сделки), RMA-номера, портал возврата для клиента.

## ECC-прогоны
Скиллы: database-migrations, error-handling, django-tdd. Агенты после кода: django-reviewer,
database-reviewer (миграция/индекс), security-reviewer (деньги/права), silent-failure-hunter.
