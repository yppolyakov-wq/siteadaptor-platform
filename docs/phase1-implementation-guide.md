# Phase 1: Реализация и спринты

Полный готовый-к-запуску стартовый набор для Django проекта + декомпозиция Phase 1 на 6 двухнедельных спринтов.

## Оглавление

**Часть 1: Project Setup** — что установить, как структурировать проект, какие зависимости, как запустить миграции и получить рабочую БД.

**Часть 2: Модели и миграции** — готовые `models.py` для всех Phase 1 apps. Запустишь `makemigrations` + `migrate_schemas` и получишь работающую схему.

**Часть 3: Sprint Plan** — 6 спринтов с user stories, acceptance criteria, техническими задачами и промптами для Claude Code.

---

# Часть 1: Project Setup

## Зависимости

`pyproject.toml`:

```toml
[project]
name = "platform"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    # Core
    "django>=5.1,<5.2",
    "django-tenants>=3.7",
    "psycopg[binary]>=3.2",
    "django-environ>=0.11",
    
    # Auth
    "django-allauth[socialaccount]>=65.0",
    
    # Async / tasks
    "celery[redis]>=5.4",
    "django-celery-beat>=2.7",
    "django-celery-results>=2.5",
    "redis>=5.0",
    
    # Admin & UI
    "django-unfold>=0.42",
    "django-htmx>=1.19",
    "django-widget-tweaks>=1.5",
    
    # Files & storage
    "django-storages[s3]>=1.14",
    "pillow>=10.4",
    
    # Email
    "django-anymail[resend]>=12.0",
    
    # Payments
    "dj-stripe>=2.9",
    
    # Import/export
    "django-import-export>=4.2",
    
    # API (для будущего)
    "djangorestframework>=3.15",
    "drf-spectacular>=0.27",
    "django-cors-headers>=4.4",
    
    # Server
    "gunicorn>=23.0",
    "whitenoise>=6.7",
    
    # Monitoring
    "sentry-sdk>=2.15",
]

[project.optional-dependencies]
dev = [
    "django-debug-toolbar>=4.4",
    "django-extensions>=3.2",
    "pytest>=8.3",
    "pytest-django>=4.9",
    "factory-boy>=3.3",
    "faker>=30.0",
    "ruff>=0.7",
    "ipython>=8.27",
]
```

## Структура проекта

```
platform/
├── pyproject.toml
├── manage.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── caddy/
│   └── Caddyfile
├── config/                        # Django project
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls_public.py             # SHARED schema urls
│   ├── urls_tenant.py             # TENANT schema urls
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── __init__.py
│   ├── tenants/                   # SHARED
│   ├── core/                      # TENANT
│   ├── catalog/                   # TENANT
│   ├── promotions/                # TENANT
│   ├── subscriptions/             # TENANT
│   ├── publishing/                # TENANT
│   ├── notifications/             # TENANT
│   ├── billing/                   # TENANT
│   ├── aggregator/                # SHARED
│   └── global_categories/         # SHARED
├── templates/
│   ├── base.html
│   ├── tenant/
│   └── aggregator/
├── static/
└── locale/
```

## Settings

`config/settings/base.py`:

```python
import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

# django-tenants config
SHARED_APPS = [
    'django_tenants',
    'apps.tenants',
    
    # Django built-ins
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'unfold',                      # должен быть до admin
    'django.contrib.admin',
    'django.contrib.sites',
    
    # Third-party shared
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_celery_beat',
    'django_celery_results',
    'djstripe',
    
    # SHARED apps
    'apps.aggregator',
    'apps.global_categories',
]

TENANT_APPS = [
    # Django built-ins (нужны в обоих)
    'django.contrib.contenttypes',
    'django.contrib.auth',
    
    # TENANT apps
    'apps.core',
    'apps.catalog',
    'apps.promotions',
    'apps.subscriptions',
    'apps.publishing',
    'apps.notifications',
    'apps.billing',
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = 'tenants.Tenant'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
    }
}

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

# Middleware
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls_tenant'
PUBLIC_SCHEMA_URLCONF = 'config.urls_public'

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]

# i18n
LANGUAGE_CODE = 'de'
LANGUAGES = [
    ('de', 'Deutsch'),
    ('en', 'English'),
]
USE_I18N = True
USE_TZ = True
TIME_ZONE = 'Europe/Berlin'
LOCALE_PATHS = [BASE_DIR / 'locale']

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Auth
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# Celery
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Email
ANYMAIL = {
    'RESEND_API_KEY': env('RESEND_API_KEY', default=''),
}
EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@platform.com')

# Stripe (dj-stripe)
STRIPE_LIVE_MODE = env.bool('STRIPE_LIVE_MODE', default=False)
STRIPE_TEST_PUBLIC_KEY = env('STRIPE_TEST_PUBLIC_KEY', default='')
STRIPE_TEST_SECRET_KEY = env('STRIPE_TEST_SECRET_KEY', default='')
DJSTRIPE_WEBHOOK_SECRET = env('DJSTRIPE_WEBHOOK_SECRET', default='')
DJSTRIPE_FOREIGN_KEY_TO_FIELD = 'id'

# Storage (S3-compatible Hetzner Object Storage)
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'access_key': env('AWS_ACCESS_KEY_ID', default=''),
            'secret_key': env('AWS_SECRET_ACCESS_KEY', default=''),
            'bucket_name': env('AWS_STORAGE_BUCKET_NAME', default=''),
            'endpoint_url': env('AWS_S3_ENDPOINT_URL', default=''),
            'region_name': env('AWS_S3_REGION_NAME', default='eu-central'),
        },
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
```

`config/settings/development.py`:

```python
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ['*']

# Local development: use *.localhost
TENANT_DOMAIN_BASE = 'localhost:8000'

# Email to console in dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Local file storage in dev (override S3)
STORAGES['default'] = {
    'BACKEND': 'django.core.files.storage.FileSystemStorage',
    'OPTIONS': {'location': str(BASE_DIR / 'media')},
}
MEDIA_URL = '/media/'

INSTALLED_APPS += ['debug_toolbar', 'django_extensions']
MIDDLEWARE.insert(2, 'debug_toolbar.middleware.DebugToolbarMiddleware')

INTERNAL_IPS = ['127.0.0.1']
```

## .env.example

