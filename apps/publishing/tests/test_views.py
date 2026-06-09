import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from apps.publishing import views
from apps.publishing.models import Channel
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _User:
    is_authenticated = True
    is_active = True


def _req(method, path, data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.user = _User()
    request.tenant = TenantFactory.build(subscription_status="active")
    request._messages = CookieStorage(request)
    return request


def test_channels_page_auto_creates_and_renders():
    resp = views.channels(_req("get", "/dashboard/channels/"))
    assert resp.status_code == 200
    assert Channel.objects.filter(type="log").exists()  # авто-создан на странице


def test_toggle_enables_then_disables():
    Channel.objects.get_or_create(type="log")
    resp = views.channel_toggle(_req("post", "/dashboard/channels/toggle/", {"type": "log"}))
    assert resp.status_code == 302
    assert Channel.objects.get(type="log").is_enabled is True

    views.channel_toggle(_req("post", "/dashboard/channels/toggle/", {"type": "log"}))
    assert Channel.objects.get(type="log").is_enabled is False


def test_channel_config_saves_and_keeps_secret_on_blank():
    Channel.objects.get_or_create(type="google_business")
    views.channel_config(
        _req(
            "post",
            "/dashboard/channels/config/",
            {
                "type": "google_business",
                "location": "accounts/1/locations/2",
                "refresh_token": "rt",
            },
        )
    )
    channel = Channel.objects.get(type="google_business")
    assert channel.config == {"location": "accounts/1/locations/2", "refresh_token": "rt"}

    # пустой refresh_token при повторном сохранении не затирает сохранённый
    views.channel_config(
        _req(
            "post",
            "/dashboard/channels/config/",
            {"type": "google_business", "location": "accounts/1/locations/3", "refresh_token": ""},
        )
    )
    channel.refresh_from_db()
    assert channel.config["refresh_token"] == "rt"
    assert channel.config["location"] == "accounts/1/locations/3"
