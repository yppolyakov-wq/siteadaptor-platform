"""Перерегистрация вебхуков: бот без домена не пропускается молча (SEC-A4, ops 2026-11-02).

Владелец видел `bots=1` при трёх подключённых ботах — два без домена выпадали без
следа, и было непонятно, какие боты остались на старом заголовке.
"""

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import DomainFactory, TenantFactory

pytestmark = pytest.mark.django_db


def test_bot_without_domain_is_reported_as_skipped():
    TenantFactory(schema_name="nodomain")
    TelegramBot.objects.create(token="t", is_active=True)
    out = StringIO()
    with mock.patch("apps.telegram.services.set_webhook") as set_webhook:
        call_command("telegram_resync_webhooks", "--apply", stdout=out)
    text = out.getvalue()
    assert "skip (no domain): nodomain" in text
    assert "skipped=" in text
    set_webhook.assert_not_called()


def test_bot_with_domain_is_resynced_not_skipped():
    tenant = TenantFactory(schema_name="withdomain")
    DomainFactory(tenant=tenant)
    TelegramBot.objects.create(token="t", is_active=True)
    out = StringIO()
    with mock.patch("apps.telegram.services.set_webhook") as set_webhook:
        call_command("telegram_resync_webhooks", "--apply", stdout=out)
    assert "skip (no domain): withdomain" not in out.getvalue()
    assert set_webhook.called
