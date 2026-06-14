"""Шифрование секретных подключей Channel.config at-rest (apps.secrets.crypto).

Шифруем только токены (SECRET_KEYS), не весь конфиг: остальные поля (location,
page_id, chat_id, board_id, ig_user_id) не секретны и остаются читаемыми. Толе-
рантно к легаси-плейнтексту: нерасшифровываемое значение читается как есть.
"""

from apps.secrets import crypto

SECRET_KEYS = ("refresh_token", "access_token", "bot_token")


def decrypted_config(channel) -> dict:
    """Конфиг канала с расшифрованными секретными подключами (для адаптеров)."""
    config = dict(channel.config or {})
    for key in SECRET_KEYS:
        value = config.get(key)
        if value:
            config[key] = crypto.try_decrypt(value) or value
    return config
