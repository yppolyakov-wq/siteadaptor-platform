"""P0-3 (аудит 2026-09-03 §9.3): явный ключ шифрования без потери данных.

Опасность наивного «просто задать SECRETS_ENCRYPTION_KEY в проде»: все
существующие шифротексты (токены ботов, Meldeschein, документы) были сделаны
производным от SECRET_KEY ключом и читались бы как '' — `decrypt` глотает
InvalidToken. Поэтому: MultiFernet (шифруем явным, читаем обоими) + команда
`rotate_secrets`, которая перешифровывает всё явным ключом, + деплой, который
останавливается ДО миграций, если ключа нет.
"""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection
from django.test import override_settings

from apps.secrets import crypto
from apps.secrets.models import PlatformSecret

pytestmark = pytest.mark.django_db

NEW_KEY = Fernet.generate_key().decode()
# Сниффер документов проверяет сигнатуру файла — нужен настоящий PNG-заголовок.
PNG = b"\x89PNG\r\n\x1a\n" + bytes(16)


@pytest.fixture(autouse=True)
def _fresh_fernet():
    """`_fernet` закэширован lru_cache — каждый тест начинает с чистого листа."""
    crypto._fernet.cache_clear()
    yield
    crypto._fernet.cache_clear()


def _legacy(plain: str) -> str:
    """Шифротекст ПРОИЗВОДНЫМ ключом — так сегодня выглядит всё в проде."""
    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        token = crypto.encrypt(plain)
    crypto._fernet.cache_clear()
    return token


def test_explicit_key_keeps_reading_legacy_and_encrypts_with_new_key():
    legacy = _legacy("bot-token")
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        assert crypto.decrypt(legacy) == "bot-token"  # непрерывность: старое читается
        fresh = crypto.encrypt("bot-token")
        assert crypto.needs_rotation(legacy) is True
        assert crypto.needs_rotation(fresh) is False
    # А производный ключ в одиночку НОВЫЙ шифротекст уже не читает — утечка
    # SECRET_KEY после ротации ничего не раскрывает.
    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        assert crypto.decrypt(fresh) == ""


def test_rotate_secrets_dry_run_counts_apply_reencrypts(capsys, settings):
    from apps.documents import storage as doc_storage
    from apps.documents.models import SecureDocument
    from apps.publishing.models import Channel
    from apps.publishing.secrets import decrypted_config
    from apps.telegram.models import TelegramBot
    from apps.tenants.tests.factories import TenantFactory

    # Всё создано ПРОИЗВОДНЫМ ключом (состояние прода до правки).
    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        PlatformSecret.objects.create(key="meta_app_secret", value_encrypted=crypto.encrypt("pw"))
        bot = TelegramBot.objects.create(token="123:abc", bot_username="b")
        channel = Channel.objects.create(
            type="log", name="c", config={"access_token": crypto.encrypt("acc"), "page_id": "42"}
        )
        path, mime, size = doc_storage.save_encrypted(ContentFile(PNG, name="x.png"))
        doc = SecureDocument.objects.create(path=path, mime=mime, size=size, note="secret note")
    crypto._fernet.cache_clear()
    # Тенант нужен, чтобы команда вошла в схему; в тестах все таблицы в public.
    TenantFactory(schema_name="rot_t1", slug="rot-t1")

    def raw(table, pk):
        with connection.cursor() as cur:
            cur.execute(f"SELECT {table[1]} FROM {table[0]} WHERE id = %s", [pk])
            return cur.fetchone()[0]

    settings.SECRETS_ENCRYPTION_KEY = NEW_KEY
    crypto._fernet.cache_clear()
    bot_raw_before = raw(("telegram_telegrambot", "token"), bot.pk)
    assert crypto.needs_rotation(bot_raw_before)

    call_command("rotate_secrets")  # dry-run по умолчанию — ничего не трогает
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert raw(("telegram_telegrambot", "token"), bot.pk) == bot_raw_before

    call_command("rotate_secrets", "--apply")
    out = capsys.readouterr().out
    assert "dry-run" not in out

    assert not crypto.needs_rotation(raw(("telegram_telegrambot", "token"), bot.pk))
    assert TelegramBot.objects.get(pk=bot.pk).token == "123:abc"
    assert not crypto.needs_rotation(
        PlatformSecret.objects.get(key="meta_app_secret").value_encrypted
    )
    assert PlatformSecret.objects.get(key="meta_app_secret").get_value() == "pw"
    channel.refresh_from_db()
    assert not crypto.needs_rotation(channel.config["access_token"])
    assert channel.config["page_id"] == "42"  # несекретные ключи не тронуты
    assert decrypted_config(channel)["access_token"] == "acc"
    assert not crypto.needs_rotation(raw(("documents_securedocument", "note"), doc.pk))
    with doc_storage.default_storage.open(path, "rb") as fh:
        assert not crypto.needs_rotation(fh.read())
    assert doc_storage.read_decrypted(path) == PNG

    # Идемпотентно: повторный apply ничего не находит.
    call_command("rotate_secrets", "--apply")
    assert "0" in capsys.readouterr().out


def test_deploy_script_stops_before_migrations_when_deploy_check_fails():
    """`check --deploy` больше не под `|| true` и стоит ДО миграций и рестарта:
    отсутствие ключа в проде останавливает деплой, не тронув контейнеры."""
    text = (Path(__file__).resolve().parents[3] / "scripts" / "deploy.sh").read_text()
    check_lines = [line for line in text.splitlines() if "check --deploy" in line]
    assert check_lines, "префлайт check --deploy исчез из deploy.sh"
    assert all("|| true" not in line for line in check_lines)
    assert text.index("check --deploy") < text.index("migrate_schemas --shared")
