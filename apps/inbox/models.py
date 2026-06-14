"""Inbox — чат и тикеты клиент↔бизнес (M22a, TENANT).

Единый тред (Conversation) + сообщения (Message). «Тикет» = тот же тред со
статусом (open→pending→resolved→closed), приоритетом и назначением на сотрудника.
v1 — асинхронно: кабинет-inbox здесь, витрина-виджет + доставка через
`notifications` — M22b. Платформенная техподдержка (tenant↔SiteAdaptor) — M22c
(SHARED). Швы realtime/AI/внешний-тред — пустые поля (master-plan §7).
"""

import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Conversation(TimestampedModel):
    STATUS_OPEN = "open"
    STATUS_PENDING = "pending"  # ждём ответа клиента
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUSES = [
        (STATUS_OPEN, "Open"),
        (STATUS_PENDING, "Pending"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CLOSED, "Closed"),
    ]
    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITIES = [(PRIORITY_LOW, "Low"), (PRIORITY_NORMAL, "Normal"), (PRIORITY_HIGH, "High")]
    CHANNEL_WEB = "web"
    CHANNEL_EMAIL = "email"
    CHANNEL_WHATSAPP = "whatsapp"

    # Сторона-клиент (reuse по email, как везде). null = аноним до указания email.
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="conversations"
    )
    subject = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default=PRIORITY_NORMAL)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_conversations",
    )
    channel = models.CharField(max_length=12, default=CHANNEL_WEB)
    # Мягкая привязка к объекту (товар/акция/заказ/бронь) — строкой, без жёстких FK
    # (тред переживает удаление объекта; контекст для владельца).
    ref_kind = models.CharField(max_length=20, blank=True)
    ref_id = models.CharField(max_length=64, blank=True)
    ref_label = models.CharField(max_length=200, blank=True)  # человекочитаемый снимок
    # Клиент видит свой тред по ссылке без аккаунта (как код брони).
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    unread_for_staff = models.BooleanField(default=False)  # бейдж непрочитанного в кабинете

    # Швы под будущее (master-plan §7), пассивные:
    ai_handled = models.BooleanField(default=False)  # обработано AI-триажем (Stage 3)
    external_ref = models.CharField(max_length=200, blank=True)  # id email/WA-треда

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "last_message_at"], name="conv_status_last_idx"),
        ]

    def __str__(self):
        return self.subject or f"Conversation {self.pk}"


class Message(TimestampedModel):
    AUTHOR_STAFF = "staff"
    AUTHOR_CUSTOMER = "customer"
    AUTHOR_SYSTEM = "system"
    AUTHOR_ROLES = [
        (AUTHOR_STAFF, "Staff"),
        (AUTHOR_CUSTOMER, "Customer"),
        (AUTHOR_SYSTEM, "System"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    author_role = models.CharField(max_length=10, choices=AUTHOR_ROLES)
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    body = models.TextField()
    channel = models.CharField(max_length=12, default=Conversation.CHANNEL_WEB)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author_role}: {self.body[:40]}"
