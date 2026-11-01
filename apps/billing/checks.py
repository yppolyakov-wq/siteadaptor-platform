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
