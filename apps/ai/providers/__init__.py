"""Реестр маршрутов: имя в `AI_ROUTE_*` → адаптер."""

from __future__ import annotations

from ..errors import AIConfigError


def _build():
    from .anthropic_direct import AnthropicProvider
    from .bedrock import BedrockProvider
    from .fake import FakeProvider
    from .openai_chat import AzureOpenAIProvider, MistralProvider, OpenAIProvider

    return {
        "bedrock": BedrockProvider(),
        "azure": AzureOpenAIProvider(),
        "mistral": MistralProvider(),
        "anthropic": AnthropicProvider(),
        "openai": OpenAIProvider(),
        "fake": FakeProvider("fake"),
        "fake_b": FakeProvider("fake_b"),  # второй фейк — для замков резерва
    }


ROUTE_NAMES = ("bedrock", "azure", "mistral", "anthropic", "openai", "fake", "fake_b")
FAKE_ROUTES = frozenset({"fake", "fake_b"})
_CACHE: dict = {}


def get(name: str):
    if not _CACHE:
        _CACHE.update(_build())
    try:
        return _CACHE[name]
    except KeyError:
        raise AIConfigError(f"unknown route {name}") from None
