"""Прозрачно шифрующие поля (at-rest, Fernet) — apps.secrets.

EncryptedTextField хранит значение зашифрованным, а в Python отдаёт открытый
текст. Толерантно к легаси-плейнтексту: если значение в БД не наш шифротекст
(старые незашифрованные строки), читаем его как есть и шифруем при следующей
записи (ленивая миграция, без отдельной data-миграции).

Не фильтровать по зашифрованному значению (Fernet недетерминирован — каждый
шифротекст уникален). Сравнение с пустым (`exclude(field="")`) работает: пустое
не шифруем.
"""

from django.db import models

from . import crypto


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        plain = crypto.try_decrypt(value)
        return plain if plain is not None else value

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        return crypto.encrypt(str(value))


class _Unreadable(dict):
    """Шифротекст, который нельзя расшифровать (ключ потерян/не тот). В коде — пустой
    dict; при записи возвращается ИСХОДНЫЙ шифротекст, чтобы сохранение модели не
    затёрло данные пустым значением (ревью волны 3)."""

    def __init__(self, raw: str):
        super().__init__()
        self.raw = raw


class EncryptedJSONField(EncryptedTextField):
    """SEC-G3 (аудит 2026-11-01): JSON, хранимый зашифрованным текстом (Fernet).

    Для данных особой категории (Art. 9 DSGVO: аллергии, медпоказания в анкетах
    участников). В Python — обычный dict/list; в БД — шифротекст. Легаси-значение
    (открытый JSON после смены типа колонки jsonb → text) читается как есть и
    шифруется при следующей записи. Фильтровать по содержимому нельзя.
    """

    def from_db_value(self, value, expression, connection):
        import json

        if value is None:
            return value
        plain = crypto.try_decrypt(value)
        if plain is None and value.startswith("gAAAA"):
            import logging

            logging.getLogger(__name__).error(
                "EncryptedJSONField: unreadable ciphertext (wrong SECRETS_ENCRYPTION_KEY?)"
            )
            return _Unreadable(value)
        raw = plain if plain is not None else value
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}

    def to_python(self, value):
        import json

        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return {}
        return value

    def get_prep_value(self, value):
        import json

        if value is None:
            return None
        if isinstance(value, _Unreadable):
            return value.raw
        return crypto.encrypt(json.dumps(value, ensure_ascii=False, sort_keys=True))

    def value_to_string(self, obj):
        import json

        return json.dumps(self.value_from_object(obj), ensure_ascii=False)
