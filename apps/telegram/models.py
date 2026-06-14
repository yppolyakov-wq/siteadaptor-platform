"""Telegram-бот бизнеса (M23/TG1, TENANT-схема).

Свой бот на тенанта (токен из @BotFather вводится в кабинете), webhook на домене
арендатора /tg/<secret>/. v1: на /start бот шлёт кнопку «Shop öffnen» (Telegram
Web App = наша витрина внутри Telegram). Одна строка на тенанта.

DSGVO: chat_id и переписка = PII (Telegram — не-EU). Учитывать в AVV; чат-история
в v1 не хранится (бот реактивный, без логирования сообщений).
"""

import secrets

from django.db import models

from apps.core.models import TimestampedModel


class TelegramBot(TimestampedModel):
    token = models.CharField(max_length=100, blank=True)  # из @BotFather
    bot_username = models.CharField(max_length=64, blank=True)
    # Секрет в URL вебхука + заголовок X-Telegram-Bot-Api-Secret-Token.
    webhook_secret = models.CharField(max_length=48, blank=True)
    is_active = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.webhook_secret:
            self.webhook_secret = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.bot_username or "TelegramBot"
