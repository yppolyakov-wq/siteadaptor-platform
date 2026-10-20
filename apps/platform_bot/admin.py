from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext as _

from .models import OwnerTelegramLink


def superuser_only(request) -> bool:
    """Пункт меню unfold «Telegram platform bot» — только суперпользователю (экран тоже)."""
    return bool(getattr(request.user, "is_superuser", False))


@admin.register(OwnerTelegramLink)
class OwnerTelegramLinkAdmin(admin.ModelAdmin):
    list_display = ("tg_user_id", "tenant", "via", "is_active", "blocked_at", "created_at")
    list_filter = ("via", "is_active")
    search_fields = ("tg_user_id", "tenant__name", "tenant__slug")
    raw_id_fields = ("tenant",)
    readonly_fields = ("created_at", "updated_at")

    def get_urls(self):
        return [
            path(
                "einstellungen/",
                self.admin_site.admin_view(self.settings_view),
                name="platform_bot_settings",
            ),
            *super().get_urls(),
        ]

    def settings_view(self, request):
        """T-8.10h: экран «Plattform-Bot» — включение, токен, вебхук и статус без сервера."""
        if not request.user.is_superuser:
            raise PermissionDenied
        from . import config

        if request.method == "POST":
            self._handle_post(request, config)
            return redirect("admin:platform_bot_settings")
        from apps.telegram import bots

        context = {
            **self.admin_site.each_context(request),
            "title": _("Telegram-Bot der Plattform"),
            "enabled": config.enabled(),
            "token_set": bool(config.token()),
            "username": config.username(),
            "secret_set": len(config.webhook_secret()) >= config.SECRET_MIN,
            "webhook_url": config.webhook_url(),
            "info": config.webhook_info(bot.token) if (bot := bots.platform_bot()) else {},
            "last_update": config.last_update(),
            "sources": config.sources(),
            "links_active": OwnerTelegramLink.objects.filter(is_active=True).count(),
            "links_url": "admin:platform_bot_ownertelegramlink_changelist",
        }
        return TemplateResponse(request, "admin/platform_bot/settings.html", context)

    def _handle_post(self, request, config) -> None:
        action = request.POST.get("action")
        if action == "save":
            raw = (request.POST.get("token") or "").strip()
            if raw:
                try:
                    name = config.check_token(raw)
                except ValueError as exc:
                    messages.error(request, _("Token ungültig (%(err)s).") % {"err": exc})
                    return
                config.set_token(raw)
                config.set_username(name)
            config.set_enabled(bool(request.POST.get("enabled")))
            messages.success(request, _("Gespeichert."))
        elif action == "webhook":
            try:
                config.apply_webhook()
            except ValueError as exc:
                messages.error(request, _("Webhook fehlgeschlagen (%(err)s).") % {"err": exc})
                return
            messages.success(request, _("Webhook gesetzt."))
        elif action == "unhook":
            try:
                config.remove_webhook()
            except ValueError as exc:
                messages.error(request, _("Webhook fehlgeschlagen (%(err)s).") % {"err": exc})
                return
            messages.success(request, _("Webhook entfernt."))
