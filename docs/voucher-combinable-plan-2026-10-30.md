# Промокод и другие скидки — «не суммируются» по умолчанию (2026-10-30)

**Решение владельца:** по умолчанию скидки не суммируются; в настройках ваучера — опция
«Mit anderen Rabatten kombinierbar».

## Правило

- `Voucher.combinable` (⚠️ миграция `loyalty/0008`, аддитивная, default False). Решение владельца:
  **существующие коды при обновлении помечаются combinable** (data-миграция `loyalty/0009`) — они
  ведут себя как прежде; правило действует на коды, выпущенные после деплоя.
- Без флага промокод считается только от части суммы **без** другой скидки:
  - заказ/корзина — строки по акции (SF-4b), количественной акции (PR-3), акции из `custom_lines`;
  - бронь услуги — цена услуги по акции (Extras остаются базой кода);
  - проживание — номер с авто-скидкой (G4/Lücken/акция; услуги остаются базой).
- Всё уже со скидкой → `VoucherError("not_combinable")`, код НЕ гасится; в корзине — подсказка
  «Dieser Code gilt nicht für bereits reduzierte Artikel.».
- Сертификат с остатком (Wertgutschein) — оплата, а не скидка: действует на всю сумму всегда.
- Ранняя цена билета (T-3) и смета (jobs) — цена, а не скидка: не затронуты.

## Где

Одна точка: `promotions.services.eligible_base` → `spend_voucher(…, discounted_cents)` и
`preview_discount(…, discounted_cents)` (превью = списанию). Вызовы: `orders.services.create_order`,
`orders.public_views` (корзина), `booking.services.book`, `stays.services.book_stay`.

## Замки

`apps/promotions/tests/test_voucher_combinable.py` (8): дефолт False, только нескидочная часть,
флаг — вся сумма, всё со скидкой → отказ без погашения, сертификат всегда, превью = списание,
чекаут заказа с акционной строкой с флагом и без.

## ECC-прогоны

Скиллы: `django-patterns`, `database-migrations` (BooleanField default — мгновенно в PG 11+).
Агенты: `django-reviewer` (деньги) — после диффа.
