# KA-12 Волна 3 · батч 1 «Деньги без миграций» (E1.6–E1.12) — 2026-10-24

План — агент planner, сверка с кодом. Источник — `ka-12-master-plan-2026-10-23.md` §1 E1,
`ka-mc-money-contract-plan-2026-10-23.md` (пробелы MC-E8/H6/Z9/J1/T1).

Замечание: strict-xfail на MC-* в коде нет (`test_money_invariant.KNOWN = {}`), ID только в
докстрингах — поэтому каждый пункт начинается с нового замка.

## Коммит 1 — E1.12 + E1.6 (`apps/core/refunds.py`)
- **E1.12** флаг `no_refund` у своего статуса роли cancelled: `site_config.status_defs`
  (presence-minimal, только при True и роли cancelled → golden целы), `StatusDescriptor.no_refund`,
  чекбокс «ohne Erstattung» в редакторе статусов; `wants_refund` → False. Отмена рассрочки
  возвращает КАЖДУЮ оплаченную долю (условный UPDATE доли paid→refunded, ключ идемпотентности на
  intent доли; сбой доли — откат только её, письмо владельцу, FAILED); билет «refunded», когда
  оплаченных долей не осталось. Прежний MANUAL больше не возникает.
- **E1.6** депозит картой + остаток «bezahlt» вручную: карта возвращает депозит, сумма остатка
  (`paid − online`) показывается владельцу сообщением и письмом (dedupe `refund-rest:…`).
  Учёт наличного возврата (`refunded_cents`, MC-E8) — батч 2.

## Коммит 2 — E1.7 + E1.9 + E1.10
- **E1.7** ручной билет без оплаты: выручка не при `confirmed`, а при `attended`
  (`events/state_machine.py`, зеркало `status_effects.record_revenue_for`). Vorkasse/счёт не трогаем.
- **E1.9** депозит заявки не меняется после оплаты / вне new|quoted (`jobs/views.py`); принятие
  сметы — одна `atomic` с `select_for_update` Job, повторная проверка `quoted`, `spend_voucher`, `apply`.
- **E1.10** MC-T1: `deposit` убрать из `UNPAID_HOLD_STATES` билета (удержание не снимает билет с
  оплаченной Anzahlung); MC-J1: заявка с неоплаченным депозитом — строка Offene Posten; письмо-
  напоминание об остатке билета за N дней (dedupe по notify). Онлайн «Rest bezahlen» — батч 2.

## Коммит 3 — E1.8 (MC-Z9)
Сертификат с остатком в счёте из stay/booking/order — не «Rabatt», а предоплата («Gutschein …»),
база НДС = полная цена. ⚖️ Вопрос владельцу/Steuerberater: проводить ли продажу Mehrzweckgutschein
выручкой (§ 3 Abs. 15 UStG) — журнал не трогаем до решения.

## Батч 2 (миграции)
E1.11 фолио `core.DealPayment` (несколько платежей на сделку: intent, сумма, способ, возврат) +
онлайн «Rest bezahlen», MC-E8 `refunded_cents`, точное `voucher_paid_cents` для stay/booking/
order/ticket, E1.4 (Anzahlungs-/Abschlags-/Schlussrechnung), E1.5 (частичный возврат + Gutschrift).

## Риски
Двойной возврат долей (claim + ключ на intent) · повтор писем (dedupe) · перенос выручки билета
(идемпотентность по `source_ref`) · GoBD (проведённое не правим — только сторно).
