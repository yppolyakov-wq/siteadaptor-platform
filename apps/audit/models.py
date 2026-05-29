"""Журнал действий (audit). SHARED-схема — единый журнал по всем арендаторам.

Спецификация: docs/references/patterns/audit-log.md.
Audit-данные нельзя backfill'ить, поэтому модуль подключён с первого дня.
"""

from django.db import models


class AuditEvent(models.Model):
    ACTOR_TYPES = [
        ("user", "User"),
        ("system", "System"),
        ("cron", "Cron"),
        ("integration", "Integration"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # какой арендатор (schema_name); пусто = действие на уровне платформы
    tenant_schema = models.CharField(max_length=100, db_index=True, blank=True)

    actor_type = models.CharField(max_length=20, choices=ACTOR_TYPES, default="system")
    actor_id = models.CharField(max_length=100, blank=True)
    actor_display = models.CharField(max_length=200, blank=True)

    action = models.CharField(max_length=100, db_index=True)  # 'tenant.created'
    resource_type = models.CharField(max_length=50, db_index=True)  # 'tenant'
    resource_id = models.CharField(max_length=100, db_index=True)

    changes = models.JSONField(default=dict, blank=True)  # {"status": ["draft","active"]}
    diff_summary = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)  # ip, request_id, ...

    class Meta:
        indexes = [
            models.Index(fields=["resource_type", "resource_id"], name="audit_resource_idx"),
            models.Index(fields=["tenant_schema", "-created_at"], name="audit_tenant_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.resource_type}:{self.resource_id}"
