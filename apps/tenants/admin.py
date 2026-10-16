from django.contrib import admin
from django.utils.translation import gettext_lazy as _
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
    list_filter = ("business_type", "subscription_status", "country", "is_demo", "is_internal")
    actions = ("mark_internal",)
    # T-8.26: поля, от которых зависит присутствие в каталоге города — правка в админке
    # действует сразу (снимки удаляются / реконсилируются), без ресинка.
    VISIBILITY_FIELDS = ("is_active", "is_demo", "is_internal", "in_city_catalog", "email_pending")
    readonly_fields = ("schema_name", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {"fields": ("name", "slug", "schema_name", "business_type", "is_active", "is_demo")},
        ),
        (
            _("Stadtkatalog"),
            {
                "fields": ("is_internal", "in_city_catalog", "email_pending"),
                "description": _(
                    "Intern = Test-/Teamregistrierung: erscheint nie im Stadtkatalog. "
                    "Zustimmung und E-Mail-Status setzt sonst der Betrieb selbst."
                ),
            },
        ),
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and set(getattr(form, "changed_data", ())) & set(self.VISIBILITY_FIELDS):
            from apps.aggregator.visibility import apply_visibility

            apply_visibility(obj)

    @admin.action(description=_("Als intern markieren (nie im Stadtkatalog)"))
    def mark_internal(self, request, queryset):
        from apps.aggregator.visibility import apply_visibility

        for tenant in queryset.exclude(schema_name="public"):
            tenant.is_internal = True
            tenant.save(update_fields=["is_internal"])
            apply_visibility(tenant)


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