```bash
SECRET_KEY=your-secret-key-here-change-me
DEBUG=True
ALLOWED_HOSTS=localhost,*.localhost,127.0.0.1

DB_NAME=platform
DB_USER=platform
DB_PASSWORD=platform
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0

# Email (dev: console, prod: Resend)
RESEND_API_KEY=
DEFAULT_FROM_EMAIL=noreply@platform.local

# Stripe
STRIPE_TEST_PUBLIC_KEY=
STRIPE_TEST_SECRET_KEY=
DJSTRIPE_WEBHOOK_SECRET=

# S3 (Hetzner Object Storage)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=platform-media
AWS_S3_ENDPOINT_URL=https://nbg1.your-objectstorage.com
AWS_S3_REGION_NAME=nbg1

# Sentry
SENTRY_DSN=
```

## Docker Compose (dev)

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: platform
      POSTGRES_USER: platform
      POSTGRES_PASSWORD: platform
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

Запустить: `docker compose up -d db redis`.

## Команды первого запуска

```bash
# 1. Установить uv (один раз)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Создать venv и установить зависимости
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Запустить БД и Redis
docker compose up -d db redis

# 4. Скопировать env
cp .env.example .env
# отредактировать .env при необходимости

# 5. Создать миграции (после того как добавлены модели — см. Часть 2)
python manage.py makemigrations tenants
python manage.py makemigrations core catalog promotions subscriptions \
    publishing notifications billing aggregator global_categories

# 6. Применить SHARED миграции (создаёт public schema)
python manage.py migrate_schemas --shared

# 7. Создать суперюзера в public schema
python manage.py createsuperuser

# 8. Запустить сервер
python manage.py runserver 0.0.0.0:8000

# В отдельном терминале: Celery worker
celery -A config worker -l info

# Зайти в admin: http://localhost:8000/admin/
# Создать первый Tenant через admin → автоматически создаётся его schema
```

---

# Часть 2: Модели

## apps/tenants/models.py (SHARED schema)

```python
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    BUSINESS_TYPES = [
        ('bakery', 'Bakery / Bäckerei'),
        ('butcher', 'Butcher / Metzgerei'),
        ('grocery', 'Grocery / Lebensmittel'),
        ('clothing', 'Clothing / Bekleidung'),
        ('restaurant', 'Restaurant'),
        ('cafe', 'Cafe'),
        ('retail', 'Retail / Einzelhandel'),
        ('tour_operator', 'Tour Operator'),
        ('hotel', 'Hotel'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES, default='other')
    
    # Location
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default='DE')
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Localization
    default_locale = models.CharField(max_length=10, default='de')
    enabled_locales = models.JSONField(default=list)  # ['de', 'en']
    default_currency = models.CharField(max_length=3, default='EUR')
    timezone = models.CharField(max_length=50, default='Europe/Berlin')
    
    # Region (multi-region future-proofing)
    data_region = models.CharField(max_length=10, default='EU')
    
    # Modules (для billing tiers)
    enabled_modules = models.JSONField(default=list)
    # ['catalog', 'promotions', 'publishing', 'aggregator']
    
    # Branding
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default='#000000')
    
    # Billing (Stripe)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    subscription_status = models.CharField(max_length=20, default='trial')
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_ends_at = models.DateTimeField(null=True, blank=True)
    
    # Owner contact
    owner_email = models.EmailField(blank=True)
    owner_phone = models.CharField(max_length=30, blank=True)
    
    # Meta
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # django-tenants
    auto_create_schema = True
    auto_drop_schema = False  # для безопасности — не удалять автоматически
    
    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    pass
```

## apps/core/models.py (TENANT schema, abstract)

```python
import uuid
from django.db import models
from django.utils.translation import get_language


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class I18nMixin:
    """Утилиты для работы с i18n JSONField."""
    
    def get_i18n(self, field_name: str, locale: str = None) -> str:
        locale = locale or get_language() or 'de'
        value = getattr(self, field_name) or {}
        return value.get(locale) or value.get('de') or value.get('en') or ''
```

## apps/catalog/models.py

```python
from django.db import models
from apps.core.models import TimestampedModel, I18nMixin


class Category(TimestampedModel, I18nMixin):
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        related_name='children', on_delete=models.SET_NULL
    )
    name = models.JSONField(default=dict)
    slug = models.SlugField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['sort_order', 'slug']
    
    def __str__(self):
        return self.get_i18n('name')


class Product(TimestampedModel, I18nMixin):
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    name = models.JSONField(default=dict)
    description = models.JSONField(default=dict)
    
    category = models.ForeignKey(
        Category, null=True, blank=True,
        related_name='products', on_delete=models.SET_NULL
    )
    
    images = models.JSONField(default=list)
    # [{"url": "...", "alt": "...", "is_primary": true}]
    
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    
    stock_quantity = models.IntegerField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    metadata = models.JSONField(default=dict)
    # Bakery:    {"perishable": true, "baked_at": "...", "allergens": []}
    # Hotel:     {"room_type": "...", "max_guests": 2}
    # Tour:      {"duration_days": 3, "languages_offered": []}
    
    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return self.get_i18n('name')
```

## apps/promotions/models.py

```python
import secrets
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimestampedModel, I18nMixin


class Promotion(TimestampedModel, I18nMixin):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('scheduled', _('Scheduled')),
        ('active', _('Active')),
        ('ended', _('Ended')),
        ('cancelled', _('Cancelled')),
    ]
    
    DISCOUNT_TYPES = [
        ('percent', _('Percent off')),
        ('amount', _('Fixed amount off')),
        ('fixed_price', _('Fixed final price')),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    title = models.JSONField(default=dict)
    description = models.JSONField(default=dict)
    
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    
    # Бронирование
    is_bookable = models.BooleanField(default=False)
    total_quantity = models.IntegerField(null=True, blank=True)
    available_quantity = models.IntegerField(null=True, blank=True)
    max_per_customer = models.IntegerField(default=10)
    
    pickup_window_start = models.DateTimeField(null=True, blank=True)
    pickup_window_end = models.DateTimeField(null=True, blank=True)
    pickup_location = models.CharField(max_length=200, blank=True)
    
    # Применимость
    products = models.ManyToManyField(
        'catalog.Product', blank=True, related_name='promotions'
    )
    categories = models.ManyToManyField(
        'catalog.Category', blank=True, related_name='promotions'
    )
    
    # Targeting (для notification engine)
    target_city = models.CharField(max_length=100, blank=True)
    target_district = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list)
    
    # Cover image
    cover_image_url = models.URLField(blank=True)
    
    metadata = models.JSONField(default=dict)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'starts_at']),
            models.Index(fields=['status', 'ends_at']),
        ]
        ordering = ['-starts_at']
    
    def __str__(self):
        return f"{self.get_i18n('title')} [{self.status}]"


class Reservation(TimestampedModel):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('confirmed', _('Confirmed')),
        ('collected', _('Collected')),
        ('cancelled', _('Cancelled')),
        ('expired', _('Expired')),
    ]
    
    promotion = models.ForeignKey(
        Promotion, related_name='reservations', on_delete=models.PROTECT
    )
    customer = models.ForeignKey(
        'subscriptions.Customer', related_name='reservations', on_delete=models.PROTECT
    )
    
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    pickup_code = models.CharField(max_length=20, unique=True, db_index=True)
    
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['customer', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.pickup_code:
            self.pickup_code = self._generate_code()
        super().save(*args, **kwargs)
    
    @staticmethod
    def _generate_code():
        return secrets.token_urlsafe(6).upper().replace('_', '').replace('-', '')[:8]
    
    def __str__(self):
        return f"Reservation {self.pickup_code} ({self.status})"
```

