"""Unfold-админка порталов агрегатора (P2.1d).

Django admin живёт только на public (config/urls_public.py). Внимание: портал
отдаётся по хосту только при наличии строки Domain(host → public tenant) —
команда `create_portal` создаёт обе записи разом; при создании портала через
админку строку Domain нужно добавить вручную (см. docs/portal-setup.md).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AggregatorListing, AggregatorPortal


@admin.register(AggregatorListing)
class AggregatorListingAdmin(ModelAdmin):
    """Листинги: продажа продвижения вручную (P2.4a) — выставить featured_until.

    Карточные поля редактировать незачем — их перезаписывает sync_listing;
    featured_until синк не трогает.
    """

    list_display = ("business_name", "city", "business_type", "featured_until", "is_active")
    search_fields = ("business_name", "city", "tenant_slug")
    list_filter = ("is_active", "business_type")
    fields = ("business_name", "city", "business_type", "detail_url", "featured_until")
    readonly_fields = ("business_name", "city", "business_type", "detail_url")
    ordering = ("-updated_at",)

    def has_add_permission(self, request):
        return False  # листинги создаёт только sync_listing


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
