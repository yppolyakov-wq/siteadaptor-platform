"""Кабинет Telegram-бота (M23/TG1): ввод токена → getMe + setWebhook, тумблер.

Владелец создаёт бота в @BotFather, вставляет токен. Мы проверяем токен (getMe),
сохраняем username и ставим webhook на домен арендатора. Отключение снимает
webhook. Под gated-подпиской POST блокирует middleware (read-only).
"""

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services
from .models import TelegramBot


def _bot() -> TelegramBot:
    bot = TelegramBot.objects.first()
    if bot is None:
        bot = TelegramBot.objects.create()
    return bot


@login_required
def settings_view(request):
    bot = _bot()
    return render(
        request,
        "telegram/settings.html",
        {
            "nav": "telegram",
            "bot": bot,
            "bot_link": f"https://t.me/{bot.bot_username}" if bot.bot_username else "",
        },
    )


@login_required
@require_POST
def connect(request):
    token = (request.POST.get("token") or "").strip()
    if not token:
        messages.error(request, _("Please paste the bot token from @BotFather."))
        return redirect("telegram-settings")
    try:
        me = services.get_me(token)
    except requests.RequestException:
        messages.error(request, _("Could not verify the token. Please check it."))
        return redirect("telegram-settings")

    bot = _bot()
    bot.token = token
    bot.bot_username = me.get("username", "")
    bot.save()

    base = services.tenant_base_url()
    if base:
        url = base + reverse("telegram-webhook", args=[bot.webhook_secret])
        try:
            services.set_webhook(token, url, bot.webhook_secret)
            bot.is_active = True
            bot.save(update_fields=["is_active", "updated_at"])
            messages.success(request, _("Telegram bot connected."))
        except requests.RequestException:
            messages.error(request, _("Token saved, but the webhook could not be set."))
    else:
        messages.error(request, _("No domain configured for this business yet."))
    return redirect("telegram-settings")


@login_required
@require_POST
def disconnect(request):
    bot = TelegramBot.objects.first()
    if bot and bot.token:
        try:
            services.delete_webhook(bot.token)
        except requests.RequestException:
            pass
        bot.is_active = False
        bot.save(update_fields=["is_active", "updated_at"])
        messages.success(request, _("Telegram bot disconnected."))
    return redirect("telegram-settings")
