import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# CSRF: Django требует доверенные origins для HTTPS-POST. Платформенный домен и
# ВСЕ субдомены арендаторов (`*.siteadaptor.de`) трастим ВСЕГДА — даже при узком
# env-override — иначе логин/формы на субдомене отдают 403 CSRF. `CsrfViewMiddleware`
# кэширует список на инициализации (динамически, как ALLOWED_HOSTS, дополнить нельзя),
# поэтому базовые origin'ы жёстко в коде, а env лишь ДОБАВЛЯЕТ (напр. кастомные
# домены арендаторов, у которых CSRF держится на совпадении Origin==Host).
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [
            "https://siteadaptor.de",
            "https://*.siteadaptor.de",
            *env.list("CSRF_TRUSTED_ORIGINS", default=[]),
        ]
    )
)

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# Внутренние проверки не должны редиректиться на https: Caddy on-demand TLS
# дёргает /internal/verify-domain по http, а health-проба контейнера — /health/.
# Иначе они получают 301 вместо 200 и ломают выпуск сертификата / healthcheck.
SECURE_REDIRECT_EXEMPT = [
    r"^internal/verify-domain",
    r"^health/",
]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Sentry
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
