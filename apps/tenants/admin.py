from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Domain, SignupRequest, Tenant


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    list_display = (
        "name",
        "schema_name",
        "business_type",
        "city",
        "subscription_status",
        "created_at",
    )
    search_fields = ("name", "slug", "schema_name")
    list_filter = ("business_type", "subscription_status", "country")
    readonly_fields = ("schema_name", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {"fields": ("name", "slug", "schema_name", "business_type", "is_active")}),
        (
            "Location",
            {"fields": ("country", "city", "district", "address", "latitude", "longitude")},
        ),
        (
            "Localization",
            {"fields": ("default_locale", "enabled_locales", "default_currency", "timezone")},
        ),
        ("Region / Modules", {"fields": ("data_region", "enabled_modules")}),
        ("Branding", {"fields": ("logo_url", "primary_color")}),
        (
            "Billing",
            {
                "fields": (
                    "stripe_customer_id",
                    "subscription_status",
                    "trial_ends_at",
                    "subscription_ends_at",
                )
            },
        ),
        ("Owner contact", {"fields": ("owner_email", "owner_phone")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain", "tenant__name", "tenant__schema_name")
    list_filter = ("is_primary",)
    autocomplete_fields = ("tenant",)


@admin.register(SignupRequest)
class SignupRequestAdmin(ModelAdmin):
    """AB5.1: диагностика double-opt-in регистраций (дошло ли письмо, кто завис)."""

    list_display = ("email", "slug", "business_type", "created_at", "confirmed_at", "tenant")
    search_fields = ("email", "slug", "business_name")
    list_filter = ("business_type",)
    ordering = ("-created_at",)
    # Заявка создаётся только формой регистрации; хэш/токен в админке не правим.
    readonly_fields = ("token", "password_hash", "created_at", "confirmed_at", "tenant")

    def has_add_permission(self, request):
        return False
