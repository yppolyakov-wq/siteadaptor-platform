# Архитектура ядра платформы (Django stack)

## Принцип: build minimal, architect for extension

| Уровень | Что входит |
|---------|-----------|
| **Реализуем в Phase 1** (8–12 недель) | Multi-tenant ядро, каталог, акции с бронированием, publishing engine, notification engine, базовый агрегатор, billing |
| **Архитектурно заложено, не реализовано** | CRM, ERP, dropshipping, наследование заказов, тур-продукт, multi-region инфраструктура, полная мультиязычность UI, AI-модули |

Цель: к концу Phase 1 — 10 платящих пекарен/мини-маркетов. Не «полная экосистема за полгода».

---

## Tech Stack

### Рекомендованный для Phase 1: Django + HTMX

- **Backend & Frontend:** Django 5.x + HTMX + Alpine.js + Tailwind CSS
- **БД:** PostgreSQL 16+
- **Кэш / Sessions / Locks:** Redis 7+
- **Фоновые задачи:** Celery 5 + Redis broker
- **API (для внешних интеграций):** Django REST Framework
- **Multi-tenancy:** django-tenants (schema-per-tenant)
- **i18n:** django.utils.translation + django-modeltranslation
- **Auth:** django-allauth (email, OAuth)
- **Admin:** Django Admin (встроенный, ничего не строить) + django-unfold для современного UI
- **Email:** Anymail + Resend/Postmark provider
- **Файлы:** django-storages + Hetzner Object Storage (S3-compatible)
- **Платежи:** dj-stripe (Stripe wrapper для Django)
- **Хостинг:** Hetzner Cloud EU
- **Reverse proxy:** Caddy (автоматический SSL для custom domains)
- **CI/CD:** GitHub Actions + Docker Compose
- **Мониторинг:** Sentry + django-prometheus + Plausible

Почему этот стек:
- Один язык на весь стек
- В разы меньше кода чем SPA-подход
- Django Admin = готовый backoffice бесплатно
- django-tenants = mature multi-tenancy
- HTMX даёт interactivity SPA-уровня без React/Vue
- Claude Code отлично работает с Django (одна из самых документированных тем в обучающих данных)

### Альтернатива: Django backend + Next.js frontend

Если на каком-то этапе понадобится тяжёлая SPA-функциональность (drag-and-drop конструктор, real-time дашборды):
- Backend остаётся тот же: Django + DRF + Celery
- Frontend: Next.js (только дашборд клиента и публичный агрегатор)
- API: DRF + drf-spectacular для OpenAPI → typescript codegen

В Phase 1 этого не нужно. HTMX покрывает 95% UX-задач для SMB-дашборда.

---

## Multi-tenancy (django-tenants)

**Подход:** schema-per-tenant в одной БД (PostgreSQL schemas).

Что это значит:
- Один PostgreSQL instance
- Public schema хранит Tenant, Domain, и общие данные (например, категории агрегатора)
- Каждый tenant получает свой schema (`tenant_baeckerei_mueller`) со своими таблицами
- Запросы автоматически направляются в нужный schema по subdomain/custom domain

### Структура settings

```python
# settings.py
SHARED_APPS = [
    'django_tenants',
    'tenants',           # наша app с моделями Tenant и Domain
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    # глобальные данные агрегатора
    'aggregator',
    'global_categories',
]

TENANT_APPS = [
    # всё что специфично для tenant'а
    'core',
    'catalog',
    'promotions',
    'publishing',
    'notifications',
    'subscriptions',
    'billing',
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = 'tenants.Tenant'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        # ...
    }
}

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)
```

### Tenant routing middleware
```python
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',  # должен быть первым
    # ...остальные middleware
]
```

Когда приходит запрос на `baeckerei-mueller.platform.com` — django-tenants автоматически переключает schema на `tenant_baeckerei_mueller`. Все ORM-запросы автоматически изолированы.

