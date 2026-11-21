---
name: sa-deals-money
description: Сделки и деньги siteadaptor-platform — шесть видов сделок (order, booking, stay, ticket, job, reservation), смена статуса через FSM, эффекты статусов, денежный контракт и фолио, возвраты, разбор сумм, способы оплаты, НДС, счета, корректуры и Anzahlung, Stripe (вебхук, Connect, идемпотентность), склад, письма по состоянию. Грузить ДО кода при любой правке fsm.py, transactions.py, status_registry.py, status_effects.py, money_contract.py, folio.py, refunds.py, money.py, payment_methods.py, vat.py, apps/finance, apps/billing/webhooks.py и connect.py, apps/inventory/services.py, чекаута и писем заказа.
metadata:
  origin: project
---

# Сделки и деньги: статусы, оплата, возвраты, счета, склад

Все единые точки — `docs/project-memory.md` §3; грабли целиком — `docs/pitfalls.md` §1 и
«SEC волны 1–4»; паттерны — `docs/references/patterns/state-machine.md` и соседи. Здесь — что
звать и на чём уже ошибались. Дата у грабли — последнее срабатывание.

## Когда грузить
До плана и до кода любой правки статусов сделки, оплаты, возврата, счёта, складского движения,
вебхука Stripe, чекаута и писем по сделке. Экраны кабинета — вместе с `sa-cabinet-screen`.

## Модель в пяти строках
- Шесть видов сделки сведены одним слоем: вид → модель, машина, поля —
  `apps/core/transactions.py::TRANSACTION_KINDS, model_for, sm_for, transaction_for`.
- Статус меняет только `StateMachine.apply()` (`apps/core/fsm.py::StateMachine`): переход
  считается от статуса В БД, в `atomic`, под блокировкой строки.
- Деньги сделки читаются одним чтением из книги платежей `DealPayment`
  (`money_contract.py::money_state` поверх `folio.py::rows, totals`), а не из полей сделки.
- Внешнее (Stripe, письма) — с ключом идемпотентности или `dedupe_key`; письма — после коммита.
- **Деньги, данные, закон — исключение из правила «без хотфиксов»: чинить сразу, но тем же
  циклом** (план → замки до кода → ревьюеры → зелёный CI → FF в `main`).

## Единые точки
**Статусы:**
- смена статуса с любой поверхности кабинета — `apps/core/transactions.py::apply_action`
  (внутри — проверка «возврат отменой — только владелец или бухгалтер» и `refund_on_cancel`);
  доступные действия — `allowed_actions_for`; виды с продажами — `kinds_with_sales`;
- машина и её отказы — `apps/core/fsm.py::StateMachine, Transition, IllegalTransition,
  PaymentRequired, GuestCheckedIn`; клиентские и системные пути зовут машину напрямую;
- роли и свои статусы — `apps/core/status_registry.py::BUILTIN, resolve, all_descriptors,
  active_statuses_for, counted_statuses_for, cancelled_statuses_for, stage_of, custom_edges`;
- эффекты по роли (выручка, сторно, склад) — `apps/core/status_effects.py::record_revenue_for,
  record_reversal_for, commit_stock_for, restore_stock_for, apply_custom_effects`.

**Деньги сделки:**
- чтение (итог, оплачено, возвращено, ждём, проведено) — `apps/core/money_contract.py::money_state,
  due, invoice_for`; карты состояний — `OPEN_STATES, PAID_STATES, REFUNDED_STATES`; запись
  «оплачено» — `settle_payment`, `settle_invoice_deal`, `record_job_balance`;
- книга платежей — `apps/core/folio.py::record, record_online, record_job_payment,
  ensure_opening, mark_refunded`; виды с книгой — `FOLIO_KINDS`, с датами — `DATED_KINDS`;
- возвраты — `apps/core/refunds.py::refund_on_cancel, refund_payment, refund_partial,
  refund_cancel_fee, reduce_price, overpaid_cents, would_refund, may_refund, needs_choice`;
  исход — `RefundResult` (разные исходы — разные тексты), показ — `flash`;
- суммы из форм — `apps/core/money.py::parse_amount, parse_money, to_cents, lenient_cents,
  MAX_FORM_AMOUNT` и поле `apps/core/form_fields.py::MoneyField`;
- способы оплаты и тип покупателя — `apps/core/payment_methods.py::METHODS, KINDS, available,
  normalize, pair_refused, picker_context`; карточка сделки — `apps/core/deal_card.py::card_context`.

**НДС, счета, корректуры, Anzahlung:**
- НДС сделки по позициям — `apps/core/vat.py::deal_vat, deal_components`; ставка из формы —
  `parse_rate, parse_rate_optional, RATE_CHOICES`;
- суммы по ставкам и строка от брутто — `apps/finance/totals.py::rate_groups, gross_line`
  (единственный пересчёт групп); итоги заказа — `apps/orders/totals.py::split_gross,
  order_totals`; итоги сметы — `apps/jobs/totals.py::quote_totals`;
