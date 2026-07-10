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
    "rosetta",  # T1-c (FB-12): веб-редактор переводов .po (платформенный, superuser-only)
    "apps.audit",  # журнал действий (SHARED), дополнение 1.1
    "apps.integrations.webhooks",  # scaffold исходящих вебхуков (SHARED), доп. 1.4
    "apps.billing",  # Sprint 5 — биллинг/подписки (SHARED: статус подписки на Tenant)
    "apps.secrets",  # M23+ — зашифрованные ключи интеграций, управляемые из админки (SHARED)
    # SHARED apps платформы (раскомментируются по мере прохождения спринтов)
    "apps.aggregator",  # Sprint 4 — локальный агрегатор (SHARED, материализованные листинги)
    "apps.support",  # M22c — платформенная техподдержка тенант↔SiteAdaptor (SHARED)
    "apps.partners",  # D3 — партнёрка веб-студий: реф-атрибуция + кабинет /partner/ (SHARED)
    # "apps.global_categories",  # Sprint 5
]

TENANT_APPS = [
    # Django built-ins (нужны и в tenant schema)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    # TENANT apps платформы (раскомментируются по мере прохождения спринтов)
    "apps.core",  # Task 1.3 — абстрактные миксины/утилиты, без своих таблиц
    "apps.catalog",  # Sprint 2 — каталог товаров/категорий
    "apps.imports",  # Sprint 2 — CSV-импорт товаров
    "apps.promotions",  # Sprint 3 — акции и резервирование
    "apps.loyalty",  # вынесено из promotions (2026-06-22): штампы + ваучеры (TENANT)
    # "apps.subscriptions",
    "apps.publishing",  # Sprint 4 — каналы публикации (TENANT)
    "apps.notifications",  # Sprint 6 — уведомления (TENANT)
    "apps.crm",  # Track C3 — CRM-минимум «Клиенты» (TENANT)
    "apps.orders",  # Track D / D2 — Click & Collect (TENANT)
    "apps.booking",  # Track D / D3 — запись по времени (TENANT)
    "apps.finance",  # Track D / D4 — журнал выручки (TENANT)
    "apps.stays",  # Track E — date-range-бронь / Übernachtung (TENANT)
    "apps.jobs",  # G6 — Aufträge/Angebote / смета Handwerker (TENANT)
    "apps.inbox",  # M22 — чат/поддержка/тикеты клиент↔бизнес (TENANT)
    "apps.telegram",  # M23/TG1 — Telegram-бот бизнеса (Mini App) (TENANT)
    "apps.events",  # A6 — события/ретриты: платный билет + ростер (TENANT)
    "apps.account",  # CA — ЛК клиента на витрине бизнеса (magic-link), без моделей
    "apps.reviews",  # UA4-4a — generic-отзывы о продаваемой сущности (TENANT)
    "apps.collections",  # UB3-2 — M2M-подборки (коллекции) услуг/номеров (TENANT)
    "apps.inventory",  # U-D3 — склад-леджер StockMovement (append-only) (TENANT)
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
    # Автоподключение кастомных доменов: трастит хосты из таблицы Domain ДО
    # проверки ALLOWED_HOSTS в TenantMainMiddleware (иначе DisallowedHost → 404).
    "apps.tenants.middleware.CustomDomainHostMiddleware",
    "django_tenants.middleware.main.TenantMainMiddleware",
    # Резолвер мульти-доменных порталов агрегатора (P2.1): кладёт request.portal
    # на public-схеме. Должен идти сразу после TenantMainMiddleware (нужен tenant).
    "apps.aggregator.middleware.AggregatorPortalMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    # T1 (FB-12): язык кабинета перекрывает язык витрины на кабинет-путях. После
    # LocaleMiddleware (нужны session+tenant) и до рендера вьюх.
    "apps.core.middleware.CabinetLocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Гейтинг подписки: suspended/trial_expired → кабинет read-only (Sprint 5).
    "apps.billing.middleware.SubscriptionGatingMiddleware",
    # Гейтинг модулей (Track D / D0a): неактивный модуль кабинета → 404.
    "apps.core.middleware.ModuleGatingMiddleware",
    # H1.1: витрина кадрируется same-origin (live-preview редактора может переходить
    # по ссылкам между storefront-страницами). ВЫШЕ XFrameOptions → перебивает DENY.
    "apps.core.middleware.StorefrontFrameOptionsMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

# Диагностическая 403-страница CSRF: показывает точную причину отказа Django +
# сигналы запроса (кука csrftoken, Origin/Referer, is_secure за прокси, host),
# чтобы чинить прицельно без DEBUG/доступа к логам. Причина также в django.security.csrf.
CSRF_FAILURE_VIEW = "apps.core.csrf.csrf_failure"

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
                "apps.billing.context.subscription",
                # Навигация кабинета из реестра модулей (Track D / D0a).
                "apps.core.context.modules_nav",
                # Клиент портала (P2.3a): portal_user в шаблонах портальных хостов.
                "apps.aggregator.context.portal_user",
                # SEO-1: title/description витрины из движка мета-заготовок.
                "apps.core.context_processors.seo",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "de"
# Реестр языков платформы. Владелец включает нужное подмножество на /dashboard/settings/
# languages/ (страница «Sprachen»); витрина-переключатель и per-locale поля контента
# генерятся по включённым (L1/L2, active_locales). Добавить язык = одна строка здесь
# (всё остальное — генерик). Набор — под DACH-микробизнес с разноязычной клиентурой; все
# LTR (RTL-языки типа арабского — отдельно, нужен dir=rtl). Хром (кнопки) переводится .po
# отдельно — контент (названия/описания) владелец заполняет per-locale сразу.
LANGUAGES = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("tr", "Türkçe"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("pl", "Polski"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("es", "Español"),
    ("nl", "Nederlands"),
    ("pt", "Português"),
]
USE_I18N = True

# T1-c (FB-12): django-rosetta — веб-редактор переводов .po (на /rosetta/, public-схема).
# ⚠️ Правит .po НА ДИСКЕ; в проде ФС эфемерна (образ) → изменения теряются на деплое,
# пока не закоммичены в git. Рабочий цикл: править в dev/staging → скачать/закоммитить
# .po → задеплоить. Доступ — только суперпользователю (инструмент платформы, не тенанта).
ROSETTA_ACCESS_CONTROL_FUNCTION = "config.rosetta_access.can_translate"
ROSETTA_MESSAGES_PER_PAGE = 25
ROSETTA_SHOW_AT_ADMIN_PANEL = False
ROSETTA_STORAGE_CLASS = "rosetta.storage.SessionRosettaStorage"

# T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка ВИТРИНЫ. Курируемый
# список ПЕРЕВЕДЁННЫХ языков кабинета (у которых есть `.po`); растёт по мере готовности
# перевода (T1-b). Не путать с LANGUAGES (весь реестр витрины). de = исходный (msgid).
CABINET_LANGUAGES = ["de", "en"]

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
# Публичный IP сервера для self-service custom-доменов: владелец ставит на него
# A-запись своего домена, мы сверяем и активируем (apps.tenants.domains). Пусто →
# страница доменов показывает «недоступно» вместо проверки.
CUSTOM_DOMAIN_TARGET_IP = env("CUSTOM_DOMAIN_TARGET_IP", default="")
# Кэш публичной выдачи агрегатора/порталов, сек (apps.core.pagecache);
# 0 — выключен (так в тестах, см. settings/test.py).
PUBLIC_PAGE_CACHE_TTL = env.int("PUBLIC_PAGE_CACHE_TTL", default=120)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# mandatory требует рабочей отправки почты (Resend). Пока RESEND_API_KEY не
# настроен, держим optional через env, иначе вход падает 500 на отправке письма.
# На боевом проде с настроенным Resend → ACCOUNT_EMAIL_VERIFICATION=mandatory.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="optional")
# после логина — в кабинет владельца; после выхода — на публичную витрину
LOGIN_REDIRECT_URL = "/dashboard/"
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

# Периодические задачи. DatabaseScheduler синхронизирует это в БД при старте
# beat'а. Задачи сами проходят по всем схемам арендаторов (см. apps/*/tasks.py).
CELERY_BEAT_SCHEDULE = {
    "expire-reservations": {
        "task": "apps.promotions.tasks.expire_reservations",
        "schedule": 300.0,  # каждые 5 минут — просрочка броней + возврат остатка
    },
    # C1: утренний дайджест владельцу — раз в час; внутри гейт «локальный час
    # тенанта == 7» (tenant.timezone) + дедуп по дате (unique dedupe_key).
    "owner-digests": {
        "task": "apps.core.tasks.send_owner_digests",
        "schedule": 3600.0,
    },
    # CM-2: отложенные посты контент-календаря + запланированный блог.
    "send-due-content": {
        "task": "apps.publishing.tasks.send_due_content",
        "schedule": 300.0,
    },
    "roll-promotion-statuses": {
        "task": "apps.promotions.tasks.roll_promotion_statuses",
        "schedule": 300.0,  # каждые 5 минут — scheduled→active, active→ended
    },
    "roll-recurring-promotions": {
        "task": "apps.promotions.tasks.roll_recurring_promotions",
        "schedule": 3600.0,  # раз в час — авто-повтор завершившихся акций (Track B3b)
    },
    "purge-reservation-pii": {
        "task": "apps.promotions.tasks.purge_reservation_pii",
        "schedule": 86400.0,  # раз в сутки — DSGVO-обезличивание старых контактов
    },
    # B4.4: авто-win-back — персональный код «не покупал N дней» (opt-in-база,
    # настройки на кампании kind=auto_winback, дедуп-окно = N дней).
    "send-winback-coupons": {
        "task": "apps.promotions.tasks.send_winback_coupons",
        "schedule": 86400.0,
    },
    "roll-subscriptions": {
        "task": "apps.billing.tasks.roll_subscriptions",
        "schedule": 86400.0,  # раз в сутки — жизненный цикл подписок + напоминания
    },
    "bill-usage-fees": {
        "task": "apps.billing.tasks.bill_usage_fees",
        "schedule": 86400.0,  # раз в сутки — Nutzungsgebühr за прошлый месяц (P2.5-fee)
    },
    "send-booking-reminders": {
        "task": "apps.booking.tasks.send_booking_reminders",
        "schedule": 3600.0,  # раз в час — напоминание за N часов до записи (D3c)
    },
    "send-booking-post-visits": {
        "task": "apps.booking.tasks.send_booking_post_visits",
        "schedule": 86400.0,  # раз в сутки — danke + запрос отзыва об услуге (UA4-4b)
    },
    # CM-6.4: danke + запрос отзыва о товарах после выдачи/отправки заказа.
    "send-order-post-purchases": {
        "task": "apps.orders.tasks.send_order_post_purchases",
        "schedule": 86400.0,
    },
    # B2.1: напоминание о незавершённой Stripe-оплате заказа (раз в час).
    "send-order-payment-reminders": {
        "task": "apps.orders.tasks.send_order_payment_reminders",
        "schedule": 3600.0,
    },
    # B2.2/B2.3: то же для депозита брони, предоплаты проживания и билета.
    "send-booking-payment-reminders": {
        "task": "apps.booking.tasks.send_booking_payment_reminders",
        "schedule": 3600.0,
    },
    "send-stay-payment-reminders": {
        "task": "apps.stays.tasks.send_stay_payment_reminders",
        "schedule": 3600.0,
    },
    "send-ticket-payment-reminders": {
        "task": "apps.events.tasks.send_ticket_payment_reminders",
        "schedule": 3600.0,
    },
    "send-service-reminders": {
        "task": "apps.jobs.tasks.send_service_reminders",
        "schedule": 86400.0,  # раз в сутки — TÜV/Service-Reminder за N дней (A9)
    },
    "send-stay-reminders": {
        "task": "apps.stays.tasks.send_stay_reminders",
        "schedule": 86400.0,  # раз в сутки — напоминание о заезде (Track E / E3)
    },
    "sync-ical-sources": {
        "task": "apps.stays.tasks.sync_ical_sources",
        "schedule": 3600.0,  # раз в час — импорт занятости Booking.com/Airbnb (A5b)
    },
    "send-stay-post-stay": {
        "task": "apps.stays.tasks.send_stay_post_stay",
        "schedule": 86400.0,  # раз в сутки — post-stay письмо + запрос отзыва (G2)
    },
    "purge-old-registrations": {
        "task": "apps.stays.tasks.purge_old_registrations",
        "schedule": 86400.0,  # раз в сутки — удаление Meldescheine >1 года (G6/DSGVO)
    },
    "send-event-reminders": {
        "task": "apps.events.tasks.send_event_reminders",
        "schedule": 86400.0,  # раз в сутки — pre-event напоминание участникам (R9)
    },
    "send-event-post-event": {
        "task": "apps.events.tasks.send_event_post_event",
        "schedule": 86400.0,  # раз в сутки — post-event письмо + запрос отзыва (R9)
    },
    "charge-installments": {
        "task": "apps.events.tasks.charge_installments",
        "schedule": 86400.0,  # раз в сутки — off-session списания долей рассрочки (R10c)
    },
    "recheck-custom-domains": {
        "task": "apps.tenants.tasks.recheck_pending_custom_domains",
        "schedule": 300.0,  # каждые 5 минут — авто-подтверждение кастомных доменов по DNS
    },
}

# За сколько часов до начала записи слать напоминание (Track D / D3c).
BOOKING_REMINDER_HOURS = env.int("BOOKING_REMINDER_HOURS", default=24)
# A9: за сколько дней до TÜV/Service слать напоминание клиенту (Werkstatt-ретеншн).
SERVICE_REMINDER_LEAD_DAYS = env.int("SERVICE_REMINDER_LEAD_DAYS", default=21)
# R9: за сколько дней до события слать напоминание участникам / после — post-event.
EVENT_REMINDER_DAYS = env.int("EVENT_REMINDER_DAYS", default=7)
EVENT_POSTEVENT_DAYS = env.int("EVENT_POSTEVENT_DAYS", default=1)
# R10: сколько раз пытаться списать долю рассрочки до эскалации (план → failed).
INSTALLMENT_MAX_ATTEMPTS = env.int("INSTALLMENT_MAX_ATTEMPTS", default=3)

# За сколько дней до заезда слать напоминание о брони (Track E / E3).
STAY_REMINDER_DAYS = env.int("STAY_REMINDER_DAYS", default=1)

# DSGVO: через сколько дней после последней активности обезличивать контакты
# клиентов без активных броней (см. apps/promotions/tasks.py::purge_due_customers).
RESERVATION_PII_RETENTION_DAYS = env.int("RESERVATION_PII_RETENTION_DAYS", default=90)

# ---------------------------------------------------------------------------
# Email (Resend через django-anymail)
# ---------------------------------------------------------------------------
_RESEND_API_KEY = env("RESEND_API_KEY", default="")
ANYMAIL = {"RESEND_API_KEY": _RESEND_API_KEY}
# «Свои письма без Resend»: достаточно EMAIL_HOST/USER/PASSWORD в .env.prod —
# обычный SMTP-бэкенд Django (например, ящик Hostinger; порт 465 → SSL, иначе TLS).
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_USE_TLS = not EMAIL_USE_SSL
# Приоритет: Resend → SMTP → console (без почты отправка не должна падать 500).
if _RESEND_API_KEY:
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
elif EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@platform.local")

# ---------------------------------------------------------------------------
# Stripe (dj-stripe)
# ---------------------------------------------------------------------------
STRIPE_LIVE_MODE = env.bool("STRIPE_LIVE_MODE", default=False)
STRIPE_TEST_PUBLIC_KEY = env("STRIPE_TEST_PUBLIC_KEY", default="")
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", default="")
STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY", default="")
DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET", default="")
# Секрет подписи Stripe-вебхука (наш эндпоинт apps.billing.webhooks.stripe_webhook).
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
# P2.5 Stripe Connect (Standard-аккаунты, онбординг через OAuth): client_id платформы.
STRIPE_CONNECT_CLIENT_ID = env("STRIPE_CONNECT_CLIENT_ID", default="")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"

# Тариф Standard (39 €/мес) и длительности жизненного цикла подписки.
# trial_ends_at + BILLING_GRACE_DAYS = день перехода trial_expired → suspended.
STRIPE_PRICE_ID = env("STRIPE_PRICE_ID", default="")
# D3: цена тарифа в € для внутренних расчётов (ревшара-сводка партнёра);
# источник правды оплаты — Stripe Price, это только отображение.
BILLING_PLAN_PRICE_EUR = env.int("BILLING_PLAN_PRICE_EUR", default=39)
BILLING_TRIAL_DAYS = env.int("BILLING_TRIAL_DAYS", default=14)
BILLING_GRACE_DAYS = env.int("BILLING_GRACE_DAYS", default=7)

# Featured-продвижение листинга в агрегаторе (P2.4b): разовый Stripe-платёж.
# Дни→центы; пусто = дефолты apps.billing.featured. Формат env:
# BILLING_FEATURED_PRICES="7=900,14=1500,30=2500".
BILLING_FEATURED_PRICES = env.dict("BILLING_FEATURED_PRICES", default={})

# P2.5 Stripe Connect: application fee платформы ПО ТИПУ БИЗНЕСА (%, дефолт 0 для
# всех — настройка существует, монетизацию включаем позже). Ключ "" — дефолт для
# всех типов. Формат env: BILLING_APPLICATION_FEE_PERCENT="hotel=3,tour_operator=5".
BILLING_APPLICATION_FEE_PERCENT = env.dict("BILLING_APPLICATION_FEE_PERCENT", default={})

# ---------------------------------------------------------------------------
# Google OAuth (адаптер Google Business Profile, Track B1)
# ---------------------------------------------------------------------------
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")

# ---------------------------------------------------------------------------
# Meta Graph API (соц-постинг Facebook/Instagram, M23a)
# Токены доступа — per-канал в кабинете; настройка — docs/meta-social-setup.md
# ---------------------------------------------------------------------------
META_GRAPH_API_VERSION = env("META_GRAPH_API_VERSION", default="v21.0")

# ---------------------------------------------------------------------------
# Шифрование платформенных секретов (apps.secrets). Если пусто — ключ выводится
# из SECRET_KEY (dev/CI); в проде задаём отдельный Fernet-ключ в .env.prod:
#   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
# ---------------------------------------------------------------------------
SECRETS_ENCRYPTION_KEY = env("SECRETS_ENCRYPTION_KEY", default="")

# ---------------------------------------------------------------------------
# In-app OAuth подключение каналов (OAuth-A). Callback — единый на основном
# домене; провайдер-креды читаются из apps.secrets (фолбэк на эти .env).
# ---------------------------------------------------------------------------
OAUTH_CALLBACK_BASE = env("OAUTH_CALLBACK_BASE", default="")  # пусто → https://TENANT_DOMAIN_BASE
PINTEREST_CLIENT_ID = env("PINTEREST_CLIENT_ID", default="")
PINTEREST_CLIENT_SECRET = env("PINTEREST_CLIENT_SECRET", default="")
# Meta-приложение для OAuth-B (FB/IG one-click); креды также в admin-сторе.
META_APP_ID = env("META_APP_ID", default="")
META_APP_SECRET = env("META_APP_SECRET", default="")

# ---------------------------------------------------------------------------
# Media & storage
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# S3 (Hetzner Object Storage), если задан ключ; иначе — локальная ФС.
# Так single-сервер без S3 хранит загрузки на диске (медиа-том в compose),
# а полноценный прод с ключами — в объектном хранилище.
_AWS_KEY = env("AWS_ACCESS_KEY_ID", default="").strip()
# Плейсхолдер CHANGE-ME из .env.prod.example НЕ считается настоящим ключом,
# иначе S3 выбирается с фейковыми кредами и загрузка падает InvalidAccessKeyId.
if _AWS_KEY and not _AWS_KEY.upper().startswith("CHANGE-ME"):
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

# ---------------------------------------------------------------------------
# django-unfold — платформенная админка (только public, config/urls_public).
# Без этого блока unfold показывает голый список приложений Django. Здесь:
# брендинг, акцент в indigo (как кабинет), сгруппированный мобильный сайдбар и
# KPI-дашборд (DASHBOARD_CALLBACK + templates/admin/index.html). В сайдбаре —
# только платформенные (SHARED) модели; tenant-модели сняты с регистрации в
# apps.core.admin (их таблиц нет в public-схеме). Сами URL берём через
# reverse_lazy, т.к. settings грузятся раньше urlconf.
# ---------------------------------------------------------------------------
from django.urls import reverse_lazy  # noqa: E402
from django.utils.translation import gettext_lazy as _  # noqa: E402

UNFOLD = {
    "SITE_TITLE": "SiteAdaptor Admin",
    "SITE_HEADER": "SiteAdaptor",
    "SITE_SUBHEADER": _("Platform administration"),
    "SITE_SYMBOL": "rocket_launch",  # Material Symbol рядом с заголовком
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,  # платформенные модели без публичной страницы
    "DASHBOARD_CALLBACK": "apps.core.admin_dashboard.dashboard_callback",
    "COLORS": {
        # Акцент indigo — как в кабинете владельца (indigo-600 = #4f46e5).
        "primary": {
            "50": "#eef2ff",
            "100": "#e0e7ff",
            "200": "#c7d2fe",
            "300": "#a5b4fc",
            "400": "#818cf8",
            "500": "#6366f1",
            "600": "#4f46e5",
            "700": "#4338ca",
            "800": "#3730a3",
            "900": "#312e81",
            "950": "#1e1b4b",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,  # только курируемая навигация ниже
        "navigation": [
            {
                "title": _("Overview"),
                "separator": False,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Businesses"),
                "separator": True,
                "items": [
                    {
                        "title": _("Tenants"),
                        "icon": "storefront",
                        "link": reverse_lazy("admin:tenants_tenant_changelist"),
                    },
                    {
                        # D3: партнёры-реселлеры (реф-атрибуция + кабинет /partner/)
                        "title": _("Partners"),
                        "icon": "handshake",
                        "link": reverse_lazy("admin:partners_partner_changelist"),
                    },
                    {
                        "title": _("Domains"),
                        "icon": "dns",
                        "link": reverse_lazy("admin:tenants_domain_changelist"),
                    },
                ],
            },
            {
                "title": _("Aggregator & portals"),
                "separator": True,
                "items": [
                    {
                        "title": _("Portals"),
                        "icon": "public",
                        "link": reverse_lazy("admin:aggregator_aggregatorportal_changelist"),
                    },
                    {
                        "title": _("Listings"),
                        "icon": "format_list_bulleted",
                        "link": reverse_lazy("admin:aggregator_aggregatorlisting_changelist"),
                    },
                    {
                        "title": _("Reviews"),
                        "icon": "reviews",
                        "link": reverse_lazy("admin:aggregator_businessreview_changelist"),
                    },
                    {
                        "title": _("Portal bots"),
                        "icon": "smart_toy",
                        "link": reverse_lazy("admin:aggregator_portalbot_changelist"),
                    },
                ],
            },
            {
                "title": _("Support"),
                "separator": True,
                "items": [
                    {
                        "title": _("Support tickets"),
                        "icon": "support_agent",
                        "link": reverse_lazy("admin:support_supportthread_changelist"),
                    },
                ],
            },
            {
                "title": _("Platform"),
                "separator": True,
                "items": [
                    {
                        "title": _("Secrets"),
                        "icon": "key",
                        "link": reverse_lazy("admin:secrets_platformsecret_changelist"),
                    },
                    {
                        "title": _("Audit log"),
                        "icon": "history",
                        "link": reverse_lazy("admin:audit_auditevent_changelist"),
                    },
                    {
                        "title": _("Webhooks"),
                        "icon": "webhook",
                        "link": reverse_lazy("admin:webhooks_outgoingwebhook_changelist"),
                    },
                    {
                        "title": _("Webhook deliveries"),
                        "icon": "send",
                        "link": reverse_lazy("admin:webhooks_webhookdelivery_changelist"),
                    },
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": _("Groups"),
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}
