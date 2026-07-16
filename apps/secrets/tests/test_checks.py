"""Deploy-check секретов: без SECRETS_ENCRYPTION_KEY ключ падает на фолбэк из
SECRET_KEY. Fail-closed — в проде (DEBUG=False) это Error (деплой-гейт), в dev/CI
(DEBUG=True) — Warning."""

from django.test import override_settings

from apps.secrets.checks import secrets_encryption_key_set

# валидный Fernet-ключ (32 байта urlsafe-base64)
_KEY = "ZmFrZS1rZXktMzItYnl0ZXMtZm9yLXRlc3QtdXNlLTEyMzQ1Ng=="


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
