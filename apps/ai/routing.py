"""Маршруты задачи: список из настроек `AI_ROUTE_FAST`/`AI_ROUTE_STRONG`, порядок =
резерв. Правило ЕС (fail-closed): при `AI_REQUIRE_EU` маршрут вне ЕС и фейк
вырезаются ДО вызова — запрос туда не уходит даже как резерв."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from . import providers
from .errors import AIUnavailable

_MODEL_SETTINGS = {
    "bedrock": "BEDROCK_MODEL_{}",
    "azure": "AZURE_OPENAI_DEPLOYMENT_{}",
    "mistral": "MISTRAL_MODEL_{}",
    "anthropic": "ANTHROPIC_MODEL_{}",
    "openai": "OPENAI_MODEL_{}",
}


@dataclass(frozen=True)
class Route:
    name: str
    provider: object
    model: str
    eu: bool


def configured(tier: str) -> list[str]:
    raw = settings.AI_ROUTE_STRONG if tier == "strong" else settings.AI_ROUTE_FAST
    return [str(r).strip() for r in raw or () if str(r).strip()]


def model_for(name: str, tier: str) -> str:
    if name in providers.FAKE_ROUTES:
        return "fake"
    attr = _MODEL_SETTINGS[name].format(tier.upper())
    return getattr(settings, attr, "") or ""


def describe(name: str, tier: str) -> Route:
    provider = providers.get(name)
    model = model_for(name, tier)
    return Route(name=name, provider=provider, model=model, eu=bool(provider.eu_for(model)))


def allowed(route: Route) -> bool:
    if not settings.AI_REQUIRE_EU:
        return True
    return route.eu and route.name not in providers.FAKE_ROUTES


def routes_for(tier: str) -> list[Route]:
    routes = [r for r in (describe(n, tier) for n in configured(tier)) if allowed(r)]
    if not routes:
        raise AIUnavailable("no allowed route")
    return routes
