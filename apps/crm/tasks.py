"""KA-12 E6.4d: срок хранения заметок мастера к процедурам (решение владельца 2026-10-25).

Заметка `kind=service` удаляется через `SERVICE_NOTE_RETENTION_DAYS` (3 года) после
последней записи клиента — в ЛЮБОМ статусе: отмена и неявка тоже контакт, будущая
запись продлевает срок. Заметку моложе срока не удаляем никогда (Greatest с
`created_at`), даже если её дописали после последнего визита. Обычные заметки
(`kind=note`) живут с карточкой клиента и здесь не трогаются.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from django_tenants.utils import get_tenant_model, tenant_context

from apps.core.jobs import idempotent_task

logger = logging.getLogger(__name__)

BATCH = 1000


def purge_due_service_notes(now=None) -> int:
    """Удаляет просроченные заметки к процедурам в ТЕКУЩЕЙ схеме. Пачками по pk."""
    from apps.booking.models import Booking

    from .models import CustomerNote

    # Срок в днях (3 × 365), а не календарных годах: расхождение в 1–2 дня в пользу
    # более раннего удаления — допустимо для «spätestens 3 Jahre».
    cutoff = (now or timezone.now()) - timedelta(days=settings.SERVICE_NOTE_RETENTION_DAYS)
    last_booking = Subquery(
        Booking.objects.filter(customer_id=OuterRef("customer_id"))
        .order_by("-start")
        .values("start")[:1]
    )
    due = (
        CustomerNote.objects.filter(kind=CustomerNote.KIND_SERVICE, created_at__lt=cutoff)
        .annotate(anchor=Greatest(Coalesce(last_booking, F("created_at")), F("created_at")))
        .filter(anchor__lt=cutoff)
        .order_by()
    )
    # Keyset по pk: каждая пачка продолжает с места предыдущей, а не пересканирует
    # таблицу заново (бэклог первого запуска). Считаем удалённые ЗАМЕТКИ, а не все
    # объекты коллектора — появись у заметки зависимые модели, счёт не раздуется.
    total, last_pk = 0, 0
    while True:
        ids = list(due.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True)[:BATCH])
        if not ids:
            return total
        _, per_model = CustomerNote.objects.filter(pk__in=ids).delete()
        total += per_model.get(CustomerNote._meta.label, 0)
        last_pk = ids[-1]


@idempotent_task()
def purge_old_service_notes():
    """Beat: просроченные заметки к процедурам во всех схемах тенантов. Чистим
    независимо от включённых модулей — данные живут и при выключенном тумблере."""
    total = 0
    now = timezone.now()
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        try:
            with tenant_context(tenant):
                total += purge_due_service_notes(now)
        except Exception:  # noqa: BLE001 — сломанная схема не останавливает остальных
            logger.exception("purge_old_service_notes: tenant %s failed", tenant.schema_name)
    if total:
        logger.info("purge_old_service_notes: %s deleted", total)
    return {"deleted": total}
