"""AI-CFG-2: разбор и проверка формы «KI-Einstellungen» админки платформы.

Пустое поле = «как в .env» (ключ не пишется). Проверка — те же правила, что у system
checks: неизвестный маршрут, маршрут вне ЕС при «nur EU», маршрут без модели, задача вне
реестра или без описания для Datenschutz. Ошибка — сохранение не проходит."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils.translation import gettext as _

from . import config, providers

ROUTE_SLOTS = 3
BOOL_KEYS = ("AI_ENABLED", "AI_REQUIRE_EU", "AI_SEARCH_ENABLED", "AI_CATALOG_MODERATION")
NUMBER_KEYS = (
    "AI_TENANT_DAILY_CALLS",
    "AI_TENANT_DAILY_EUR",
    "AI_DAILY_BUDGET_EUR",
    "AI_SEARCH_DAILY",
    "AI_CATALOG_MODERATION_DAILY",
    "AI_CATALOG_MODERATION_TENANT_DAILY",
)
MODEL_KEYS = tuple(k for k, s in config.SPECS.items() if s.group == "models")
_MODEL_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/@")


def route_choices() -> list[str]:
    names = [n for n in providers.ROUTE_NAMES if n not in providers.FAKE_ROUTES]
    return names + sorted(providers.FAKE_ROUTES) if settings.DEBUG else names


def task_choices() -> list[tuple[str, str, str]]:
    """(имя, что уходит в модель, круг лиц) — только задачи с описанием для Datenschutz."""
    from . import api, disclosure, registry

    return [
        (name, data[0], data[2])
        for name, data in disclosure.TASK_DATA.items()
        if name in registry.TASKS and name not in api.ALWAYS_ALLOWED
    ]


def parse(post) -> tuple[dict, list[str]]:
    """POST → (values для AIConfig, ошибки разбора)."""
    values: dict = {}
    errors: list[str] = []
    for key in BOOL_KEYS:
        raw = post.get(key, "")
        if raw in ("1", "0"):
            values[key] = raw == "1"
    for tier in ("FAST", "STRONG"):
        picked = [post.get(f"AI_ROUTE_{tier}_{i}", "").strip() for i in range(ROUTE_SLOTS)]
        picked = [p for p in picked if p]
        if picked:
            values[f"AI_ROUTE_{tier}"] = list(dict.fromkeys(picked))
    for key in MODEL_KEYS:
        raw = (post.get(key) or "").strip()
        if raw:
            if len(raw) > 120 or not set(raw) <= _MODEL_CHARS:
                errors.append(_("Ungültiger Modellname: %(name)s") % {"name": key})
            else:
                values[key] = raw
    if post.get("tasks_custom"):
        values["AI_TASKS_ENABLED"] = [t for t in post.getlist("tasks") if t]
    for key in NUMBER_KEYS:
        raw = (post.get(key) or "").strip().replace(",", ".")
        if not raw:
            continue
        kind = config.SPECS[key].kind
        try:
            number = int(raw) if kind == "int" else float(Decimal(raw))
        except (ValueError, InvalidOperation):
            errors.append(_("Keine Zahl: %(name)s") % {"name": key})
            continue
        if number < 0 or number > 1_000_000:
            errors.append(_("Außerhalb des erlaubten Bereichs: %(name)s") % {"name": key})
            continue
        values[key] = number
    prices_raw = (post.get("AI_PRICES") or "").strip()
    if prices_raw:
        prices = {}
        for line in prices_raw.splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                model, cent_in, cent_out = parts[0], int(parts[1]), int(parts[2])
            except (IndexError, ValueError):
                errors.append(_("Preiszeile unklar: %(line)s") % {"line": line[:60]})
                continue
            if not set(model) <= _MODEL_CHARS or cent_in < 0 or cent_out < 0:
                errors.append(_("Preiszeile unklar: %(line)s") % {"line": line[:60]})
                continue
            prices[model] = [cent_in, cent_out]
        values["AI_PRICES"] = prices
    return values, errors


def validate(values: dict) -> tuple[list[str], list[str]]:
    """(ошибки, предупреждения) итоговой конфигурации: значения формы поверх .env."""
    from . import routing

    errors: list[str] = []
    warnings: list[str] = []
    with config.override(**values):
        enabled = bool(config.get("AI_ENABLED"))
        known_tasks = {name for name, _w, _s in task_choices()}
        for task in config.get("AI_TASKS_ENABLED", ()) or ():
            if task not in known_tasks:
                errors.append(_("Unbekannte oder nicht dokumentierte Aufgabe: %(t)s") % {"t": task})
        for tier in ("fast", "strong"):
            names = routing.configured(tier)
            if enabled and not names:
                errors.append(_("Keine Route für %(tier)s.") % {"tier": tier})
            usable = 0
            for name in names:
                if name not in providers.ROUTE_NAMES:
                    errors.append(_("Unbekannte Route: %(r)s") % {"r": name})
                    continue
                route = routing.describe(name, tier)
                if name not in providers.FAKE_ROUTES and not route.model:
                    errors.append(
                        _("Route %(r)s (%(tier)s) hat kein Modell.") % {"r": name, "tier": tier}
                    )
                    continue
                if not routing.allowed(route):
                    errors.append(
                        _("Route %(r)s liegt außerhalb der EU — mit „Nur EU“ nicht erlaubt.")
                        % {"r": name}
                    )
                    continue
                usable += 1
                if name not in providers.FAKE_ROUTES and not (config.get("AI_PRICES") or {}).get(
                    route.model
                ):
                    warnings.append(_("Kein Preis für Modell %(m)s.") % {"m": route.model})
            if enabled and names and not usable:
                errors.append(_("Keine nutzbare Route für %(tier)s.") % {"tier": tier})
        tasks = set(config.get("AI_TASKS_ENABLED", ()) or ())
        if config.get("AI_SEARCH_ENABLED") and "search_phrase_filters" not in tasks:
            warnings.append(_("KI-Suche ist an, aber die Aufgabe „search_phrase_filters“ fehlt."))
        if config.get("AI_CATALOG_MODERATION") and "catalog_moderation" not in tasks:
            warnings.append(_("Moderation ist an, aber die Aufgabe „catalog_moderation“ fehlt."))
        if enabled and not config.require_eu() and not settings.DEBUG:
            warnings.append(
                _("Daten gehen an Dienste außerhalb der EU — nur mit Demo-Daten zulässig.")
            )
    return errors, warnings
