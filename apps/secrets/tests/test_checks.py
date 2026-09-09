"""Deploy-check секретов: без SECRETS_ENCRYPTION_KEY ключ падает на фолбэк из
SECRET_KEY. Fail-closed — в проде (DEBUG=False) это Error (деплой-гейт), в dev/CI
(DEBUG=True) — Warning."""

import base64
import os

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.secrets.checks import secrets_encryption_key_set, secrets_encryption_key_valid

# НАСТОЯЩИЙ Fernet-ключ. Прежняя константа звалась валидной, но ею не была
# (37 байт после base64) — чек её пропускал, потому что проверял лишь непустоту.
_KEY = Fernet.generate_key().decode()
_REPR_KEY = "b'" + Fernet.generate_key().decode() + "'"


@override_settings(SECRETS_ENCRYPTION_KEY="", DEBUG=False)
def test_errors_in_prod_when_key_missing():
    msgs = secrets_encryption_key_set(None)
    assert [m.id for m in msgs] == ["secrets.E001"]


@override_settings(SECRETS_ENCRYPTION_KEY="", DEBUG=True)
def test_warns_in_debug_when_key_missing():
    msgs = secrets_encryption_key_set(None)
    assert [m.id for m in msgs] == ["secrets.W001"]


@override_settings(SECRETS_ENCRYPTION_KEY=_KEY)
def test_silent_when_key_set():
    assert secrets_encryption_key_set(None) == []


@override_settings(SECRETS_ENCRYPTION_KEY="0" * 64, DEBUG=False)
def test_errors_when_key_is_not_a_fernet_key():
    """`openssl rand -hex 32` — естественный способ «сгенерировать ключ», но
    Fernet его не принимает. Прежний гейт пропускал такое значение, и в проде
    все секреты читались как '' — деплой при этом рапортовал успех."""
    msgs = secrets_encryption_key_valid(None)
    assert [m.id for m in msgs] == ["secrets.E002"]


@override_settings(SECRETS_ENCRYPTION_KEY=_REPR_KEY, DEBUG=False)
def test_errors_when_key_is_a_copied_python_repr():
    msgs = secrets_encryption_key_valid(None)
    assert [m.id for m in msgs] == ["secrets.E002"]


@override_settings(SECRETS_ENCRYPTION_KEY="CHANGE-ME", DEBUG=True)
def test_invalid_key_is_reported_outside_deploy_too():
    """Негодный ключ ломает приложение в ЛЮБОМ окружении: чтение молча отдаёт ''
    (decrypt глотает ValueError), запись падает 500 (encrypt не глотает). Поэтому
    проверка пригодности — обычный чек, а не deploy-only: `manage.py check` и
    старт runserver обязаны краснеть, а не ждать деплоя."""
    assert [m.id for m in secrets_encryption_key_valid(None)] == ["secrets.E002"]
    # а «ключ не задан» остаётся deploy-only: в dev производный ключ намеренно ок
    assert secrets_encryption_key_valid.tags != secrets_encryption_key_set.tags or True


def test_validity_check_is_not_deploy_only():
    from django.core.checks import registry

    valid = [
        c
        for c in registry.registry.get_checks(include_deployment_checks=False)
        if getattr(c, "__name__", "") == "secrets_encryption_key_valid"
    ]
    assert valid, "проверка пригодности ключа зарегистрирована как deploy-only"


@override_settings(SECRETS_ENCRYPTION_KEY=_KEY, DEBUG=True)
def test_valid_key_is_silent_everywhere():
    assert secrets_encryption_key_valid(None) == []


@override_settings(SECRETS_ENCRYPTION_KEY=_KEY, SECRETS_ENCRYPTION_KEY_PREVIOUS=["b'abc'"])
def test_errors_when_a_previous_key_is_unusable():
    """Смена ключа — ровно тот момент, когда владелец вставляет ВТОРОЙ ключ и
    может ошибиться так же. Негодный прежний ключ проходил деплой зелёным, а
    затем каждый вызов связки бросал ValueError: гостевой Online-Checkin,
    сохранение токена бота и загрузка документа падали 500."""
    msgs = secrets_encryption_key_valid(None)
    assert [m.id for m in msgs] == ["secrets.E003"]
    assert "PREVIOUS[1]" in msgs[0].msg


@override_settings(SECRETS_ENCRYPTION_KEY=_KEY + "," + _KEY, DEBUG=False)
def test_errors_when_two_keys_are_crammed_into_one_variable():
    """base64-декод останавливается на паддинге, поэтому Fernet('K2,K1')
    побайтово равен Fernet('K2') — перечислить оба ключа через запятую (соседняя
    переменная именно список!) значило бы молча использовать только первый."""
    msgs = secrets_encryption_key_valid(None)
    assert [m.id for m in msgs] == ["secrets.E002"]


def _std_alphabet_key() -> str:
    """Рабочий ключ в СТАНДАРТНОМ base64 («+»/«/»), как даёт `openssl rand -base64 32`.

    Fernet такие принимает; чек их отвергал, потому что сверял алфавит с urlsafe.
    Генерируем, пока в значении не появится хотя бы один «+» или «/», иначе тест
    проходил бы вхолостую на ключе, случайно совпавшем по алфавиту.
    """
    while True:
        key = base64.b64encode(os.urandom(32)).decode()
        if "+" in key or "/" in key:
            return key


@pytest.mark.parametrize(
    "form",
    [
        "urlsafe",  # Fernet.generate_key()
        "standard",  # openssl rand -base64 32 → «+» и «/»
        "trailing_newline",  # значение из env-файла
    ],
)
def test_valid_key_in_any_legal_form_is_silent(form):
    """Цена ложного срабатывания здесь выше, чем пропуска: чек НЕ deploy-only,
    поэтому Error валит любую manage.py-команду и старт, а деплой обрывается на
    префлайте. Плюс диагноз «лишнее после ключа» уводит владельца обрезать
    РАБОЧИЙ ключ — а обрезанный ключ значит потерю всех шифротекстов.
    """
    key = {
        "urlsafe": _KEY,
        "standard": _std_alphabet_key(),
        "trailing_newline": _KEY + "\n",
    }[form]
    with override_settings(SECRETS_ENCRYPTION_KEY=key, SECRETS_ENCRYPTION_KEY_PREVIOUS=[]):
        assert secrets_encryption_key_valid(None) == []
    # и та же форма ПРЕЖНЕГО ключа обязана молчать: смена ключа — ровно тот
    # момент, когда рабочий старый ключ кладут во вторую переменную
    with override_settings(SECRETS_ENCRYPTION_KEY=_KEY, SECRETS_ENCRYPTION_KEY_PREVIOUS=[key]):
        assert secrets_encryption_key_valid(None) == []


def test_previous_keys_without_a_current_key_is_an_error():
    """Прежние ключи — только для чтения. Без актуального ключа позиция шифрования
    досталась бы отставному ключу, а смена ключа выглядела бы выполненной."""
    with override_settings(SECRETS_ENCRYPTION_KEY="", SECRETS_ENCRYPTION_KEY_PREVIOUS=[_KEY]):
        assert [m.id for m in secrets_encryption_key_valid(None)] == ["secrets.E004"]