- счёт из сделки, сторно, Gutschrift — `apps/finance/services.py::issue_invoice_for_deal,
  invoice_from_order, invoice_from_stay, invoice_from_booking, invoice_from_ticket,
  create_storno, create_credit, manual_credit`; из сметы — `apps/jobs/services.py::quote_to_invoice`;
- Anzahlungsrechnung — `apps/finance/advance.py::create_advance_invoice, lock_deal,
  sync_advance_paid, on_advance_paid, settle_for_final, cancel_unpaid_for_deal, mail_storno`;
- Offene Posten и банк — `apps/finance/bank.py`; срез UStVA — `apps/finance/ustva.py`;
  PDF — `apps/core/documents.py::document_language, money, doc_date`.

**Stripe:**
- вебхук — `apps/billing/webhooks.py::stripe_webhook, handle_event` (один эндпоинт на события
  платформы и connected-аккаунтов); замок секрета — `apps/billing/checks.py::stripe_webhook_secret_set`;
- Connect — `apps/billing/connect.py::connected_checkout_session, installment_checkout_session,
  refund, charge_off_session, application_fee_cents` (шов `payment_method_types` — там же);
- оплата заказа — `apps/orders/payments.py::mark_order_paid, order_checkout_url` (там же
  единственный путь «адрес плательщика из Stripe → `Customer.email`»).

**Заказ, брони, склад, письма:**
- заказ — `apps/orders/services.py::create_order`; чекаут и отказ —
  `apps/orders/public_views.py::checkout, _refused`; правка — `apps/orders/editing.py`;
  возврат товара — `apps/orders/returns.py::return_goods, return_items`;
- запись — `apps/booking/services.py::book, book_many, create_manual`; область блокировки —
  `apps/booking/occupancy.py::lock_scope`; номер — `apps/stays/services.py::assign_room`;
  резервация акции — `apps/promotions/services.py::reserve, purchase, cancel, expire`;
- **склад — единственный путь** `apps/inventory/services.py::record_movement,
  apply_manual_movement, consume_fefo, restore_fefo, receive_lot, produce`; резерв из сметы —
  `apps/jobs/services.py::commit_stock, release_stock`; закупки — `apps/inventory/purchasing.py`;
- письма — `apps/notifications/services.py::notify` (единственное создание `Notification`,
  `get_or_create` по `dedupe_key`, отправка после коммита); письма заказа —
  `apps/orders/notifications.py::enqueue_order_email`; задачи — `apps/core/jobs.py::idempotent_task`.

## Нельзя
- Присваивать `obj.status = …` или писать статус через `update()` — только `apply()`; из кабинета —
  только `apply_action` (иначе отмена меняет статус, а деньги остаются у бизнеса).
- Считать «оплачено / возвращено / к оплате» своей формулой мимо `money_state` и книги платежей;
  читать книгу для вида вне `FOLIO_KINDS`; метить ручную строку как `stripe`.
- Разбирать суммы через `float`, `int()` или `type=number` (в de/ru «12,50» приходит пустым) —
  только `parse_amount` / `MoneyField` и `Decimal`; ставку НДС — только `parse_rate`.
- Заводить вторую копию пересчёта групп НДС рядом с `rate_groups`.
- Двигать остатки мимо `apps/inventory/services.py`.
- Слать `.delay()` из `on_transition` без `transaction.on_commit`.
- Доверять `metadata`, `client_reference_id`, адресу и числам из вебхука без сверки аккаунта.
- Отдавать наружу закупочные цены; создавать `Notification` мимо `notify`.

## Грабли
Stripe и вебхуки:
- «Stripe не ответил» ≠ «Stripe отказал»: при таймауте или обрыве захват НЕ откатывать,
  владельцу «проверьте в Stripe»; откат — только при явном отказе (`InvalidRequestError`,
  `CardError`, `PermissionError`, `AuthenticationError`) · посл. 2026-10-24.
- Ключ идемпотентности = суть операции: полный возврат — на платёж, частичный — на
  НАКОПЛЕННУЮ сумму, иначе Stripe вернёт прежний частичный ответ · посл. 2026-10-24.
- Вебхук идемпотентен: сначала искать строку по intent (иначе повтор рождает ложную
  «переплату»); упавшая обработка снимает ключ дедупа, иначе оплата не попадёт в книгу
  · посл. 2026-10-24.
- Источник события — часть авторизации: Connect-виды только при
  `event.account == tenant.stripe_connect_id`, платформенные — только без `account`, деньги —
  только при `payment_status == "paid"`, числа — из своей таблицы; без
  `STRIPE_WEBHOOK_SECRET` вебхук отвечает 503 (замок `billing.E001`) · посл. 2026-11-01.
