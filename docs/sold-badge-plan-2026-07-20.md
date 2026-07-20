# «Verkauft N diese Woche» — social-proof счётчики (план, 2026-07-20)

Одобрено владельцем («делаем», LS-4 v2). Принцип ЧЕСТНОСТИ (паттерн бейджа
времени ответа LS-4): показываем ТОЛЬКО при реальном сигнале — порог ≥ 5
продаж за 7 дней; меньше/нет данных → бейджа нет вообще. Без миграций.

## §1 Решение

- НОВЫЙ `apps/core/social_proof.py`::`sold_last_week(kind, obj) -> int|None`
  — per-kind счётчики за 7 дней, только committed-статусы:
  - product: Σ qty OrderItem заказов (status НЕ cancelled) за окно;
  - service: ServiceBooking confirmed/done за окно (по service);
  - stay: StayBooking confirmed+ за окно (по unit) — метка «gebucht»;
  - event: билеты paid за окно — метка «Tickets verkauft»;
  fail-safe try/except (None = нет бейджа), константа `SOLD_BADGE_MIN = 5`.
- Партиал `storefront/_sold_badge.html`: «🔥 {{ n }}× verkauft diese Woche»
  (stay/event — своя формулировка), рендер ТОЛЬКО при n ≥ порога.
- Врезка: детальные страницы 4 kind (единый detail.html — в зоне buybox/цены);
  карточки листингов НЕ трогаем (v1 — деталь; шум и N+1 на гридах).
- Тумблера нет в v1: бейдж сам гейтится порогом (виден только у ходовых
  позиций). Если владелец захочет прятать — follow-up чекбокс в настройках.

## §2 Риски

- N+1 нет: одна агрегация на детальную страницу.
- Никаких выдуманных чисел: только реальные строки заказов/броней committed-
  статусов; отменённые исключены. Окно ровно 7 дней.
- i18n: msgid по конвенции витрины + переводы en/tr/ru/uk.

## §3 Инкременты

1. social_proof.py + партиал + врезка в detail-контексты 4 kind + тесты
   (порог/окно/статусы/fail-safe) + i18n + докблок (этап B/C ТЗ — маркер
   «продано N» ✅; CLAUDE.md/task-catalog).
