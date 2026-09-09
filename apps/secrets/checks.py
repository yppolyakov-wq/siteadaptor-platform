"""Deploy-check: боевой конфиг шифрования секретов.

Регистрируется как deploy-only (`manage.py check --deploy`), чтобы не шуметь в
dev/CI, где фолбэк ключа из SECRET_KEY допустим намеренно. В проде отсутствие
отдельного `SECRETS_ENCRYPTION_KEY` — риск: утечка `SECRET_KEY` раскрывает все
зашифрованные секреты.
"""

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def secrets_encryption_key_set(app_configs, **kwargs):
    key = getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""
    if key:
        # Проверяем ПРИГОДНОСТЬ, а не факт наличия: деплой стал fail-closed по
        # этой переменной, и владелец задаёт её впервые. Естественные варианты
        # — `openssl rand -hex 32` (64 hex) или скопированный python-repr
        # `b'…='` — Fernet отвергает, но прежний гейт (`if key`) их пропускал:
        # деплой рапортовал успех, а в проде ВСЕ секреты читались как ''
        # (decrypt глотает ValueError), и интеграции молча умирали.
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as exc:
            return [
                Error(
                    f"SECRETS_ENCRYPTION_KEY задан, но не является ключом Fernet: {exc}",
                    hint=(
                        "Нужны 32 байта в urlsafe-base64. Сгенерировать: python -c "
                        '"from cryptography.fernet import Fernet; '
                        "print(Fernet.generate_key().decode())\". Значение без префикса b'…'."
                    ),
                    id="secrets.E002",
                )
            ]
        return []
    msg = (
        "SECRETS_ENCRYPTION_KEY не задан — ключ шифрования секретов выводится из "
        "SECRET_KEY (детерминированный фолбэк)."
    )
    hint = (
        "В проде задайте отдельный SECRETS_ENCRYPTION_KEY (Fernet.generate_key()) "
        "в .env.prod: иначе утечка SECRET_KEY раскрывает все зашифрованные секреты "
        "(токены ботов, OAuth-токены, ключи интеграций)."
    )
    # Fail-closed в проде (DEBUG=False): `manage.py check --deploy` завершится с
    # ошибкой → деплой-пайплайн ловит отсутствие ключа. В dev/CI фолбэк намеренно
    # допустим, поэтому там — предупреждение.
    if settings.DEBUG:
        return [Warning(msg, hint=hint, id="secrets.W001")]
    return [Error(msg, hint=hint, id="secrets.E001")]
