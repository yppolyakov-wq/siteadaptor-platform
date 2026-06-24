# R10 — План рассрочки (Ratenzahlung) для билетов событий

Статус: **в работе** (R10a — модель+график). Часть ретрит-бэклога R7+
(`retreat-archetype-plan.md` §4.1). Killer-фича WeTravel для дорогих ретритов
(1.5–3 k€): гость платит частями, бизнес получает деньги на свой Stripe-аккаунт
(Connect, вариант B — как остальные платежи событий).

## Решения владельца (2026-06-24)

1. **График — обе модели, per-event настройка** (`Event.installment_mode`):
   - `until_event` — первая доля (депозит) сейчас + равные списания, последнее
     за `installment_lead_days` дней до начала события;
   - `fixed` — фиксированное число равных ежемесячных списаний (3/6), первое сейчас.
2. **Сбой off-session списания (SCA / отказ карты)** — ретраи + письмо клиенту
   со ссылкой «подтвердить оплату» (on-session); **без авто-отмены билета**; после
   исчерпания попыток — эскалация владельцу (статус plan=`failed`, видно в кабинете).
3. **Отмена билета при активной рассрочке** — всегда **стоп будущих списаний**;
   возврат уже оплаченного — **вручную владельцем** в кабинете (без авто-refund).

## Архитектура

Деньги «клиент → бизнес» через connected account (как `events.payments`,
`billing.connect`). Off-session списания — сохранённый `PaymentMethod` (мандат),
полученный при первой оплате (`setup_future_usage=off_session`).

### Модель (R10a)
- **`InstallmentPlan`** (OneToOne→`Ticket`): `total_cents`, `count`, `status`
  (active/completed/failed/cancelled), `stripe_customer_id`,
  `stripe_payment_method_id` (мандат, заполняется в R10b). Свойства `paid_cents`/
  `remaining_cents`.
- **`InstallmentCharge`** (FK→plan): `sequence`, `due_date`, `amount_cents`,
  `status` (scheduled/paid/failed/refunded), `stripe_payment_intent`, `attempts`,
  `last_error`. Уникальность (plan, sequence).
- **`Event`** конфиг: `allow_installments`, `installment_mode`, `installment_count`,
  `installment_min_cents` (мин. сумма к рассрочке), `installment_lead_days`.

### График (R10a, чистая логика — `apps/events/installments.py`)
- `installments_available(event, total_cents, today, start_date)` — eligibility
  (включено + count≥2 + сумма ≥ min + хватает времени до события для `until_event`).
- `build_schedule(event, total_cents, today, start_date)` → список
  `{sequence, due_date, amount_cents}`. Суммы — равный сплит, остаток центов
  на первые доли (sum == total). Даты: `fixed` — помесячно от сегодня;
  `until_event` — равномерно между сегодня и `start − lead_days`.

## Подзадачи
- **R10a** ✅(тек.) — модель + конфиг + график + миграция + тесты (без Stripe).
- **R10b** — первый платёж + сохранение мандата (Checkout `setup_future_usage`,
  вебхук `event_installment_first` → создать plan/charges, отметить 1-ю долю paid).
- **R10c** — beat `charge_due_installments` (off-session `PaymentIntent`) + ретраи
  + письма (подтверждение/напоминание/успех/сбой со ссылкой на on-session оплату).
- **R10d** — кабинет (график/статусы/ручное списание/отмена плана) + витрина-выбор.
- **R10e** — стоп плана при отмене билета (R12) + демо/доки.

## Заметки
- Идемпотентность списаний — `dedupe_key` по charge.id; FSM статусов charge.
- Per-tenant обход в beat — как `events.tasks` (R9 drip).
- min/lead — гард и в `installments_available`, и в витрине (не предлагать, если рано).
