"""Уведомления (TENANT-схема): единая модель с гарантией без дублей.

Гарантия — unique `dedupe_key` в БД + проверка статуса перед отправкой (см.
docs/references/patterns/notification-dedupe.md). Redis-lock (idempotent_task) —
лишь оптимизация. Статус двигается только через NotificationSM. Канал-агностична:
адаптер на каждый `channel` (email — базовый; whatsapp — опц., S6.5).
"""

from django.db import models

from apps.core.models import TimestampedModel


class Notification(TimestampedModel):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    CHANNELS = [(EMAIL, "Email"), (WHATSAPP, "WhatsApp"), (TELEGRAM, "Telegram")]

    # publish:{...} / reservation:{res}:{status} / waitlist:{entry}:available
    dedupe_key = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=50)
    channel = models.CharField(max_length=20, choices=CHANNELS, default=EMAIL)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, default="pending", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="notif_status_sched_idx"),
        ]

    def __str__(self):
        return f"{self.type}→{self.recipient}: {self.status}"
