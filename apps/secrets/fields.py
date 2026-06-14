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
