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

### 1.4 Outgoing webhooks scaffold (DONE)

Создать `apps/integrations/webhooks/` с моделями `OutgoingWebhook` и `WebhookDelivery`. Реализация отправки появится в Phase 2, но модели и admin готовы.

Реализовано (SHARED-приложение): `OutgoingWebhook` (url, secret через `token_hex(32)`, event_types, is_active), `WebhookDelivery` (event_id как idempotency-ключ, status, attempts, next_retry_at), read-only-friendly admin, миграция `0001_initial`. Доставка/HMAC/ретраи — Phase 2.

Полная спецификация: `docs/references/patterns/webhook-hmac-signing.md`.

### 1.5 Инфраструктурный хардненинг конфига (DONE)

Реализовано в `config/settings/base.py` и моделях до старта спринтов — дешёвые правки, которые потом стоят дорого:

- **Redis-кэш + сессии в кэше.** Без явного `CACHES` Django падает на `LocMemCache` (не шарится между gunicorn-воркерами). Добавлен `CACHES` (Redis db `/1`); `SESSION_ENGINE = cache` — сессии больше не пишутся в БД shared-схемы на каждый запрос.
- **Celery result backend → Redis** (db `/2`, TTL 1 час) вместо `django-db`. Прежний бэкенд писал строку в Postgres на каждую задачу (рассылки, публикации) → bloat + write-нагрузка.
- **Персистентные соединения с БД:** `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS`. При schema-per-tenant каждый запрос делает `SET search_path`, пересоздавать соединение на каждый request дорого.
  - ⚠️ При вводе PgBouncer — только **session-pooling**; transaction-pooling несовместим с `search_path` арендатора. Зафиксировать в runbook деплоя.
- **Индексы на `Tenant`** (миграция `0002_tenant_indexes`): `(city, is_active)` — агрегатор; `(business_type, city)` — вертикальные порталы (см. 5.6); `(subscription_status, trial_ends_at)` — биллинг-cron (см. 6.5).

Распределение Redis db: `/0` — Celery broker, `/1` — cache+сессии, `/2` — Celery results.

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

**Требования к корректности (обязательны, не опциональны):**

- Conditional `UPDATE ... F()` атомарен на уровне одной строки в PostgreSQL READ COMMITTED — этого достаточно для анти-oversell остатка. **Дополнительная блокировка не нужна**, пока вся логика списания умещается в один `UPDATE` с условием `available_quantity__gte`. Если появится многошаговая логика (например, резерв + запись в связанную таблицу в одной бизнес-операции) — оборачивать в транзакцию с `SERIALIZABLE` и обрабатывать `serialization_failure` ретраем.
- **Тест на гонку обязан быть настоящим параллельным**, а не последовательными вызовами фабрик: `ThreadPoolExecutor` + `TransactionTestCase` (НЕ `TestCase` — он оборачивает каждый тест в транзакцию и маскирует гонки). Python-потоки тут валидны, т.к. ожидание идёт на стороне БД, а не под GIL.
- **DoD-критерий:** 100 параллельных резерваций на акции с `available_quantity=50` → ровно 50 успешных, 50 `OutOfStock`, итог `available_quantity=0`, ноль перепродаж.

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

### 4.1 dedupe_key в Publication — ОБЯЗАТЕЛЬНО В ЯДРЕ Sprint 4

⚠️ **Это не опциональное улучшение.** Раньше идемпотентность планировалась через wrapper из Sprint 6 (6.3), но публикация во внешние каналы и рассылки идут уже в Sprint 4. Webhooks от Stripe/Resend и сами воркеры доставляют/перезапускаются 2–3 раза штатно → без `dedupe_key` каждый retry создаёт дубль публикации, а агрегатор (Sprint 5), читающий из `Publication`, показывает акцию дважды. Поэтому `dedupe_key` + проверка идемпотентности (6.3 `idempotent_task`) **обязаны существовать к моменту первой реальной публикации**, т.е. внутри Sprint 4.

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

