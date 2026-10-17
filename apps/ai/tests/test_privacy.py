"""AI-0: текст и ключи не утекают в учёт/логи; ПД чистятся до провайдера."""

import logging
from unittest import mock

import pytest
import requests

from apps.ai import api
from apps.ai.errors import AIConfigError
from apps.ai.models import AIUsage
from apps.ai.providers import fake

pytestmark = pytest.mark.django_db

MARK = "ZQX7marker"


def test_prompt_and_response_never_in_usage_or_logs(ai_on, caplog):
    caplog.set_level(logging.DEBUG)
    with mock.patch.object(fake.FakeProvider, "call") as call:
        from apps.ai.providers.base import ProviderResponse

        call.return_value = ProviderResponse(text=f"answer {MARK}", tokens_in=3, tokens_out=2)
        api.generate("smoke", f"prompt {MARK}", system=f"sys {MARK}")
    for row in AIUsage.objects.values():
        assert all(MARK not in str(v) for v in row.values())
    assert MARK not in caplog.text


def test_pii_scrubbed_before_provider(ai_on):
    api.generate("smoke", "Mail max@example.de, Tel +49 212 1234567, IBAN DE89370400440532013000")
    sent = fake.CALLS[0][1].prompt
    assert "max@example.de" not in sent and "1234567" not in sent and "DE8937" not in sent
    assert "‹email›" in sent and "‹nummer›" in sent and "‹iban›" in sent


def test_api_key_not_in_exception_or_log(ai_on, caplog):
    caplog.set_level(logging.DEBUG)
    ai_on.AI_ROUTE_FAST = ["mistral"]
    ai_on.MISTRAL_API_KEY = f"sk-{MARK}"
    resp = mock.Mock(status_code=401, text=f"invalid key sk-{MARK}")
    with mock.patch("apps.ai.providers.http.requests.post", return_value=resp):
        with pytest.raises(AIConfigError) as exc:
            api.generate("smoke", "x")
    assert MARK not in str(exc.value) and MARK not in repr(exc.value)
    assert MARK not in caplog.text


def test_network_error_detail_has_no_url_or_key(ai_on):
    ai_on.AI_ROUTE_FAST = ["mistral"]
    ai_on.MISTRAL_API_KEY = f"sk-{MARK}"
    err = requests.ConnectionError(f"https://api.mistral.ai/?key=sk-{MARK}")
    with mock.patch("apps.ai.providers.http.requests.post", side_effect=err):
        with pytest.raises(Exception) as exc:
            api.generate("smoke", "x")
    assert MARK not in str(exc.value)
    assert exc.value.__suppress_context__ is True


def test_search_log_scrub_still_reexported():
    from apps.aggregator import search_log
    from apps.core import pii

    assert search_log.scrub is pii.scrub
