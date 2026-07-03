from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Partner


@admin.register(Partner)
class PartnerAdmin(ModelAdmin):
    list_display = ("name", "code", "reward_kind", "is_active", "tenant_count", "created_at")
    search_fields = ("name", "code", "contact_email")
    list_filter = ("reward_kind", "is_active")
    readonly_fields = ("created_at", "updated_at")

    def tenant_count(self, obj):
        return obj.tenants.count()

    tenant_count.short_description = "Kunden"
