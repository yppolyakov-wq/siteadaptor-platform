"""Прямой Anthropic Messages API — dev-маршрут (личный ключ владельца).

Обработка не гарантированно в ЕС → `eu_for` = False: при `AI_REQUIRE_EU` маршрут
не вызывается никогда (routing)."""

from __future__ import annotations

import base64

from django.conf import settings

from apps.secrets.store import get_or_setting

from ..errors import AIConfigError, AIRefused
from . import http
from .base import Provider, ProviderRequest, ProviderResponse


def messages_payload(req: ProviderRequest) -> dict:
    """Тело Messages API (общее для прямого Anthropic; Bedrock идёт через Converse)."""
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.mime,
                "data": base64.b64encode(img.data).decode(),
            },
        }
        for img in req.images
    ]
    content.append({"type": "text", "text": req.prompt})
    payload = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if req.system:
        payload["system"] = req.system
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    return payload


def parse_messages(data: dict, model: str) -> ProviderResponse:
    if data.get("stop_reason") == "refusal":
        raise AIRefused("model refusal")
    text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
    usage = data.get("usage") or {}
    return ProviderResponse(
        text=text,
        tokens_in=int(usage.get("input_tokens") or 0),
        tokens_out=int(usage.get("output_tokens") or 0),
        model=data.get("model") or model,
    )


class AnthropicProvider(Provider):
    name = "anthropic"

    def eu_for(self, model: str) -> bool:
        return False

    def call(self, req: ProviderRequest) -> ProviderResponse:
        key = get_or_setting("anthropic_api_key", "ANTHROPIC_API_KEY")
        if not key:
            raise AIConfigError("anthropic key missing")
        data = http.post_json(
            settings.ANTHROPIC_BASE_URL.rstrip("/") + "/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": settings.ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            payload=messages_payload(req),
            timeout_s=req.timeout_s,
        )
        return parse_messages(data, req.model)
