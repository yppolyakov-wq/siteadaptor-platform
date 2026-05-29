from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import OutgoingWebhook, WebhookDelivery


@admin.register(OutgoingWebhook)
class OutgoingWebhookAdmin(ModelAdmin):
    list_display = ("tenant_schema", "url", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("tenant_schema", "url")
    readonly_fields = ("secret", "created_at", "updated_at")


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(ModelAdmin):
    list_display = ("event_type", "status", "attempts", "response_code", "created_at")
    list_filter = ("status", "event_type")
    search_fields = ("event_id", "event_type")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
