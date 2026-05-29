# Pattern: Audit Log (журнал действий с первого дня)

Статус: Phase 1, Sprint 1.
Ссылается из: `phase1-plan-additions.md` §1.1.

## Зачем с первого дня

Audit-данные **нельзя backfill'ить** — если событие не записано в момент, оно
потеряно навсегда. Поэтому модуль ставится в Sprint 1, а сервисы подключают
свои события по мере появления. Хранилище — **SHARED-схема**: единый журнал по
всем арендаторам, переживает удаление tenant-схемы, доступен суперадмину.

## Модель

```python
# apps/core/audit/models.py — SHARED schema
import uuid
from django.db import models
from apps.core.models import TimestampedModel


class AuditEvent(TimestampedModel):
    # какой арендатор (schema_name), пусто = действие на уровне платформы
    tenant_schema = models.CharField(max_length=100, db_index=True, blank=True)

    actor_type = models.CharField(max_length=20, choices=[
        ("user", "User"), ("system", "System"),
        ("cron", "Cron"), ("integration", "Integration"),
    ])
    actor_id = models.UUIDField(null=True, blank=True)
    actor_display = models.CharField(max_length=200, blank=True)

    action = models.CharField(max_length=100, db_index=True)        # 'promotion.activated'
    resource_type = models.CharField(max_length=50, db_index=True)  # 'promotion'
    resource_id = models.CharField(max_length=100, db_index=True)

    changes = models.JSONField(default=dict, blank=True)   # {"status": ["draft","active"]}
    diff_summary = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)   # ip, request_id, ...

    class Meta:
        indexes = [
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["tenant_schema", "-created_at"]),
        ]
```

## Хелпер: единая точка записи

```python
# apps/core/audit/__init__.py
from django.db import connection
from .models import AuditEvent


def audit_event(*, action, resource_type, resource_id,
                actor=None, changes=None, context=None, diff_summary=""):
    """Пишет событие в SHARED-схему. Никогда не падает в основной поток —
    audit не должен ронять бизнес-операцию."""
    try:
        actor_type, actor_id, actor_display = _resolve_actor(actor)
        AuditEvent.objects.create(
            tenant_schema=getattr(connection, "schema_name", "") or "",
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
        import logging
        logging.getLogger("audit").exception("audit_event failed: %s", action)


def _resolve_actor(actor):
    if actor is None:
        return "system", None, ""
    if getattr(actor, "is_authenticated", False):
        return "user", getattr(actor, "uuid", None), actor.get_username()
    return "system", None, str(actor)
```

> ⚠️ `connection.schema_name` берётся из текущего соединения django-tenants.
> В Celery-задаче, работающей в tenant-контексте, schema выставлена; в чисто
> платформенной задаче будет `public` → нормализуем в `""`.

## Что подключить в Sprint 1

1. **Tenant create/update** — через Django signals:

```python
# apps/tenants/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.core.audit import audit_event
from .models import Tenant

@receiver(post_save, sender=Tenant)
def audit_tenant(sender, instance, created, **kwargs):
    audit_event(
        action="tenant.created" if created else "tenant.updated",
        resource_type="tenant",
        resource_id=instance.pk,
        context={"schema": instance.schema_name},
    )
```

2. **login / logout / password_change** — через allauth signals
   (`user_logged_in`, `user_logged_out`, `password_changed`).

Дальше каждая FSM (см. `state-machine.md`) пишет событие на каждый переход.

## Принципы

- Пишем **факт + diff**, не «снимок всей записи» (place changes как `[old,new]`).
- Audit **не блокирует** бизнес-операцию: ошибка записи логируется, не пробрасывается.
- Для критичных операций (переход статуса) вызов внутри той же транзакции —
  чтобы при rollback бизнес-операции откатился и audit (консистентность).
  Для некритичных (login) — fire-and-forget.
- Ретеншн: beat-задача чистит события старше N месяцев (политика — Phase 2).

## Чек-лист

- [ ] `AuditEvent` в SHARED-схеме с индексами.
- [ ] `audit_event()` — единственная точка записи, не роняет запрос.
- [ ] Подключены tenant create/update + allauth login/logout/password.
- [ ] `changes` хранит `[old, new]`, не полный снимок.
