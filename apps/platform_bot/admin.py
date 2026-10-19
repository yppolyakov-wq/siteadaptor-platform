from django.contrib import admin

from .models import OwnerTelegramLink


@admin.register(OwnerTelegramLink)
class OwnerTelegramLinkAdmin(admin.ModelAdmin):
    list_display = ("tg_user_id", "tenant", "via", "is_active", "blocked_at", "created_at")
    list_filter = ("via", "is_active")
    search_fields = ("tg_user_id", "tenant__name", "tenant__slug")
    raw_id_fields = ("tenant",)
    readonly_fields = ("created_at", "updated_at")