### Изоляция данных
Schema-per-tenant даёт **более сильную изоляцию**, чем shared schema с tenant_id. Это удобный аргумент для GoBD/GDPR compliance: «данные каждого клиента в отдельной БД-схеме». Один из конкурентных аргументов для немецкого рынка.

### Premium-опция в будущем
Для enterprise-клиентов — database-per-tenant. django-tenants поддерживает обе модели в одном проекте.

---

## Multi-region (заложено, не построено)

Сейчас: один Hetzner EU сервер, все tenants с `data_region='EU'`.

Архитектурно: поле `Tenant.data_region`. Router определяет регион по subdomain/domain и направляет запрос к соответствующему backend'у.

```
            ┌─────────────┐
            │   Caddy     │ (определяет регион по host)
            └──────┬──────┘
        ┌─────────┼─────────┐
        ▼         ▼         ▼
      EU app   US app    IN app
      EU DB    US DB     IN DB
   (есть)   (потом)   (потом)
```

**Не делать сейчас:** active-active replication, cross-region sync. Это другой класс инженерных проблем.

---

## Domain handling

Три режима, работают одновременно:

| Режим | URL | SSL |
|-------|-----|-----|
| Aggregator listing | `aggregator.platform.com/biz/{slug}` | Wildcard |
| Subdomain | `{slug}.platform.com` | Wildcard |
| Custom domain | `shop.client-domain.de` | Caddy on-demand TLS + Let's Encrypt |

В django-tenants есть модель `Domain` — на один Tenant можно повесить несколько Domain'ов (subdomain + custom domain). Один из них помечается как primary.

Клиент в админке вводит свой custom domain → система проверяет CNAME → добавляет Domain → Caddy через on-demand TLS автоматически выпускает сертификат при первом запросе.

```python
# tenants/models.py
class Tenant(TenantMixin):
    name = models.CharField(max_length=100)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES)
    data_region = models.CharField(max_length=10, default='EU')
    default_locale = models.CharField(max_length=10, default='de')
    enabled_locales = models.JSONField(default=list)
    enabled_modules = models.JSONField(default=list)
    # ...

class Domain(DomainMixin):
    pass  # django-tenants даёт всё нужное
```

---

## Multilingual

### Подход для контента
**Вариант 1 (простой, рекомендую для Phase 1):** JSONField с переводами.

```python
class Product(models.Model):
    name = models.JSONField(default=dict)
    # {"de": "Apfelstrudel", "en": "Apple strudel", "ru": "Яблочный штрудель"}
    
    def get_name(self, locale=None):
        locale = locale or get_language() or 'de'
        return self.name.get(locale) or self.name.get('de') or ''
```

**Вариант 2 (зрелый, для будущего):** django-modeltranslation — генерирует колонки `name_de`, `name_en` автоматически.

Для MVP — JSONField. Мигрировать на django-modeltranslation потом легко.

### UI
Стандартный Django i18n с `gettext`. Старт: `de`, `en`. Дальше добавляются `ru`, `uk`, `tr` через `.po` файлы.

```python
LANGUAGE_CODE = 'de'
LANGUAGES = [('de', 'Deutsch'), ('en', 'English')]
USE_I18N = True
```

Каждый Tenant выбирает `default_locale` и `enabled_locales[]`, доступные его покупателям.

---

## Структура проекта

```
platform/
├── manage.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml          # uv или poetry
├── caddy/
│   └── Caddyfile
├── config/                 # Django project
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── urls_public.py      # урлы публичной части (django-tenants public schema)
│   ├── urls_tenant.py      # урлы tenant'а
│   ├── celery.py
│   └── wsgi.py
├── apps/
│   ├── tenants/            # SHARED: Tenant, Domain модели
│   ├── core/               # TENANT: общие утилиты, base модели, events
│   ├── catalog/            # TENANT: Product, Category
│   ├── promotions/         # TENANT: Promotion, Reservation
│   ├── publishing/         # TENANT: Channel, Publication, publishers
│   ├── notifications/      # TENANT: Notification, channels
│   ├── subscriptions/      # TENANT: Subscription модели
│   ├── billing/            # TENANT: Subscription plans, Stripe
│   ├── aggregator/         # SHARED: публичная витрина агрегатора
│   ├── global_categories/  # SHARED: глобальные категории
│   └── (future)
│       ├── crm/
│       ├── inventory/
│       ├── dropshipping/
│       └── tours/
├── templates/
│   ├── base.html
│   ├── tenant/
│   └── aggregator/
└── static/
```

