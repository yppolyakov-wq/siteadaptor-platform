# KA-12 GA-7 · Демо ресторана: зал из столов (2026-10-26, без миграций)

Продолжение `ka-12-w4-gastro-plan-2026-10-26.md`. Сегодня демо `restaurant` держит один пул
«Tisch» на 40 мест — GA-1…GA-6 (правило «sofort / Gruppenanfrage», места, автоподбор,
комбинации, Tischplan) в демо не видны.

## Решение
- Сидер `_seed_kit_modules`: ресурс-спека += `seats`, `min_seats`, `zone`, `sort_order`,
  `bookable_online`, `parts` (имена столов-частей → `occupancy.set_parts` вторым проходом,
  единственный писатель состава).
- Кит `restaurant`: 8 столов в зонах «Saal» (T1–T5: 2/2/4/4/6) и «Terrasse» (T6–T8: 2/4/4,
  T8 — «nur vor Ort») + «Tisch 3+4» (комбинация, 8 мест); правило столов
  `booking.tables = {instant_max: 4, online_max: 10}` (Р-2: в демо включено).
- Брони: поле кита `table_bookings` `[(день, "HH:MM", стол, имя, гостей, large)]` — сегодня и
  завтра, одна на комбинации, одна Gruppenanfrage (pending, `is_large_party`); без поля —
  прежние две брони на первый ресурс. Кафе остаётся пулом (как сейчас).
- `SEEDER_VERSION` 9 (меняется код сидера).

## Замки
Кит: 9 столов, у комбинации 2 части и 8 мест, правило в конфиге, брони есть, Tischplan
демо-тенанта отдаёт плитки двух зон.

## ECC
django-tdd; django-reviewer.
