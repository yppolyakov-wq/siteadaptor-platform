"""AI-0c: формат запросов и разбор ответов адаптеров (транспорт подменён)."""

from unittest import mock

import pytest
import requests

from apps.ai.errors import AIConfigError, AIRateLimited, AIRefused, AIUnavailable
from apps.ai.providers import anthropic_direct, bedrock, http, openai_chat
from apps.ai.providers.base import Image, ProviderRequest

pytestmark = pytest.mark.django_db

PNG = Image(mime="image/png", data=b"\x89PNG\r\n\x1a\n...")


def _req(**kw):
    base = dict(model="m-1", prompt="Hallo", system="Sys", max_tokens=50, timeout_s=7)
    base.update(kw)
    return ProviderRequest(**base)


def test_anthropic_messages_payload_and_usage(settings):
    settings.ANTHROPIC_API_KEY = "sk-a"
    reply = {
        "model": "m-1",
        "content": [{"type": "text", "text": "OK"}],
        "usage": {"input_tokens": 11, "output_tokens": 2},
        "stop_reason": "end_turn",
    }
    with mock.patch.object(http, "post_json", return_value=reply) as post:
        r = anthropic_direct.AnthropicProvider().call(_req(images=(PNG,)))
    url, kw = post.call_args.args[0], post.call_args.kwargs
    assert url == "https://api.anthropic.com/v1/messages"
    assert kw["headers"]["x-api-key"] == "sk-a"
    assert kw["headers"]["anthropic-version"] == settings.ANTHROPIC_VERSION
    body = kw["payload"]
    assert body["system"] == "Sys" and body["max_tokens"] == 50 and "temperature" not in body
    blocks = body["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[-1] == {"type": "text", "text": "Hallo"}
    assert (r.text, r.tokens_in, r.tokens_out) == ("OK", 11, 2)


def test_anthropic_refusal(settings):
    settings.ANTHROPIC_API_KEY = "k"
    with mock.patch.object(http, "post_json", return_value={"stop_reason": "refusal"}):
        with pytest.raises(AIRefused):
            anthropic_direct.AnthropicProvider().call(_req())


def test_openai_chat_json_mode(settings):
    settings.OPENAI_API_KEY = "sk-o"
    reply = {
        "choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    with mock.patch.object(http, "post_json", return_value=reply) as post:
        r = openai_chat.OpenAIProvider().call(_req(json_mode=True))
    kw = post.call_args.kwargs
    assert post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert kw["headers"]["Authorization"] == "Bearer sk-o"
    body = kw["payload"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_completion_tokens"] == 50 and body["model"] == "m-1"
    assert body["messages"][0] == {"role": "system", "content": "Sys"}
    assert (r.text, r.tokens_in, r.tokens_out) == ('{"a":1}', 5, 3)


def test_openai_content_filter_is_refusal(settings):
    settings.OPENAI_API_KEY = "k"
    reply = {"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}
    with mock.patch.object(http, "post_json", return_value=reply):
        with pytest.raises(AIRefused):
            openai_chat.OpenAIProvider().call(_req())


def test_azure_url_deployment_and_api_key_header(settings):
    settings.AZURE_OPENAI_API_KEY = "az-k"
    settings.AZURE_OPENAI_ENDPOINT = "https://res.openai.azure.com/"
    reply = {"choices": [{"message": {"content": "OK"}}], "usage": {}}
    with mock.patch.object(http, "post_json", return_value=reply) as post:
        openai_chat.AzureOpenAIProvider().call(_req(model="dep-eu"))
    url, kw = post.call_args.args[0], post.call_args.kwargs
    assert url == (
        "https://res.openai.azure.com/openai/deployments/dep-eu/chat/completions"
        f"?api-version={settings.AZURE_OPENAI_API_VERSION}"
    )
    assert kw["headers"] == {"api-key": "az-k"} and "model" not in kw["payload"]


def test_azure_without_deployment_is_config_error(settings):
    settings.AZURE_OPENAI_API_KEY = "k"
    settings.AZURE_OPENAI_ENDPOINT = "https://res.openai.azure.com"
    with pytest.raises(AIConfigError):
        openai_chat.AzureOpenAIProvider().call(_req(model=""))


def test_mistral_payload(settings):
    settings.MISTRAL_API_KEY = "mk"
    reply = {"choices": [{"message": {"content": [{"type": "text", "text": "OK"}]}}]}
    with mock.patch.object(http, "post_json", return_value=reply) as post:
        r = openai_chat.MistralProvider().call(_req(images=(PNG,)))
    body = post.call_args.kwargs["payload"]
    assert body["max_tokens"] == 50 and "max_completion_tokens" not in body
    img = body["messages"][1]["content"][1]
    assert img["type"] == "image_url" and img["image_url"].startswith("data:image/png;base64,")
    assert r.text == "OK"


@pytest.mark.parametrize("cls", ["AnthropicProvider", "OpenAIProvider", "MistralProvider"])
def test_missing_key_is_config_error(settings, cls):
    settings.ANTHROPIC_API_KEY = settings.OPENAI_API_KEY = settings.MISTRAL_API_KEY = ""
    mod = anthropic_direct if cls == "AnthropicProvider" else openai_chat
    with mock.patch.object(http, "post_json") as post:
        with pytest.raises(AIConfigError):
            getattr(mod, cls)().call(_req())
    post.assert_not_called()


def test_key_from_platform_secret_over_env(settings):
    from apps.secrets.models import PlatformSecret

    settings.MISTRAL_API_KEY = "from-env"
    obj = PlatformSecret(key="mistral_api_key")
    obj.set_value("from-store")
    obj.save()
    reply = {"choices": [{"message": {"content": "OK"}}]}
    with mock.patch.object(http, "post_json", return_value=reply) as post:
        openai_chat.MistralProvider().call(_req())
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer from-store"


@pytest.mark.parametrize(
    "status,exc",
    [
        (400, AIConfigError),
        (401, AIConfigError),
        (403, AIConfigError),
        (429, AIRateLimited),
        (500, AIUnavailable),
        (503, AIUnavailable),
    ],
)
def test_http_status_mapping(status, exc):
    resp = mock.Mock(status_code=status)
    with mock.patch.object(http.requests, "post", return_value=resp):
        with pytest.raises(exc):
            http.post_json("https://x.test", headers={}, payload={}, timeout_s=1)


def test_http_timeout_is_unavailable():
    with mock.patch.object(http.requests, "post", side_effect=requests.Timeout()):
        with pytest.raises(AIUnavailable):
            http.post_json("https://x.test", headers={}, payload={}, timeout_s=1)


def test_bedrock_converse_payload_and_usage(settings):
    import boto3
    from botocore.stub import Stubber

    settings.AWS_BEDROCK_ACCESS_KEY_ID = "AKIA"
    settings.AWS_BEDROCK_SECRET_ACCESS_KEY = "secret"
    client = boto3.client(
        "bedrock-runtime",
        region_name="eu-central-1",
        aws_access_key_id="AKIA",
        aws_secret_access_key="secret",
    )
    reply = {
        "output": {"message": {"role": "assistant", "content": [{"text": "OK"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 9, "outputTokens": 1, "totalTokens": 10},
        "metrics": {"latencyMs": 5},
    }
    req = _req(model="eu.anthropic.claude-x", images=(PNG,))
    with Stubber(client) as stub:
        stub.add_response("converse", reply, bedrock.converse_kwargs(req))
        with mock.patch.object(bedrock.BedrockProvider, "_client", return_value=client):
            r = bedrock.BedrockProvider().call(req)
    assert (r.text, r.tokens_in, r.tokens_out) == ("OK", 9, 1)
    kwargs = bedrock.converse_kwargs(req)
    assert kwargs["system"] == [{"text": "Sys"}]
    assert kwargs["messages"][0]["content"][0]["image"]["format"] == "png"


@pytest.mark.parametrize(
    "code,exc",
    [
        ("ThrottlingException", AIRateLimited),
        ("ServiceUnavailableException", AIUnavailable),
        ("AccessDeniedException", AIConfigError),
        ("ValidationException", AIConfigError),
    ],
)
def test_bedrock_error_mapping(settings, code, exc):
    import boto3
    from botocore.stub import Stubber

    client = boto3.client(
        "bedrock-runtime",
        region_name="eu-central-1",
        aws_access_key_id="a",
        aws_secret_access_key="b",
    )
    with Stubber(client) as stub:
        stub.add_client_error("converse", service_error_code=code)
        with mock.patch.object(bedrock.BedrockProvider, "_client", return_value=client):
            with pytest.raises(exc):
                bedrock.BedrockProvider().call(_req())


def test_bedrock_without_credentials_is_config_error(settings):
    settings.AWS_BEDROCK_ACCESS_KEY_ID = ""
    with pytest.raises(AIConfigError):
        bedrock.BedrockProvider().call(_req())