Каждая Django app = модуль системы. Включается/выключается через `INSTALLED_APPS` и `Tenant.enabled_modules`.

---

## Event bus (Django signals + Celery)

Django signals дают чистую точку расширения. Модули подписываются на события без зависимости друг от друга.

```python
# apps/core/events.py
from django.dispatch import Signal

promotion_created = Signal()
promotion_published = Signal()
promotion_viewed = Signal()
reservation_created = Signal()
reservation_collected = Signal()
order_created = Signal()           # для будущего

# apps/promotions/services.py
from apps.core.events import promotion_created

class PromotionService:
    @staticmethod
    def create(tenant, data):
        promo = Promotion.objects.create(...)
        promotion_created.send(
            sender=Promotion,
            promotion=promo,
            tenant=tenant
        )
        return promo

# apps/publishing/receivers.py
from django.dispatch import receiver
from apps.core.events import promotion_created
from .tasks import publish_to_channels_task

@receiver(promotion_created)
def auto_publish_promotion(sender, promotion, tenant, **kwargs):
    publish_to_channels_task.delay(promotion.id)

# apps/notifications/receivers.py
from apps.core.events import promotion_published
from .tasks import notify_subscribers_task

@receiver(promotion_published)
def notify_on_publish(sender, promotion, channel, **kwargs):
    if channel.type == 'aggregator':
        notify_subscribers_task.delay(promotion.id)
```

Tasks через Celery — для асинхронной обработки (отправка уведомлений, публикация в external API).

**Когда подключаешь новый модуль (CRM, inventory):** создаёшь `apps/crm/receivers.py`, подписываешься на нужные signals, не трогаешь существующий код.

---

## Core Data Model

### Phase 1 entities (Django ORM)

