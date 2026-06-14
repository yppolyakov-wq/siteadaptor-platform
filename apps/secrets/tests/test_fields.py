"""Шифрующие поля at-rest: round-trip, толерантность к легаси-плейнтексту."""

import pytest
from django.db import connection

from apps.secrets import crypto
from apps.telegram.models import TelegramBot

pytestmark = pytest.mark.django_db


def test_token_encrypted_at_rest_but_plaintext_in_python():
    bot = TelegramBot.objects.create(token="123:ABCsecret")
    # в Python — открытый текст
    assert TelegramBot.objects.get(pk=bot.pk).token == "123:ABCsecret"
    # в БД — зашифровано (читаем сырую колонку)
    with connection.cursor() as cur:
        cur.execute("SELECT token FROM telegram_telegrambot WHERE id = %s", [bot.pk])
        raw = cur.fetchone()[0]
    assert raw != "123:ABCsecret"
    assert crypto.try_decrypt(raw) == "123:ABCsecret"


def test_legacy_plaintext_is_readable_and_migrates_on_save():
    bot = TelegramBot.objects.create(token="x")
    # эмулируем легаси: кладём плейнтекст прямо в колонку
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE telegram_telegrambot SET token = %s WHERE id = %s", ["legacy-plain", bot.pk]
        )
    bot.refresh_from_db()
    assert bot.token == "legacy-plain"  # читается как есть (не наш шифротекст)
    bot.save()  # перезапись → шифруется
    with connection.cursor() as cur:
        cur.execute("SELECT token FROM telegram_telegrambot WHERE id = %s", [bot.pk])
        raw = cur.fetchone()[0]
    assert crypto.try_decrypt(raw) == "legacy-plain"


def test_empty_token_not_encrypted():
    bot = TelegramBot.objects.create(token="")
    with connection.cursor() as cur:
        cur.execute("SELECT token FROM telegram_telegrambot WHERE id = %s", [bot.pk])
        raw = cur.fetchone()[0]
    assert raw == ""
    # exclude(token="") по-прежнему работает
    assert not TelegramBot.objects.exclude(token="").filter(pk=bot.pk).exists()
