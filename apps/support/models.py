"""Платформенная техподдержка (M22c, SHARED): тенант-владелец ↔ SiteAdaptor.

SHARED-scope (как billing/aggregator): тред привязан к Tenant, платформа видит
все тикеты в одном месте (Django/unfold-админка на public), владелец — в кабинете
`/dashboard/help/`. Отдельно от inbox (TENANT, клиент↔бизнес). v1 — async.
"""

from django.db import models


class SupportThread(models.Model):
    STATUS_OPEN = "open"
    STATUS_PENDING = "pending"
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

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="support_threads"
    )
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default=PRIORITY_NORMAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    unread_for_platform = models.BooleanField(default=True)  # новый тред — платформе
    unread_for_owner = models.BooleanField(default=False)  # платформа ответила

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [models.Index(fields=["status", "last_message_at"], name="support_status_idx")]

    def __str__(self):
        return f"{self.subject} ({self.tenant_id})"


class SupportMessage(models.Model):
    AUTHOR_OWNER = "owner"  # тенант-владелец
    AUTHOR_PLATFORM = "platform"  # SiteAdaptor-поддержка
    AUTHOR_SYSTEM = "system"
    AUTHOR_ROLES = [
        (AUTHOR_OWNER, "Owner"),
        (AUTHOR_PLATFORM, "Platform"),
        (AUTHOR_SYSTEM, "System"),
    ]

    thread = models.ForeignKey(SupportThread, on_delete=models.CASCADE, related_name="messages")
    author_role = models.CharField(max_length=10, choices=AUTHOR_ROLES)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author_role}: {self.body[:40]}"
