from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

# ---------------------------------------------------------------------------
# django-tenants: SHARED vs TENANT apps
# ---------------------------------------------------------------------------
SHARED_APPS = [
    "django_tenants",
    "apps.tenants",
    # Django built-ins
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "unfold",  # должен быть до admin
    "django.contrib.admin",
    "django.contrib.sites",
    # Third-party shared
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "django_celery_beat",
    "django_celery_results",
    "djstripe",
    "widget_tweaks",  # template-теги для форм (без БД)
    "apps.audit",  # журнал действий (SHARED), дополнение 1.1
    "apps.integrations.webhooks",  # scaffold исходящих вебхуков (SHARED), доп. 1.4
    # SHARED apps платформы (раскомментируются по мере прохождения спринтов)
    # "apps.aggregator",       # Sprint 5
    # "apps.global_categories",  # Sprint 5
]

TENANT_APPS = [
    # Django built-ins (нужны и в tenant schema)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    # TENANT apps платформы (раскомментируются по мере прохождения спринтов)
    "apps.core",  # Task 1.3 — абстрактные миксины/утилиты, без своих таблиц
    "apps.catalog",  # Sprint 2 — каталог товаров/категорий
    # "apps.promotions",
    # "apps.subscriptions",
    # "apps.publishing",
    # "apps.notifications",
    # "apps.billing",
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        # Persistent connections: при schema-per-tenant каждый запрос делает
        # SET search_path, поэтому пересоздавать соединение на каждый request
        # дорого. CONN_MAX_AGE переиспользует соединение, health checks
        # отбраковывают «протухшие».
        # ВНИМАНИЕ: при использовании PgBouncer допустим только session-pooling
        # режим — transaction-pooling несовместим с search_path арендатора.
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
    }
}

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

# ---------------------------------------------------------------------------
# Cache & sessions (Redis)
# ---------------------------------------------------------------------------
# Redis уже есть в стеке. Без явного CACHES Django падает на LocMemCache,
# который не шарится между gunicorn-воркерами. Отдельный db-индекс (/1),
# чтобы не пересекаться с Celery broker (/0).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://localhost:6379/1"),
    }
}

# Сессии — в кэш (Redis), а не в БД shared-схемы (меньше write-нагрузки
# на каждый запрос аутентифицированного арендатора).
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls_tenant"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "de"
LANGUAGES = [
    ("de", "Deutsch"),
    ("en", "English"),
]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "Europe/Berlin"
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ---------------------------------------------------------------------------
# Auth (allauth)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
SITE_ID = 1
# Базовый домен для генерации URL арендаторов (онбординг, ссылки на субдомены).
# В dev переопределяется на "siteadaptor.de:8000" (см. development.py).
TENANT_DOMAIN_BASE = env("TENANT_DOMAIN_BASE", default="siteadaptor.de")
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# mandatory требует рабочей отправки почты (Resend). Пока RESEND_API_KEY не
# настроен, держим optional через env, иначе вход падает 500 на отправке письма.
# На боевом проде с настроенным Resend → ACCOUNT_EMAIL_VERIFICATION=mandatory.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="optional")
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
# Результаты задач — в Redis с TTL, а не в Postgres ("django-db"): тот писал
# строку на КАЖДУЮ задачу (рассылки, публикации) → bloat + write-нагрузка.
CELERY_RESULT_BACKEND = env("REDIS_RESULT_URL", default="redis://localhost:6379/2")
CELERY_RESULT_EXPIRES = 60 * 60  # 1 час
CELERY_RESULT_EXTENDED = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE = TIME_ZONE

# ---------------------------------------------------------------------------
# Email (Resend через django-anymail)
# ---------------------------------------------------------------------------
_RESEND_API_KEY = env("RESEND_API_KEY", default="")
ANYMAIL = {"RESEND_API_KEY": _RESEND_API_KEY}
# Без ключа Resend письма слать нечем → используем консольный бэкенд, иначе
# любая отправка (напр. верификация email при signup) падает 500.
if _RESEND_API_KEY:
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@platform.local")

# ---------------------------------------------------------------------------
# Stripe (dj-stripe)
# ---------------------------------------------------------------------------
STRIPE_LIVE_MODE = env.bool("STRIPE_LIVE_MODE", default=False)
STRIPE_TEST_PUBLIC_KEY = env("STRIPE_TEST_PUBLIC_KEY", default="")
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", default="")
DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET", default="")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"

# ---------------------------------------------------------------------------
# Media & storage
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# S3 (Hetzner Object Storage), если задан ключ; иначе — локальная ФС.
# Так single-сервер без S3 хранит загрузки на диске (медиа-том в compose),
# а полноценный прод с ключами — в объектном хранилище.
_AWS_KEY = env("AWS_ACCESS_KEY_ID", default="")
if _AWS_KEY:
    _default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": _AWS_KEY,
            "secret_key": env("AWS_SECRET_ACCESS_KEY", default=""),
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME", default=""),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=""),
            "region_name": env("AWS_S3_REGION_NAME", default="eu-central"),
        },
    }
    SERVE_MEDIA = False  # отдаёт S3/CDN
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    SERVE_MEDIA = True  # Django сам отдаёт /media/ (single-сервер)

STORAGES = {
    "default": _default_storage,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging: вывод в stdout (виден в docker logs). Без этого Django в DEBUG=False
# не печатает 500-трейсбеки, и прод-ошибки невидимы.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # 500-ошибки запросов с полным трейсбеком в stdout.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
