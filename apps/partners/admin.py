from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin

from .models import Partner


@admin.register(Partner)
class PartnerAdmin(ModelAdmin):
    list_display = ("name", "code", "reward_kind", "is_active", "tenant_count", "created_at")
    search_fields = ("name", "code", "contact_email")
    list_filter = ("reward_kind", "is_active")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        # annotate вместо COUNT-на-строку (N+1, ревью D3)
        return super().get_queryset(request).annotate(_tenant_count=Count("tenants"))

    def tenant_count(self, obj):
        return obj._tenant_count

    tenant_count.short_description = "Kunden"
    tenant_count.admin_order_field = "_tenant_count"
