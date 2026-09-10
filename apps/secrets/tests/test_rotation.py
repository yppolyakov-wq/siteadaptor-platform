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
from cryptography.fernet import Fernet, InvalidToken
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError, connection
from django.test import override_settings

from apps.secrets import crypto
from apps.secrets.management.commands.rotate_secrets import Command
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


def _tenant_with_schema(schema_name: str, slug: str):
    """Тенант, у которого PG-схема реально существует.

    Фабрика создаёт только строку (`auto_create_schema=False`), а команда
    отличает «сбой в живой схеме» (ошибка, ненулевой код) от «строки Tenant без
    схемы» (диагноз, код 0). Тесты про НАСТОЯЩИЙ сбой обязаны быть в первой
    категории, иначе они проверяют не то.
    """
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name=schema_name, slug=slug)
    with connection.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    return tenant


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
    # Ротация пишет в НОВОЕ имя и переключает указатель (старое удаляется после),
    # поэтому сверяемся с путём из БД, а не с исходным.
    doc.refresh_from_db()
    assert doc.path != path
    assert not doc_storage.default_storage.exists(path)  # старый blob убран
    with doc_storage.default_storage.open(doc.path, "rb") as fh:
        assert not crypto.needs_rotation(fh.read())
    assert doc_storage.read_decrypted(doc.path) == PNG

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


# --- Ревью диффа (2026-09-09): дефекты самой команды ротации ---


def test_document_blob_survives_a_storage_failure_during_rotation(monkeypatch):
    """HIGH: ротация писала НОВЫЙ шифротекст поверх удалённого старого.

    `delete(path)` → `save(path, …)`: если storage падает между ними (5xx S3,
    обрыв, OOM), плейнтекста нет нигде — blob уничтожен навсегда, а команда
    глотает исключение per-schema и выходит с кодом 0. Пишем в НОВОЕ имя и
    переключаем указатель; старый файл удаляем только после этого.
    """
    from django.core.files.storage import default_storage

    from apps.documents import storage as doc_storage
    from apps.documents.models import SecureDocument

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        path, mime, size = doc_storage.save_encrypted(ContentFile(PNG, name="x.png"))
        doc = SecureDocument.objects.create(path=path, mime=mime, size=size)
    crypto._fernet.cache_clear()
    _tenant_with_schema("rot_fail", "rot-fail")

    real_save = default_storage.save
    monkeypatch.setattr(
        default_storage, "save", lambda *a, **kw: (_ for _ in ()).throw(OSError("S3 5xx"))
    )
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        with pytest.raises(CommandError):  # сбой схемы обязан быть ненулевым кодом
            call_command("rotate_secrets", "--apply")
        monkeypatch.setattr(default_storage, "save", real_save)
        # Документ читается по-прежнему: ни blob, ни указатель не потеряны.
        doc.refresh_from_db()
        assert default_storage.exists(doc.path)
        assert doc_storage.read_decrypted(doc.path) == PNG


def test_failing_schema_makes_the_command_exit_nonzero():
    """MEDIUM: ошибка в одной схеме печаталась в stderr, а код возврата
    оставался 0 — ops-скрипт (и владелец) считали ротацию выполненной, хотя
    часть секретов всё ещё читается производным от SECRET_KEY ключом."""
    from unittest.mock import patch

    _tenant_with_schema("rot_bad", "rot-bad")
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        with patch.object(Command, "_channel_configs", side_effect=RuntimeError("boom")):
            with pytest.raises(CommandError) as exc:
                call_command("rotate_secrets", "--apply")
    assert "rot_bad" in str(exc.value)


def test_concurrent_write_during_rotation_is_not_rolled_back(monkeypatch):
    """MEDIUM: команда писала безусловным UPDATE по снимку, снятому до начала
    записи. Прод работает во время ротации: гость сохранил Meldeschein, владелец
    сменил токен бота — и ротация возвращала СТАРОЕ значение из снимка. Значение
    перечитывается под блокировкой строки, поэтому свежая запись переживает."""
    from apps.telegram.models import TelegramBot
    from apps.tenants.tests.factories import TenantFactory

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        bot = TelegramBot.objects.create(token="alt:token", bot_username="b")
    crypto._fernet.cache_clear()
    TenantFactory(schema_name="rot_race", slug="rot-race")

    def raw_token():
        with connection.cursor() as cur:
            cur.execute("SELECT token FROM telegram_telegrambot WHERE id = %s", [bot.pk])
            return cur.fetchone()[0]

    snapshot = raw_token()
    real_status = crypto.status
    state = {"raced": False}

    def racing_status(token):
        # Момент ПОСЛЕ снятия снимка: приложение пишет своё значение (уже явным
        # ключом). Дальше команда обязана перечитать строку и не трогать свежее.
        if token == snapshot and not state["raced"]:
            state["raced"] = True
            TelegramBot.objects.filter(pk=bot.pk).update(token="neu:token")
        return real_status(token)

    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        monkeypatch.setattr(crypto, "status", racing_status)
        call_command("rotate_secrets", "--apply")
    assert state["raced"], "гонка не смоделирована — снимок не совпал"
    assert TelegramBot.objects.get(pk=bot.pk).token == "neu:token"


