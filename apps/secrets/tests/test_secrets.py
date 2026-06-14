"""Зашифрованные секреты: crypto round-trip, модель (маскирование), стор-фолбэк."""

import pytest

from apps.secrets import crypto, store
from apps.secrets.admin import PlatformSecretForm
from apps.secrets.models import PlatformSecret

pytestmark = pytest.mark.django_db


def test_crypto_roundtrip():
    token = crypto.encrypt("super-secret")
    assert token and token != "super-secret"  # зашифровано, не плейнтекст
    assert crypto.decrypt(token) == "super-secret"


def test_decrypt_garbage_returns_empty():
    assert crypto.decrypt("not-a-valid-token") == ""
    assert crypto.encrypt("") == ""


def test_model_stores_encrypted_and_masks():
    s = PlatformSecret(key="meta_app_secret")
    s.set_value("abc123")
    s.save()
    assert s.value_encrypted != "abc123"  # в БД зашифровано
    assert s.is_set is True
    assert PlatformSecret.objects.get(key="meta_app_secret").get_value() == "abc123"


def test_store_get_and_fallback(settings):
    assert store.get("missing_key", default="fb") == "fb"
    obj = PlatformSecret(key="google_oauth_client_id")
    obj.set_value("from-admin")
    obj.save()
    assert store.get("google_oauth_client_id") == "from-admin"

    # get_or_setting: админка перекрывает settings; иначе — settings.
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "from-env"
    assert store.get_or_setting("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET") == (
        "from-env"
    )
    s = PlatformSecret(key="google_oauth_client_secret")
    s.set_value("admin-wins")
    s.save()
    assert store.get_or_setting("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET") == (
        "admin-wins"
    )


def test_admin_form_write_only_and_keep_on_blank():
    obj = PlatformSecret.objects.create(key="resend_api_key")
    obj.set_value("rk_live_1")
    obj.save()

    # пустое значение не затирает сохранённый секрет
    form = PlatformSecretForm(
        {"key": "resend_api_key", "description": "Resend", "value": ""}, instance=obj
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.get_value() == "rk_live_1"

    # новое значение перезаписывает
    form2 = PlatformSecretForm(
        {"key": "resend_api_key", "description": "Resend", "value": "rk_live_2"}, instance=saved
    )
    assert form2.is_valid(), form2.errors
    assert form2.save().get_value() == "rk_live_2"