## apps/subscriptions/models.py

```python
from django.db import models
from apps.core.models import TimestampedModel


class Customer(TimestampedModel):
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    
    telegram_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    
    name = models.CharField(max_length=200, blank=True)
    locale = models.CharField(max_length=10, default='de')
    
    consents = models.JSONField(default=dict)
    # {"email": true, "sms": false, "whatsapp": false, "telegram": true, "push": false}
    
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)
    # для будущей CRM сегментации
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(email__gt='') | models.Q(telegram_id__isnull=False) | models.Q(phone__gt=''),
                name='customer_has_contact'
            )
        ]
    
    def __str__(self):
        return self.name or self.email or f"Customer #{self.id}"


class Subscription(TimestampedModel):
    """Подписка потребителя на бизнес/категорию.
    
    В TENANT schema это означает: customer подписан на ЭТОТ tenant.
    Дополнительно может быть фильтр по категории/локации.
    """
    customer = models.ForeignKey(
        Customer, related_name='subscriptions', on_delete=models.CASCADE
    )
    
    category = models.ForeignKey(
        'catalog.Category', null=True, blank=True,
        related_name='subscriptions', on_delete=models.CASCADE
    )
    
    # Дополнительные фильтры
    target_city = models.CharField(max_length=100, blank=True)
    target_district = models.CharField(max_length=100, blank=True)
    
    notification_channels = models.JSONField(default=list)
    # ['email', 'telegram', 'push']
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['customer', 'is_active']),
            models.Index(fields=['category']),
        ]
```

## apps/publishing/models.py

```python
from django.db import models
from apps.core.models import TimestampedModel


class Channel(TimestampedModel):
    CHANNEL_TYPES = [
        ('subdomain', 'Subdomain landing page'),
        ('custom_domain', 'Custom domain'),
        ('aggregator', 'Platform aggregator'),
        ('email', 'Email broadcast'),
        ('telegram_channel', 'Telegram channel'),
        ('whatsapp_broadcast', 'WhatsApp broadcast'),
        ('google_business', 'Google Business Profile'),
        ('instagram', 'Instagram'),
        ('meta_business', 'Meta Business'),
        ('sms', 'SMS'),
    ]
    
    type = models.CharField(max_length=30, choices=CHANNEL_TYPES)
    name = models.CharField(max_length=100, blank=True)
    
    config = models.JSONField(default=dict)
    # credentials, settings per channel type
    
    is_enabled = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.JSONField(default=dict, blank=True)
    
    class Meta:
        indexes = [models.Index(fields=['type', 'is_enabled'])]


class Publication(TimestampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('publishing', 'Publishing'),
        ('published', 'Published'),
        ('failed', 'Failed'),
        ('unpublished', 'Unpublished'),
    ]
    
    promotion = models.ForeignKey(
        'promotions.Promotion', related_name='publications', on_delete=models.CASCADE
    )
    channel = models.ForeignKey(
        Channel, related_name='publications', on_delete=models.CASCADE
    )
    
    external_id = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    published_at = models.DateTimeField(null=True, blank=True)
    unpublished_at = models.DateTimeField(null=True, blank=True)
    
    error = models.JSONField(default=dict, blank=True)
    retry_count = models.IntegerField(default=0)
    
    class Meta:
        unique_together = [['promotion', 'channel']]
        indexes = [models.Index(fields=['status'])]
```

## apps/notifications/models.py

```python
from django.db import models
from apps.core.models import TimestampedModel


class Notification(TimestampedModel):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('failed', 'Failed'),
        ('bounced', 'Bounced'),
    ]
    
    CHANNEL_TYPES = [
        ('email', 'Email'),
        ('telegram', 'Telegram'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('push', 'Push'),
    ]
    
    customer = models.ForeignKey(
        'subscriptions.Customer', related_name='notifications', on_delete=models.CASCADE
    )
    promotion = models.ForeignKey(
        'promotions.Promotion', related_name='notifications', on_delete=models.CASCADE
    )
    
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    external_id = models.CharField(max_length=200, blank=True)
    error = models.JSONField(default=dict, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'channel_type']),
        ]
```

## apps/aggregator/models.py (SHARED schema, denormalized index)

```python
from django.db import models
from apps.core.models import TimestampedModel


class AggregatorListing(TimestampedModel):
    """Денормализованный индекс активных акций для быстрого чтения агрегатором.
    
    Обновляется через signals при изменении Promotion.status или Publication.status.
    """
    # Откуда (denormalized из tenant schema)
    tenant_schema = models.CharField(max_length=100, db_index=True)
    tenant_slug = models.CharField(max_length=100)
    tenant_name = models.CharField(max_length=200)
    tenant_logo_url = models.URLField(blank=True)
    business_type = models.CharField(max_length=50)
    
    # Promotion data (denormalized)
    promotion_id = models.UUIDField(db_index=True)
    title = models.JSONField(default=dict)
    description = models.JSONField(default=dict)
    cover_image_url = models.URLField(blank=True)
    
    discount_type = models.CharField(max_length=20)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    is_bookable = models.BooleanField(default=False)
    available_quantity = models.IntegerField(null=True)
    
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    
    # Location & targeting
    city = models.CharField(max_length=100, db_index=True)
    district = models.CharField(max_length=100, blank=True, db_index=True)
    country = models.CharField(max_length=2, default='DE')
    
    # Categories (global mapping)
    global_category_slug = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['city', 'is_active', '-starts_at']),
            models.Index(fields=['city', 'global_category_slug', 'is_active']),
            models.Index(fields=['tenant_slug', 'is_active']),
        ]
        unique_together = [['tenant_schema', 'promotion_id']]
```

