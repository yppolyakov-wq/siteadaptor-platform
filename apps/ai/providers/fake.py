"""Фейковый провайдер: CI и dev без ключей. Детерминированный, без сети.

Режимы — `settings.AI_FAKE_MODE` или очередь `script(name, [...])` (тесты):
ok · down · 429 · bad_json · refuse · config. При JSON-режиме «ok» отвечает минимальным
примером, проходящим схему задачи (см. `example_for`)."""

from __future__ import annotations

import json

from django.conf import settings

from ..errors import AIConfigError, AIRateLimited, AIRefused, AIUnavailable
from .base import Provider, ProviderRequest, ProviderResponse

_SCRIPTS: dict[str, list[str]] = {}
CALLS: list[tuple[str, ProviderRequest]] = []
# Схема текущего вызова: фейку нужна, чтобы собрать валидный пример (api ставит её).
SCHEMAS: dict[str, dict] = {}


def script(name: str, modes: list[str]) -> None:
    _SCRIPTS[name] = list(modes)


def reset() -> None:
    _SCRIPTS.clear()
    CALLS.clear()
    SCHEMAS.clear()


def example_for(schema: dict | None):
    """Минимальный экземпляр, проходящий схему: обязательные поля, первые значения enum."""
    schema = schema or {}
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = kind[0]
    if kind == "object":
        props = schema.get("properties", {})
        return {k: example_for(props.get(k)) for k in schema.get("required", [])}
    if kind == "array":
        n = schema.get("minItems", 0)
        return [example_for(schema.get("items")) for _ in range(n)]
    if kind == "string":
        return "fake" + "x" * max(0, schema.get("minLength", 0) - 4)
    if kind in ("integer", "number"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "fake"


class FakeProvider(Provider):
    def __init__(self, name: str = "fake"):
        self.name = name

    def eu_for(self, model: str) -> bool:
        return True

    def call(self, req: ProviderRequest) -> ProviderResponse:
        CALLS.append((self.name, req))
        queue = _SCRIPTS.get(self.name)
        mode = queue.pop(0) if queue else getattr(settings, "AI_FAKE_MODE", "ok")
        if mode == "down":
            raise AIUnavailable("fake down")
        if mode == "429":
            raise AIRateLimited("fake 429")
        if mode == "refuse":
            raise AIRefused("fake refusal")
        if mode == "config":
            raise AIConfigError("fake config")
        tokens_in = len(req.system + req.prompt) // 4 + 1
        if mode == "bad_json":
            text = "not json {"
        elif req.json_mode:
            text = json.dumps(example_for(SCHEMAS.get(req.task)))
        else:
            text = f"fake:{req.task}"
        return ProviderResponse(
            text=text, tokens_in=tokens_in, tokens_out=len(text) // 4 + 1, model="fake"
        )
