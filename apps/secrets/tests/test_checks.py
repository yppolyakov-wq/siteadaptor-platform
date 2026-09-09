"""Deploy-check секретов: без SECRETS_ENCRYPTION_KEY ключ падает на фолбэк из
SECRET_KEY. Fail-closed — в проде (DEBUG=False) это Error (деплой-гейт), в dev/CI
(DEBUG=True) — Warning."""

from cryptography.fernet import Fernet
from django.test import override_settings

from apps.secrets.checks import secrets_encryption_key_set

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
    msgs = secrets_encryption_key_set(None)
    assert [m.id for m in msgs] == ["secrets.E002"]


@override_settings(SECRETS_ENCRYPTION_KEY=_REPR_KEY, DEBUG=False)
def test_errors_when_key_is_a_copied_python_repr():
    msgs = secrets_encryption_key_set(None)
    assert [m.id for m in msgs] == ["secrets.E002"]
