"""CO-2d: счёт по «Kauf auf Rechnung» у брони номера и записи — в момент подтверждения
(решение владельца В-1). Автоподтверждённая бронь = сразу; запрос — когда отель
подтвердит (встроенный «confirmed» или свой статус «держит номер»); отклонённый запрос
выставленного счёта не оставляет (иначе сторно, GoBD).

После коммита (on_commit): счёт и письмо не должны пережить откат брони. Сбой счёта не
отменяет бронь — владелец выставит его кнопкой на карточке.
"""

import logging

logger = logging.getLogger(__name__)


def _real_tenant(schema: str):
    """Настоящий Tenant по схеме: в Celery/beat/сидере `connection.tenant` — FakeTenant
    без настроек, и счёт Kleinunternehmer'а ушёл бы с НДС (ревью CO-2)."""
    from django_tenants.utils import get_tenant_model, schema_context

    with schema_context("public"):
        return get_tenant_model().objects.filter(schema_name=schema).first()


def on_confirmed(kind: str, deal) -> None:
    if getattr(deal, "payment_method", "") != "invoice":
        return
    from django.db import connection, transaction

    schema = connection.schema_name
    model, pk = type(deal), deal.pk

    def _run():
        from django_tenants.utils import schema_context

        from apps.core import status_registry
        from apps.core.status_registry import cancelled_statuses_for

        from .services import issue_invoice_for_deal

        try:
            tenant = _real_tenant(schema)
            if tenant is None and schema != "public":
                logger.error("finance: auto invoice — tenant %s not found", schema)
                return
            with schema_context(schema), transaction.atomic():
                # Блокировка сделки: два быстрых подтверждения не выпустят два счёта.
                obj = model.objects.select_for_update().filter(pk=pk).first()
                if obj is None or obj.status in cancelled_statuses_for(kind, tenant):
                    return
                desc = status_registry.resolve(kind, obj.status, tenant)
                if desc is None or desc.role not in ("active", "done"):
                    return  # ещё не подтверждена (pending / свой «intake»)
                issue_invoice_for_deal(kind, obj, tenant)
        except Exception:  # noqa: BLE001
            logger.warning("finance: auto invoice for %s failed", kind, exc_info=True)

    transaction.on_commit(_run)
