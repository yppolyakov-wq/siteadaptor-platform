"""CO-2d: счёт по «Kauf auf Rechnung» у брони номера и записи — в момент подтверждения
(решение владельца В-1). Автоподтверждённая бронь = сразу; запрос — когда отель
подтвердит: отклонённый запрос выставленного счёта не оставляет (иначе сторно, GoBD).

После коммита (on_commit): счёт и письмо не должны пережить откат брони. Сбой счёта не
отменяет бронь — владелец выставит его кнопкой на карточке.
"""

import logging

logger = logging.getLogger(__name__)


def on_confirmed(kind: str, deal) -> None:
    if getattr(deal, "payment_method", "") != "invoice":
        return
    from django.db import connection, transaction

    schema = connection.schema_name
    tenant = getattr(connection, "tenant", None)
    model, pk = type(deal), deal.pk

    def _run():
        from django_tenants.utils import schema_context

        from .services import issue_invoice_for_deal

        try:
            with schema_context(schema):
                obj = model.objects.filter(pk=pk).first()
                if obj is not None and obj.status == "confirmed":
                    issue_invoice_for_deal(kind, obj, tenant)
        except Exception:  # noqa: BLE001
            logger.warning("finance: auto invoice for %s failed", kind, exc_info=True)

    transaction.on_commit(_run)
