# PMS-A «Стойка администратора» v1 — план

**Дата:** 2026-07-28 · **Статус:** одобрено рамкой «остальное делай» (владелец,
2026-07-27) · **Миграций НЕТ** (все поля уже на StayBooking).

Разведка (агент, файлы:строки в истории сессии): кабинетная форма «Add booking»
(calendar.html) сильно беднее публичной воронки, списков «сегодня» нет, отметки
оплаты на стойке нет. `book_stay` уже принимает ВСЁ (rate_plan/extras/adults/
children/rooms/voucher_code/note) — паритет достигается вьюхой+шаблоном.

## A1. Walk-in паритет (форма «Add booking» календаря)

- Поле `guests` → `erw`/`kinder` (как витрина; Kurtaxe считается по adults —
  сейчас двойное завышение по детям). Легаси-парс `guests` оставить фолбэком.
- `rate_plan`-select (только при активных тарифах; резолв как в
  `unterkunft_book`: невалидный pk → первый тариф).
- `<details>` «Mehr Optionen»: extras-чекбоксы (`extras.active_for("stays")`,
  снапшот с nights), `rooms` (число, дефолт 1), `voucher_code`, `note`
  (сейчас читается вьюхой, но поля в шаблоне НЕТ — латентный баг).
- `stay_create`: прокинуть всё в `book_stay`; **ловить `PromoInvalid`**
  (сейчас неверный промокод на стойке = 500).
- Ограничения G12 НЕ включаем (стойка выше витринных правил — осознанно).

## A2. Списки «Heute» (заезды/выезды/в доме)

- Новая вьюха `stays:today` `/dashboard/stays/heute/`: три блока —
  **Anreisen** (arrival=today, ACTIVE_STATUSES), **Abreisen** (departure=today,
  confirmed|fulfilled), **Im Haus** (arrival<today<departure, confirmed).
  Строка: гость · юнит/🚪номер · ночи · гости · оплата · статус-кнопки
  (`{% status_actions %}` тем же FSM-путём) + ссылка на карточку брони
  (`calendar?buchung=<pk>`).
- Входы: ссылка «📋 Heute» в шапке календаря; **виджет хоума** «Anreisen
  heute» в `core/dashboard.py::home_widgets` (паттерн Abholbereit: гейт
  `is_module_active("stays")` + `_safe`; value=заезды, hint=выезды,
  url=stays:today).

## A3. Оплата на стойке

- `stay_action` += `action="mark_paid"` (образец orders): `payment_state="paid"`
  (из none/pending), `update_fields`. Refund/Stripe-пути не трогаем.
- Кнопка «✓ Als bezahlt markieren» в блоке сумм `_booking_card.html`
  (гейт: не paid/refunded); работает из панели календаря и booking_detail.

## Тесты

- walk-in полный набор → поля/цена (surcharge тарифа, extras, дети);
  невалидный ваучер → message, не 500; легаси `guests` живёт.
- today: три выборки (граничные даты не попадают в чужие блоки).
- виджет: гейт модуля + счётчик.
- mark_paid: none→paid; refunded не перетирается.

Порядок: A1 → A3 → A2 (виджет последним). Один батч, один CI.
