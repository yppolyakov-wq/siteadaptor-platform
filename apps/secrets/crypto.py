"""Симметричное шифрование секретов (Fernet).

Мастер-ключ — `settings.SECRETS_ENCRYPTION_KEY` (urlsafe-base64 32 байта, как
`Fernet.generate_key()`). Если не задан — детерминированный фолбэк из SECRET_KEY
(для dev/CI; в проде задаём отдельный ключ в .env). Расшифровка чужим ключом
даёт '' (а не падение), чтобы ротация/смена ключа не роняла приложение.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Фолбэк: ключ из SECRET_KEY (детерминированный) — dev/CI.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(raw: str) -> str:
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def try_decrypt(token: str) -> str | None:
    """Расшифровать или None, если значение не является нашим шифротекстом.

    Для прозрачных полей/конфигов: None = легаси-плейнтекст (читаем как есть,
    зашифруем при следующей записи)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
