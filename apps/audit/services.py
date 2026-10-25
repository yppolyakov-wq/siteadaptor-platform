"""Единая точка записи audit-событий.

audit_event() пишет в SHARED-схему и НИКОГДА не роняет основную операцию —
ошибка записи только логируется.
"""

import logging

from django.db import connection

logger = logging.getLogger("audit")


def _resolve_actor(actor):
    if actor is None:
        return "system", "", ""
    if getattr(actor, "is_authenticated", False):
        ident = getattr(actor, "pk", "") or ""
        return "user", str(ident), actor.get_username()
    return "system", "", str(actor)


def audit_event(
    *,
    action,
    resource_type,
    resource_id,
    actor=None,
    changes=None,
    context=None,
    diff_summary="",
    tenant_schema=None,
    strict=False,
):
    """Записать событие в журнал. Безопасно: не пробрасывает исключения.

    ``strict=True`` (KA-12 E6.7c, ревью B6): ошибка записи пробрасывается — для
    чувствительных действий (выдача прав), которые без записи в журнал не проводятся."""
    try:
        from .models import AuditEvent

        actor_type, actor_id, actor_display = _resolve_actor(actor)
        schema = tenant_schema
        if schema is None:
            schema = getattr(connection, "schema_name", "") or ""
        if schema == "public":
            schema = ""

        AuditEvent.objects.create(
            tenant_schema=schema,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display=actor_display,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            changes=changes or {},
            context=context or {},
            diff_summary=diff_summary,
        )
    except Exception:  # noqa: BLE001 — audit не критичен для запроса
        logger.exception("audit_event failed: %s", action)
        if strict:
            raise
