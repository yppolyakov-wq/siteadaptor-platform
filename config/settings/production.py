import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# AI-0: в проде данные клиентов обрабатываются только в ЕС — маршруты вне ЕС (прямые
# Anthropic/OpenAI) и фейк не вызываются. Снять можно только явным env на dev-сервере
# с демо-данными.
AI_REQUIRE_EU = env.bool("AI_REQUIRE_EU", default=True)

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
_SENTRY_SCRUB_PATHS = ("/tg/",)


def _sentry_tg_path(value) -> bool:
    from urllib.parse import urlsplit

    try:
        path = urlsplit(str(value or "")).path
    except ValueError:
        return False
    return path.startswith(_SENTRY_SCRUB_PATHS)


def _sentry_before_send(event, hint):
    """T-8.30: тело и query входов Mini App/handoff (initData, одноразовые токены) —
    не в Sentry; Referer страницы после входа тоже несёт токен."""
    req = event.get("request") or {}
    url = req.get("url") or ""
    if _sentry_tg_path(url):
        req.pop("data", None)
        req.pop("query_string", None)
        req["url"] = url.split("/tg/", 1)[0] + "/tg/…"
    if _sentry_tg_path(event.get("transaction")):
        event["transaction"] = "/tg/…"
    headers = req.get("headers")
    if isinstance(headers, dict):
        for name in [k for k in headers if k.lower() == "referer"]:
            if _sentry_tg_path(headers[name]):
                headers.pop(name)
    return event


SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        # AI-0: локальные переменные кадров несут промпты ИИ и заголовки с ключами
        # провайдеров — в Sentry не отправляем.
        include_local_variables=False,
        before_send=_sentry_before_send,
        before_send_transaction=_sentry_before_send,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
