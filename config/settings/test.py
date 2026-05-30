"""Настройки для тестов (pytest).

Базируемся на base (НЕ development): development добавляет debug_toolbar,
который при рендере вьюх в тестах падает (его модель не в INSTALLED_APPS после
нашей пересборки). Тестам toolbar не нужен.

django-tenants держит TENANT_APPS только в схемах арендаторов, а pytest-django
мигрирует public-БД → таблиц TENANT-приложений в тестах нет. Поэтому объявляем
ВСЕ приложения как SHARED: стандартный migrate создаёт все таблицы в public,
роутер остаётся на месте (django-tenants требует его на старте).
"""

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, SHARED_APPS, STORAGES, TENANT_APPS

DEBUG = False
ALLOWED_HOSTS = ["*"]
TENANT_DOMAIN_BASE = "siteadaptor.de"

# Все tenant-приложения видны и как shared → их таблицы создаются в public.
SHARED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]
INSTALLED_APPS = list(SHARED_APPS)

# Почта в память, без внешних провайдеров.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ACCOUNT_EMAIL_VERIFICATION = "optional"

# Локальное файловое хранилище вместо S3.
STORAGES["default"] = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": str(BASE_DIR / "media")},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