```python
# apps/tenants/models.py (SHARED schema)
class Tenant(TenantMixin):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    business_type = models.CharField(max_length=50, choices=[
        ('bakery', 'Bakery'),
        ('restaurant', 'Restaurant'),
        ('retail', 'Retail'),
        ('tour_operator', 'Tour Operator'),
        ('hotel', 'Hotel'),
    ])
    data_region = models.CharField(max_length=10, default='EU')
    default_locale = models.CharField(max_length=10, default='de')
    enabled_locales = models.JSONField(default=list)
    enabled_modules = models.JSONField(default=list)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default='DE')
    default_currency = models.CharField(max_length=3, default='EUR')
    
    # Billing (Stripe via dj-stripe)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    subscription_status = models.CharField(max_length=20, default='trial')
    trial_ends_at = models.DateTimeField(null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    auto_create_schema = True  # django-tenants создаст schema автоматически

class Domain(DomainMixin):
    pass


# apps/core/models.py (TENANT schema, base abstract)
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


# apps/catalog/models.py (TENANT schema)
class Category(TimestampedModel):
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    name = models.JSONField(default=dict)        # i18n
    slug = models.SlugField()
    icon = models.CharField(max_length=50, blank=True)

class Product(TimestampedModel):
    sku = models.CharField(max_length=100, blank=True)
    name = models.JSONField(default=dict)        # i18n
    description = models.JSONField(default=dict) # i18n
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    images = models.JSONField(default=list)      # [{ url, alt }]
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    stock_quantity = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)    # отраслевая специфика


# apps/promotions/models.py (TENANT schema)
class Promotion(TimestampedModel):
    STATUS = [('draft','Draft'),('scheduled','Scheduled'),('active','Active'),
              ('ended','Ended'),('cancelled','Cancelled')]
    DISCOUNT_TYPE = [('percent','Percent'),('amount','Amount'),('fixed_price','Fixed price')]
    
    status = models.CharField(max_length=20, choices=STATUS, default='draft')
    title = models.JSONField(default=dict)
    description = models.JSONField(default=dict)
    
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    
    # Бронирование
    is_bookable = models.BooleanField(default=False)
    total_quantity = models.IntegerField(null=True, blank=True)
    available_quantity = models.IntegerField(null=True, blank=True)
    pickup_window_start = models.DateTimeField(null=True, blank=True)
    pickup_window_end = models.DateTimeField(null=True, blank=True)
    pickup_location = models.CharField(max_length=200, blank=True)
    
    # Применимость
    products = models.ManyToManyField(Product, blank=True)
    categories = models.ManyToManyField(Category, blank=True)
    
    # Targeting
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list)
    
    metadata = models.JSONField(default=dict)

class Reservation(TimestampedModel):
    STATUS = [('pending','Pending'),('confirmed','Confirmed'),
              ('collected','Collected'),('cancelled','Cancelled'),('expired','Expired')]
    
    promotion = models.ForeignKey(Promotion, on_delete=models.PROTECT)
    customer = models.ForeignKey('subscriptions.Customer', on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    pickup_code = models.CharField(max_length=20, unique=True)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)


# apps/subscriptions/models.py (TENANT schema)
class Customer(TimestampedModel):
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=200, blank=True)
    locale = models.CharField(max_length=10, default='de')
    consents = models.JSONField(default=dict)
    # { email: true, sms: false, whatsapp: true, telegram: true, push: false }
    metadata = models.JSONField(default=dict)

class Subscription(TimestampedModel):
    """Подписка потребителя на бизнес/категорию/локацию."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    # tenant_id уже в схеме через django-tenants
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    notification_channels = models.JSONField(default=list)
    # ['email', 'telegram', 'push']


# apps/publishing/models.py (TENANT schema)
class Channel(TimestampedModel):
    TYPE = [('own_site','Own site'),('subdomain','Subdomain'),
            ('aggregator','Aggregator'),('google_business','Google Business'),
            ('instagram','Instagram'),('whatsapp_broadcast','WhatsApp Broadcast'),
            ('telegram_channel','Telegram Channel'),('email','Email')]
    
    type = models.CharField(max_length=30, choices=TYPE)
    config = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=False)
    last_tested_at = models.DateTimeField(null=True, blank=True)

class Publication(TimestampedModel):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default='pending')
    published_at = models.DateTimeField(null=True, blank=True)
    error = models.JSONField(default=dict, blank=True)


# apps/notifications/models.py (TENANT schema)
class Notification(TimestampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE)
    channel_type = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default='queued')
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    error = models.JSONField(default=dict, blank=True)
```

### Extension hooks (заложено для будущего)

```python
# Product.metadata — отраслевая специфика
# Bakery:    {"perishable": true, "baked_at": "...", "allergens": [...]}
# Hotel:     {"room_type": "...", "max_guests": 2}
# Tour:      {"duration_days": 3, "languages_offered": [...], "max_participants": 12}

# Order entity (НЕ в Phase 1, поля для будущего):
# class Order(TimestampedModel):
#     customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
#     parent_order = models.ForeignKey('self', null=True, blank=True, ...)  # dropshipping
#     supplier_tenant_id = models.UUIDField(null=True, blank=True)          # cross-tenant
#     origin_type = models.CharField(...)
#     items = models.JSONField()
#     # ...
```

`parent_order` + `supplier_tenant_id` — архитектурная заготовка под dropshipping. Когда добавишь Order модель — поля будут готовы с первой миграции.

---

## Publishing Engine

Один абстрактный интерфейс, реализации на канал:

