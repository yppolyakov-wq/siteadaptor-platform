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


def test_no_fallback_on_refusal(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["refuse"])
    with pytest.raises(AIRefused):
        api.generate("smoke", "x")
    assert [n for n, _ in fake.CALLS] == ["fake"]


def test_broken_key_on_first_route_falls_back(ai_on, caplog):
    """Ревью AI-0 (M2): ключ первого маршрута сломан (401/«key missing») — исправный
    второй маршрут отвечает, в лог — предупреждение."""
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["config"])
    r = api.generate("smoke", "x")
    assert r.route == "fake_b" and r.fallback_used
    assert "config error" in caplog.text


def test_config_error_on_all_routes_raises_config_error(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake"]
    fake.script("fake", ["config"])
    with pytest.raises(AIConfigError):
        api.generate("smoke", "x")


SCHEMA = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}


def test_schema_retry_survives_429_on_same_route(ai_on):
    """Ревью AI-0 (M1): повтор по схеме тоже ретраится при 429."""
    fake.script("fake", ["bad_json", "429", "ok"])
    r = api.generate("smoke", "x", schema=SCHEMA)
    assert r.data == {"a": "fake"} and r.route == "fake"


def test_schema_retry_down_falls_back_to_next_route(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["bad_json", "down", "down"])
    r = api.generate("smoke", "x", schema=SCHEMA)
    assert r.route == "fake_b" and r.data == {"a": "fake"}


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
        ("eu-central-1", "anthropic.claude-x", True),
        ("eu-central-1", "mistral.mistral-large", True),
        ("eu-central-1", "global.anthropic.claude-x", False),
        ("eu-central-1", "in.anthropic.claude-x", False),  # будущий геопрофиль — не ЕС
        (
            "eu-central-1",
            "arn:aws:bedrock:eu-central-1:1:inference-profile/global.anthropic.claude-x",
            False,
        ),
        ("eu-central-1", "", False),
        ("eu-central-1", "us.anthropic.claude-x", False),
        ("us-east-1", "anthropic.claude-x", False),
    ],
)
def test_bedrock_eu_depends_on_region_and_profile(ai_on, region, model, eu):
    from apps.ai.providers.bedrock import BedrockProvider

    ai_on.AWS_BEDROCK_REGION = region
    assert BedrockProvider().eu_for(model) is eu


def test_system_check_flags_non_eu_route_under_require_eu(settings):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = True
    settings.AI_ROUTE_FAST = ["openai"]
    ids = [p.id for p in checks.check_ai_routes()]
    assert "ai.E001" in ids


def test_system_check_silent_in_prod_defaults_when_disabled(settings):
    """Ревью AI-0 (H1): прод с дефолтами (ИИ выключен, маршрут fake) не ломает
    `check --deploy` — иначе деплой этого коммита остановился бы."""
    settings.AI_ENABLED = False
    settings.AI_REQUIRE_EU = True
    settings.AI_ROUTE_FAST = settings.AI_ROUTE_STRONG = ["fake"]
    assert checks.check_ai_routes() == []


def test_system_check_flags_missing_model(settings):
    settings.AI_ENABLED = True
    settings.AI_ROUTE_FAST = ["bedrock"]
    settings.BEDROCK_MODEL_FAST = ""
    assert "ai.E003" in [p.id for p in checks.check_ai_routes()]


@pytest.mark.parametrize(
    "flag,endpoint,eu",
    [
        (True, "https://res.openai.azure.com", True),
        (False, "https://res.openai.azure.com", False),  # тип развёртывания не подтверждён
        (True, "http://res.openai.azure.com", False),
        (True, "https://evil.example.com", False),
        (True, "https://res.openai.azure.com.evil.example", False),
    ],
)
def test_azure_eu_only_with_confirmed_data_zone_and_azure_host(settings, flag, endpoint, eu):
    from apps.ai.providers.openai_chat import AzureOpenAIProvider

    settings.AZURE_OPENAI_EU_DATA_ZONE = flag
    settings.AZURE_OPENAI_ENDPOINT = endpoint
    assert AzureOpenAIProvider().eu_for("dep") is eu


def test_mistral_plain_http_is_not_eu(settings):
    from apps.ai.providers.openai_chat import MistralProvider

    settings.MISTRAL_BASE_URL = "http://api.mistral.ai"
    assert MistralProvider().eu_for("m") is False


def test_system_check_warns_when_eu_rule_off_without_debug(settings):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.DEBUG = False
    assert "ai.W004" in [p.id for p in checks.check_ai_routes()]


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
    # Sentry не получает локальные переменные кадров (промпты, заголовки с ключами).
    assert "include_local_variables=False" in text


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
