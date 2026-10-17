"""System checks ИИ-слоя (видны в `manage.py check` и `check --deploy`)."""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from . import providers, routing
from .registry import TIERS


@register(Tags.security)
def check_ai_routes(app_configs=None, **kwargs):
    problems = []
    for tier in TIERS:
        for name in routing.configured(tier):
            if name not in providers.ROUTE_NAMES:
                problems.append(
                    Error(f"AI_ROUTE_{tier.upper()}: неизвестный маршрут {name!r}", id="ai.E002")
                )
                continue
            route = routing.describe(name, tier)
            if settings.AI_REQUIRE_EU and not routing.allowed(route):
                problems.append(
                    Error(
                        f"AI_REQUIRE_EU: маршрут {name!r} ({tier}) вне ЕС или фейк — "
                        "он не будет вызываться.",
                        hint="Уберите маршрут из AI_ROUTE_* или используйте bedrock/azure/mistral.",
                        id="ai.E001",
                    )
                )
            if (
                settings.AI_ENABLED
                and name not in providers.FAKE_ROUTES
                and route.model
                and not (getattr(settings, "AI_PRICES", None) or {}).get(route.model)
            ):
                problems.append(
                    Warning(
                        f"AI_PRICES: нет цены для модели {route.model!r} — бюджет её не учтёт.",
                        id="ai.W002",
                    )
                )
    return problems
