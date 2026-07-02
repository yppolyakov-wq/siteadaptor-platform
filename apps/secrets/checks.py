"""Deploy-check: боевой конфиг шифрования секретов.

Регистрируется как deploy-only (`manage.py check --deploy`), чтобы не шуметь в
dev/CI, где фолбэк ключа из SECRET_KEY допустим намеренно. В проде отсутствие
отдельного `SECRETS_ENCRYPTION_KEY` — риск: утечка `SECRET_KEY` раскрывает все
зашифрованные секреты.
"""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def secrets_encryption_key_set(app_configs, **kwargs):
    key = getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""
    if key:
        return []
    return [
        Warning(
            "SECRETS_ENCRYPTION_KEY не задан — ключ шифрования секретов выводится из "
            "SECRET_KEY (детерминированный фолбэк).",
            hint=(
                "В проде задайте отдельный SECRETS_ENCRYPTION_KEY (Fernet.generate_key()) "
                "в .env.prod: иначе утечка SECRET_KEY раскрывает все зашифрованные секреты "
                "(токены ботов, OAuth-токены, ключи интеграций)."
            ),
            id="secrets.W001",
        )
    ]