## apps/global_categories/models.py (SHARED schema)

```python
from django.db import models
from apps.core.models import TimestampedModel, I18nMixin


class GlobalCategory(TimestampedModel, I18nMixin):
    """Унифицированные категории для агрегатора (cross-tenant).
    
    Примеры: 'Bäckerei', 'Restaurant', 'Bekleidung', 'Touren'.
    Tenant.Category мапится на GlobalCategory для агрегатора.
    """
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        related_name='children', on_delete=models.SET_NULL
    )
    name = models.JSONField(default=dict)
    slug = models.SlugField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True)
    business_types = models.JSONField(default=list)
    # ['bakery', 'butcher', 'grocery'] — какие business_types сюда мапятся
    sort_order = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = 'Global Categories'
        ordering = ['sort_order', 'slug']
```

## apps/billing/models.py

```python
from django.db import models
from apps.core.models import TimestampedModel


class SubscriptionPlan(TimestampedModel):
    """План подписки tenant'а.
    
    Phase 1: один план. Поле остаётся под мульти-tier архитектуру в будущем.
    """
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    
    stripe_price_id = models.CharField(max_length=100, blank=True)
    
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    
    # Лимиты плана (для будущих tier'ов)
    max_promotions_per_month = models.IntegerField(null=True, blank=True)
    max_customers = models.IntegerField(null=True, blank=True)
    max_notifications_per_month = models.IntegerField(null=True, blank=True)
    included_channels = models.JSONField(default=list)
    included_modules = models.JSONField(default=list)
    
    is_active = models.BooleanField(default=True)
```

## Команды миграции

```bash
# Создать все миграции
python manage.py makemigrations tenants
python manage.py makemigrations core
python manage.py makemigrations catalog
python manage.py makemigrations promotions
python manage.py makemigrations subscriptions
python manage.py makemigrations publishing
python manage.py makemigrations notifications
python manage.py makemigrations billing
python manage.py makemigrations aggregator
python manage.py makemigrations global_categories

# Применить SHARED schema (Tenant, Domain, aggregator, global_categories)
python manage.py migrate_schemas --shared

# При создании Tenant через admin или management команду
# его schema будет создана автоматически (auto_create_schema=True)
# и все TENANT_APPS миграции применятся к ней

# Если нужно применить новые TENANT миграции ко всем существующим tenants:
python manage.py migrate_schemas

# Если нужно к конкретному tenant'у:
python manage.py migrate_schemas --schema=baeckerei_mueller
```

## Создание первого Tenant (для тестирования)

`apps/tenants/management/commands/create_test_tenant.py`:

```python
from django.core.management.base import BaseCommand
from apps.tenants.models import Tenant, Domain


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Public tenant (для админки) — должен существовать
        if not Tenant.objects.filter(schema_name='public').exists():
            public = Tenant(
                schema_name='public',
                name='Public',
                slug='public',
                auto_create_schema=False,
            )
            public.save()
            Domain.objects.create(
                domain='localhost',
                tenant=public,
                is_primary=True,
            )
        
        # Тестовый tenant
        if not Tenant.objects.filter(schema_name='baeckerei_test').exists():
            tenant = Tenant(
                schema_name='baeckerei_test',
                name='Bäckerei Test',
                slug='baeckerei-test',
                business_type='bakery',
                city='Hilden',
                country='DE',
                default_locale='de',
                enabled_locales=['de', 'en'],
                enabled_modules=['catalog', 'promotions', 'publishing'],
                subscription_status='trial',
            )
            tenant.save()
            Domain.objects.create(
                domain='baeckerei-test.localhost',
                tenant=tenant,
                is_primary=True,
            )
            self.stdout.write(self.style.SUCCESS(
                'Created tenant: baeckerei-test.localhost:8000'
            ))
```

Запуск: `python manage.py create_test_tenant`

Браузер: `http://baeckerei-test.localhost:8000/` → попадёшь в схему `baeckerei_test`.

---

# Часть 3: Sprint Plan

Общий принцип: **каждый спринт заканчивается работающим, проверяемым результатом**. Не «архитектура готова», а «можно зайти, нажать кнопку, что-то произойдёт».

В конце каждого спринта — проверка на демо-сценарий: «может ли владелец пекарни Тест войти и сделать X».

## Sprint 1 (Week 1–2): Foundation & Multi-tenancy

**Цель:** Работающий Django-проект с настроенным django-tenants, можно создать tenant и зайти в его схему по subdomain.

### User Stories

**Story 1.1:** Как разработчик, я хочу запустить проект локально одной командой, чтобы быстро войти в цикл разработки.
- AC: `docker compose up -d` + `manage.py runserver` запускают всё
- AC: `.env.example` содержит все нужные переменные
- AC: README описывает первичную настройку

**Story 1.2:** Как разработчик, я хочу чтобы django-tenants был настроен и работал, чтобы данные tenant'ов были изолированы.
- AC: SHARED_APPS и TENANT_APPS разделены корректно
- AC: middleware распознаёт subdomain и переключает schema
- AC: `migrate_schemas --shared` создаёт public schema

**Story 1.3:** Как админ платформы, я хочу создать нового tenant'а через Django Admin, чтобы добавлять клиентов.
- AC: Tenant и Domain видны в Django Admin
- AC: При создании Tenant автоматически создаётся PostgreSQL schema
- AC: Domain `{slug}.localhost` автоматически создаётся

**Story 1.4:** Как владелец бизнеса, я хочу зарегистрироваться через форму, чтобы получить аккаунт.
- AC: Форма регистрации с полями (email, password, business name, city, business_type)
- AC: После регистрации создаётся Tenant, User в его schema, Domain
- AC: Email верификация через django-allauth работает

**Story 1.5:** Как владелец бизнеса, я хочу войти в свой кабинет, чтобы управлять данными.
- AC: Login через email/password
- AC: Logout
- AC: Password reset через email
- AC: После логина — redirect на dashboard (пока пустой)

### Технические задачи

1. Инициализировать Django проект, добавить зависимости
2. Настроить settings (base, development)
3. Создать app `tenants` с Tenant и Domain моделями
4. Настроить django-tenants middleware и роутинг
5. Создать `urls_public.py` и `urls_tenant.py`
6. Создать management command `create_test_tenant`
7. Настроить django-allauth
8. Создать onboarding view (форма создания бизнеса → tenant + первый user)
9. Базовый layout с Tailwind CSS
10. Dashboard placeholder view
11. Health-check endpoint
12. Базовые tests (pytest + factory-boy)

