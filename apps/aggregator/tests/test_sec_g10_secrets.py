"""SEC-G10 (аудит 2026-11-01): токен бота портала и секрет вебхука — шифротекстом в БД."""

import pytest
from django.db import connection

from apps.aggregator.models import PortalBot
from apps.aggregator.tests.test_portal_bot import _portal
from apps.integrations.webhooks.models import OutgoingWebhook

pytestmark = pytest.mark.django_db


def _raw(model, field, pk):
    with connection.cursor() as cur:
        cur.execute(f'SELECT "{field}"::text FROM "{model._meta.db_table}" WHERE id = %s', [pk])
        return cur.fetchone()[0]


def test_portal_bot_token_is_encrypted():
    bot = PortalBot.objects.create(portal=_portal(host="g10.siteadaptor.de"), token="123:ABCsecret")
    assert "ABCsecret" not in _raw(PortalBot, "token", bot.pk)
    bot.refresh_from_db()
    assert bot.token == "123:ABCsecret"


def test_outgoing_webhook_secret_is_encrypted():
    hook = OutgoingWebhook.objects.create(tenant_schema="g10", url="https://example.test/hook")
    plain = hook.secret
    assert plain and plain not in _raw(OutgoingWebhook, "secret", hook.pk)
    hook.refresh_from_db()
    assert hook.secret == plain
