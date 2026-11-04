"""SEC-D7: события с подключённых аккаунтов (Connect) подписаны ДРУГИМ секретом.

У Stripe эндпоинт «Events on Connected accounts» — отдельный, со своим Signing secret.
Вебхук знал один секрет и отбрасывал оплаты клиентов бизнесов как неподписанные.
Замки гоняют НАСТОЯЩУЮ проверку подписи stripe (без подмены construct_event).
"""

import hashlib
import hmac
import json
import time
import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from apps.billing import checks, webhooks

pytestmark = pytest.mark.django_db

PLATFORM = "whsec_platform"
CONNECT = "whsec_connect"


def _signed(secret: str, account: str = ""):
    evt_id = f"evt_{uuid.uuid4().hex[:12]}"
    cache.delete(f"stripe_evt:{evt_id}")
    event = {"id": evt_id, "object": "event", "type": "ping", "data": {"object": {}}}
    if account:
        event["account"] = account
    payload = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return RequestFactory().post(
        "/stripe/webhook/",
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}",
    )


def test_platform_signature_accepted(settings):
    settings.STRIPE_WEBHOOK_SECRET = PLATFORM
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert webhooks.stripe_webhook(_signed(PLATFORM)).status_code == 200


def test_connect_signature_accepted(settings):
    settings.STRIPE_WEBHOOK_SECRET = PLATFORM
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert webhooks.stripe_webhook(_signed(CONNECT, "acct_1")).status_code == 200


def test_connect_signed_event_without_account_is_refused(settings):
    """Ревью: утёкший Connect-секрет не подделает платформенное событие (подписку)."""
    settings.STRIPE_WEBHOOK_SECRET = PLATFORM
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert webhooks.stripe_webhook(_signed(CONNECT)).status_code == 400


def test_connect_signature_refused_without_connect_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = PLATFORM
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = ""
    assert webhooks.stripe_webhook(_signed(CONNECT, "acct_1")).status_code == 400


def test_foreign_signature_refused(settings):
    settings.STRIPE_WEBHOOK_SECRET = PLATFORM
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert webhooks.stripe_webhook(_signed("whsec_attacker")).status_code == 400


def test_connect_secret_alone_does_not_open_the_endpoint(settings):
    # Платформенный секрет обязателен: без него вебхук выключен (SEC-D2), как и раньше.
    settings.STRIPE_WEBHOOK_SECRET = ""
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert webhooks.stripe_webhook(_signed(CONNECT)).status_code == 503


def test_deploy_check_warns_when_connect_on_without_its_secret(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_123"
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = ""
    assert [w.id for w in checks.stripe_connect_webhook_secret_set(None)] == ["billing.W002"]
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = CONNECT
    assert checks.stripe_connect_webhook_secret_set(None) == []
    settings.STRIPE_CONNECT_CLIENT_ID = ""
    settings.STRIPE_CONNECT_WEBHOOK_SECRET = ""
    assert checks.stripe_connect_webhook_secret_set(None) == []
