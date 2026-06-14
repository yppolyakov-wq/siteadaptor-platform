"""Платформенная сторона поддержки (M22c): unfold-админка на public.

SiteAdaptor-поддержка видит тикеты всех тенантов и отвечает (инлайн-сообщение с
ролью platform). Уведомление владельца о непрочитанном — отложено (владелец видит
ответ в `/dashboard/help/`).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import SupportMessage, SupportThread


class SupportMessageInline(TabularInline):
    model = SupportMessage
    extra = 1
    fields = ("author_role", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(SupportThread)
class SupportThreadAdmin(ModelAdmin):
    list_display = (
        "subject",
        "tenant",
        "status",
        "priority",
        "unread_for_platform",
        "last_message_at",
    )
    list_filter = ("status", "priority", "unread_for_platform")
    search_fields = ("subject", "tenant__name")
    inlines = (SupportMessageInline,)