def test_malformed_key_stops_the_deploy_instead_of_silently_emptying_secrets():
    """Деплой стал fail-closed по переменной, а чек проверял только НЕПУСТОТУ:
    `openssl rand -hex 32` (64 hex) или python-repr `b'...'` проходили гейт, и в
    проде все секреты читались как '' (интеграции молча умирали). Проверяем
    пригодность ключа, а не факт его наличия."""
    from django.core.checks import Error

    from apps.secrets.checks import secrets_encryption_key_valid

    with override_settings(SECRETS_ENCRYPTION_KEY="0" * 64, DEBUG=False):
        issues = secrets_encryption_key_valid(None)
    assert issues and isinstance(issues[0], Error) and issues[0].id == "secrets.E002"

    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY, DEBUG=False):
        assert secrets_encryption_key_valid(None) == []


def test_malformed_key_is_not_swallowed_by_needs_rotation():
    """`needs_rotation` ловила ValueError и на КОНСТРУКТОРЕ Fernet — при кривом
    ключе команда честно печатала «0 к перешифровке» и выходила успешно."""
    with override_settings(SECRETS_ENCRYPTION_KEY="0" * 64):
        crypto._fernet.cache_clear()
        with pytest.raises(ValueError):
            crypto.needs_rotation("gAAAAAB-nonsense")


def test_env_example_documents_the_now_mandatory_key():
    """Деплой без переменной больше не проходит — шаблон окружения обязан её
    называть, иначе владелец узнаёт о ней из упавшего префлайта."""
    root = Path(__file__).resolve().parents[3]
    for name in (".env.prod.example", ".env.example"):
        text = (root / name).read_text()
        assert "SECRETS_ENCRYPTION_KEY" in text, name
        assert "Fernet.generate_key" in text, name


def test_orphan_blob_is_removed_when_the_row_vanishes_mid_rotation(monkeypatch):
    """LOW, но с правовым хвостом: ретеншн-задача документов ходит ПО СТРОКАМ.

    Если строку SecureDocument убрали между save нового файла и update указателя
    (beat `purge_expired` или удаление владельцем), апдейт затрагивает 0 строк, а
    новый шифротекст остаётся в бакете навсегда — скан документа переживает свою
    дату удаления, и найти его можно только руками. Проверяем rowcount и убираем
    за собой."""
    from django.core.files.storage import default_storage

    from apps.documents import storage as doc_storage
    from apps.documents.models import SecureDocument
    from apps.tenants.tests.factories import TenantFactory

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        path, mime, size = doc_storage.save_encrypted(ContentFile(PNG, name="x.png"))
        doc = SecureDocument.objects.create(path=path, mime=mime, size=size)
    crypto._fernet.cache_clear()
    TenantFactory(schema_name="rot_purge", slug="rot-purge")

    real_rotate = crypto.rotate_bytes

    def rotate_and_purge(blob):
        # Эмуляция гонки с ретеншн-чисткой: строки уже нет.
        SecureDocument.objects.filter(pk=doc.pk).delete()
        return real_rotate(blob)

    before = set(default_storage.listdir("documents")[1])
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        monkeypatch.setattr(crypto, "rotate_bytes", rotate_and_purge)
        call_command("rotate_secrets", "--apply")
    after = set(default_storage.listdir("documents")[1])
    assert after <= before, f"осиротевший шифротекст остался: {sorted(after - before)}"


