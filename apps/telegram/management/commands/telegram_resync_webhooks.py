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
        from apps.telegram import ownership, services
        from apps.telegram.models import TelegramBot

        bots = errors = skipped = 0
        # Один бот у двух хозяев: вебхук у Telegram один — ставим его первому и
        # показываем дубль, а не перетягиваем адрес туда-сюда (ops 2026-11-02).
        seen: dict[str, str] = {}
        # Стабильный порядок: при дубле вебхук всегда получает один и тот же (старший) бизнес.
        for tenant in get_tenant_model().objects.exclude(schema_name="public").order_by("pk"):
            with schema_context(tenant.schema_name):
                try:
                    bot = TelegramBot.objects.filter(is_active=True).exclude(token="").first()
                except Exception:  # noqa: BLE001 — схема без таблицы бота
                    continue
                if bot is None:
                    continue
                bid = ownership.bot_id(bot.token)
                if bid and bid in seen:
                    skipped += 1
                    self.stdout.write(f"skip (same bot as {seen[bid]}): {tenant.schema_name}")
                    continue
                base = services.tenant_base_url()
                if not base:
                    # Без домена вебхуку некуда указывать — пропуск не молчаливый:
                    # владелец должен видеть, какой бот не перерегистрирован.
                    skipped += 1
                    self.stdout.write(f"skip (no domain): {tenant.schema_name}")
                    continue
                if bid:
                    seen[bid] = tenant.schema_name
                bots += 1
                if not apply:
                    self.stdout.write(f"would resync: {tenant.schema_name}")
                    continue
                url = base + reverse(
                    "telegram-webhook", args=[bot.webhook_secret], urlconf="config.urls_tenant"
                )
                try:
                    services.set_webhook(bot.token, url, services.header_secret(bot.webhook_secret))
                except Exception as exc:  # noqa: BLE001 — токен в URL, печатаем только тип
                    errors += 1
                    self.stdout.write(f"error: {tenant.schema_name}: {type(exc).__name__}")
        # SEC-A4: боты порталов (public) — тот же производный секрет заголовка.
        from apps.aggregator.models import PortalBot

        for pbot in (
            PortalBot.objects.filter(is_active=True).exclude(token="").select_related("portal")
        ):
            bid = ownership.bot_id(pbot.token)
            if bid and bid in seen:
                skipped += 1
                self.stdout.write(f"skip (same bot as {seen[bid]}): portal {pbot.portal.host}")
                continue
            if bid:
                seen[bid] = f"portal {pbot.portal.host}"
            bots += 1
            if not apply:
                self.stdout.write(f"would resync portal bot: {pbot.portal.host}")
                continue
            url = f"https://{pbot.portal.host}/tg/{pbot.webhook_secret}/"
            try:
                services.set_webhook(pbot.token, url, services.header_secret(pbot.webhook_secret))
            except Exception as exc:  # noqa: BLE001 — токен в URL, печатаем только тип
                errors += 1
                self.stdout.write(f"error: portal {pbot.portal.host}: {type(exc).__name__}")
        mode = "applied" if apply else "dry-run"
        self.stdout.write(f"{mode}: bots={bots} errors={errors} skipped={skipped}")
