"""T-8.10h: проверить токен общего бота платформы и зарегистрировать его webhook.

По умолчанию — пробный прогон (только getMe); `--apply` вызывает setWebhook. Ошибки
печатаются типом: в URL запроса к Telegram стоит токен бота.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse


class Command(BaseCommand):
    help = "Check the platform Telegram bot token and register its webhook (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Call Telegram setWebhook.")

    def handle(self, *args, apply=False, **options):
        from apps.telegram import bots, services
        from apps.tenants.quickstart import domain_base

        bot = bots.platform_bot()
        if bot is None:
            raise CommandError(
                "Plattform-Bot aus: TELEGRAM_PLATFORM_BOT_ENABLED=1 und Token setzen."
            )
        secret = getattr(settings, "TELEGRAM_PLATFORM_WEBHOOK_SECRET", "") or ""
        if len(secret) < 24:
            raise CommandError("TELEGRAM_PLATFORM_WEBHOOK_SECRET fehlt oder ist zu kurz (≥ 24).")
        try:
            me = services.get_me(bot.token)
        except Exception as exc:  # noqa: BLE001 — токен в URL, печатаем только тип
            raise CommandError(f"getMe fehlgeschlagen: {type(exc).__name__}") from None
        username = me.get("username", "")
        self.stdout.write(f"bot: @{username}")
        if bot.username and username and bot.username.lstrip("@") != username:
            self.stdout.write(
                f"warning: TELEGRAM_PLATFORM_BOT_USERNAME={bot.username} ≠ @{username}"
            )
        url = f"https://{domain_base()}" + reverse(
            "platform-bot-webhook", urlconf="config.urls_public"
        )
        if not apply:
            self.stdout.write("dry-run: webhook would be set on the platform host")
            return
        try:
            services.set_webhook(bot.token, url, secret)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"setWebhook fehlgeschlagen: {type(exc).__name__}") from None
        self.stdout.write("applied: webhook set")