При >10k листингов на город live `COUNT GROUP BY` на каждый запрос дорог → кэшировать результат facets в Redis с TTL 60с (ключ `facets:{portal_id}:{city}`), инвалидация — по сигналу из 5.5. **DoD:** facets-эндпоинт < 500мс на топ-20 городов с 10k+ листингов.

### 5.5 Стратегия материализации AggregatorListing (обязательна)

`AggregatorListing` (SHARED) — денормализованный индекс акций. **Категорически нельзя** строить фид обходом схем арендаторов в цикле (`for tenant: with schema_context(...)`) — это N+1 по схемам и не масштабируется.

Правило обновления индекса:

- Источник истины — `Publication`/`Promotion` в tenant-схеме. На события `promotion_activated` / `promotion_ended` / изменение `Publication.status` вешается **сигнал → async-задача** `sync_aggregator_listing(tenant_schema, promotion_id)` (идемпотентная, через `idempotent_task`).
- Задача читает данные из tenant-схемы и upsert'ит одну строку `AggregatorListing` в shared-схеме. Никаких массовых обходов.
- Фид агрегатора читает **только** `AggregatorListing` — он самодостаточен (денормализованы title/city/category_slug/price/cover_image).
- Допустимая «свежесть»: ~30с (eventual consistency приемлема для каталога акций). Если очередь забита — деградация только в задержке появления акции, не в корректности.
- Полная пере-материализация (reconciliation) — отдельная beat-задача раз в ночь, чинит дрейф.

**Полнотекстовый поиск:** добавить в `AggregatorListing` поле `search_vector` (`SearchVectorField`, GIN-индекс) **сразу в Sprint 5**, заполнять в той же sync-задаче. Это снимает необходимость мигрировать схему потом и закрывает поиск «apfel» по заголовкам без внешнего движка. Elasticsearch/Meilisearch — явно Phase 2, если перерастём `tsvector`.

### 5.6 AggregatorPortal — шов под вертикальные/мультидоменные агрегаторы

**Решение:** в Phase 1 закладываем абстракцию портала, но поднимаем ровно один портал (главный домен). Полноценную мультидоменную операционку откладываем в Phase 2. Причина: дописать «агрегатор параметризован порталом» ПОСЛЕ хардкода «один глобальный агрегатор» — болезненный рефактор URL/запросов/кэша/sitemap/SEO; зарезервировать абстракцию сейчас — почти бесплатно.

```python
# apps/aggregator/models.py — SHARED schema
class AggregatorPortal(TimestampedModel):
    slug = models.SlugField(unique=True)              # 'main', 'baeckerei', 'metzgerei'
    name = models.CharField(max_length=200)
    # [] = все категории (глобальный портал); ['bakery'] = только булочные;
    # ['bakery', 'cafe'] = несколько выбранных вертикалей.
    category_filter = models.JSONField(default=list, blank=True)
    # null = все города; иначе — портал ограничен городом/городами.
    city_filter = models.JSONField(default=list, blank=True)
    default_locale = models.CharField(max_length=10, default='de')
    # Брендинг портала (логотип/цвета/домен) — используется со 2-й фазы.
    branding = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
```

Принципы, которые надо соблюсти уже в Phase 1, чтобы шов работал:

- **Все запросы фида идут через портал:** `listings = AggregatorListing.for_portal(portal)`, где метод применяет `category_filter` / `city_filter`. Глобальный портал = пустые фильтры. «Только булочные» / «все выбранные категории» ложатся в `category_filter` без изменений кода.
- **Кэш-ключи, sitemap, SEO-мета, facets — с префиксом `portal_id`** с самого начала.
- **Роутинг доменов (Phase 2):** django-tenants требует, чтобы каждый домен указывал на tenant. Публичные домены порталов (`baeckerei.de`, `metzgerei.de`) вешаются на **public-tenant** (несколько `Domain` на public-схему), нужный `AggregatorPortal` резолвится по `Host` в `urls_public` через middleware. TLS для произвольных доменов — Caddy **on-demand TLS** (уже в стеке).

