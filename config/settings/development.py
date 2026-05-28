from .base import *  # noqa: F401, F403
from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE, STORAGES

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Local development: subdomains через *.localhost
TENANT_DOMAIN_BASE = "localhost:8000"

# Email на консоль в dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Локальное файловое хранилище в dev (override S3)
STORAGES["default"] = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": str(BASE_DIR / "media")},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Dev-only апсы и middleware
INSTALLED_APPS += ["debug_toolbar", "django_extensions"]
MIDDLEWARE.insert(2, "debug_toolbar.middleware.DebugToolbarMiddleware")

INTERNAL_IPS = ["127.0.0.1"]

# В dev allauth не требует подтверждения email
ACCOUNT_EMAIL_VERIFICATION = "optional"