### Definition of Done

- Локально: `manage.py migrate_schemas --shared` без ошибок
- Можно зайти на `localhost:8000/admin/` и создать Tenant через UI
- Subdomain `baeckerei-test.localhost:8000` открывается и видна tenant-specific страница
- Регистрация нового бизнеса через форму создаёт работающий tenant
- Тесты проходят: `pytest`

### Промпт для Claude Code

```
Контекст: см. артефакт "Phase 1: Реализация и спринты", раздел "Часть 1" и "Часть 2".

Задача Sprint 1: Реализовать foundation проекта.

1. Создай Django проект структуры как описано в "Часть 1: Project Setup"
2. Настрой settings/base.py и settings/development.py точно как в спецификации
3. Создай apps/tenants/ с моделями Tenant и Domain точно как в "Часть 2"
4. Создай config/urls_public.py и config/urls_tenant.py
5. Реализуй management command create_test_tenant
6. Настрой django-allauth для email-based auth
7. Создай простую страницу onboarding (создание бизнеса = создание Tenant)
8. Создай шаблоны: base.html, tenant/dashboard.html (placeholder)
9. Напиши тесты на:
   - Создание Tenant через management command
   - Регистрацию нового бизнеса через onboarding view
   - Изоляцию данных между tenants

Проверка готовности: после твоей работы я должен суметь:
1. Запустить проект (`docker compose up -d && python manage.py runserver`)
2. Применить миграции (`migrate_schemas --shared`)
3. Создать superuser в public
4. Создать тестовый tenant командой
5. Открыть в браузере baeckerei-test.localhost:8000/ — должен быть доступен tenant context
```

---

## Sprint 2 (Week 3–4): Catalog & Tenant Dashboard

**Цель:** Владелец бизнеса может полноценно управлять каталогом товаров через HTMX dashboard.

### User Stories

**Story 2.1:** Как владелец бизнеса, я хочу видеть список своих товаров с фильтрами и поиском.
- AC: Список с пагинацией (25 на страницу)
- AC: Поиск по name (по всем локалям)
- AC: Фильтр по category, is_active
- AC: HTMX live search без перезагрузки

**Story 2.2:** Как владелец, я хочу создать новый товар с фото.
- AC: Форма с полями name (мультиязычная), description, price, category, image
- AC: Загрузка изображения с превью
- AC: Валидация (price > 0, name не пустое)
- AC: После создания — redirect на детальную страницу

**Story 2.3:** Как владелец, я хочу редактировать товар.
- AC: Inline-редактирование через HTMX (клик на поле → input → save)
- AC: Изменение полей сохраняется без перезагрузки
- AC: История изменений в metadata

**Story 2.4:** Как владелец, я хочу управлять категориями.
- AC: CRUD категорий
- AC: Вложенность через parent
- AC: Drag-and-drop сортировка через sort_order

**Story 2.5:** Как владелец, я хочу импортировать товары из CSV.
- AC: Upload CSV файла
- AC: Маппинг столбцов на поля Product
- AC: Превью первых 5 строк перед импортом
- AC: Импорт с rollback при ошибке

### Технические задачи

1. Создать app `catalog` с моделями (см. Часть 2)
2. Django Admin для Product и Category
3. Tenant dashboard layout (sidebar + content)
4. Products list view (HTMX)
5. Product create/edit forms
6. Image upload (django-storages, локально FileSystemStorage)
7. Image preview component
8. Categories management UI
9. CSV import через django-import-export
10. Helper для i18n JSONField (виджет для нескольких локалей)
11. Tests на CRUD продуктов

### DoD

- В dashboard есть раздел "Products" с полным CRUD
- Можно загрузить картинку, она отображается в превью
- CSV импорт работает на минимум 100 строк без ошибок
- Тесты покрывают create, edit, delete, import

### Промпт для Claude Code

```
Контекст: см. артефакт Phase 1, "Часть 2: apps/catalog/models.py". Sprint 1 завершён.

Задача Sprint 2: Реализовать catalog с tenant dashboard.

1. Создай app apps/catalog с моделями (точно как в спецификации)
2. Создай миграции и убедись что они применяются к tenant schemas
3. Реализуй Django Admin для Product, Category с unfold-стилем
4. Создай tenant dashboard layout (templates/tenant/_layout.html):
   - Sidebar с навигацией (Catalog, Promotions [placeholder], Settings)
   - Top bar с email пользователя и logout
   - Tailwind CSS, минимальный clean дизайн
5. Реализуй views:
   - ProductListView с HTMX live search и фильтрами
   - ProductCreateView с image upload
   - ProductDetailView с inline-редактированием
   - ProductDeleteView
   - CategoryListView/CreateView/EditView
6. Создай i18n widget (мультиязычные input'ы для name, description)
7. Реализуй CSV import через django-import-export
8. Напиши тесты на CRUD и CSV import

Проверка готовности:
- В dashboard tenant'а есть рабочий каталог
- Можно создать категорию, потом товар в этой категории
- Загруженное изображение сохраняется и отображается
- CSV из 50 строк импортируется
```

---

## Sprint 3 (Week 5–6): Promotions & Reservations

**Цель:** Владелец бизнеса может создать акцию, опционально с бронированием. Бронирование работает с правильной конкурентностью.

### User Stories

**Story 3.1:** Как владелец, я хочу создать акцию с базовыми параметрами.
- AC: Форма: title, description, discount_type, discount_value, products/categories, starts_at, ends_at, cover_image
- AC: Валидация: ends_at > starts_at, discount_value > 0
- AC: Статус draft по умолчанию

**Story 3.2:** Как владелец, я хочу включить бронирование для акции.
- AC: Toggle "Allow booking"
- AC: При включении: total_quantity, pickup_window, pickup_location обязательны
- AC: available_quantity = total_quantity при создании

**Story 3.3:** Как владелец, я хочу изменить статус акции.
- AC: Action кнопки: Schedule, Activate, End, Cancel
- AC: Переходы статусов с валидацией (draft → scheduled → active → ended)
- AC: При ends_at в прошлом — статус автоматически ended через Celery beat

**Story 3.4:** Как владелец, я хочу видеть список броней по моей акции.
- AC: Список Reservation с фильтрами по статусу
- AC: Контактные данные клиента
- AC: Кнопка "Mark as collected" (статус → collected)