**Объём Phase 1:** модель `AggregatorPortal` + `AggregatorListing.for_portal()` + сид одного портала `main`. Мультидомен/брендинг/on-demand TLS/per-portal sitemap — Phase 2.

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

### 6.5 Политика ретраев по каналам + DLQ

Сейчас задача-доставка падает по дефолту Celery (3 ретрая) и молча умирает — плохой Telegram-токен никто не заметит до жалобы. Зафиксировать per-channel политику:

| Канал | Ретраи | Backoff | Терминальное состояние |
|---|---|---|---|
| email (Resend) | до 7 дней | exponential (1м→…→6ч) | `failed` + алерт после исчерпания |
| telegram | 3 | linear 30с | при `401/bad token` — `failed` сразу, флаг «нужна починка оператором» |
| web push | без ретраев на `410 Gone` | — | `410` → `PushDevice.is_active=False` |
| sms/whatsapp | 3 | exponential | `failed` + алерт |

- Различать **транзиентные** (5xx, timeout — ретраить) и **перманентные** (401/403/невалидный адрес — не ретраить, сразу `failed`) ошибки.
- Исчерпанные задачи попадают в `failed`-состояние `Notification`/`Publication` с `last_error`; beat-задача раз в час собирает их и шлёт алерт оператору (Sentry/email). Это и есть лёгкий DLQ без отдельной инфраструктуры.
- Подтверждения доставки: где провайдер шлёт webhook (Resend delivered/bounced), обновлять статус из `sent` → `delivered`/`bounced`, а не считать «отправлено = доставлено».

### 6.6 Явный жизненный цикл триала/подписки

Не размазывать переходы по cron'ам — оформить state machine `Tenant.subscription_status`:

```
trial → (day 11) send trial_ending:3d
      → (day 13) send trial_ending:1d
      → (day 14, нет оплаты) → trial_expired + письмо «оплатите или потеряете доступ»
      → (day 21) → suspended: read-only доступ к дашборду, публикация/рассылки выключены
trial|trial_expired → (оплата Stripe) → active
active → (Stripe webhook: payment_failed) → past_due → (grace 7д, нет оплаты) → suspended
```

- Один beat-таск раз в сутки сканирует по индексу `(subscription_status, trial_ends_at)` (см. 1.5), ставит переходы и ставит в очередь reminder-события (с dedupe из 6.4).
- `suspended` = мягкое отключение (read-only), не удаление данных. Полная переходная таблица — `docs/references/patterns/state-machine.md` (раздел "Subscription lifecycle").

## Summary: список новых файлов/моделей в Phase 1

| Sprint | Новые apps | Новые модели | Новые utilities |
|---|---|---|---|
| 1 | `apps/core/audit/`, `apps/integrations/webhooks/` | `AuditEvent`, `OutgoingWebhook`, `WebhookDelivery` | `apps/core/pagination.py`, `apps/core/models.SoftDeleteMixin`, `apps/core/audit.audit_event()`; инфра-хардненинг конфига (1.5, DONE): Redis cache+сессии, Celery results→Redis, `CONN_MAX_AGE`, индексы `Tenant` |
| 2 | `apps/imports/` | `ImportJob`, `ImportRow` | `apps/imports/processors/` (handlers по resource_type) |
| 3 | — | (доп. поле `metadata` на Reservation) | `apps/promotions/state_machine.py` |
| 4 | — | (доп. поля на Publication: dedupe_key, attempts, next_retry_at, metadata) | `BasePublisher.publish_with_audit()` |
| 5 | — | `MagicLinkToken` (или Redis-cache), `AggregatorPortal`, `AggregatorListing.search_vector` (GIN) | `apps/aggregator/feed_reorder.py` (anti-spam), `AggregatorListing.for_portal()`, `sync_aggregator_listing` task |
| 6 | — | `PushDevice`, (доп. поля на Notification) | `apps/core/jobs.idempotent_task`, per-channel retry policy (6.5), subscription lifecycle state machine (6.6) |
