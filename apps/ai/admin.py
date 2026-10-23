"""AI-0b: сводка расхода ИИ — только платформе (суперпользователь), паттерн PortalStatAdmin."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext as _
from unfold.admin import ModelAdmin

from . import budget
from .models import AIUsage


def _eu(routing, name: str) -> bool:
    try:
        return bool(routing.describe(name, "fast").eu)
    except Exception:  # noqa: BLE001 — провайдер не настроен: просто без бейджа
        return False


@admin.register(AIUsage)
class AIUsageAdmin(ModelAdmin):
    list_display = (
        "created_at",
        "tenant_schema",
        "task",
        "route",
        "model",
        "tokens_in",
        "tokens_out",
        "cost_cents",
        "duration_ms",
        "ok",
        "error_code",
        "fallback_used",
    )
    list_filter = ("ok", "route", "task", "is_demo", "day")
    date_hierarchy = "day"
    search_fields = ("tenant_schema", "model")

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def changelist_view(self, request, extra_context=None):
        today = budget.today_totals()
        extra_context = {
            **(extra_context or {}),
            "subtitle": f"Heute: {today['calls']} Aufrufe · {today['cost_cents'] / 100:.2f} €",
        }
        return super().changelist_view(request, extra_context=extra_context)

    # --- AI-CFG-2: экран «KI-Einstellungen» (только суперпользователь) ----------------

    def get_urls(self):
        return [
            path(
                "einstellungen/",
                self.admin_site.admin_view(self.settings_view),
                name="ai_settings",
            ),
            *super().get_urls(),
        ]

    def settings_view(self, request):
        from django.conf import settings as dj_settings

        from apps.audit.services import audit_event

        from . import config, config_form, routing

        if not request.user.is_superuser:
            raise PermissionDenied
        if request.method == "POST":
            values, errors = config_form.parse(request.POST)
            if not errors:
                errors, _warnings = config_form.validate(values)
            if errors:
                for err in errors:
                    messages.error(request, err)
                return redirect("admin:ai_settings")
            diff = config.save(values, user=request.user)
            audit_event(
                action="ai.config.changed",
                resource_type="ai_config",
                resource_id="1",
                actor=request.user,
                changes=diff,
                tenant_schema="",
            )
            messages.success(
                request, _("Gespeichert — wirkt in allen Prozessen binnen 15 Sekunden.")
            )
            return redirect("admin:ai_settings")

        sources = config.sources()
        admin_values = config.admin_values()

        def env(name):
            return getattr(dj_settings, name, "")

        routes = {
            tier: {
                "picked": (routing.configured(tier) + [""] * config_form.ROUTE_SLOTS)[
                    : config_form.ROUTE_SLOTS
                ],
                "admin": sources[f"AI_ROUTE_{tier.upper()}"] == "admin",
                "env": ", ".join(env(f"AI_ROUTE_{tier.upper()}") or []),
            }
            for tier in ("fast", "strong")
        }
        errors, warnings = config_form.validate({})
        context = {
            **self.admin_site.each_context(request),
            "title": _("KI-Einstellungen"),
            "bools": [
                {
                    "key": key,
                    "admin": admin_values.get(key),
                    "env": bool(env(key)),
                    "locked": key == "AI_REQUIRE_EU" and bool(env(key)),
                }
                for key in config_form.BOOL_KEYS
            ],
            "routes": routes,
            "route_choices": [(name, _eu(routing, name)) for name in config_form.route_choices()],
            "models": [
                {"key": key, "admin": admin_values.get(key, ""), "env": env(key) or ""}
                for key in config_form.MODEL_KEYS
            ],
            "tasks": config_form.task_choices(),
            "tasks_custom": "AI_TASKS_ENABLED" in admin_values,
            "tasks_active": set(config.get("AI_TASKS_ENABLED", ()) or ()),
            "tasks_env": ", ".join(env("AI_TASKS_ENABLED") or []),
            "numbers": [
                {"key": key, "admin": admin_values.get(key, ""), "env": env(key)}
                for key in config_form.NUMBER_KEYS
            ],
            "prices_admin": "\n".join(
                f"{m} {p[0]} {p[1]}" for m, p in (admin_values.get("AI_PRICES") or {}).items()
            ),
            "prices_env": "; ".join(
                f"{m} {p[0]}/{p[1]}" for m, p in (env("AI_PRICES") or {}).items()
            ),
            "check_errors": errors,
            "check_warnings": warnings,
        }
        return TemplateResponse(request, "admin/ai/settings.html", context)
