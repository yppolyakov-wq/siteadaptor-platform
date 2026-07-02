# E-7 Платёжный микс DACH — внутренняя часть (план, 2026-07-02)

> Приоритет №1 вне волн (аудит 2026-07-01: сквозной блокер 6 архетипов A1/A2/A4/A5/A6/A7/A9).
> Скоуп этого плана — ВНУТРЕННЯЯ часть (без внешних провайдер-аккаунтов), одобрена владельцем:
> `Order.payment_method` → Vorkasse/Überweisung → шов `payment_method_types` (Stripe).
> Нативные PayPal/Klarna direct/SEPA-мандаты — `external-integrations-backlog.md` (блокер
> владельца); БОЛЬШИНСТВО способов реально закрывается через Stripe payment_method_types.

## 1. Факт (разведка 2026-07-02)

- `Order.payment_state` (unpaid/paid/refunded) ЕСТЬ; `payment_method` НЕТ (ud-plan §7: UD1-1
  выставит поле в проекции Transaction, UI строит E-7 — этот план).
- Оплата заказов сейчас: (а) Stripe Checkout prepay АВТОМАТОМ при `orders_prepay` +
  `payments_enabled` + Connect + total>0 (`orders/public_views.py:568-585`; StripeError →
  тихий фолбэк на оплату при получении); (б) иначе оплата при получении. Выбора у клиента НЕТ.
- Stripe-сессия — ЕДИНАЯ точка `billing/connect.py::checkout_session` (без
  `payment_method_types` → дефолт Stripe Dashboard подключённого аккаунта); через неё идут
  orders, stays (G7 prepay), booking-депозит, events-билеты, Geschenkgutschein.
- Банковских реквизитов у бизнеса НЕТ нигде (Tenant/finance/Invoice-PDF) — для Vorkasse нужны.
- Настройки заказов — блок на `/dashboard/orders/` (`orders/views.py:302`, чекбокс
  `orders_prepay` автосабмитом в `templates/orders/order_list.html:32`).
- Checkout-форма (`cart.html` `#checkout-form`, поля см. `ua3-1-buybox-plan §2.1`) — honeypot
  `website`, rate-limit 5/600с; поля `payment` нет.

## 2. Разбивка (подзадачи-инкременты)

### E7-1 (M, ДВЕ миграции: tenants SHARED + orders TENANT) — поле метода + реквизиты + кабинет
- `Order.payment_method` — CharField(choices, blank, default "") — реестр:
  `on_site` (Barzahlung bei Abholung/Lieferung) · `stripe` (Online-Zahlung) ·
  `vorkasse` (Überweisung/Vorkasse); позже `paypal`/`klarna`/`sepa` (нативные). "" = легаси.
- Проставление в СУЩЕСТВУЮЩИХ флоу (без UI): Stripe-redirect-ветка → `stripe`;
  обычная ветка → `on_site`. Существующие заказы остаются "".
- `Tenant` += `vorkasse_enabled` (bool, default False), `bank_holder`/`bank_iban`/`bank_bic`
  (CharField blank) — SHARED-миграция. Реквизиты пригодятся и finance/Invoice-PDF (отложено).
- Кабинет `/dashboard/orders/` (блок настроек, где orders_prepay): чекбокс «Vorkasse
  (Überweisung)» + 3 поля реквизитов (сохранение тем же POST-обработчиком настроек);
  guard: vorkasse активна только при заполненном IBAN. Список заказов — бейдж способа.
- Гейт: `apps/orders/` + `apps/tenants/` тесты; новые: проставление метода в обоих флоу,
  сохранение настроек, guard IBAN.

### E7-2 (M) — пикер способа на checkout + Vorkasse-флоу
- ДО правок — характеризационный паритет-замок checkout-формы (точный набор полей, как в UA3):
  один способ → пикер НЕ рендерится, POST без `payment` → поведение байт-в-байт прежнее.
- Доступные способы (хелпер, напр. `orders/payments.py::available_methods(tenant)`):
  `on_site` всегда; `stripe` при prepay+payments+Connect; `vorkasse` при
  `vorkasse_enabled`+IBAN. >1 → radio `payment` в checkout-форме (cart.html).
- `checkout`: разбор POST `payment` (валидация по доступным; дефолт = текущее поведение:
  stripe-ветка если сконфигурирована, иначе on_site); `vorkasse` → БЕЗ Stripe-redirect,
  `payment_method="vorkasse"`, payment_state остаётся unpaid.
- Подтверждение `/bestellung/<code>/` + письмо `order_created`: при vorkasse — блок
  реквизитов (Kontoinhaber/IBAN/BIC, Verwendungszweck = reference_code, сумма).
  Письмо владельцу — пометка «Vorkasse, ждём оплату».
- Гейт: паритет-замок + orders-сьют; новые: пикер рендерится только при >1, выбор vorkasse
  создаёт заказ без redirect и с реквизитами в письме/подтверждении, невалидный POST
  `payment` → как дефолт (не падаем).

### E7-3 (S) — шов Stripe `payment_method_types` (сразу 6 архетипов)
- `Tenant.stripe_payment_methods` (JSONField list, default []) — уже в SHARED-миграции E7-1
  (одна миграция tenants на весь трек).
- `connect.checkout_session(...)` += опц. `payment_method_types` (не передаём при пустом —
  текущее поведение); прокинуть из tenant во ВСЕ вызовы (orders/stays/booking/events/gift).
- Кабинет (блок платежей): чекбоксы card/paypal/klarna/sepa_debit + подсказка «способ должен
  быть активирован в Stripe Dashboard» (иначе Stripe вернёт ошибку — ловим StripeError как
  сейчас, фолбэк не ломается).
- Гейт: юнит на прокидывание параметра (мок Stripe), пустой список = параметр отсутствует.

### E7-4 (отложено, следующий чекпоинт) — Vorkasse за пределами orders
- stays G7 (тарифы с предоплатой), booking-депозит, events — сейчас только Stripe;
  Vorkasse-вариант там = отдельное согласование UX (брони с дедлайном оплаты, авто-отмена).
  НЕ в этом батче; заметка в roadmap §Отложено.

## 3. Порядок/гейты
E7-1 → E7-2 → E7-3 одним батчем (связный срез; локальный гейт на каждый: ruff + pytest
затронутых модулей, миграции — `--create-db`; шаблонные правки — + core-замки), push стопкой,
один CI, FF-мерж по зелёному. Деплой владельцем ПОСЛЕ мержа (миграции tenants+orders).

## 4. Риски
- Checkout — денежный путь: паритет-замок ДО правок; дефолт без POST `payment` = текущее
  поведение (существующие тенанты не видят изменений, пока не включат способы).
- SHARED-миграция tenants — как billing (public-схема), деплой обязателен.
- `payment_method_types` с неактивированным в Stripe способом → StripeError: уже есть
  try/except-фолбэк в обоих флоу (orders/stays), поведение деградирует мягко.
- Verwendungszweck: только reference_code (без PII) — DSGVO-safe.
