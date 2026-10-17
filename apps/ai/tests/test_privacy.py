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


def test_scrub_is_linear_on_long_text_without_spaces():
    """Ревью AI-0 (H-1, ReDoS): раньше 50 000 символов без пробелов ≈ 5 с."""
    import time

    from apps.core.pii import scrub

    for text in ("a" * 200_000, "1-" * 100_000, "a@" * 100_000):
        started = time.monotonic()
        scrub(text)
        assert time.monotonic() - started < 2


def test_prompt_too_large_rejected_before_provider(ai_on):
    ai_on.AI_MAX_PROMPT_CHARS = 100
    with pytest.raises(AIConfigError):
        api.generate("smoke", "x" * 101)
    assert fake.CALLS == [] and AIUsage.objects.count() == 0


def test_unexpected_adapter_error_is_normalized_and_falls_back(ai_on):
    """Ревью AI-0 (M-6): сбой адаптера без цепочки исключений (её кадры несут промпт/ключ)
    и с резервом на следующий маршрут."""
    from apps.ai.errors import AIUnavailable
    from apps.ai.providers import get

    ai_on.AI_ROUTE_FAST = ["fake"]
    with mock.patch.object(get("fake"), "call", side_effect=ValueError(f"boom {MARK}")):
        with pytest.raises(AIUnavailable) as exc:
            api.generate("smoke", "x")
    assert MARK not in str(exc.value) and exc.value.__suppress_context__ is True
    assert set(AIUsage.objects.values_list("error_code", flat=True)) == {"provider_error"}

    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    with mock.patch.object(get("fake"), "call", side_effect=ValueError("boom")):
        assert api.generate("smoke", "x").route == "fake_b"


def test_overall_deadline_stops_chain(ai_on, monkeypatch):
    from apps.ai.errors import AIUnavailable

    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    clock = iter([0.0] + [10_000.0] * 50)
    monkeypatch.setattr("apps.ai.api.time.monotonic", lambda: next(clock))
    with pytest.raises(AIUnavailable):
        api.generate("smoke", "x")
    assert fake.CALLS == []


def test_images_total_size_capped(ai_on):
    img = b"\xff\xd8\xff" + b"0" * (3 * 1024 * 1024)
    with pytest.raises(AIConfigError):
        api.generate("smoke", "x", images=[img] * 4)
