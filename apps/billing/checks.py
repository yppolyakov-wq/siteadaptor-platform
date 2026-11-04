"""Django-чеки боевого конфига биллинга (SEC-D2, аудит безопасности 2026-11-01).

Пустой `STRIPE_WEBHOOK_SECRET` означает, что подпись вебхука проверяется HMAC с пустым
ключом — любой подделанный `checkout.session.completed` прошёл бы. Сам вебхук при пустом
секрете отвечает 503, а этот deploy-check не даёт выкатить такой конфиг: в live-режиме
Stripe секрет обязан быть задан и иметь форму `whsec_…`.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def stripe_webhook_secret_set(app_configs, **kwargs):
    if not getattr(settings, "STRIPE_LIVE_MODE", False):
        return []
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""
    if secret.startswith("whsec_"):
        return []
    return [
        Error(
            "STRIPE_WEBHOOK_SECRET не задан или не похож на whsec_… при STRIPE_LIVE_MODE=True.",
            hint="Stripe Dashboard → Developers → Webhooks → Signing secret → .env.prod "
            "(STRIPE_WEBHOOK_SECRET=whsec_…). Без него вебхук отвечает 503, оплаты не бронируются.",
            id="billing.E001",
        )
    ]


@register(Tags.security, deploy=True)
def stripe_connect_webhook_secret_set(app_configs, **kwargs):
    """Connect включён, а секрета эндпоинта подключённых аккаунтов нет — оплаты
    клиентов (заказы, депозиты, билеты) не подтвердятся: подпись не сойдётся."""
    from django.core.checks import Warning as CheckWarning

    if not getattr(settings, "STRIPE_CONNECT_CLIENT_ID", ""):
        return []
    secret = getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", "") or ""
    if secret.startswith("whsec_"):
        return []
    return [
        CheckWarning(
            "STRIPE_CONNECT_CLIENT_ID задан, а STRIPE_CONNECT_WEBHOOK_SECRET — нет.",
            hint="Stripe Dashboard → Webhooks → endpoint «Connected accounts» → Signing secret "
            "→ .env.prod (STRIPE_CONNECT_WEBHOOK_SECRET=whsec_…). Без него оплаты клиентов "
            "не подтверждаются.",
            id="billing.W002",
        )
    ]


@register(Tags.security, deploy=True)
def email_backend_not_console(app_configs, **kwargs):
    """SEC (ревью аудита, SM13): с консольным почтовым бэкендом страница «проверьте
    почту» показывает ссылку подтверждения прямо в браузере (`signup.show_direct_link`) —
    в проде так любой подтверждает регистрацию на чужой адрес без доступа к почте."""
    backend = getattr(settings, "EMAIL_BACKEND", "") or ""
    if getattr(settings, "DEBUG", False) or "console" not in backend:
        return []
    return [
        Error(
            "EMAIL_BACKEND — консольный при DEBUG=False.",
            hint="Задать RESEND_API_KEY (anymail) или SMTP в .env.prod.",
            id="billing.E002",
        )
    ]


@register(Tags.security, deploy=True)
def telegram_legacy_webhook_header(app_configs, **kwargs):
    """SEC-A4: пока принимается прежний заголовок вебхука (= секрет пути), знание пути
    из логов позволяет подделать запрос от Telegram. Напоминание для ops."""
    from django.core.checks import Warning as CheckWarning

    if not getattr(settings, "TELEGRAM_WEBHOOK_LEGACY_HEADER", True):
        return []
    return [
        CheckWarning(
            "TELEGRAM_WEBHOOK_LEGACY_HEADER=True: Telegram-вебхуки принимают прежний заголовок.",
            hint="manage.py telegram_resync_webhooks --apply, затем TELEGRAM_WEBHOOK_LEGACY_HEADER=False.",
            id="billing.W001",
        )
    ]
