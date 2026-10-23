# KA-W1 «Abholzeit» — план (пилот, батч C, 2026-10-23)

> Источник: `pilot-wave-plan-2026-10-23.md` §«Батч C». План — агент planner, сверен с кодом.

## Факты
- **Миграция не нужна.** `Order.pickup_slot` (DateTimeField null) есть с `orders/0001`;
  `create_order(pickup_slot=)` принимает, но **никто не передаёт** → Auftragsbuch всегда
  пуст, хотя витрина обещает «Zur Wunschzeit vorbestellen».
- Поле уже читают: `core/deal_card.py`, `core/transactions.py`, `core/zusatz.py`,
  `finance/services.py`; вкладка «Kalender» продаж включается сама с первым слотом.
- Часы: `apps/tenants/openinghours.py`, `Tenant.opening_hours_structured`
  `{"0": ["09:00","18:00"]}` (один интервал на день).
- Чекаут: `apps/orders/public_views.py`, ветка самовывоза после `delivery_choice.resolve`.

## Настройки (без миграции)
`site_config["pickup_slots"] = {"step": 30, "capacity": 0, "lead": 60, "days": 7}`,
`siteconfig.normalize_pickup_slots` (presence-minimal; step ∈ {15,30,60}, capacity
0..999 (0 = без лимита), lead 0..2880 мин, days 1..14; мусор → ключ снят). Нет ключа =
чекаут байт-в-байт прежний. UI — подблок в разделе ② `_payment_fields.html` с
сентинелом `sec_pickup_slots`, запись targeted (W6), предупреждение без часов работы.

## Модуль `apps/orders/pickup_slots.py`
`config(tenant)`, `slots_for(tenant, now)` (шаг от открытия, S ≥ now+lead,
S+step ≤ закрытия, закрытые дни пропускаются; занятость — один агрегат, статусы через
`cancelled_statuses_for`), `validate(tenant, raw, now)` — fail-closed: только значение
из сетки.

## Гонка
В atomic `create_order` при `pickup_slot and capacity`: `pg_advisory_xact_lock(hashtext(
"pickup:<schema>:<iso>"))` → пересчёт → `SlotFull` (откатывает склад/лимит акции).
Вьюха: сообщение «Dieses Zeitfenster ist gerade voll geworden…» + назад в корзину.

## Правила
Доставка — без слота (даже если в POST пришёл). Обязателен при включённой опции и
наличии слотов; слотов нет → «Zurzeit keine Abholzeiten verfügbar», заказ не
принимается. Заказ за столиком (QR) — без слота. v1 — только корзина; акция/предложение/
Anprobe — follow-up.

## Показ
Корзина (`<select>` с `<optgroup>` по дням, работает без JS), подтверждение, письма
клиенту/владельцу, карточка заказа (без дубля с deal_card), Auftragsbuch — сам.

## Замки (до кода)
без ключа — нет поля, `pickup_slot=None` · normalize (клампы/мусор/presence) · сетка
(lead, закрытие, выходной, DST, пустые часы) · validate (вне сетки/прошлое/мусор) ·
ёмкость (N заказов → слот исчез, отмена освобождает) · `SlotFull` откатывает склад ·
доставка игнорирует слот · показ в подтверждении/письмах/карточке · targeted-write
настроек · вьюха на `SlotFull`.

## Риски
ключ блокировки со схемой; aware-время и DST; кастом-статусы (SM-3); W0/W6 —
свой сентинел; включение блокирует чекаут без часов работы — предупреждать.
Вне v1: две смены в день, срок изготовления по товару, слоты вне корзины.
