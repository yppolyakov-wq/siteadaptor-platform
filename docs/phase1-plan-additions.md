================================================================================
FILE: `docs/phase1-plan-additions.md`
================================================================================

# Phase 1: дополнения и изменения

Этот документ — слой улучшений поверх `phase1-plan.md`. Он описывает, что добавляется или меняется в каждом спринте на основе анализа существующих сервисов BOLTCAD (ProcessCRM, TaskPlanner, Deals).

Phase 1 удлиняется с 12 до примерно 13 недель за счёт этих улучшений. Это окупится в Phase 2–3.

## Sprint 1: Foundation — три критичных дополнения

### 1.1 Audit-модуль с первого дня

Текущий план откладывает audit на Phase 3. Это ошибка — audit данные нельзя backfill'ить.

Создать `apps/core/audit/`:

```python
# apps/core/audit/models.py — SHARED schema
class AuditEvent(TimestampedModel):
    tenant_schema = models.CharField(max_length=100, db_index=True, blank=True)
    actor_type = models.CharField(max_length=20, choices=[
        ('user', 'User'), ('system', 'System'),
        ('cron', 'Cron'), ('integration', 'Integration'),
    ])
    actor_id = models.UUIDField(null=True, blank=True)
    actor_display = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=50, db_index=True)
    resource_id = models.CharField(max_length=100, db_index=True)
    changes = models.JSONField(default=dict, blank=True)
    diff_summary = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['tenant_schema', '-created_at']),
        ]
```

Подключить к двум событиям в Sprint 1: создание/обновление Tenant (Django signals) и login/logout/password_change (allauth signals). Остальные сервисы добавят свои события по мере появления.

Полная спецификация: `docs/references/patterns/audit-log.md`.

### 1.2 Cursor pagination utility

Добавить в `apps/core/pagination.py` с самого начала. Используется в API эндпоинтах с Sprint 3.

Полная спецификация: `docs/references/patterns/cursor-pagination.md`.

### 1.3 SoftDeleteMixin как стандарт

Стандартизировать pattern soft-delete во всех моделях с первого дня. Применяется к Product, Promotion, Customer, Reservation сразу при их создании.

Полная спецификация: `docs/references/patterns/soft-delete.md`.

### 1.4 Outgoing webhooks scaffold

Создать `apps/integrations/webhooks/` с моделями `OutgoingWebhook` и `WebhookDelivery`. Реализация отправки появится в Phase 2, но модели и admin готовы.

Полная спецификация: `docs/references/patterns/webhook-hmac-signing.md`.

## Sprint 2: Catalog — замена импорта

### 2.1 4-step CSV import wizard вместо django-import-export

Текущий план использует django-import-export как one-shot. Заменить на 4-шаговую state machine: `uploaded → mapped → previewed → running → completed | failed`.

Стоимость: +3 дня к Sprint 2. Окупается мгновенно — Phase 2 нужен этот же wizard для Shopify/WooCommerce import.

Полная спецификация: `docs/references/patterns/csv-import-wizard.md`.

### 2.2 FileRef envelope для Product.images

Зафиксировать форму массива:

```python
# Product.images формат с Sprint 2:
# [{
#   "id": "uuid",
#   "url": "https://...",
#   "alt": {"de": "...", "en": "..."},
#   "mime_type": "image/jpeg",
#   "size": 123456,
#   "is_primary": false,
#   "sort_order": 0
# }]
```

Когда в Phase 3 появится централизованный файловый модуль с S3 presign — мигрировать тривиально.

## Sprint 3: Promotions & Reservations — три дополнения

### 3.1 Anti-oversell вместо select_for_update

Использовать pattern conditional UPDATE из Deals вместо явной блокировки транзакции:

```python
rows = Promotion.objects.filter(
    id=promotion_id,
    available_quantity__gte=quantity,
).update(
    available_quantity=F('available_quantity') - quantity,
)
if rows == 0:
    raise OutOfStock()
```

Полная спецификация: `docs/references/patterns/anti-oversell.md`.

### 3.2 Формальная state machine для Promotion и Reservation

Не оставлять переходы статусов разрозненными методами. Завести явную таблицу разрешённых переходов.

Полная спецификация: `docs/references/patterns/state-machine.md`.

### 3.3 metadata JSONField на всех runtime-моделях

Добавить `metadata = models.JSONField(default=dict, blank=True)` на:
- Reservation
- Publication (Sprint 4)
- Channel (Sprint 4)
- Notification (Sprint 6)

Стоимость нулевая, спасает от ALTER TABLE в Phase 2-3.

## Sprint 4: Publishing — idempotent publications

### 4.1 dedupe_key в Publication

Добавить:

