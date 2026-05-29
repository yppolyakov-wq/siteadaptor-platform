# Pattern: Notification Dedupe & Idempotency

Статус: Phase 1, Sprint 4 (Publication idempotency), Sprint 6 (Notification dedupe).
Ссылается из: `phase1-plan-additions.md` §4.1, §6.1, §6.3.

## Проблема

Триггеры дублируются штатно: воркер перезапустился и переисполнил задачу,
Stripe/Resend шлёт webhook 2–3 раза, cron сработал повторно, пользователь
дважды нажал кнопку. Без защиты получаем дубль письма/публикации во внешний
канал — это видит конечный клиент.

Защита двухуровневая: **БД-уникальность** (источник истины) +
**Redis-лок** (дешёвый ранний отсев до тяжёлой работы).

## Уровень 1: уникальный dedupe_key в БД

Каждое «доставляемое» событие несёт детерминированный ключ. UNIQUE-constraint
не даёт создать второе.

```python
# Notification (Sprint 6) — см. §6.1
class Notification(TimestampedModel):
    dedupe_key = models.CharField(max_length=200, unique=True, null=True,
                                  blank=True, db_index=True)
    related_resource_type = models.CharField(max_length=50, blank=True)
    related_resource_id = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=20, default="normal")
    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, default="pending")  # см. state-machine
    metadata = models.JSONField(default=dict, blank=True)
```

Форматы ключей (детерминированные, без таймстампов):

| Событие | dedupe_key |
|---|---|
| совпадение акции с подпиской | `promo_match:{subscription_id}:{promotion_id}` |
| подтверждение резерва | `reservation_confirmed:{reservation_id}` |
| напоминание о триале | `trial_ending:{tenant_id}:{days_left}d` |
| истечение триала | `trial_expired:{tenant_id}` |
| публикация в канал | `publish:{promotion_id}:{channel_id}` |

Создание — атомарно, дубль ловим на constraint:

```python
from django.db import IntegrityError

def enqueue_notification(*, dedupe_key, **fields):
    try:
        n = Notification.objects.create(dedupe_key=dedupe_key, **fields)
    except IntegrityError:
        return None  # уже поставлено — тихо выходим
    send_notification_task.delay(dedupe_key=dedupe_key, notification_id=n.id)
    return n
```

> ⚠️ Правило составления ключа должно покрывать «легитимный повтор». Если акция
> перепланируется и должна уведомить заново — включай версию/слот в ключ
> (`promo_match:{sub}:{promo}:{schedule_version}`), иначе второе уведомление
> будет ошибочно подавлено.

## Уровень 2: idempotent Celery wrapper (§6.3)

Отсекает повторный запуск задачи **до** тяжёлой работы, через `cache.add`
(атомарный SET-if-not-exists в Redis).

```python
# apps/core/jobs.py
from celery import shared_task
from django.core.cache import cache


def idempotent_task(*task_args, **task_kwargs):
    def decorator(fn):
        @shared_task(*task_args, **task_kwargs)
        def wrapped(dedupe_key=None, **kwargs):
            if dedupe_key:
                lock = f"job_lock:{dedupe_key}"
                # add() ставит ключ только если его нет → атомарный лок
                if not cache.add(lock, "1", timeout=3600):
                    return {"skipped": True, "reason": "duplicate"}
            return fn(**kwargs)
        return wrapped
    return decorator
```

Применять ко всем задачам с риском двойного запуска: `notify_subscribers`,
`publish_to_channel`, `send_trial_reminder`, `sync_aggregator_listing`.

```python
@idempotent_task(bind=False, max_retries=3)
def send_notification_task(notification_id):
    ...
```

> Redis-лок — оптимизация, не гарантия (TTL истекает, Redis можно потерять).
> **Гарантию даёт только UNIQUE в БД** + финальная проверка статуса перед
> отправкой во внешний канал: `if n.status != "pending": return`.

## Publication idempotency (Sprint 4)

`Publication` несёт `dedupe_key = "publish:{promotion_id}:{channel_id}"`,
`attempts`, `last_attempt_at`, `next_retry_at`. Публикация:

1. `get_or_create(dedupe_key=...)` — одна строка на (акция, канал).
2. Если `status == "published"` → выходим (уже опубликовано).
3. Публикуем во внешний канал, сохраняем внешний `external_id` в `metadata`.
4. Ретрай переиспользует ту же строку (инкремент `attempts`), **не создаёт
   новую** — поэтому повтор не плодит постов в канале.

Связка с retry-политикой по каналам — см. `phase1-plan-additions.md` §6.5.

## Чек-лист

- [ ] `dedupe_key` UNIQUE на Notification и Publication.
- [ ] Формат ключа покрывает легитимные повторы (версия/слот при необходимости).
- [ ] Создание ловит `IntegrityError` и тихо выходит.
- [ ] `idempotent_task` навешан на все рассыльные/публикующие задачи.
- [ ] Перед внешней отправкой — финальная проверка `status == pending`.