def test_env_examples_do_not_ship_an_unusable_key():
    """CHANGE-ME в примере ХУЖЕ отсутствия: `_explicit_key` считает ключ заданным,
    чтение молча отдаёт '', запись падает 500. Пустое/закомментированное значение
    = штатный производный ключ, и dev работает."""
    root = Path(__file__).resolve().parents[3]
    for name in (".env.prod.example", ".env.example"):
        for line in (root / name).read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("SECRETS_ENCRYPTION_KEY=", "SECRETS_ENCRYPTION_KEY_PREVIOUS=")):
                assert stripped.endswith("="), f"{name}: {stripped}"
        text = (root / name).read_text()
        assert "SECRETS_ENCRYPTION_KEY_PREVIOUS" in text, f"{name}: смена ключа не описана"


def test_key_change_without_previous_key_is_loud_not_silent():
    """HIGH из ревью: инструкция «смени ключ и прогони rotate_secrets» приводила
    к тому, что НИЧЕГО не читается, а команда честно печатала «0 к перешифровке»
    и выходила успешно. Теперь нечитаемое считается отдельно и валит команду."""
    from apps.tenants.tests.factories import TenantFactory

    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    with override_settings(SECRETS_ENCRYPTION_KEY=key1):
        crypto._fernet.cache_clear()
        PlatformSecret.objects.create(key="meta_app_secret", value_encrypted=crypto.encrypt("pw"))
    TenantFactory(schema_name="rot_keychg", slug="rot-keychg")

    with override_settings(SECRETS_ENCRYPTION_KEY=key2, SECRETS_ENCRYPTION_KEY_PREVIOUS=[]):
        crypto._fernet.cache_clear()
        with pytest.raises(CommandError) as exc:
            call_command("rotate_secrets")  # уже DRY-RUN обязан кричать
    assert "PREVIOUS" in str(exc.value)


def test_key_change_with_previous_key_rotates_and_keeps_data():
    """Обратная сторона: со старым ключом в SECRETS_ENCRYPTION_KEY_PREVIOUS смена
    ключа работает — старое читается, перешифровывается новым, данные целы."""
    from apps.tenants.tests.factories import TenantFactory

    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    with override_settings(SECRETS_ENCRYPTION_KEY=key1):
        crypto._fernet.cache_clear()
        secret = PlatformSecret.objects.create(
            key="meta_app_secret", value_encrypted=crypto.encrypt("pw")
        )
    TenantFactory(schema_name="rot_keychg2", slug="rot-keychg2")

    with override_settings(SECRETS_ENCRYPTION_KEY=key2, SECRETS_ENCRYPTION_KEY_PREVIOUS=[key1]):
        crypto._fernet.cache_clear()
        call_command("rotate_secrets", "--apply")
        assert PlatformSecret.objects.get(pk=secret.pk).get_value() == "pw"
        fresh = PlatformSecret.objects.get(pk=secret.pk).value_encrypted
        assert crypto.status(fresh) == crypto.CURRENT

    # и новый шифротекст больше не читается ПЕРВЫМ ключом
    with override_settings(SECRETS_ENCRYPTION_KEY=key1, SECRETS_ENCRYPTION_KEY_PREVIOUS=[]):
        crypto._fernet.cache_clear()
        assert crypto.decrypt(fresh) == ""


def test_failed_delete_of_the_old_blob_is_reported_not_just_logged(monkeypatch):
    """Неудалённый старый blob по-прежнему читается ключом из SECRET_KEY — то
    есть цель ротации НЕ достигнута. Молчаливый успех здесь и есть та ложь,
    которую волна убирала из кода возврата."""
    from django.core.files.storage import default_storage

    from apps.documents import storage as doc_storage
    from apps.documents.models import SecureDocument

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        path, mime, size = doc_storage.save_encrypted(ContentFile(PNG, name="x.png"))
        SecureDocument.objects.create(path=path, mime=mime, size=size)
    crypto._fernet.cache_clear()
    _tenant_with_schema("rot_nodel", "rot-nodel")

    monkeypatch.setattr(
        default_storage, "delete", lambda *a, **kw: (_ for _ in ()).throw(OSError("AccessDenied"))
    )
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        with pytest.raises(CommandError):
            call_command("rotate_secrets", "--apply")


