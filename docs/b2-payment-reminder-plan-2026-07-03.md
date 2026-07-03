# Идея B2 — напоминание о незавершённой оплате (план, 2026-07-03)

ID — каталог §3 (B2.1–B2.3 + отложенный B2.4). Разведка агентом (file:line
в транскрипте). Ключевой факт: «бросил корзину/бронь ДО ввода email» не
ловится ничем (корзина только в сессии, email — на финальном POST) — зато
во ВСЕХ Stripe-доменах запись создаётся ДО оплаты с email на Customer и
не протухает: Order (stripe+unpaid+new), Booking (payment_state=pending),
StayBooking (pending), Ticket (pending+total>0). Письмо о СВОЕЙ
незавершённой сделке — transactional (Vertragsanbahnung): гейт как у
reminder'ов (`email and not unsubscribed`), без opt-in.

## Слайсы

- **B2.1 (S) — Orders.** `Order.payment_reminder_sent_at` (миграция) +
  beat-задача (окно [X…X+7д] от created_at, X=ORDERS_PAYREMIND_HOURS=24,
  фильтр payment_method=stripe, payment_state=unpaid, status=new) + письмо
  `order_payment_reminder` (DE=msgid+en.po) со ссылкой на
  `storefront-order` + НОВЫЙ мини-view «Jetzt bezahlen» (перегенерация
  Stripe Checkout из order_checkout_url — URL не хранится, генерится на
  лету) + кнопка на странице подтверждения при stripe+unpaid.
- **B2.2 (S) — Booking.** Зеркало: `payment_reminder_sent_at`, фильтр
  payment_state=pending + start__gt=now, письмо со ссылкой на
  `storefront-termin-ok` (депозит перегенерится deposit_checkout_url —
  кнопка на странице подтверждения).
- **B2.3 (S) — Stays + Tickets.** То же для StayBooking (arrival>=today)
  и Ticket (status=pending, total_cents>0).
- **B2.4 (⏸ отложено, UWG-серо) — настоящий cart-abandonment.** Требует
  захвата email до чекаута (CartLead) + DOI; в roadmap §Отложено.

Замки: письмо один раз (окно+флаг+БД-дедуп), фильтры не задевают
on_site/vorkasse (unpaid — норма) и прошедшие брони, «Jetzt bezahlen»
работает и 404 для оплаченного/чужого.
