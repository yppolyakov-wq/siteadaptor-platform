"""Шифрование секретных подключей Channel.config at-rest (TG/M23 + кабинет)."""

import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from apps.publishing import views
from apps.publishing.models import Channel
from apps.publishing.secrets import decrypted_config
from apps.secrets import crypto
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _User:
    is_authenticated = True
    is_active = True


def _post(data):
    request = RequestFactory().post("/dashboard/channels/config/", data)
    request.user = _User()
    request.tenant = TenantFactory.build(subscription_status="active")
    request._messages = CookieStorage(request)
    return request


def test_channel_config_encrypts_secret_key():
    Channel.objects.get_or_create(type="google_business")
    views.channel_config(
        _post(
            {
                "type": "google_business",
                "location": "accounts/1/locations/2",
                "refresh_token": "rt-secret",
            }
        )
    )
    channel = Channel.objects.get(type="google_business")
    # location — плейнтекст, refresh_token — шифротекст
    assert channel.config["location"] == "accounts/1/locations/2"
    assert channel.config["refresh_token"] != "rt-secret"
    assert crypto.try_decrypt(channel.config["refresh_token"]) == "rt-secret"
    # adapters читают расшифрованным
    assert decrypted_config(channel)["refresh_token"] == "rt-secret"


def test_decrypted_config_tolerates_legacy_plaintext():
    channel = Channel.objects.create(
        type="facebook", config={"page_id": "1", "access_token": "legacy-token"}
    )
    # старое значение (плейнтекст) читается как есть
    assert decrypted_config(channel)["access_token"] == "legacy-token"


def test_blank_secret_keeps_existing_encrypted():
    Channel.objects.get_or_create(type="pinterest")
    views.channel_config(_post({"type": "pinterest", "board_id": "b1", "access_token": "tok1"}))
    enc = Channel.objects.get(type="pinterest").config["access_token"]
    # повторное сохранение без токена не затирает и не двойно-шифрует
    views.channel_config(_post({"type": "pinterest", "board_id": "b2", "access_token": ""}))
    channel = Channel.objects.get(type="pinterest")
    assert channel.config["access_token"] == enc  # тот же шифротекст
    assert channel.config["board_id"] == "b2"
    assert decrypted_config(channel)["access_token"] == "tok1"
