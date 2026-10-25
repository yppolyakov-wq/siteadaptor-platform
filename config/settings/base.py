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
    "django.contrib.postgres",  # T-8.20: полнотекст + pg_trgm (лукапы search/trigram)
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
    "apps.ai",  # AI-0 — общий ИИ-слой: провайдеры, маршруты ЕС, учёт и лимиты (SHARED)
    "apps.platform_bot",  # T-8.10h — общий Telegram-бот платформы: привязки владельцев (SHARED)
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
    "apps.documents",  # MT-2 — досье участника: файлы шифруются в storage (TENANT)
    "apps.community",  # MT-3 — пространство поездки: лента/чат группы (TENANT)
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

# P0-5 (аудит 2026-09-03): приложения, живущие ТОЛЬКО в схемах тенантов. Считается
# здесь, ДО переопределения SHARED_APPS в test.py (там все tenant-апп делаются
# SHARED ради одной схемы) — поэтому список верен и в тестах. Потребители:
# чистка платформенной админки (apps.core.admin) — их моделей в public нет и
# быть не должно, независимо от того, кто и когда зарегистрировал admin.
TENANT_ONLY_APPS = [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"
# T-10: `migrate_schemas --executor=multiprocessing` — столько схем мигрируется
# одновременно (деплой: сотня схем по одной шла минутами). Переменная окружения —
# TENANT_MIGRATION_PROCESSES.
# 3, а не больше: миграции с FK на public-таблицы блокируют их, и параллельные
# ALTER при живом трафике копят очередь (ревью T-10). Значение < 1 → 1.
TENANT_MULTIPROCESSING_MAX_PROCESSES = max(1, env.int("TENANT_MIGRATION_PROCESSES", default=3))

# T-10 D-1: новая схема бизнеса создаётся КОПИЕЙ этой шаблонной схемы (секунды вместо
# минуты миграций). Пустая строка в env = выключено (прежний путь миграциями). Шаблон строит и держит
# свежим `manage.py ensure_template_schema` (шаг деплоя); устаревший или «грязный» шаблон
# не копируется — схема создаётся миграциями. Встроенный TENANT_BASE_SCHEMA НЕ используем:
# он после копии помечает недостающие миграции применёнными (`--fake`).
TENANT_TEMPLATE_SCHEMA = env("TENANT_TEMPLATE_SCHEMA", default="_template")

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
# ⚠️ HIGH-10: НЕ задавать SESSION_COOKIE_DOMAIN. auth — TENANT-приложение, у каждой
# схемы свой auth_user с независимым pk → общий cookie-domain между субдоменами
# позволил бы кросс-тенант вход по совпадению _auth_user_id. Инвариант защищён
# system-check'ом core.E001 и SessionSchemaGuardMiddleware (сессия ↔ схема логина).
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
    # SF-1.8: витрина тенанта говорит только на включённых им языках — негоциация
    # Accept-Language по всему LANGUAGES давала msgid-микс на локалях без .po.
    # После LocaleMiddleware (клампим его выбор), до CabinetLocaleMiddleware.
    "apps.core.middleware.StorefrontLocaleClampMiddleware",
    # T1 (FB-12): язык кабинета перекрывает язык витрины на кабинет-путях. После
    # LocaleMiddleware (нужны session+tenant) и до рендера вьюх.
    "apps.core.middleware.CabinetLocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # HIGH-10: сессия привязана к схеме логина — кука из чужой схемы сбрасывается
    # (защита от pk-коллизии auth_user при расширении SESSION_COOKIE_DOMAIN).
    "apps.core.middleware.SessionSchemaGuardMiddleware",
    # T-8.25: свой домен — основной адрес; анонимную витрину с поддомена 301 туда.
    "apps.tenants.middleware.PrimaryDomainRedirectMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Гейтинг подписки: suspended/trial_expired → кабинет read-only (Sprint 5).
    "apps.billing.middleware.SubscriptionGatingMiddleware",
    # Гейтинг модулей (Track D / D0a): неактивный модуль кабинета → 404.
    "apps.core.middleware.ModuleGatingMiddleware",
    # Гейт доступа к кабинету: только члены тенанта (Membership) — fail-closed
    # поверх @login_required. После AuthenticationMiddleware (нужен request.user).
    "apps.core.middleware.CabinetOwnerAccessMiddleware",
    # KA-D4: витрина скрыта до подтверждения почты владельцем (нужен request.user).
    "apps.core.middleware.PendingStorefrontMiddleware",
    # T-8.30 (Р-2): вход из Telegram Mini App — только лёгкие экраны (process_view).
    "apps.core.middleware.TelegramLiteScopeMiddleware",
    # T-8.32b: лёгкий пакет — только свои экраны кабинета (после Telegram-скоупа).
    "apps.core.middleware.PackageScopeMiddleware",
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
                "apps.aggregator.context.shortlist",  # MEN-12: отложенное/сравнение
                "apps.aggregator.context.languages",  # переключатель языка портала
                "apps.aggregator.context.platform_legal",  # T-8.8: Impressum/Datenschutz
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

# T-8.20: единый поиск каталога города (apps/aggregator/search.py). Веса меток вектора
# A (заголовок) · B (блюда) · C (тизер, категории, признаки) · D (город, район, имя бизнеса — Б5)
# применяются в момент запроса — менять без переиндексации.
AGGREGATOR_SEARCH = {
    "weights": {"A": 1.0, "B": 0.6, "C": 0.3, "D": 0.1},
    "trigram_threshold": 0.3,  # word_similarity: «mesesr»/«messer» = 0.43
    "max_tokens": 8,
    "prefix_min_len": 3,  # последнее слово — ещё и как начало слова («brot» → «Brötchen»)
    "max_results": 240,  # 10 страниц по 24
}
# T-8.7 «Folgen»: подписки жителей портала и сводки (docs/t8-7-folgen-plan-2026-10-15.md).
AGGREGATOR_FOLLOW = {
    "daily_hour": 8,  # местное время (TIME_ZONE); beat раз в час, письмо — в первый прогон после
    "items_per_follow": 5,
    "quiet_hours": (21, 7),  # мгновенные письма копятся ночью
    "doi_ttl_days": 7,
    "digest_retention_days": 90,
    "recent_sent_days": 30,  # уже показанный источник не повторяется (синк пересоздаёт строки)
}
# T-8.21: журнал поиска каталога города — агрегат по дням, без персональных данных,
# только для платформы (админка public). Чистка — beat `purge-search-log`.
AGGREGATOR_SEARCH_LOG = {
    "enabled": env.bool("SEARCH_LOG_ENABLED", default=True),
    "retention_days": env.int("SEARCH_LOG_RETENTION_DAYS", default=180),
    # Одиночные запросы (searches == 1) — раньше: в них вероятнее имя/адрес (DSGVO-минимизация).
    "retention_days_single": env.int("SEARCH_LOG_RETENTION_DAYS_SINGLE", default=30),
    "min_len": 2,
}

# В5: учёт результатов каталога города — агрегат по дням без персональных данных;
# экран владельца «Besuche aus dem Stadtportal». Чистка — beat `purge-portal-stats`.
# В3: подложка карт — векторный стиль MapLibre (OpenFreeMap: бесплатно, без ключа,
# коммерческое использование разрешено). Смена провайдера (свои PMTiles, Stadia) —
# эти две переменные; растровые тайлы OSM политикой OSM для нагрузки запрещены.
MAP_STYLE_URL = env("MAP_STYLE_URL", default="https://tiles.openfreemap.org/styles/liberty")
MAP_ATTRIBUTION = env(
    "MAP_ATTRIBUTION",
    default=(
        '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> '
        '© <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> '
        'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" '
        'rel="noopener">OpenStreetMap</a>'
    ),
)

AGGREGATOR_PORTAL_STATS = {
    "enabled": env.bool("PORTAL_STATS_ENABLED", default=True),
    "retention_days": env.int("PORTAL_STATS_RETENTION_DAYS", default=400),
    # счётных событий на IP за час — сверх лимита молча не считаем (страница отвечает)
    "rate_limit": env.int("PORTAL_STATS_RATE_LIMIT", default=300),
    # В5 V5-4: пачек маячка показов на IP за час — отсекается ДО запроса в БД
    "beacon_limit": env.int("PORTAL_STATS_BEACON_LIMIT", default=120),
    # T-8.10f F-3: учтённых ответов ассистентов (MCP) на адрес платформы за час
    "machine_limit": env.int("PORTAL_STATS_MACHINE_LIMIT", default=3000),
}

# T-8.10f: MCP-сервер каталога города для ассистентов (Claude/ChatGPT) — POST /mcp/ на
# хосте портала. Выключен по умолчанию; hosts пусто = все активные порталы.
MCP_ENABLED = env.bool("MCP_ENABLED", default=False)
# KA-12 B2-8b: Anzahlungsrechnung. Включать вместе с B2-8c (вычет в итоговом
# счёте) — иначе НДС предоплаты был бы указан в двух счетах (§ 14c UStG).
ADVANCE_INVOICES_ENABLED = env.bool("ADVANCE_INVOICES_ENABLED", default=False)
MCP_PORTAL_HOSTS = env.list("MCP_PORTAL_HOSTS", default=[])
# Origin, которым разрешено звать эндпоинт из браузера (DNS-rebinding); серверные клиенты
# ассистентов Origin не шлют.
MCP_ALLOWED_ORIGINS = env.list("MCP_ALLOWED_ORIGINS", default=[])
# Запросов в минуту: на IP (у MCP это адрес платформы ассистента — общий для жителей,
# поэтому высокий) и на весь сервер (предохранитель; на IP — десятая часть общего, чтобы
# один-два адреса не исчерпали общий лимит для платформ ассистентов).
MCP_RATE_PER_IP = env.int("MCP_RATE_PER_IP", default=300)
MCP_RATE_GLOBAL = env.int("MCP_RATE_GLOBAL", default=3000)
MCP_MAX_BODY = env.int("MCP_MAX_BODY", default=64 * 1024)
# T-8.10f F-4: «Zurücklegen»/«Coupon» из ассистента с подтверждением по e-mail. Работает
# только вместе с настоящей почтой (Resend или SMTP); иначе инструменты скрыты.
MCP_ACTIONS_ENABLED = env.bool("MCP_ACTIONS_ENABLED", default=False)
MCP_ACTION_TTL = env.int("MCP_ACTION_TTL", default=60 * 60 * 24)  # срок ссылки, сек
MCP_ACTION_RATE_IP = env.int("MCP_ACTION_RATE_IP", default=20)  # за 10 минут
MCP_ACTION_RATE_EMAIL = env.int("MCP_ACTION_RATE_EMAIL", default=3)  # писем на адрес в сутки
MCP_ACTION_RATE_OFFER = env.int("MCP_ACTION_RATE_OFFER", default=50)  # на предложение в сутки
MCP_ACTION_RATE_GLOBAL = env.int("MCP_ACTION_RATE_GLOBAL", default=300)  # писем в час

# T-8.10h: общий Telegram-бот платформы (старт акций без своего бота). Выключен по
# умолчанию; токен — PlatformSecret «telegram_platform_bot_token» или env.
TELEGRAM_PLATFORM_BOT_ENABLED = env.bool("TELEGRAM_PLATFORM_BOT_ENABLED", default=False)
TELEGRAM_PLATFORM_BOT_TOKEN = env("TELEGRAM_PLATFORM_BOT_TOKEN", default="")
TELEGRAM_PLATFORM_BOT_USERNAME = env("TELEGRAM_PLATFORM_BOT_USERNAME", default="")
TELEGRAM_PLATFORM_WEBHOOK_SECRET = env("TELEGRAM_PLATFORM_WEBHOOK_SECRET", default="")

# Г5: «живой» район портала — сколько РАЗНЫХ бизнесов нужно району, чтобы не добавлять
# под его выдачей «Auch in der Nähe» (соседние районы). 0 = функция выключена.
PORTAL_DISTRICT_MIN_BUSINESSES = env.int("PORTAL_DISTRICT_MIN_BUSINESSES", default=10)
PORTAL_DISTRICT_COUNT_TTL = env.int("PORTAL_DISTRICT_COUNT_TTL", default=300)  # сек, кэш подсчёта

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
CABINET_LANGUAGES = ["de", "en", "tr", "ru", "uk"]

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
# T-8.26 п.3: разброс ночной сверки агрегатора между схемами, секунд на схему.
AGG_RECONCILE_SPREAD_S = env.int("AGG_RECONCILE_SPREAD_S", default=20)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# Открытая allauth-регистрация закрыта: бизнес регистрируется только через
# BusinessSignupView (create_business с ролью владельца). Иначе аноним мог создать
# User в схеме тенанта и захватить кабинет (см. apps.tenants.adapters).
ACCOUNT_ADAPTER = "apps.tenants.adapters.AccountAdapter"
# mandatory требует рабочей отправки почты (Resend). Пока RESEND_API_KEY не
# настроен, держим optional через env, иначе вход падает 500 на отправке письма.
# На боевом проде с настроенным Resend → ACCOUNT_EMAIL_VERIFICATION=mandatory.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="optional")
# AB5.1: double-opt-in регистрации бизнеса — тенант создаётся только после клика
# по ссылке из письма (SignupRequest). env-выключатель возвращает прямой флоу.
# При console-бэкенде (нет Resend/SMTP) confirm-ссылка показывается на странице.
SIGNUP_EMAIL_CONFIRMATION = env.bool("SIGNUP_EMAIL_CONFIRMATION", default=True)
# после логина — в кабинет владельца; после выхода — на публичную витрину
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# Политика паролей: без валидаторов Django принимает тривиальные пароли ("1"),
# что критично для владельцев кабинета. Стандартный набор Django.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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
    # M3 Boutique: просрочка Anprobe-резервов (Click&Reserve) — тот же ритм.
    "expire-anprobe": {
        "task": "apps.orders.tasks.expire_anprobe_reservations",
        "schedule": 300.0,
    },
    # SH-23d (Р-4): снятие удержания с неоплаченных сделок по прошедшему сроку
    # оплаты (счёт — до Zahlungsziel, Vorkasse — 3 дня). Тот же ритм, что у
    # прочих просрочек: место не должно висеть занятым дольше договорённого.
    "expire-payment-holds": {
        "task": "apps.core.tasks.expire_payment_holds",
        "schedule": 300.0,
    },
    # C1: утренний дайджест владельцу — раз в час; внутри гейт «локальный час
    # тенанта == 7» (tenant.timezone) + дедуп по дате (unique dedupe_key).
    "owner-digests": {
        "task": "apps.core.tasks.send_owner_digests",
        "schedule": 3600.0,
    },
    # Г3: предупреждение «позиции скоро уйдут из каталога города» — раз в сутки,
    # письмо не чаще раза в ISO-неделю (dedupe_key).
    "warn-city-freshness": {
        "task": "apps.core.tasks.warn_city_freshness",
        "schedule": 86400.0,
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
    "roll-event-group-listings": {
        "task": "apps.aggregator.tasks.roll_aggregator_event_groups",
        "schedule": 3600.0,  # 6c: перекат групповых карточек событий на следующий заезд
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
    # PMS-B: авто-тег «stammkunde» (≥3 покупки по RevenueEntry) — питает
    # сегменты кампаний; только добавление, ручные теги владельца целы.
    "auto-tag-customers": {
        "task": "apps.promotions.tasks.auto_tag_customers",
        "schedule": 86400.0,
    },
    # PMS-B2: «Geburtstagsgruß» — персональный код именинникам (opt-in-база,
    # настройки на кампании kind=birthday, годовой дедуп).
    "send-birthday-coupons": {
        "task": "apps.promotions.tasks.send_birthday_coupons",
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
    "auto-fulfil-stays": {
        "task": "apps.stays.tasks.auto_fulfil_stays",
        # PMS-B2 + KA-12 E0.4: раз в час — в день выезда закрывает после check-out.
        "schedule": 3600.0,
    },
    "purge-old-registrations": {
        "task": "apps.stays.tasks.purge_old_registrations",
        "schedule": 86400.0,  # раз в сутки — удаление Meldescheine >1 года (G6/DSGVO)
    },
    "purge-old-night-rates": {
        "task": "apps.stays.tasks.purge_old_night_rates",
        "schedule": 86400.0,  # раз в сутки — прошлые переопределения ночей (KA-12 Z-2)
    },
    "purge-old-service-notes": {
        "task": "apps.crm.tasks.purge_old_service_notes",
        "schedule": 86400.0,  # раз в сутки — заметки к процедурам 3 года после визита (E6.4d)
    },
    "purge-team-audit": {
        "task": "apps.audit.tasks.purge_team_audit",
        "schedule": 86400.0,  # раз в сутки — журнал команды старше TEAM_AUDIT_RETENTION_DAYS (E6.7c)
    },
    "purge-portal-stats": {
        "task": "apps.aggregator.tasks.purge_portal_stats",
        "schedule": 86400.0,  # раз в сутки — учёт портала старше PORTAL_STATS_RETENTION_DAYS (В5)
    },
    "purge-portal-bot-chats": {
        "task": "apps.aggregator.tasks.purge_portal_chats",
        "schedule": 86400.0,  # раз в сутки — сроки хранения чатов бота портала (T-8.28)
    },
    "purge-platform-bot-links": {
        "task": "apps.platform_bot.tasks.purge_stale_links",
        "schedule": 86400.0,  # раз в сутки — сроки хранения связей общего бота (T-8.10h H-6)
    },
    "purge-ai-usage": {
        "task": "apps.ai.tasks.purge_ai_usage",
        "schedule": 86400.0,  # раз в сутки — учёт ИИ старше AI_USAGE_RETENTION_DAYS (AI-0)
    },
    "purge-search-log": {
        "task": "apps.aggregator.tasks.purge_search_log",
        "schedule": 86400.0,  # раз в сутки — журнал поиска старше SEARCH_LOG_RETENTION_DAYS (T-8.21)
    },
    # T-8.7 «Folgen»: сводки жителям портала — раз в час с гейтом 08:00 внутри (как
    # owner-digests), мгновенные — раз в 15 минут (тихие часы внутри), чистка — раз в сутки.
    "send-follow-digests": {
        "task": "apps.aggregator.tasks.send_follow_digests",
        "schedule": 3600.0,
    },
    "send-follow-instant": {
        "task": "apps.aggregator.tasks.send_follow_instant",
        "schedule": 900.0,
    },
    "purge-follow-digests": {
        "task": "apps.aggregator.tasks.purge_follow_digests",
        "schedule": 86400.0,
    },
    # T-8.26 п.3: ночная полная сверка снимка каталога города по всем схемам (с разбросом).
    "reconcile-aggregator-nightly": {
        "task": "apps.aggregator.tasks.reconcile_aggregator_nightly",
        "schedule": 86400.0,
    },
    "purge-expired-documents": {
        "task": "apps.documents.tasks.purge_expired_documents",
        "schedule": 86400.0,  # раз в сутки — досье участников после поездки (MT-2)
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
    # GK-11: обновление Google-рейтингов (кэш ≤30 дней по ToS; свежесть — env
    # GOOGLE_RATING_REFRESH_DAYS, дефолт 7). SHARED-обход, без schema_context.
    "refresh-google-ratings": {
        "task": "apps.tenants.tasks.refresh_google_ratings",
        "schedule": 86400.0,
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
# MT-2: сколько дней документы участника живут ПОСЛЕ окончания поездки.
DOCUMENT_RETENTION_DAYS = env.int("DOCUMENT_RETENTION_DAYS", default=90)
# KA-12 E6.4d: заметки мастера к процедурам живут 3 года после последней записи
# клиента (решение владельца 2026-10-25). Константа, не env: срок назван в тексте
# Datenschutzerklärung — разойтись с ним он не должен.
SERVICE_NOTE_RETENTION_DAYS = 3 * 365
# KA-12 E6.7c (Р-c6, В-8): журнал выдачи прав/ролей команды — 3 года.
TEAM_AUDIT_RETENTION_DAYS = env.int("TEAM_AUDIT_RETENTION_DAYS", default=3 * 365)

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
# T-8.4 (Р-5): бесплатная лёгкая ступень («Nur Aktionen» без подписки) держит не
# больше N активных акций одновременно; на N+1 — «Mehr Aktionen? Schreiben Sie uns».
LITE_FREE_ACTIVE_PROMOS = env.int("LITE_FREE_ACTIVE_PROMOS", default=5)
# KA-12 E6.6: потолки против «выкупа витрины» резервами и купонами (Р-2/Р-4).
PROMO_PENDING_HOLD_HOURS = env.int("PROMO_PENDING_HOLD_HOURS", default=4)
PROMO_RESERVATIONS_PER_IP_DAY = env.int("PROMO_RESERVATIONS_PER_IP_DAY", default=10)
PROMO_OPEN_RESERVATIONS_PER_CONTACT = env.int("PROMO_OPEN_RESERVATIONS_PER_CONTACT", default=3)
PROMO_COUPONS_PER_IP_DAY = env.int("PROMO_COUPONS_PER_IP_DAY", default=3)
PLATFORM_CONTACT_EMAIL = env("PLATFORM_CONTACT_EMAIL", default="kontakt@siteadaptor.de")
# SF-8b: исключение § 11 Abs. 4 PAngV (schnell verderblich / kurze Haltbarkeit) — акция
# с флагом владельца НЕ ограничивается 30-дневным минимумом. Выключатель для отката по
# решению юриста: False → флаг игнорируется целиком (данные владельцев не трогаются).
PANGV_PERISHABLE_EXEMPTION = env.bool("PANGV_PERISHABLE_EXEMPTION", default=True)

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
# Google Places API (GK-11: рейтинг бизнеса на витрине; ключ платформенный,
# шифрованный стор имеет приоритет — apps.secrets.store.get_or_setting)
# ---------------------------------------------------------------------------
GOOGLE_PLACES_API_KEY = env("GOOGLE_PLACES_API_KEY", default="")
GOOGLE_RATING_REFRESH_DAYS = env.int("GOOGLE_RATING_REFRESH_DAYS", default=7)

# ---------------------------------------------------------------------------
# T-8.27 «Импорт с сайта клиента» (docs/t8-27-site-import-plan-2026-10-17.md).
# Р-B: бесплатно до IMPORT_FREE_ITEMS позиций (тенант без подписки); обход — вежливый.
# ---------------------------------------------------------------------------
IMPORT_FREE_ITEMS = env.int("IMPORT_FREE_ITEMS", default=50)
# Г3: товар/услуга без подтверждения владельца N дней уходят из каталога города
# (0 — механизм выключен); предупреждение — за K дней до этого.
CITY_FRESHNESS_DAYS = env.int("CITY_FRESHNESS_DAYS", default=60)
CITY_FRESHNESS_WARN_DAYS = env.int("CITY_FRESHNESS_WARN_DAYS", default=7)
SITE_IMPORT_MAX_PAGES = env.int("SITE_IMPORT_MAX_PAGES", default=20)
SITE_IMPORT_MAX_PAGE_BYTES = env.int("SITE_IMPORT_MAX_PAGE_BYTES", default=2 * 1024 * 1024)
SITE_IMPORT_MAX_IMAGE_BYTES = env.int("SITE_IMPORT_MAX_IMAGE_BYTES", default=5 * 1024 * 1024)
SITE_IMPORT_TIME_BUDGET_S = env.int("SITE_IMPORT_TIME_BUDGET_S", default=120)
SITE_IMPORT_PAUSE_S = env.float("SITE_IMPORT_PAUSE_S", default=0.5)
SITE_IMPORT_DAILY_RUNS = env.int("SITE_IMPORT_DAILY_RUNS", default=3)
SITE_IMPORT_USER_AGENT = env(
    "SITE_IMPORT_USER_AGENT",
    default="SiteadaptorImport/1.0 (+https://siteadaptor.de/import-bot)",
)

# ---------------------------------------------------------------------------
# AI-0: общий ИИ-слой (docs/ai0-layer-plan-2026-10-17.md, docs/ai-providers-setup-2026-10-16.md).
# Маршруты — списки по классу модели, порядок = резерв: bedrock | azure | mistral (ЕС),
# anthropic | openai (прямые API, вне ЕС — только dev с демо-данными), fake (без сети).
# AI_REQUIRE_EU=True (дефолт production.py) вырезает маршруты вне ЕС и фейк ДО вызова.
# Ключи — шифрованный стор apps.secrets (приоритет) или env ниже.
# ---------------------------------------------------------------------------
AI_ENABLED = env.bool("AI_ENABLED", default=False)
# AI-1 (2026-10-23): белый список задач — задача не из списка не выполняется, новая
# задача выключена, пока её не внесут. Переписка с клиентом (inbox_reply_draft) по
# решению владельца выключена, пока ключ ИИ не европейский. Правила —
# docs/ai-usage-policy-2026-10-23.md.
AI_TASKS_ENABLED = [
    name.strip()
    for name in env.list(
        "AI_TASKS_ENABLED",
        default=[
            "site_import_extract",
            "promo_photo_draft",
            "promo_text_check",
            "catalog_moderation",
            "search_phrase_filters",
        ],
    )
    if name.strip()
]
AI_REQUIRE_EU = env.bool("AI_REQUIRE_EU", default=False)
# Осознанно принятые предупреждения проверки (например ai.W004 — тест ИИ вне ЕС):
# SILENCED_SYSTEM_CHECKS=ai.W004 в .env — деплой перестаёт печатать их на каждом шаге.
SILENCED_SYSTEM_CHECKS = env.list("SILENCED_SYSTEM_CHECKS", default=[])
AI_ROUTE_FAST = env.list("AI_ROUTE_FAST", default=["fake"])
AI_ROUTE_STRONG = env.list("AI_ROUTE_STRONG", default=["fake"])
AI_FAKE_MODE = env("AI_FAKE_MODE", default="ok")
AI_TENANT_DAILY_CALLS = env.int("AI_TENANT_DAILY_CALLS", default=50)
AI_TENANT_DAILY_EUR = env.float("AI_TENANT_DAILY_EUR", default=1.0)
AI_DAILY_BUDGET_EUR = env.float("AI_DAILY_BUDGET_EUR", default=10.0)
# {"<модель>": [центов за 1M входных токенов, центов за 1M выходных]} — для оценки бюджета.
AI_PRICES = env.json("AI_PRICES", default={})
# Цена модели, которой нет в AI_PRICES: пессимистично (уровень сильнейших моделей, ≈15/75 €
# за 1M), чтобы денежные лимиты работали и без таблицы цен.
AI_DEFAULT_PRICE = env.list("AI_DEFAULT_PRICE", cast=float, default=[1500, 7500])
AI_USAGE_RETENTION_DAYS = env.int("AI_USAGE_RETENTION_DAYS", default=400)
# Потолок длины текста запроса (prompt + system): защита воркера и бюджета от огромного
# внешнего текста; задача может задать свой меньший предел (TaskSpec.max_input_chars).
AI_MAX_PROMPT_CHARS = env.int("AI_MAX_PROMPT_CHARS", default=60_000)
# D2b-2: ИИ-модерация каталога города — выключена до ключей ЕС, потом потолок вызовов в день
# (бюджет платформы); повтор того же текста карточки — из кэша N дней без вызова.
AI_CATALOG_MODERATION = env.bool("AI_CATALOG_MODERATION", default=False)
AI_CATALOG_MODERATION_DAILY = env.int("AI_CATALOG_MODERATION_DAILY", default=300)
AI_CATALOG_MODERATION_TENANT_DAILY = env.int("AI_CATALOG_MODERATION_TENANT_DAILY", default=20)
AI_CATALOG_MODERATION_DEDUPE_DAYS = env.int("AI_CATALOG_MODERATION_DEDUPE_DAYS", default=30)
# T-8.10d D-2: ИИ «фраза → фильтры» в поиске каталога города. Выключено по умолчанию —
# владелец включает по отчёту `search_log_report` (Р-9: ≥500 поисков и ≥10 % многословных
# пустых/малых выдач). Подсказка только предлагает фильтры ссылкой, сама ничего не применяет.
AI_SEARCH_ENABLED = env.bool("AI_SEARCH_ENABLED", default=False)
AI_SEARCH_DAILY = env.int("AI_SEARCH_DAILY", default=500)  # вызовов ИИ платформе в день
AI_SEARCH_EXPAND_DAILY = env.int("AI_SEARCH_EXPAND_DAILY", default=300)  # T-8.34d, свой потолок
AI_SEARCH_IP_LIMIT = 10  # новых фраз на IP за 10 минут
AI_SEARCH_POLL_LIMIT = 120  # обращений к эндпоинту подсказки на IP за 10 минут
AI_SEARCH_CACHE_HOURS = 24
AI_SEARCH_ERROR_TTL = 600
AI_SEARCH_MAX_RESULTS = 3  # «малая выдача» (= LOW_RESULTS отчёта D-0)
AI_SEARCH_MIN_WORDS = 2  # значимых слов в остатке запроса
# T-8.10e «Text-Check»: скидка выше этого процента — подсказка «sehr hoher Rabatt»
# (кроме скоропортящегося, § 11 Abs. 4 PAngV). Только подсказка, не запрет.
TEXT_CHECK_PLAUSIBLE_DISCOUNT = env.int("TEXT_CHECK_PLAUSIBLE_DISCOUNT", default=70)
# Прямой Anthropic API (dev, личный ключ).
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
ANTHROPIC_BASE_URL = env("ANTHROPIC_BASE_URL", default="https://api.anthropic.com")
ANTHROPIC_VERSION = env("ANTHROPIC_VERSION", default="2023-06-01")
ANTHROPIC_MODEL_FAST = env("ANTHROPIC_MODEL_FAST", default="claude-haiku-5-5")
ANTHROPIC_MODEL_STRONG = env("ANTHROPIC_MODEL_STRONG", default="claude-opus-5-5")
# Прямой OpenAI API (dev, личный ключ).
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="https://api.openai.com")
OPENAI_MODEL_FAST = env("OPENAI_MODEL_FAST", default="")
OPENAI_MODEL_STRONG = env("OPENAI_MODEL_STRONG", default="")
# AWS Bedrock (Claude, ЕС). Ключи отдельные от S3-хранилища: право только bedrock:InvokeModel.
AWS_BEDROCK_REGION = env("AWS_BEDROCK_REGION", default="eu-central-1")
AWS_BEDROCK_ACCESS_KEY_ID = env("AWS_BEDROCK_ACCESS_KEY_ID", default="")
AWS_BEDROCK_SECRET_ACCESS_KEY = env("AWS_BEDROCK_SECRET_ACCESS_KEY", default="")
BEDROCK_MODEL_FAST = env("BEDROCK_MODEL_FAST", default="")
BEDROCK_MODEL_STRONG = env("BEDROCK_MODEL_STRONG", default="")
# Azure OpenAI (GPT, развёртывание «Data Zone Standard — EU»).
AZURE_OPENAI_ENDPOINT = env("AZURE_OPENAI_ENDPOINT", default="")
AZURE_OPENAI_API_KEY = env("AZURE_OPENAI_API_KEY", default="")
AZURE_OPENAI_API_VERSION = env("AZURE_OPENAI_API_VERSION", default="2024-10-21")
AZURE_OPENAI_DEPLOYMENT_FAST = env("AZURE_OPENAI_DEPLOYMENT_FAST", default="")
AZURE_OPENAI_DEPLOYMENT_STRONG = env("AZURE_OPENAI_DEPLOYMENT_STRONG", default="")
# Владелец подтверждает тип развёртывания «Data Zone Standard (EU)» — без этого Azure не ЕС.
AZURE_OPENAI_EU_DATA_ZONE = env.bool("AZURE_OPENAI_EU_DATA_ZONE", default=False)
# Mistral (Франция): ЕС только при адресе api.mistral.ai.
MISTRAL_API_KEY = env("MISTRAL_API_KEY", default="")
MISTRAL_BASE_URL = env("MISTRAL_BASE_URL", default="https://api.mistral.ai")
MISTRAL_MODEL_FAST = env("MISTRAL_MODEL_FAST", default="mistral-small-latest")
MISTRAL_MODEL_STRONG = env("MISTRAL_MODEL_STRONG", default="mistral-large-latest")

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
# Прежние ключи — только для ЧТЕНИЯ (смена ключа: новый в SECRETS_ENCRYPTION_KEY,
# старый сюда, затем `manage.py rotate_secrets --apply`, затем строку можно
# убрать). Без этого смена ключа делала всё зашифрованное нечитаемым, а команда
# честно отвечала «нечего ротировать».
SECRETS_ENCRYPTION_KEY_PREVIOUS = env.list("SECRETS_ENCRYPTION_KEY_PREVIOUS", default=[])

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
        # AI-0: на DEBUG эти библиотеки пишут тела запросов (промпты) и адреса — держим выше.
        "botocore": {"level": "WARNING"},
        "boto3": {"level": "WARNING"},
        "urllib3": {"level": "WARNING"},
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
                        "permission": "apps.platform_bot.admin.superuser_only",
                    },
                    {
                        # AI-CFG: настройки ИИ — галочками вместо .env.prod.
                        "title": _("AI settings"),
                        "icon": "psychology",
                        "link": reverse_lazy("admin:ai_settings"),
                        "permission": "apps.platform_bot.admin.superuser_only",
                    },
                    {
                        # T-8.10h: общий Telegram-бот платформы — включение, токен, вебхук.
                        "title": _("Telegram platform bot"),
                        "icon": "smart_toy",
                        "link": reverse_lazy("admin:platform_bot_settings"),
                        "permission": "apps.platform_bot.admin.superuser_only",
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
