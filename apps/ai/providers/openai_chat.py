"""Диалект Chat Completions: прямой OpenAI (dev), Azure OpenAI (прод ЕС), Mistral (ЕС).

Отличия сведены в параметры: адрес, заголовок ключа, имя поля лимита токенов
(`max_completion_tokens` у OpenAI/Azure, `max_tokens` у Mistral), форма картинки."""

from __future__ import annotations

import base64
from urllib.parse import quote, urlsplit

from django.conf import settings

from apps.secrets.store import get_or_setting

from ..errors import AIConfigError, AIRefused
from . import http
from .base import Provider, ProviderRequest, ProviderResponse

MISTRAL_EU_HOSTS = frozenset({"api.mistral.ai"})
AZURE_HOST_SUFFIXES = (".openai.azure.com", ".cognitiveservices.azure.com")


def chat_payload(req: ProviderRequest, *, tokens_field: str, image_as_object: bool) -> dict:
    content = [{"type": "text", "text": req.prompt}]
    for img in req.images:
        url = f"data:{img.mime};base64,{base64.b64encode(img.data).decode()}"
        content.append({"type": "image_url", "image_url": {"url": url} if image_as_object else url})
    messages = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    messages.append({"role": "user", "content": content if req.images else req.prompt})
    payload = {"messages": messages, tokens_field: req.max_tokens}
    if req.model:
        payload["model"] = req.model
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def parse_chat(data: dict, model: str) -> ProviderResponse:
    choices = data.get("choices") or []
    if not choices:
        raise AIRefused("empty choices")
    choice = choices[0]
    message = choice.get("message") or {}
    if choice.get("finish_reason") == "content_filter" or message.get("refusal"):
        raise AIRefused("content filter")
    content = message.get("content") or ""
    if isinstance(content, list):  # Mistral может вернуть список блоков
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    usage = data.get("usage") or {}
    return ProviderResponse(
        text=content,
        tokens_in=int(usage.get("prompt_tokens") or 0),
        tokens_out=int(usage.get("completion_tokens") or 0),
        model=data.get("model") or model,
    )


class OpenAIProvider(Provider):
    """Прямой OpenAI API — dev-маршрут: обычный аккаунт обрабатывает в США."""

    name = "openai"

    def eu_for(self, model: str) -> bool:
        return False

    def call(self, req: ProviderRequest) -> ProviderResponse:
        key = get_or_setting("openai_api_key", "OPENAI_API_KEY")
        if not key:
            raise AIConfigError("openai key missing")
        data = http.post_json(
            settings.OPENAI_BASE_URL.rstrip("/") + "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            payload=chat_payload(req, tokens_field="max_completion_tokens", image_as_object=True),
            timeout_s=req.timeout_s,
        )
        return parse_chat(data, req.model)


class AzureOpenAIProvider(Provider):
    """Azure OpenAI: модель = имя развёртывания. ЕС гарантирует тип развёртывания
    «Data Zone Standard (EU)» — его выбирает владелец (docs/ai-providers-setup §3.2);
    проверить тип из кода нельзя, поэтому ЕС только при ЯВНОМ подтверждении
    `AZURE_OPENAI_EU_DATA_ZONE=True` и адресе https://*.openai.azure.com (ревью AI-0)."""

    name = "azure"

    def eu_for(self, model: str) -> bool:
        parts = urlsplit(settings.AZURE_OPENAI_ENDPOINT or "")
        return (
            bool(settings.AZURE_OPENAI_EU_DATA_ZONE)
            and parts.scheme == "https"
            and (parts.hostname or "").endswith(AZURE_HOST_SUFFIXES)
        )

    def call(self, req: ProviderRequest) -> ProviderResponse:
        key = get_or_setting("azure_openai_api_key", "AZURE_OPENAI_API_KEY")
        endpoint = settings.AZURE_OPENAI_ENDPOINT
        if not key or not endpoint or not req.model:
            raise AIConfigError("azure endpoint/key/deployment missing")
        url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{quote(req.model, safe='')}/chat/completions"
            f"?api-version={settings.AZURE_OPENAI_API_VERSION}"
        )
        body = chat_payload(req, tokens_field="max_completion_tokens", image_as_object=True)
        body.pop("model", None)  # у Azure модель задаёт развёртывание в адресе
        data = http.post_json(url, headers={"api-key": key}, payload=body, timeout_s=req.timeout_s)
        return parse_chat(data, req.model)


class MistralProvider(Provider):
    """Mistral La Plateforme (Франция). ЕС — только при адресе из allowlist."""

    name = "mistral"

    def eu_for(self, model: str) -> bool:
        parts = urlsplit(settings.MISTRAL_BASE_URL or "")
        return parts.scheme == "https" and (parts.hostname or "") in MISTRAL_EU_HOSTS

    def call(self, req: ProviderRequest) -> ProviderResponse:
        key = get_or_setting("mistral_api_key", "MISTRAL_API_KEY")
        if not key:
            raise AIConfigError("mistral key missing")
        data = http.post_json(
            settings.MISTRAL_BASE_URL.rstrip("/") + "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            payload=chat_payload(req, tokens_field="max_tokens", image_as_object=False),
            timeout_s=req.timeout_s,
        )
        return parse_chat(data, req.model)
