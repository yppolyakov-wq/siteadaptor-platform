"""T-8.10h: проверить токен общего бота платформы и зарегистрировать его webhook.

По умолчанию — пробный прогон (только getMe); `--apply` вызывает setWebhook. Ошибки
печатаются типом: в URL запроса к Telegram стоит токен бота.
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check the platform Telegram bot token and register its webhook (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Call Telegram setWebhook.")

    def handle(self, *args, apply=False, **options):
        from apps.platform_bot import config
        from apps.telegram import bots

        bot = bots.platform_bot()
        if bot is None:
            raise CommandError(
                "Plattform-Bot aus: im Admin unter „Plattform-Bot“ einschalten und Token setzen."
            )
        try:
            username = config.check_token(bot.token)
        except ValueError as exc:
            raise CommandError(f"getMe fehlgeschlagen: {exc}") from None
        self.stdout.write(f"bot: @{username}")
        if bot.username and bot.username != username:
            self.stdout.write(f"warning: konfigurierter Name @{bot.username} ≠ @{username}")
        if not apply:
            self.stdout.write("dry-run: webhook would be set on the platform host")
            return
        try:
            config.apply_webhook()
        except ValueError as exc:
            raise CommandError(f"setWebhook fehlgeschlagen: {exc}") from None
        self.stdout.write("applied: webhook set")