**Story 3.5:** Как клиент (через будущий aggregator или landing page), я хочу зарезервировать акцию.
- AC: POST endpoint принимает customer info + quantity
- AC: Уменьшение available_quantity атомарно (select_for_update)
- AC: При quantity > available — ошибка
- AC: Создаётся Reservation с pickup_code

### Технические задачи

1. Создать app `promotions` с моделями
2. Promotion CRUD views (HTMX-style, как у catalog)
3. Status transitions service (FSM логика)
4. Reservation service с select_for_update для атомарного booking
5. Celery beat task: автоматически переводить promotions в ended при истечении
6. Reservation expiration task: pending → expired через 30 минут
7. Pickup code генератор (уникальный, человеко-читаемый)
8. Tenant view: список броней с фильтрами
9. Reservation API endpoint (для будущего использования из агрегатора)
10. Tests:
    - Concurrent reservation (двое одновременно резервируют последнюю единицу)
    - Status transitions
    - Expiration task

### DoD

- Tenant может создать акцию через UI и активировать её
- Reservation API работает: можно зарезервировать через curl
- Concurrent test проходит (не overbook)
- При истечении ends_at promotion переходит в ended автоматически

### Промпт для Claude Code

```
Контекст: см. артефакт Phase 1, "Часть 2: apps/promotions/models.py" и "apps/subscriptions/models.py" (Customer нужен для Reservation). Sprint 2 завершён.

Задача Sprint 3:

1. Создай apps/subscriptions с моделью Customer (только Customer, Subscription будет позже)
2. Создай apps/promotions с моделями Promotion, Reservation
3. Реализуй status transitions через service класс PromotionService:
   - schedule_promotion()
   - activate_promotion()  
   - end_promotion()
   - cancel_promotion()
   с проверкой допустимых переходов
4. Реализуй ReservationService.create_reservation():
   - Использует select_for_update для блокировки Promotion
   - Уменьшает available_quantity
   - Создаёт Reservation с pickup_code
   - Атомарная транзакция
5. Создай Celery tasks:
   - check_expired_promotions (каждые 5 минут, переводит active → ended)
   - expire_pending_reservations (каждые 5 минут, переводит pending → expired через 30 минут)
6. Промо UI в tenant dashboard:
   - Promotions list с фильтром по status
   - Promotion form (со всеми полями включая bookable toggle)
   - Кнопки status transitions
   - Reservations sub-page для каждой promotion
7. Reservation API endpoint /api/v1/promotions/{id}/reserve (DRF)
8. Tests:
   - test_concurrent_reservations: 10 потоков резервируют по 1 единицу из 10 доступных, должно успешно
   - test_overbook_prevented: 11 потоков из 10 → один fail
   - test_status_transitions
   - test_expired_promotion_task

Проверка готовности:
- В tenant dashboard можно создать акцию "Apfelstrudel -30%" с bookable=true, quantity=20
- POST на /api/v1/promotions/{id}/reserve с {customer_email, quantity: 2} возвращает pickup_code
- Через 30 минут pending reservation станет expired
```

---

## Sprint 4 (Week 7–8): Publishing Engine & Landing Pages

**Цель:** При публикации promotion автоматически появляется на subdomain tenant'а. У потребителя есть нормальная публичная страница, где можно зарезервировать.

### User Stories

**Story 4.1:** Как владелец, я хочу чтобы мои активные акции автоматически отображались на моём subdomain.
- AC: При активации promotion → publication в канал `subdomain` создаётся автоматически (через signal)
- AC: `{slug}.platform.com` показывает список активных акций
- AC: При ends_at → publication.status = unpublished автоматически

**Story 4.2:** Как потребитель, я хочу зайти на сайт пекарни и увидеть текущие акции.
- AC: Public страница без auth, чистый design
- AC: Список акций с фото, скидкой, временем действия
- AC: Клик на акцию → детальная страница

**Story 4.3:** Как потребитель, я хочу зарезервировать акцию прямо со страницы.
- AC: На детальной странице форма: email/phone, quantity
- AC: После submit — pickup_code на экране и email с инструкциями
- AC: Reservation создаётся в БД tenant'а

**Story 4.4:** Как владелец, я хочу настроить branding моей страницы.
- AC: В settings: logo upload, primary color picker
- AC: На landing page используются эти настройки

**Story 4.5:** Как владелец, я хочу подключить custom domain.
- AC: В settings: ввод custom_domain
- AC: Инструкции по настройке CNAME
- AC: Verification (проверка DNS)
- AC: После verification — Domain создаётся, Caddy on-demand TLS выдаёт сертификат

### Технические задачи

1. Создать app `publishing` с моделями
2. Реализовать `BasePublisher` интерфейс
3. `SubdomainPublisher` (no-op, страница рендерится напрямую из БД)
4. Signals: `promotion_activated` → создать Publication в subdomain channel
5. Public views для subdomain landing page (LandingHomeView, PromotionDetailView)
6. Public Reservation form view (использует ReservationService из Sprint 3)
7. Tenant settings UI: branding, custom domain
8. Custom domain verification (DNS lookup проверяет CNAME)
9. Caddy on-demand TLS endpoint `/api/verify-domain` (возвращает 200 если domain зарегистрирован)
10. Confirmation email при reservation (через django.core.mail, пока console backend)
11. Tests: integration test promotion flow (create → activate → visible on subdomain → reserve → email sent)

### DoD

- При активации акции она появляется на subdomain без ручных действий
- Public страница работает без auth
- Reservation flow работает end-to-end
- Settings: branding меняет внешний вид landing page
- Custom domain verification технически работает (Caddy интеграция может быть отложена до production)

### Промпт для Claude Code

```
Контекст: артефакт Phase 1, "Часть 2: apps/publishing/models.py". Sprint 3 завершён, есть рабочие Promotion и Reservation.

Задача Sprint 4:

1. Создай apps/publishing с моделями Channel, Publication
2. Создай абстракцию BasePublisher (см. артефакт архитектуры):
   - apps/publishing/publishers/base.py
   - apps/publishing/publishers/subdomain.py
   - Registry в apps/publishing/publishers/__init__.py
3. Создай signals в apps/promotions/signals.py:
   - При status='active' → создать/обновить Publication для всех is_default=True channels
   - При status='ended' → unpublish
4. Создай publishing service который вызывает publisher.publish() асинхронно через Celery
5. Public views в apps/publishing/views/landing.py:
   - LandingHomeView (главная страница subdomain'а: список активных промо)
   - PromotionLandingView (детальная страница с reservation формой)
   - ReservationConfirmView (страница с pickup_code после резервации)
6. Templates (templates/landing/):
   - landing/base.html (с tenant branding)
   - landing/home.html
   - landing/promotion_detail.html
   - landing/reservation_confirm.html
   Дизайн: clean, responsive, Tailwind, акцент на акциях
7. URL routing:
   - urls_tenant.py: добавить landing/ urls для public части
   - URL '/' на tenant subdomain → LandingHomeView
8. Tenant settings UI:
   - Branding (logo, primary_color)
   - Custom domain (input + verification)
9. Email confirmation после reservation (через django.core.mail)
10. Tests:
    - End-to-end: создать promotion → activate → curl subdomain → видна
    - Reservation через landing page работает

Проверка готовности:
- На baeckerei-test.localhost:8000 видна главная с активными акциями
- Клик на акцию → детальная страница
- Заполнение формы → confirmation page с pickup_code
- В tenant admin видна созданная резервация
```

