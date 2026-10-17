"""AI-0: маршруты, резерв, правило ЕС (fail-closed)."""

from unittest import mock

import pytest
from django.core.management import call_command

from apps.ai import api, checks
from apps.ai.errors import AIConfigError, AIRefused, AIUnavailable
from apps.ai.models import AIUsage
from apps.ai.providers import fake

pytestmark = pytest.mark.django_db


def test_fallback_on_unavailable(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["down", "down"])
    r = api.generate("smoke", "x")
    assert r.route == "fake_b" and r.fallback_used
    rows = list(AIUsage.objects.order_by("pk").values_list("route", "ok", "error_code"))
    assert rows == [
        ("fake", False, "unavailable"),
        ("fake", False, "unavailable"),
        ("fake_b", True, ""),
    ]


def test_429_retried_once_then_succeeds_on_same_route(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["429", "ok"])
    r = api.generate("smoke", "x")
    assert r.route == "fake" and not r.fallback_used


@pytest.mark.parametrize("mode,exc", [("config", AIConfigError), ("refuse", AIRefused)])
def test_no_fallback_on_config_error_or_refusal(ai_on, mode, exc):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", [mode])
    with pytest.raises(exc):
        api.generate("smoke", "x")
    assert [n for n, _ in fake.CALLS] == ["fake"]


def test_all_routes_down_raises_unavailable(ai_on):
    ai_on.AI_FAKE_MODE = "down"
    with pytest.raises(AIUnavailable):
        api.generate("smoke", "x")


def test_require_eu_never_calls_dev_route(ai_on):
    """Адверсариальный: прямые Anthropic/OpenAI с ключами под AI_REQUIRE_EU — ни одного
    HTTP-запроса, честный отказ."""
    ai_on.AI_REQUIRE_EU = True
    ai_on.AI_ROUTE_FAST = ["anthropic", "openai"]
    ai_on.ANTHROPIC_API_KEY = ai_on.OPENAI_API_KEY = "sk-test"
    ai_on.OPENAI_MODEL_FAST = "gpt-x"
    with mock.patch("apps.ai.providers.http.post_json") as post:
        with pytest.raises(AIUnavailable):
            api.generate("smoke", "x")
    post.assert_not_called()


def test_require_eu_excludes_fake(ai_on):
    ai_on.AI_REQUIRE_EU = True
    with pytest.raises(AIUnavailable):
        api.generate("smoke", "x")
    assert fake.CALLS == []


def test_require_eu_skips_dev_route_in_mixed_list(ai_on):
    ai_on.AI_REQUIRE_EU = True
    ai_on.AI_ROUTE_FAST = ["anthropic", "mistral"]
    ai_on.ANTHROPIC_API_KEY = ai_on.MISTRAL_API_KEY = "k"
    reply = {"choices": [{"message": {"content": "OK"}}], "usage": {}}
    with mock.patch("apps.ai.providers.http.post_json", return_value=reply) as post:
        r = api.generate("smoke", "x")
    assert r.route == "mistral" and not r.fallback_used
    assert post.call_count == 1
    assert post.call_args.args[0].startswith("https://api.mistral.ai/")


def test_mistral_custom_base_url_rejected_under_require_eu(ai_on):
    ai_on.AI_REQUIRE_EU = True
    ai_on.AI_ROUTE_FAST = ["mistral"]
    ai_on.MISTRAL_BASE_URL = "https://mistral.example.com"
    with mock.patch("apps.ai.providers.http.post_json") as post:
        with pytest.raises(AIUnavailable):
            api.generate("smoke", "x")
    post.assert_not_called()


@pytest.mark.parametrize(
    "region,model,eu",
    [
        ("eu-central-1", "eu.anthropic.claude-x", True),
        ("eu-central-1", "global.anthropic.claude-x", False),
        ("eu-central-1", "us.anthropic.claude-x", False),
        ("us-east-1", "anthropic.claude-x", False),
    ],
)
def test_bedrock_eu_depends_on_region_and_profile(ai_on, region, model, eu):
    from apps.ai.providers.bedrock import BedrockProvider

    ai_on.AWS_BEDROCK_REGION = region
    assert BedrockProvider().eu_for(model) is eu


def test_system_check_flags_non_eu_route_under_require_eu(settings):
    settings.AI_REQUIRE_EU = True
    settings.AI_ROUTE_FAST = ["openai"]
    ids = [p.id for p in checks.check_ai_routes()]
    assert "ai.E001" in ids


def test_system_check_flags_unknown_route(settings):
    settings.AI_ROUTE_STRONG = ["chatgpt"]
    assert "ai.E002" in [p.id for p in checks.check_ai_routes()]


def test_system_check_warns_on_missing_price(settings):
    settings.AI_ENABLED = True
    settings.AI_ROUTE_FAST = ["mistral"]
    settings.AI_PRICES = {}
    assert "ai.W002" in [p.id for p in checks.check_ai_routes()]


def test_production_settings_require_eu_by_default():
    text = open("config/settings/production.py", encoding="utf-8").read()
    assert 'AI_REQUIRE_EU = env.bool("AI_REQUIRE_EU", default=True)' in text


def test_ai_smoke_uses_fake_and_prints_no_keys(settings, capsys):
    settings.MISTRAL_API_KEY = "sk-secret-marker"
    call_command("ai_smoke")
    out = capsys.readouterr().out
    assert "fake" in out and "OK" in out
    assert "sk-secret-marker" not in out
    assert AIUsage.objects.filter(task="smoke", tenant_schema="").count() == 1


def test_ai_smoke_refuses_non_eu_without_debug(settings):
    from django.core.management.base import CommandError

    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("ai_smoke", "--allow-non-eu")