```python
# apps/publishing/publishers/base.py
from abc import ABC, abstractmethod

class BasePublisher(ABC):
    @abstractmethod
    def publish(self, promotion, channel) -> PublicationResult: ...
    
    @abstractmethod
    def unpublish(self, publication) -> None: ...
    
    @abstractmethod
    def test(self, channel) -> bool: ...

# apps/publishing/publishers/__init__.py
PUBLISHERS = {
    'own_site': OwnSitePublisher(),
    'subdomain': SubdomainPublisher(),
    'aggregator': AggregatorPublisher(),
    'email': EmailPublisher(),
    'telegram_channel': TelegramPublisher(),
    # (потом)
    # 'google_business': GoogleBusinessPublisher(),
    # 'instagram': InstagramPublisher(),
    # 'whatsapp_broadcast': WhatsAppPublisher(),
}

def get_publisher(channel_type):
    return PUBLISHERS[channel_type]
```

**Phase 1:** subdomain, aggregator, email, telegram_channel.  
**Phase 2:** whatsapp_broadcast, google_business, instagram.

---

## Notification Engine

Аналогичная абстракция:

```python
# apps/notifications/channels/base.py
class BaseNotificationChannel(ABC):
    @abstractmethod
    def send(self, recipient, message, context) -> DeliveryResult: ...

# Реализации:
# EmailChannel (через django-anymail + Resend)
# TelegramChannel (через python-telegram-bot)
# WhatsAppChannel (WhatsApp Business API — Phase 2)
# SMSChannel (Twilio — Phase 2)
# PushChannel (когда будет приложение)
```

**Phase 1:** Email, Telegram.

### Sending flow

```python
# apps/notifications/tasks.py (Celery task)
@shared_task
def notify_subscribers_task(promotion_id):
    promo = Promotion.objects.get(id=promotion_id)
    
    # Найти подписчиков для этого tenant'а / категории / города
    subscriptions = Subscription.objects.filter(
        Q(category__in=promo.categories.all()) | Q(category__isnull=True),
        Q(city='') | Q(city=promo.city),
    ).select_related('customer')
    
    for sub in subscriptions:
        for channel_type in sub.notification_channels:
            if sub.customer.consents.get(channel_type):
                send_notification_task.delay(sub.customer.id, promo.id, channel_type)

@shared_task(rate_limit='10/s')
def send_notification_task(customer_id, promotion_id, channel_type):
    customer = Customer.objects.get(id=customer_id)
    promo = Promotion.objects.get(id=promotion_id)
    channel = get_notification_channel(channel_type)
    
    notification = Notification.objects.create(
        customer=customer, promotion=promo,
        channel_type=channel_type, status='queued'
    )
    
    try:
        result = channel.send(customer, build_message(promo, customer.locale), {})
        notification.status = 'sent'
        notification.sent_at = timezone.now()
    except Exception as e:
        notification.status = 'failed'
        notification.error = {'message': str(e)}
    
    notification.save()
```

---

## Aggregator (публичная часть)

Отдельная Django app `aggregator`, работает в SHARED schema, читает данные tenant'ов через django-tenants context-switch.

URL-структура:
- `/` — выбор города
- `/{city}/` — все актуальные акции города
- `/{city}/{category}/` — фильтр по категории
- `/biz/{tenant_slug}/` — страница конкретного бизнеса
- `/promotion/{id}/` — детальная страница акции с кнопкой резервации
- `/account/` — личный кабинет: подписки, брони, настройки уведомлений

```python
# apps/aggregator/views.py
from django_tenants.utils import schema_context

class CityPromotionsView(ListView):
    template_name = 'aggregator/city.html'
    
    def get_queryset(self):
        city = self.kwargs['city']
        # Собрать акции из всех tenants в этом городе с публикацией в aggregator
        promotions = []
        for tenant in Tenant.objects.filter(city=city):
            with schema_context(tenant.schema_name):
                tenant_promos = Promotion.objects.filter(
                    status='active',
                    publications__channel__type='aggregator',
                    publications__status='published',
                ).select_related('category')
                promotions.extend(tenant_promos)
        return promotions
```

