"""T-8.10b: перерегистрировать webhook у всех подключённых ботов.

Нужно после деплоя, где менялся список `allowed_updates` (T-8.10b добавил
`callback_query` — без перерегистрации кнопки превью акции не доходят до сервера).
По умолчанию — пробный прогон; `--apply` вызывает Telegram.
"""

from django.core.management.base import BaseCommand
from django.urls import reverse
from django_tenants.utils import get_tenant_model, schema_context


class Command(BaseCommand):
    help = "Re-register Telegram webhooks of all active bots (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Call Telegram setWebhook.")

    def handle(self, *args, apply=False, **options):
        from apps.telegram import services
        from apps.telegram.models import TelegramBot

        bots = errors = 0
        for tenant in get_tenant_model().objects.exclude(schema_name="public"):
            with schema_context(tenant.schema_name):
                try:
                    bot = TelegramBot.objects.filter(is_active=True).exclude(token="").first()
                except Exception:  # noqa: BLE001 — схема без таблицы бота
                    continue
                if bot is None:
                    continue
                base = services.tenant_base_url()
                if not base:
                    continue
                bots += 1
                if not apply:
                    self.stdout.write(f"would resync: {tenant.schema_name}")
                    continue
                url = base + reverse(
                    "telegram-webhook", args=[bot.webhook_secret], urlconf="config.urls_tenant"
                )
                try:
                    services.set_webhook(bot.token, url, bot.webhook_secret)
                except Exception as exc:  # noqa: BLE001 — токен в URL, печатаем только тип
                    errors += 1
                    self.stdout.write(f"error: {tenant.schema_name}: {type(exc).__name__}")
        mode = "applied" if apply else "dry-run"
        self.stdout.write(f"{mode}: bots={bots} errors={errors}")
