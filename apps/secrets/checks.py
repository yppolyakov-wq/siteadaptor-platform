"""Django-чеки боевого конфига шифрования секретов.

Их два, и они отвечают на РАЗНЫЕ вопросы:

* `secrets_encryption_key_set` (deploy-only) — ключ вообще задан? В dev/CI
  фолбэк из SECRET_KEY допустим намеренно, поэтому шуметь там нечем; в проде
  отсутствие отдельного ключа — риск: утечка SECRET_KEY раскрывает все секреты.
* `secrets_encryption_key_valid` (обычный чек, ЛЮБОЕ окружение) — заданный ключ
  пригоден? Негодное значение ломает приложение везде и молча: чтение отдаёт ''
  (decrypt глотает ValueError), запись падает 500 (encrypt не глотает). Ждать
  деплоя, чтобы это заметить, нельзя — `manage.py check` и старт runserver
  обязаны краснеть сразу.
"""

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


def _key() -> str:
    return getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""


@register(Tags.security)
def secrets_encryption_key_valid(app_configs, **kwargs):
    """Ключ задан, но не является ключом Fernet → Error в любом окружении.

    Естественные способы «сгенерировать ключ» дают непригодное значение:
    `openssl rand -hex 32` (64 hex = 32 байта ПОСЛЕ hex-декода, но Fernet ждёт
    base64), скопированный python-repr `b'…='`, плейсхолдер CHANGE-ME из шаблона
    окружения. Прежний гейт проверял только непустоту — деплой рапортовал успех,
    а в проде интеграции молча умирали.
    """
    key = _key()
    if not key:
        return []  # «не задан» — вопрос другого чека (deploy-only)
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        return [
            Error(
                f"SECRETS_ENCRYPTION_KEY задан, но не является ключом Fernet: {exc}",
                hint=(
                    "Нужны 32 байта в urlsafe-base64. Сгенерировать: python -c "
                    '"from cryptography.fernet import Fernet; '
                    "print(Fernet.generate_key().decode())\". Значение без префикса b'…'. "
                    "Не нужен ключ в dev? Оставьте переменную ПУСТОЙ — тогда работает "
                    "производный ключ из SECRET_KEY."
                ),
                id="secrets.E002",
            )
        ]
    return []


@register(Tags.security, deploy=True)
def secrets_encryption_key_set(app_configs, **kwargs):
    if _key():
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
