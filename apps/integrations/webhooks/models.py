"""Исходящие вебхуки (scaffold). SHARED-схема.

Phase 1: только модели + admin. Логика доставки (HMAC-подпись, ретраи с
backoff, DLQ) появится в Phase 2 — см. docs/references/patterns/webhook-hmac-signing.md.
"""

import secrets

from django.db import models


def _gen_secret() -> str:
    return secrets.token_hex(32)


class OutgoingWebhook(models.Model):
    """Подписка арендатора на события платформы."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    tenant_schema = models.CharField(max_length=100, db_index=True)
    url = models.URLField()
    # секрет для HMAC; генерится при создании, показывается владельцу один раз
    secret = models.CharField(max_length=64, default=_gen_secret)
    event_types = models.JSONField(default=list)  # ['promotion.published', ...]
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant_schema", "is_active"], name="webhook_tenant_active_idx")
        ]

    def __str__(self):
        return f"{self.tenant_schema} → {self.url}"


class WebhookDelivery(models.Model):
    """Одна попытка доставки события. event_id — idempotency-ключ для получателя."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    webhook = models.ForeignKey(
        OutgoingWebhook, on_delete=models.CASCADE, related_name="deliveries"
    )
    event_type = models.CharField(max_length=100, db_index=True)
    event_id = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    attempts = models.IntegerField(default=0)
    response_code = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="webhook_delivery_status_idx")
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} [{self.status}]"