---

## Sprint 5 (Week 9–10): Aggregator & Customer Experience

**Цель:** Публичный агрегатор работает. Потребитель может зарегистрироваться, подписаться на бизнесы, получать уведомления.

### User Stories

**Story 5.1:** Как потребитель, я хочу зайти на главную агрегатора и выбрать свой город.
- AC: Главная: список городов с активными акциями
- AC: Геолокация (опционально): preselect ближайший город

**Story 5.2:** Как потребитель, я хочу видеть все актуальные акции в моём городе.
- AC: Страница `/{city}/` показывает все active промо
- AC: Сортировка: ending soon first
- AC: Фильтр по category (через global_categories mapping)
- AC: Карточки с фото, скидкой, бизнесом, временем

**Story 5.3:** Как потребитель, я хочу подписаться на конкретный бизнес.
- AC: На странице бизнеса в агрегаторе — кнопка "Subscribe"
- AC: Регистрация через email или Telegram (lightweight)
- AC: Выбор каналов уведомлений
- AC: Confirmation email

**Story 5.4:** Как потребитель, я хочу подписаться на категорию + город.
- AC: На странице `/{city}/{category}/` — кнопка "Notify me about new {category} promotions in {city}"
- AC: Subscription создаётся с category + target_city

**Story 5.5:** Как потребитель, я хочу управлять моими подписками.
- AC: `/account/subscriptions/` — список с возможностью unsubscribe
- AC: Email-based access (magic link)

**Story 5.6:** Как владелец бизнеса, я хочу чтобы мои промо появлялись в агрегаторе автоматически.
- AC: Channel type='aggregator' создаётся при tenant onboarding с is_default=True
- AC: AggregatorPublisher создаёт AggregatorListing запись (denormalized)
- AC: При ends/cancel → AggregatorListing.is_active=False

### Технические задачи

1. Создать apps/aggregator (SHARED) с views и templates
2. Создать apps/global_categories с моделями + seed данные
3. Mapping: business_type → global_category (через GlobalCategory.business_types)
4. AggregatorPublisher реализация:
   - publish: создаёт/обновляет AggregatorListing
   - unpublish: is_active=False
5. Aggregator views:
   - HomeView (выбор города)
   - CityView (`/{city}/`)
   - CityCategoryView (`/{city}/{category}/`)
   - TenantPublicView (`/biz/{slug}/`)
   - PromotionAggregatorView (`/promotion/{id}/`)
6. Customer account:
   - Lightweight auth через magic link (email)
   - Telegram bot auth flow (опционально в этом sprint)
   - Account views: subscriptions list, manage, unsubscribe
7. Subscription create flow с consent management
8. Templates агрегатора (templates/aggregator/) — clean, mobile-first
9. Performance: cache CityView и list queries (Redis cache)
10. Tests: end-to-end customer flow

### DoD

- `aggregator.platform.com` показывает города
- В городе видны акции из нескольких тестовых tenants
- Можно зарегистрироваться и подписаться на бизнес
- Subscription создаётся, customer видит её в account

### Промпт для Claude Code

```
Контекст: артефакт Phase 1, "Часть 2: apps/aggregator/models.py, apps/global_categories/models.py, apps/subscriptions/models.py". Sprint 4 завершён.

Задача Sprint 5:

1. Создай apps/global_categories с моделью GlobalCategory + миграция + seed data:
   - Bäckerei (business_types: ['bakery'])
   - Metzgerei (business_types: ['butcher'])
   - Lebensmittel (business_types: ['grocery'])
   - Restaurant (business_types: ['restaurant', 'cafe'])
   - Bekleidung (business_types: ['clothing'])
   - и т.д.
   
2. Создай apps/aggregator с AggregatorListing моделью
3. Создай AggregatorPublisher в apps/publishing/publishers/aggregator.py:
   - publish: создаёт/обновляет AggregatorListing с denormalized данными tenant'а
   - unpublish: is_active=False
   - Использует schema_context для cross-schema запросов
4. Signals в apps/aggregator/signals.py:
   - При изменении Promotion → triggered AggregatorPublisher
5. Создай apps/subscriptions/models/Subscription модель (Customer уже есть)
6. Customer auth через magic link:
   - email → POST /account/login/ → магическая ссылка на email
   - Click → session создаётся
7. Aggregator views (apps/aggregator/views/):
   - HomeView: список городов
   - CityView: `/{city_slug}/`
   - CityCategoryView: `/{city_slug}/{category_slug}/`
   - TenantPublicView: `/biz/{tenant_slug}/`
   - PromotionView: `/promotion/{listing_id}/`
   - AccountView, SubscriptionListView, SubscribeView
8. Templates агрегатора с Tailwind, mobile-first design
9. Cache: list views кэшируются в Redis на 60 секунд
10. Tests:
    - test_listing_created_on_activation
    - test_listing_deactivated_on_end
    - test_subscribe_flow
    - test_magic_link_auth

Проверка готовности:
- Создаю 2 тестовых tenant'а в Hilden, по 2 промо в каждом
- На aggregator.localhost:8000 видны оба
- /hilden/ показывает все 4 промо
- Регистрируюсь email'ом, подписываюсь на один из бизнесов
- В account/subscriptions/ вижу свою подписку
```

---

## Sprint 6 (Week 11–12): Notifications, Billing & Launch

**Цель:** Уведомления работают (email + telegram). Stripe billing работает. Готовы к запуску — продакшен развёрнут, мониторинг работает.

### User Stories

**Story 6.1:** Как подписчик, я хочу получить email когда мой выбранный бизнес публикует новое промо.
- AC: При publish в канал aggregator → notification engine находит matching subscriptions → отправляет email
- AC: Rate-limited (max 100 emails/минуту)
- AC: Можно unsubscribe одним кликом из email

