# Telegram-канал в кампаниях — план v1

**Дата:** 2026-07-28 · **Статус:** очередь владельца «делай все», п.2.
Без миграций (TelegramLink/боты/notify-каналы уже есть).

## Рамка v1 (законно и без новых сущностей)

Telegram — **второй канал доставки той же кампании** тем же получателям:
consented-база (DOI-подтверждённый `marketing_opt_in`, не отписан, email есть)
∩ привязавшие бота (`TelegramLink.chat_id`). Согласие уже доказано (UWG §7
DOI), one-click отписка ставит `unsubscribed=True` и по построению глушит ОБА
канала; ссылка «Abmelden» включается и в Telegram-текст.

**Осознанно НЕ в v1:** клиенты «только Telegram» (без email) — им нужен
DOI-флоу внутри бота (`maybe_send_doi` требует email); команда /stop у бота.
→ v2 по спросу (external-independent, но отдельная волна).

## Врезки (обе идемпотентны — свой `…:tg` dedupe_key поверх get_or_create)

- `send_coupon_campaign`: после email-notify — `send_to_customer(customer,
  type="coupon_campaign", dedupe_key=f"coupon:<c>:<cust>:<code>:tg",
  text=subject + body_parts)`; функция сама no-op без привязки/бота.
- `send_campaign` (Newsletter): аналогично `campaign:<id>:<cust>:tg`.
- `recipient_count` НЕ меняем (те же адресаты, TG — дубль-канал).

## Тесты

- coupon: привязанный клиент → email + TELEGRAM-нотификация (dedupe :tg);
  без привязки → только email; повторный вызов → без дублей.
- newsletter: то же. Паттерн — telegram/tests/test_notify.py (_bot/_link).
