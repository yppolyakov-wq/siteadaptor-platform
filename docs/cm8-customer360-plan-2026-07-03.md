# CM-8 — Карточка клиента 360° (план, 2026-07-03)

ID — каталог §3 (CM-8.1–CM-8.5). Разведка агентом, факты сверены (file:line
в транскрипте). База: CRM-деталь `/crm/<uuid>/` УЖЕ есть (брони/заказы/
лояльность/ваучеры/заметки); `account_data.py` уже агрегирует 11 разделов
для ЛК клиента — но с клиентскими ссылками, поэтому для кабинета — свой
сборщик `apps/crm/customer360.py` (owner-URL + суммы), вьюха остаётся тонкой.

## Слайсы

- **CM-8.1 (S) — KPI-шапка LTV.** Один запрос
  `customer.revenue_entries.aggregate(Sum/Count/Max("date"))` (RevenueEntry —
  единственный DB-агрегируемый источник, наполняют все 5 FSM) + счётчики
  orders/bookings/stays/tickets/jobs. KPI-строка в шапке detail.
- **CM-8.2 (M) — недостающие разделы.** Termine+Mehrfachkarten (booking),
  Übernachtungen (stays), Tickets (events), Aufträge (jobs), Rechnungen
  (finance) — readonly-карточки по образцу существующих, гейт
  `is_module_active`, fail-soft per-раздел; сборка в customer360.py.
- **CM-8.3 (S) — переписка.** `customer.conversations` (посл. N) со ссылкой
  в кабинетный inbox + бейдж telegram_link.
- **CM-8.4 (S) — отзывы.** `reviews.Review` НЕ имеет FK на Customer — матч
  по `email=customer.email` (только при непустом email, fail-soft).
- **CM-8.5 (M, опц.) — timeline взаимодействий** (слить события в ленту) —
  последним, по спросу.

Минимальный 360 = 8.1+8.2; полный = +8.3/8.4. Без миграций. Замки: KPI
считается из RevenueEntry; разделы появляются только при активном модуле;
отзыв без email не матчится; существующие блоки detail не тронуты.