**Story 6.2:** Как подписчик, я хочу получить Telegram уведомление.
- AC: При регистрации можно привязать Telegram через бот
- AC: При новом промо приходит сообщение в личку

**Story 6.3:** Как владелец, я хочу начать 14-дневный trial автоматически при регистрации.
- AC: При создании Tenant: subscription_status='trial', trial_ends_at=now+14d
- AC: В dashboard виден countdown trial
- AC: За 3 дня до окончания — email напоминание

**Story 6.4:** Как владелец, я хочу подписаться на план через Stripe.
- AC: В billing settings — кнопка "Subscribe"
- AC: Redirect на Stripe Checkout
- AC: После успешной оплаты — webhook → subscription_status='active'
- AC: Customer portal для управления подпиской

**Story 6.5:** Как владелец trial с истекшим сроком, я не могу публиковать новые промо.
- AC: Если trial expired и no active subscription → UI блокирует create promotion
- AC: Существующие активные промо продолжают работать ещё 7 дней (grace period)
- AC: После grace period — все promotions move to draft

**Story 6.6:** Как админ платформы, я хочу видеть ошибки в production.
- AC: Sentry настроен
- AC: Health-check endpoint
- AC: Basic metrics (active tenants, daily promotions, daily notifications)

### Технические задачи

1. NotificationEngine реализация в apps/notifications/:
   - BaseNotificationChannel
   - EmailChannel (через django-anymail + Resend)
   - TelegramChannel (через python-telegram-bot)
   - notify_subscribers_task (Celery, rate-limited)
2. Email templates (subscription_confirmation, new_promotion, trial_ending)
3. Telegram bot setup:
   - Bot создаётся в Botfather
   - Polling worker через Celery beat
   - Auth flow: customer вводит код в боте → linked
4. Stripe integration через dj-stripe:
   - SubscriptionPlan seed (один план: "Standard 30€/мес")
   - Stripe Checkout integration
   - Webhook handler для subscription events
   - Customer Portal redirect
5. Trial management:
   - Celery beat task: проверяет trial_ends_at, шлёт напоминания
   - Middleware blocks actions если trial expired & no subscription
6. Production deployment:
   - Dockerfile production-ready
   - Hetzner setup (1× CCX23 + 1× CX31)
   - Caddyfile с automatic TLS
   - GitHub Actions deploy workflow
   - Postgres backups через Hetzner snapshots
7. Sentry integration
8. Health-check `/health/` endpoint
9. Basic admin metrics dashboard
10. End-to-end tests

### DoD

- Notification flow работает end-to-end (создание промо → email подписчикам)
- Telegram bot работает (опционально, если успели)
- Stripe trial → paid конверсия работает
- Production deployed: `platform.com` доступен
- Sentry получает события
- Health-check возвращает 200

### Промпт для Claude Code

```
Контекст: артефакт Phase 1, "Часть 2: apps/notifications/models.py, apps/billing/models.py". Sprint 5 завершён.

Задача Sprint 6 разбита на 4 под-задачи. Делай по одной за раз, я буду проверять между ними.

Под-задача 6A: Notification engine (email)
1. apps/notifications/channels/base.py — BaseNotificationChannel
2. apps/notifications/channels/email.py — EmailChannel (django-anymail + Resend backend)
3. apps/notifications/tasks.py:
   - notify_subscribers_task(promotion_id) — find matching subscriptions, queue send tasks
   - send_notification_task(customer_id, promotion_id, channel_type) — rate-limited
4. Signal: при AggregatorListing создании → notify_subscribers_task.delay()
5. Email templates: templates/emails/new_promotion.html + .txt
6. Unsubscribe one-click link с signed token
7. Tests

Под-задача 6B: Telegram bot
1. apps/notifications/channels/telegram.py — TelegramChannel
2. Bot setup: python-telegram-bot, polling через Celery
3. Customer auth flow:
   - В account: button "Connect Telegram" → showing /start link с token
   - Customer открывает бота, /start <token> → linked
4. Bot handlers: /start, /subscriptions, /unsubscribe
5. Send notification через bot.send_message
6. Tests с mock bot

Под-задача 6C: Billing
1. SubscriptionPlan seed: один план "Standard" — 30€/мес, stripe_price_id
2. Stripe Checkout view: create session, redirect
3. dj-stripe webhook handler:
   - customer.subscription.created → Tenant.subscription_status='active'
   - customer.subscription.deleted → 'cancelled'
   - invoice.payment_failed → 'past_due'
4. Customer Portal redirect view
5. Middleware: блокирует create promotion если trial expired & no active subscription
6. Trial reminder task: за 3 дня до trial_ends_at — email
7. Grace period logic

Под-задача 6D: Production deployment
1. Production Dockerfile (multi-stage, non-root user)
2. docker-compose.production.yml
3. Caddyfile с on-demand TLS
4. GitHub Actions workflow: build → deploy на Hetzner через SSH
5. Sentry integration в settings/production.py
6. Health check endpoint
7. README с инструкцией по deploy
```

---

## Что после Phase 1

После 12 недель ожидаемый результат:
- Работающий продукт с end-to-end flow
- 0-5 платящих клиентов (зависит от того, искал ли ты их параллельно)
- Архитектурные точки расширения для CRM, ERP, dropshipping, туров — на месте

Следующие шаги (Phase 2):
- **Sprint 7-8:** WhatsApp Business + Google Business Profile интеграции (главные каналы привлечения)
- **Sprint 9-10:** Customer database (CRM-light): сегментация, теги, lifetime value
- **Sprint 11-12:** Onboarding optimization, self-service signup, инструменты роста

И только после 30+ платящих клиентов — рефакторинг core для второго продукта (туры).

---

## Принципы работы с Claude Code

1. **Один спринт за раз.** Не давай задачи через несколько спринтов.
2. **Дай контекст артефакта.** Каждая сессия — копируй ссылку на этот документ или вставляй релевантные части.
3. **Проверяй между задачами.** После каждой под-задачи запускай локально, проверяй, что работает.
4. **Не отступай от спецификации моделей.** Если Claude Code предлагает изменить поле — спроси меня сначала.
5. **Tests пиши параллельно, не "потом".** Phase 1 должен иметь >70% coverage.
6. **Commit часто.** Маленькие коммиты после каждой story.
7. **Code review с Claude.** После каждого спринта прогоняй код через "review этот PR на: security, performance, Django best practices".