- Адрес плательщика из вебхука — данные отправителя: только из оплаченного события своего
  аккаунта, strip, ≤254, без управляющих знаков, `validate_email`; писать только в ПУСТОЙ
  адрес, клиента по адресу не искать · посл. 2026-11-21.

Статусы и гонки:
- `apply` идёт в `atomic` с блокировкой строки: `.delay()` без `on_commit` уходит воркеру до
  коммита и читает старый статус · посл. 2026-11-02.
- Проверки — под блокировкой; применение после внешнего вызова — снова под блокировкой с
  повторной проверкой (отмена или счёт могли случиться между) · посл. 2026-10-24.
- Идемпотентны «писатели» ≠ идемпотентна операция: `скидка += X` повторяется при каждом
  ретрае — проверять «уже применено с этим ключом» под блокировкой ДО изменения · посл. 2026-10-24.
- Два документа на одних деньгах — один порядок замков: сначала сделка, потом документ
  (`apps/finance/advance.py::lock_deal`), иначе взаимная блокировка вебхука и кнопки;
  синк вторичного документа — fail-soft с логом · посл. 2026-10-24.
- Блокировка ресурсов до `book()` — вся область `lock_scope` одним запросом в порядке pk,
  иначе встречный дедлок · посл. 2026-10-26.

Суммы и НДС:
- Счёт из брутто-сделки считать тем же путём, что сделку (`split_gross`, `gross_line`):
  «от нетто» расходится на цент (45,00 € при 19 %) · посл. 2026-10-24.
- НДС округлять ПО ГРУППЕ ставки; проживание в счёте — одной строкой; Kurtaxe вне налога,
  допы отеля — 19 %, а не 7 % проживания · посл. 2026-08-26.
- Пересчёт существующей сделки берёт СНИМОК тарифа и цены на сделке, снижение — от
  сохранённого итога, а не по сегодняшним тарифам · посл. 2026-11-03.

Возвраты:
- «Возвращено» ставить, только когда вернули ВСЁ, включая доплату остатка отдельным платежом;
  иначе повтор ответит «уже возвращено» · посл. 2026-10-24.
- Решение «вернуть / удержать» фиксировать в момент отмены, повтор — только по снимку; гость
  не переигрывает отмену владельцем; денежный шаг после коммита — в try · посл. 2026-10-24.
- Сторно читает исходную запись и вычитает уже сторнированное (Minderung, удержание); при
  нескольких ставках — по записям, каждая своей ставкой · посл. 2026-10-24.

Склад:
- Строки сметы пересоздаются каждым Save — возврат склада считать по леджеру (ровно
  списанное), а не по строкам · посл. 2026-08-25.
- Движения ручной правки заказа — без `source_ref`: дедуп съест повтор · посл. 2026-08-20.

Письма и чекаут:
- Любой отказ после `create_order` возвращает введённое и ответы через `_refused`;
  обязательные поля проверять ДО расчёта и брони склада · посл. 2026-11-21.
- Письма — по разу и по состоянию: догонять по «адрес есть и совпадает» + текущий статус, а
  не по флагу «записал сейчас»; дубли гасит `dedupe_key`; «created» ставить ДО авто-confirm
  · посл. 2026-11-21.
- Письмо об ошибке денег — ключ на причину и сумму; «не платите» по сторно — только для
  неоплаченного документа и на адрес, куда он ушёл · посл. 2026-10-24.

## Что гейтить
- `uv run python scripts/preflight.py`; локально `apps/billing/tests/test_tasks.py` — с `--ignore`.
- Статусы, книга, возвраты: `apps/core/tests/test_fsm.py`, `apps/core/tests/test_folio.py`,
  `apps/core/tests/test_money_invariant.py`, `apps/core/tests/test_d6_0b_money_input.py`,
  `apps/core/tests/test_partial_refund.py`, `apps/core/tests/test_refund_roles.py`.
- Stripe: `apps/billing/tests/test_webhooks.py`, `apps/billing/tests/test_sec_d_webhook_account.py`.
- Счета: `apps/finance/tests/test_mixed_vat_invoice.py`,
  `apps/finance/tests/test_b2_8b_advance_invoice.py`; заказ и письма:
  `apps/orders/tests/test_fb33_m2i34_checkout.py`, `apps/orders/tests/test_fb33_m2i7_payer_email.py`.
- Сквозной «сделка → выручка → счёт» — `apps/booking/tests/test_golden_termine.py` (ловит цент,
  которого не видят модульные); стенд покупателя — `scripts/golden_paths.py`.

## Агенты ECC
`django-reviewer` — каждый срез; `security-reviewer` — вебхук, ввод сумм, права на возврат;
`silent-failure-hunter` — любой путь денег и внешний вызов (широкие `except`, fail-soft);
`database-reviewer` — блокировки, порядок замков, миграции. Промпт — `docs/review-checklist.md`.
