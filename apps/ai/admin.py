"""AI-0b: сводка расхода ИИ — только платформе (суперпользователь), паттерн PortalStatAdmin."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from . import budget
from .models import AIUsage


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
