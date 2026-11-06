"""Платформенная сторона поддержки (M22c): unfold-админка на public.

SiteAdaptor-поддержка видит тикеты всех тенантов и отвечает (инлайн-сообщение с
ролью platform). AIS A-3b: новое сообщение из админки проходит `services.add_message`
(роль всегда platform — подделать «owner» нельзя; флаги треда; письмо владельцу).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import SupportMessage, SupportThread


class SupportMessageInline(TabularInline):
    model = SupportMessage
    extra = 1
    fields = ("author_role", "body", "created_at")
    readonly_fields = ("author_role", "created_at")


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

    def save_formset(self, request, form, formset, change):
        from . import services

        if formset.model is not SupportMessage:
            return super().save_formset(request, form, formset, change)
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if obj.pk:
                obj.save()  # правка старого сообщения — без уведомлений
                continue
            body = (obj.body or "").strip()
            if body:
                services.add_message(
                    formset.instance, body=body[:5000], author_role=SupportMessage.AUTHOR_PLATFORM
                )
        formset.save_m2m()
