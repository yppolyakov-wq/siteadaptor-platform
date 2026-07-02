"""Deploy-check секретов (аудит 2026-07-01): предупреждать в проде, если
SECRETS_ENCRYPTION_KEY не задан (ключ падает на фолбэк из SECRET_KEY)."""

from django.test import override_settings

from apps.secrets.checks import secrets_encryption_key_set

# валидный Fernet-ключ (32 байта urlsafe-base64)
_KEY = "ZmFrZS1rZXktMzItYnl0ZXMtZm9yLXRlc3QtdXNlLTEyMzQ1Ng=="


@override_settings(SECRETS_ENCRYPTION_KEY="")
def test_warns_when_key_missing():
    msgs = secrets_encryption_key_set(None)
    assert [m.id for m in msgs] == ["secrets.W001"]


@override_settings(SECRETS_ENCRYPTION_KEY=_KEY)
def test_silent_when_key_set():
    assert secrets_encryption_key_set(None) == []