```python
class Publication(TimestampedModel):
    # ... existing fields ...
    dedupe_key = models.CharField(max_length=200, unique=True, db_index=True)
    # формат: 'publish:{promotion_id}:{channel_id}'
    attempts = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
```

Без этого каждый retry создаёт дубль публикации во внешний канал.

Полная спецификация: `docs/references/patterns/notification-dedupe.md` (раздел "Publication idempotency").

### 4.2 BasePublisher с audit callback

Каждая публикация — audit-событие (`publication.published`, `publication.unpublished`, `publication.failed`). Подключить через signal или прямой вызов `audit_event()` в сервисе.

## Sprint 5: Aggregator — три дополнения

### 5.1 Cursor pagination в feed

Использовать utility из Sprint 1.

### 5.2 Anti-spam reorder

После основной выборки feed-листингов пройти и переставить так, чтобы не было более 2 акций одного tenant'а подряд. Прямой port из Deals.

### 5.3 Magic-link auth для customer

Заменить email/password регистрацию customer'а на чистый magic-link: один email с одноразовой ссылкой, ни паролей, ни verification flow.

Полная спецификация: `docs/references/patterns/magic-link-auth.md`.

### 5.4 Facets endpoint

`/aggregator/{city}/facets/` возвращает counts по категориям/брендам/диапазону цен для активных листингов города. Простой SQL с COUNT GROUP BY по AggregatorListing.

## Sprint 6: Notifications & Billing — четыре дополнения

### 6.1 NotificationEvent.dedupe_key UNIQUE с первого дня

```python
class Notification(TimestampedModel):
    # ... existing fields ...
    dedupe_key = models.CharField(max_length=200, unique=True, null=True, blank=True, db_index=True)
    related_resource_type = models.CharField(max_length=50, blank=True)
    related_resource_id = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=20, default='normal')
    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
```

Формат dedupe_key: `promo_match:{subscription_id}:{promotion_id}`, `trial_ending:{tenant_id}:{days_left}`, `reservation_confirmed:{reservation_id}`.

Полная спецификация: `docs/references/patterns/notification-dedupe.md`.

### 6.2 Web Push с первого дня

Добавить `PushDevice` модель и web push отправку через `pywebpush` с VAPID-ключами. Без мобильного приложения, через Service Worker в браузере.

```python
class PushDevice(TimestampedModel):
    customer = models.ForeignKey('subscriptions.Customer', related_name='push_devices', on_delete=models.CASCADE)
    endpoint = models.TextField()
    keys_p256dh = models.TextField()
    keys_auth = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [['customer', 'endpoint']]
```

Обработка 410 Gone от push provider'а → `is_active=False`, не ретраить.

### 6.3 Idempotent Celery wrapper

Завести thin-wrapper над `@shared_task`, который проверяет dedupe_key до выполнения:

```python
# apps/core/jobs.py
from celery import shared_task
from django.core.cache import cache

def idempotent_task(*args, **kwargs):
    def decorator(fn):
        @shared_task(*args, **kwargs)
        def wrapped(dedupe_key=None, **task_kwargs):
            if dedupe_key:
                lock_key = f'job_lock:{dedupe_key}'
                if not cache.add(lock_key, '1', timeout=3600):
                    return {'skipped': True, 'reason': 'duplicate'}
            return fn(**task_kwargs)
        return wrapped
    return decorator
```

Применять ко всем задачам с риском двойного запуска: notify_subscribers, publish_to_channel, send_trial_reminder.

### 6.4 Trial reminder events с dedupe

`trial_ending:{tenant_id}:3d`, `trial_ending:{tenant_id}:1d`, `trial_expired:{tenant_id}` — все с unique dedupe_key. Не отправит дважды, даже если cron сработает повторно.

## Summary: список новых файлов/моделей в Phase 1

| Sprint | Новые apps | Новые модели | Новые utilities |
|---|---|---|---|
| 1 | `apps/core/audit/`, `apps/integrations/webhooks/` | `AuditEvent`, `OutgoingWebhook`, `WebhookDelivery` | `apps/core/pagination.py`, `apps/core/models.SoftDeleteMixin`, `apps/core/audit.audit_event()` |
| 2 | `apps/imports/` | `ImportJob`, `ImportRow` | `apps/imports/processors/` (handlers по resource_type) |
| 3 | — | (доп. поле `metadata` на Reservation) | `apps/promotions/state_machine.py` |
| 4 | — | (доп. поля на Publication: dedupe_key, attempts, next_retry_at, metadata) | `BasePublisher.publish_with_audit()` |
| 5 | — | `MagicLinkToken` (или просто Redis-cache, см. pattern) | `apps/aggregator/feed_reorder.py` (anti-spam) |
| 6 | — | `PushDevice`, (доп. поля на Notification) | `apps/core/jobs.idempotent_task` |
