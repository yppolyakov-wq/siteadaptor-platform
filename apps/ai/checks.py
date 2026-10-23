"""System checks ИИ-слоя (видны в `manage.py check` и `check --deploy`)."""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from . import config, providers, routing
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
            # При выключенном слое маршрут не вызывается — не ломаем деплой (check --deploy).
            if config.get("AI_ENABLED") and config.require_eu() and not routing.allowed(route):
                problems.append(
                    Error(
                        f"AI_REQUIRE_EU: маршрут {name!r} ({tier}) вне ЕС или фейк — "
                        "он не будет вызываться.",
                        hint="Уберите маршрут из AI_ROUTE_* или используйте bedrock/azure/mistral.",
                        id="ai.E001",
                    )
                )
            if config.get("AI_ENABLED") and name not in providers.FAKE_ROUTES and not route.model:
                problems.append(
                    Error(
                        f"AI_ROUTE_{tier.upper()}: у маршрута {name!r} не задана модель.",
                        id="ai.E003",
                    )
                )
            elif (
                config.get("AI_ENABLED")
                and name not in providers.FAKE_ROUTES
                and not (config.get("AI_PRICES") or {}).get(route.model)
            ):
                problems.append(
                    Warning(
                        f"AI_PRICES: нет цены для модели {route.model!r} — бюджет считает по "
                        "пессимистичной AI_DEFAULT_PRICE.",
                        id="ai.W002",
                    )
                )
    # AI-1: опечатка в списке задач молча выключила бы задачу.
    from .registry import TASKS

    for name in config.get("AI_TASKS_ENABLED", ()) or ():
        if name not in TASKS:
            problems.append(
                Warning(
                    f"AI_TASKS_ENABLED: неизвестная задача {name!r} — она не включится.",
                    hint="Имена задач — docs/ai-usage-policy-2026-10-23.md §2.",
                    id="ai.W005",
                )
            )
    if config.get("AI_ENABLED") and not config.require_eu() and not settings.DEBUG:
        problems.append(
            Warning(
                "AI_REQUIRE_EU=False на сервере без DEBUG: прямые API вне ЕС разрешены. "
                "Допустимо только с демо-данными, без реальных клиентов.",
                id="ai.W004",
            )
        )
    return problems