Для performance оптимизации: materialized view или dedicated `AggregatorIndex` таблица в SHARED schema, которая обновляется при `promotion_published` signal.

---

## Billing

dj-stripe для интеграции со Stripe:
- Free trial 14 дней
- Один тариф на старте ~30-50 €/мес
- Webhook handler автоматически обновляет `Tenant.subscription_status`

```python
INSTALLED_APPS += ['djstripe']
DJSTRIPE_FOREIGN_KEY_TO_FIELD = 'id'

# При создании Tenant
def create_tenant_with_trial(name, slug, email, ...):
    tenant = Tenant.objects.create(
        name=name, slug=slug,
        trial_ends_at=timezone.now() + timedelta(days=14),
        subscription_status='trial',
    )
    customer = djstripe.models.Customer.create(email=email)
    tenant.stripe_customer_id = customer.id
    tenant.save()
    return tenant
```

---

## Экспорты и синхронизации

**Phase 1 минимум:**
- CSV/Excel экспорт каталога, акций, клиентов, броней (через django-import-export)
- REST API на чтение через DRF + drf-spectacular (OpenAPI)

**Заложено архитектурно:**
- Outbound webhooks (модуль `webhooks/`, listens to signals, отправляет в external endpoints)
- Inbound integrations (модуль `integrations/`, импорт каталога из CSV/Shopify/WooCommerce — Phase 2+)

Всё в отдельных Django apps, добавляются без перестройки ядра.

---

## Второй продукт: тур-агрегатор

### Архитектурно

Тур-агрегатор использует то же ядро, добавляет специфические apps:

```
apps/
  tours/              # Phase 2 product
    models.py         # Tour, TourDeparture extends Product
    services/
      commissions.py  # расчёт комиссии оператору
      payouts.py      # выплаты операторам
      escrow.py       # удержание средств до оказания услуги
```

Тур моделируется через те же entities:
- `Tenant` с `business_type='tour_operator'`
- `Product` с metadata `{duration_days, languages, meeting_point, max_participants}`
- `Promotion` для last-minute спецпредложений
- `Reservation` расширяется до `TourBooking` (наследование через ForeignKey OneToOne)

### Стратегически: не параллельно

**Последовательность:**

1. **Месяцы 1–6:** Продукт 1 → 30–50 платящих пекарен/мини-маркетов
2. **Месяц 7:** Рефакторинг — вынос общих частей в `core/`, аудит extension points
3. **Месяцы 8–11:** Продукт 2 (туры) на готовом ядре
4. **Месяц 12+:** Параллельное развитие

Причины:
- Параллельная разработка двух продуктов одним человеком = оба провалятся
- К Phase 2 ты будешь знать что РЕАЛЬНО общее, а что нет — рефакторинг будет осмысленным
- Первый продукт даст cash flow для второго

### Когда туры требуют значимо отдельной логики

Туры — это booking с предоплатой, escrow, commission split, payouts оператору. Это значимый финансовый flow. Решается отдельным модулем `tours/payments/`, не отдельным кодом всего стека.

---

## Deployment

**Старт:**
- 1× Hetzner CCX23 (Django app + Caddy + Celery worker)
- 1× Hetzner CX31 (PostgreSQL + Redis)
- Hetzner Object Storage для файлов
- Hetzner Snapshots ежедневно

Docker Compose:

```yaml
services:
  web:
    build: .
    command: gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 4
    depends_on: [db, redis]
    
  worker:
    build: .
    command: celery -A config worker -l info
    depends_on: [db, redis]
    
  beat:
    build: .
    command: celery -A config beat -l info
    
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    
  db:
    image: postgres:16
    volumes: [pg_data:/var/lib/postgresql/data]
    
  redis:
    image: redis:7
```

Caddyfile для on-demand TLS:
```
*.platform.com, platform.com {
    reverse_proxy web:8000
}

# Custom domains через on-demand TLS
{
    on_demand_tls {
        ask https://platform.com/api/verify-domain
    }
}

:443 {
    tls {
        on_demand
    }
    reverse_proxy web:8000
}
```

