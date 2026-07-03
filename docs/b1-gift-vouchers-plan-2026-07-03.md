# Идея B1 — Geschenkgutscheine на все архетипы (план, 2026-07-03)

ID — `task-catalog.md §3` (B1.1–B1.6). Первый «средний» одобренного стека.
Разведка агентом, факты сверены (file:line в транскрипте).

## 1. Что уже есть (G1 отеля — чистый реюз)

- `loyalty.GiftVoucher` (покупка/оплата/доставка) → после оплаты выпускает
  обычный `loyalty.Voucher` (discount_cents=номинал, max_uses=1);
  Stripe Connect Checkout (metadata kind=gift_voucher), webhook-выпуск
  идемпотентен (`gift.mark_gift_voucher_paid`), письмо gift_voucher.txt.
- Роуты `/gutschein/*` УЖЕ нейтральные (`storefront-gutschein[-buy|-ok]`),
  но вьюхи живут в `stays/public_views.py:583+` и гейтятся stays-модулем.
- Погашение кода — единый `promotions.services.redeem_voucher`
  (select_for_update + F(), double-redeem защищён). Принимают: orders,
  stays, events. НЕ принимают: booking (только абонементы), jobs.

## 2. Слайсы

- **B1.1 (S) — расгейтить покупку.** Gift-вьюхи → `apps/loyalty/public_views.py`
  (перенос 1:1), гейт: новый `ModuleSpec("gift")` в реестре (группа sell,
  recommended_for — широкий B2C-набор) И `payments_enabled+connect` (как было).
  Ссылка «Gutschein verschenken» — футер витрины (generic, при активном
  модуле+connect), не только stay_index. Характеризационный замок: отельный
  флоу 1:1 (паритет до/после переноса).
- **B1.2 (S) — booking принимает код.** Миграция: `voucher_code` +
  `discount_cents` на booking-модель (snapshot скидки, как у events);
  зеркало `_apply_voucher` (копия events/services.py:52, ВНУТРИ транзакции
  book(), паттерн redeem_voucher сохранить) + инпут кода в booking-форме
  (двухшаговый buybox — форма партиала `_buybox_service_*`).
- **B1.3 (S) — кабинет.** Список проданных GiftVoucher в кабинете loyalty
  (/promotions/vouchers/ рядом): покупатель/номинал/оплачен/погашен
  (voucher.used_count>0). Без новых моделей.
- **B1.4 (M) — un-redeem при отмене.** Новый сервис `unredeem_voucher`
  (декремент used_count, идемпотентный по снапшоту «был ли код») + вызовы в
  cancel/expire orders/stays/events/booking. Сейчас отмена сжигает ваучер —
  чинит корректность денег ВСЕХ купонов, не только gift.
- **B1.5 (M, ⚖️ РЕШЕНИЕ ВЛАДЕЛЬЦА) — остаток сертификата.** Сейчас
  сертификат 100 € на заказ 30 € сгорает целиком (discount_for капает,
  max_uses=1). Для DACH-Wertgutschein правильно вести `balance_cents`
  (частичное погашение, остаток живёт) — инвазивно (redeem/discount_for во
  всех 4 чекаутах). Вариант-минимум без кода: показать «Restbetrag verfällt»
  при покупке/погашении. Вопрос владельцу: делаем balance (M) или нотис (S)?
- **B1.6 (S, опц.) — jobs принимает код** (сметы Handwerker — по спросу).

Порядок: B1.1 → B1.2 → B1.3 (базовая ценность) → B1.4; B1.5 — после ответа.

## 3. Замки/тесты

B1.1: паритет отельного гутшайн-флоу; гейт по модулю gift (выкл → 404);
покупка у friseur-типа (не stays). B1.2: код в booking → скидка+snapshot,
double-redeem, невалидный/min_order. B1.3: список показывает
оплачен/погашен. B1.4: отмена возвращает use; двойная отмена не
декрементит дважды.

## 4. Не трогаем (реюз)

`loyalty.Voucher`, `redeem_voucher`, `discount_for`, `gift.py` целиком,
webhook-ветка billing, `connected_checkout_session`, шаблоны gift_voucher*.

## 5. B1.5 — решение владельца: (а) полноценный balance (2026-07-03)

Схема: `Voucher.balance_cents` (null = обычный промокод, поведение прежнее;
миграция loyalty/0003). Семантика Wertgutschein: `discount_for` = min(balance,
сумма); НОВАЯ единая точка чекаутов `promotions.services.spend_voucher(code,
base_cents)` — расчёт+списание ПОД ОДНОЙ блокировкой (закрывает гонку
«прочитал → списал», заодно сводит 4 копии _apply_voucher к одному вызову);
`unredeem_voucher(code, amount_cents)` возвращает остаток (FSM-хуки передают
снимок discount_cents). Выпуск gift: balance=номинал, max_uses=0 (многораз до
исчерпания), discount_cents остаётся как номинал для дисплея. Кабинет:
«Rest X €» у balance-ваучеров. Замки test_gift обновляются осознанно
(max_uses 1→0 + balance); новые: частичное списание/кап/исчерпание,
возврат остатка при отмене, legacy-промокоды не тронуты.
