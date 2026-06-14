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
from apps.secrets.fields import EncryptedTextField


class TelegramBot(TimestampedModel):
    token = EncryptedTextField(blank=True, default="")  # из @BotFather, шифруется at-rest
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


class TelegramLink(TimestampedModel):
    """Привязка клиента ↔ Telegram chat_id (TG3) для доставки уведомлений.

    Deep-link `t.me/<bot>?start=<link_token>` ведёт в бота; на /start <token> бот
    находит запись по токену и проставляет chat_id. link_token — короткий
    url-safe (без ':' и в пределах 64 символов лимита Telegram start-payload).
    chat_id пустой = клиент ещё не нажал /start (привязка «в ожидании»).
    """

    customer = models.OneToOneField(
        "promotions.Customer", on_delete=models.CASCADE, related_name="telegram_link"
    )
    link_token = models.CharField(max_length=48, unique=True)
    chat_id = models.CharField(max_length=40, blank=True, db_index=True)

    def __str__(self):
        return f"{self.customer_id} ↔ {self.chat_id or 'pending'}"

    @property
    def is_linked(self) -> bool:
        return bool(self.chat_id)
