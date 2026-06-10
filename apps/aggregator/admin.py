"""Unfold-админка порталов агрегатора (P2.1d).

Django admin живёт только на public (config/urls_public.py). Внимание: портал
отдаётся по хосту только при наличии строки Domain(host → public tenant) —
команда `create_portal` создаёт обе записи разом; при создании портала через
админку строку Domain нужно добавить вручную (см. docs/portal-setup.md).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AggregatorPortal


@admin.register(AggregatorPortal)
class AggregatorPortalAdmin(ModelAdmin):
    list_display = ("host", "kind", "city", "business_type", "is_active", "updated_at")
    search_fields = ("host", "city")
    list_filter = ("kind", "is_active", "business_type")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("host",)

    fieldsets = (
        (None, {"fields": ("host", "kind", "is_active")}),
        ("Filters", {"fields": ("city", "business_type")}),
        ("Branding", {"fields": ("title", "tagline", "intro", "logo_url", "primary_color")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