def test_platform_secret_concurrent_write_is_not_rolled_back(monkeypatch):
    """Тот же перечит под блокировкой, что у полей тенанта: докстринг команды
    обещал его для всего, а public-проход писал по снимку — свежая правка
    секрета в админке платформы молча терялась."""
    from apps.tenants.tests.factories import TenantFactory

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        secret = PlatformSecret.objects.create(
            key="meta_app_secret", value_encrypted=crypto.encrypt("alt")
        )
    crypto._fernet.cache_clear()
    TenantFactory(schema_name="rot_psrace", slug="rot-psrace")

    snapshot = PlatformSecret.objects.get(pk=secret.pk).value_encrypted
    real_status = crypto.status
    state = {"raced": False}

    def racing_status(token):
        if token == snapshot and not state["raced"]:
            state["raced"] = True
            fresh = PlatformSecret.objects.get(pk=secret.pk)
            fresh.set_value("neu")
            fresh.save(update_fields=["value_encrypted"])
        return real_status(token)

    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        monkeypatch.setattr(crypto, "status", racing_status)
        call_command("rotate_secrets", "--apply")
    assert state["raced"]
    assert PlatformSecret.objects.get(pk=secret.pk).get_value() == "neu"


def test_purge_removes_the_blob_even_if_rotation_moved_it(monkeypatch):
    """Ретеншн документов ходит ПО СТРОКАМ и работал по снимку пути. Ротация
    ключей переносит blob на новое имя — purge удалял бы СТАРЫЙ путь и сносил
    строку, а новый шифротекст с PII оставался в бакете навсегда."""
    from django.core.files.storage import default_storage

    from apps.documents import services as doc_services
    from apps.documents import storage as doc_storage
    from apps.documents.models import SecureDocument

    with override_settings(SECRETS_ENCRYPTION_KEY=""):
        crypto._fernet.cache_clear()
        path, mime, size = doc_storage.save_encrypted(ContentFile(PNG, name="x.png"))
        doc = SecureDocument.objects.create(path=path, mime=mime, size=size)
    crypto._fernet.cache_clear()

    # blob «переехал» после того, как ретеншн снял свой снимок
    moved = doc_storage.default_storage.save(
        "documents/moved.enc", ContentFile(crypto.encrypt_bytes(PNG))
    )
    SecureDocument.objects.filter(pk=doc.pk).update(path=moved)

    doc_services.purge(doc)  # doc в памяти всё ещё держит СТАРЫЙ путь
    assert not default_storage.exists(moved), "новый шифротекст остался в бакете"


def test_previous_key_never_takes_the_encryption_slot():
    """MultiFernet шифрует ПЕРВЫМ ключом. При пустом SECRETS_ENCRYPTION_KEY и
    заполненном PREVIOUS первым оказывался отставной ключ — новые секреты
    шифровались бы тем, что владелец вывел из обращения."""
    retired = Fernet.generate_key().decode()
    with override_settings(SECRETS_ENCRYPTION_KEY="", SECRETS_ENCRYPTION_KEY_PREVIOUS=[retired]):
        crypto._fernet.cache_clear()
        token = crypto.encrypt("neues-geheimnis")
    # Отставной ключ САМ ПО СЕБЕ не читает то, что зашифровано сейчас — значит
    # шифровали не им. (Через `crypto.decrypt` не проверить: связка всегда
    # содержит производный ключ и прочтёт токен любым из них.)
    with pytest.raises(InvalidToken):
        Fernet(retired.encode()).decrypt(token.encode())
    # а производный (штатный фолбэк без явного ключа) — читает
    with override_settings(SECRETS_ENCRYPTION_KEY="", SECRETS_ENCRYPTION_KEY_PREVIOUS=[]):
        crypto._fernet.cache_clear()
        assert crypto.decrypt(token) == "neues-geheimnis"


def test_tenant_row_without_a_schema_does_not_make_the_command_unpassable(capsys):
    """Строка Tenant без PG-схемы (провалившийся провижининг) не должна навсегда
    делать код возврата ненулевым: ops-инструкция «повторить после устранения
    причины» стала бы невыполнимой — устранять нечего. Тот же диагноз, что у
    `manage.py migration_state`: «СХЕМЫ ОТСУТСТВУЮТ», а не «ошибка схемы»."""
    from unittest.mock import patch

    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="ghost_schema", slug="ghost")  # схемы в БД нет
    with override_settings(SECRETS_ENCRYPTION_KEY=NEW_KEY):
        crypto._fernet.cache_clear()
        # В тестовой конфигурации все таблицы лежат в public, поэтому обход
        # такой схемы не падает сам — воспроизводим прод: таблиц по search_path
        # нет, шаг бросает ProgrammingError.
        with patch.object(Command, "_encrypted_fields", side_effect=ProgrammingError("no table")):
            call_command("rotate_secrets", "--apply")  # НЕ бросает
    out = capsys.readouterr().out
    assert "СХЕМЫ ОТСУТСТВУЮТ" in out and "ghost_schema" in out
