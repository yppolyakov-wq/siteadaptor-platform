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
#
# SEC-C-M2 (аудит 2026-11-01): POST на свой же хост Django пропускает сам (Origin ==
# Host при SECURE_PROXY_SSL_HEADER), поэтому wildcard по всем поддоменам не нужен для
# форм бизнеса, а вредит: страница ЛЮБОГО поддомена (XSS у одного бизнеса) могла
# отправлять формы в кабинеты соседей. Включить обратно — CSRF_TRUST_ALL_SUBDOMAINS=1.
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [
            "https://siteadaptor.de",
            *(
                ["https://*.siteadaptor.de"]
                if env.bool("CSRF_TRUST_ALL_SUBDOMAINS", default=False)
                else []
            ),
            *env.list("CSRF_TRUSTED_ORIGINS", default=[]),
        ]
    )
)
# SEC-C-M2: префикс __Host- — куку нельзя поставить с соседнего поддомена (cookie
# tossing) и нельзя расширить на домен; требует Secure + Path=/ без Domain.
CSRF_COOKIE_NAME = "__Host-csrftoken"

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SEC-G2b: allauth считает лимиты входа/сброса пароля по IP клиента. Без этой
# настройки он игнорирует X-Forwarded-For и видел IP самого Caddy — один общий
# «бакет» на всех: 10 неудачных входов в минуту от кого угодно блокировали вход
# всем. Caddy (единственный прокси) ПЕРЕЗАПИСЫВАЕТ X-Forwarded-For реальным адресом
# одним значением (header_up в caddy/Caddyfile, замок test_sec_g2b) — подделать
# заголовок клиент не может. Больше прокси перед Caddy (CDN) → увеличить.
ALLAUTH_TRUSTED_PROXY_COUNT = env.int("ALLAUTH_TRUSTED_PROXY_COUNT", default=1)
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
_SENTRY_SCRUB_PATHS = ("/tg/", "/start/", "/anmelden/", "/team/beitreten/", "/konto/login/")
# SEC-A1/G4: токены ботов живут в URL Bot API (текст HTTPError), ключи Stripe/вебхука —
# в редких исключениях SDK. Вырезаем из текста исключений, логов и breadcrumbs.
_SENTRY_SECRET_RE = __import__("re").compile(
    r"bot\d+:[A-Za-z0-9_-]+|sk_(?:live|test)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+|rk_(?:live|test)_[A-Za-z0-9]+"
)


def _sentry_scrub_text(value):
    return _SENTRY_SECRET_RE.sub("<secret>", value) if isinstance(value, str) else value


def _sentry_scrub_obj(value, depth=0):
    """Рекурсивно вырезать секреты из строк внутри dict/list (breadcrumbs `data.url`,
    spans `description`/`data` несут URL Bot API с токеном)."""
    if depth > 6:
        return value
    if isinstance(value, str):
        return _sentry_scrub_text(value)
    if isinstance(value, dict):
        for key in list(value):
            value[key] = _sentry_scrub_obj(value[key], depth + 1)
        return value
    if isinstance(value, list):
        return [_sentry_scrub_obj(item, depth + 1) for item in value]
    return value


def _sentry_before_breadcrumb(crumb, hint):
    return _sentry_scrub_obj(crumb)


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
    for item in (event.get("exception") or {}).get("values") or []:
        if isinstance(item, dict) and "value" in item:
            item["value"] = _sentry_scrub_text(item["value"])
    entry = event.get("logentry")
    if isinstance(entry, dict):
        _sentry_scrub_obj(entry)
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict):
        _sentry_scrub_obj(crumbs)
    if isinstance(event.get("spans"), list):
        _sentry_scrub_obj(event["spans"])
    # Аргументы Celery-задач несут e-mail, текст сообщений владельца, хэш пароля
    # регистрации — Sentry они не нужны (имя задачи остаётся).
    job = (event.get("extra") or {}).get("celery-job")
    if isinstance(job, dict):
        job.pop("args", None)
        job.pop("kwargs", None)
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
        # Тела запросов витрины несут имена, адреса, свободный текст о здоровье (анкеты).
        max_request_body_size="never",
        before_send=_sentry_before_send,
        before_send_transaction=_sentry_before_send,
        before_breadcrumb=_sentry_before_breadcrumb,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