Масштабирование когда понадобится:
- Вынос db на managed PostgreSQL
- Read replica
- Несколько web instances за load balancer
- Celery workers на отдельных серверах

---

## Phase 1 scope (8–12 недель)

### Минимальный продукт для первого платящего клиента

**Tenant onboarding:**
- Регистрация бизнеса (email + пароль через django-allauth)
- Wizard: business_type, slug, city, default_locale
- Subdomain автоматически выдаётся через django-tenants

**Catalog:**
- CRUD товаров с фото, ценой, категорией
- CSV импорт через django-import-export
- Django Admin = базовый интерфейс. UI для клиента — HTMX views.

**Promotions:**
- Создание акции: товары/категории, тип скидки, окно действия
- Опциональное бронирование с pickup window
- Статусы (draft → scheduled → active → ended)

**Publishing:**
- Auto-published landing page на subdomain
- Auto-published в агрегаторе
- Email broadcast подписчикам

**Aggregator:**
- Публичная витрина по городам/категориям
- Регистрация потребителя (email или Telegram)
- Opt-in подписка на бизнес/категорию

**Reservations:**
- Покупатель резервирует количество единиц
- Получает pickup_code
- Бизнес в админке видит брони, отмечает collected

**Notifications:**
- Email (Resend через django-anymail)
- Telegram channel publish + bot для personal notifications

**Billing:**
- dj-stripe, 14-дневный trial
- Один тариф, фикс цена

**Languages:**
- UI: de + en через `gettext` и `.po` файлы
- Контент: i18n JSONField работает на старте даже на одном языке

### Что НЕ делать в Phase 1

Соблазны, которые убьют сроки:
- Мобильное приложение iOS/Android (только web на старте)
- Drag-and-drop конструктор сайтов (фиксированные шаблоны)
- WhatsApp Business API (требует верификации 2–4 недели — отложить)
- Все 8+ каналов публикации (хватит 3–4)
- CRM, ERP, склад, бухгалтерия
- AI-фичи
- Реальный дропшипинг и наследование заказов
- Тур-продукт
- Real-time push с геолокацией
- Multi-region (только EU)

Эти вещи МОГУТ быть добавлены позже без переписывания — архитектура их учитывает.

---

## Работа с Claude Code на Django stack

### Хорошие промпты для Claude Code

Не давай Claude Code «реализуй всё ядро». Декомпозируй до уровня одной Django app:

1. «Настрой Django 5 проект с django-tenants, PostgreSQL, Redis, Celery. Структура проекта — см. артефакт. Создай Tenant и Domain модели по спецификации.»
2. «Реализуй apps/catalog с моделями Product, Category по спецификации. Добавь Django Admin, форматирование JSONField для i18n. Создай миграции.»
3. «Реализуй apps/promotions с моделями Promotion, Reservation. Логика бронирования: уменьшение available_quantity при создании резервации с использованием select_for_update.»
4. «Реализуй publishing engine: абстрактный BasePublisher, реализации SubdomainPublisher и AggregatorPublisher.»
5. «Реализуй Celery task notify_subscribers_task по спецификации.»
6. И так далее по модулям.

### Полезные пакеты для ускорения

- `django-environ` — env vars
- `django-cors-headers` — для будущего API
- `django-debug-toolbar` — debugging
- `django-extensions` — shell_plus, и т.д.
- `django-import-export` — CSV/Excel imports
- `django-allauth` — auth (email, OAuth)
- `dj-stripe` — Stripe integration
- `django-anymail` — email через Resend/Postmark/etc.
- `django-unfold` — современный UI для Django Admin
- `django-modeltranslation` — для будущего (когда JSONField станет узок)
- `drf-spectacular` — OpenAPI для будущего API
- `django-htmx` — helper для HTMX интеграции
- `pytest-django` + `factory-boy` — для тестов
