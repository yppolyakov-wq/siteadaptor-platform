"""Beat-задачи журнала аудита."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.jobs import idempotent_task

_BATCH = 2000


@idempotent_task()
def purge_team_audit():
    """KA-12 E6.7c (Р-c6): события команды ``team.*`` старше срока (3 года) — пачками.

    Прочий журнал не трогаем: у него свои сроки (GoBD, выгрузки)."""
    from .models import AuditEvent

    cutoff = timezone.now() - timedelta(days=settings.TEAM_AUDIT_RETENTION_DAYS)
    total = 0
    while True:
        ids = list(
            AuditEvent.objects.filter(action__startswith="team.", created_at__lt=cutoff)
            .order_by("pk")
            .values_list("pk", flat=True)[:_BATCH]
        )
        if not ids:
            return total
        total += AuditEvent.objects.filter(pk__in=ids).delete()[0]
