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
        # B2-8d: «Kauf auf Rechnung» выпускает итоговый счёт — предоплата не нужна;
        # иначе фирме с депозитом — Anzahlungsrechnung.
        advance_on_confirmed(kind, deal)
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


def advance_on_confirmed(kind: str, deal) -> None:
    """B2-8d: подтверждённая сделка фирмы с депозитом → Anzahlungsrechnung + письмо с PDF.

    После коммита (как счёт CO-2d): документ не переживёт откат подтверждения, а сбой
    документа не отменяет подтверждение — владелец выставит его кнопкой на карточке.
    Повтор — тот же документ и одно письмо (дедуп)."""
    from apps.core import payment_methods

    from . import advance

    if not advance.enabled() or kind not in advance.KINDS:
        return
    if getattr(deal, "customer_type", "") != payment_methods.COMPANY:
        return
    if not getattr(deal, "deposit_cents", 0) or getattr(deal, "payment_method", "") == "invoice":
        return
    from django.db import connection, transaction

    schema = connection.schema_name
    model, pk = type(deal), deal.pk

    def _run():
        from django_tenants.utils import schema_context

        from apps.core import status_registry
        from apps.core.status_registry import cancelled_statuses_for

        try:
            tenant = _real_tenant(schema)
            if tenant is None and schema != "public":
                logger.error("finance: auto advance — tenant %s not found", schema)
                return
            with schema_context(schema):
                with transaction.atomic():
                    obj = model.objects.select_for_update().filter(pk=pk).first()
                    if obj is None or obj.status in cancelled_statuses_for(kind, tenant):
                        return
                    desc = status_registry.resolve(kind, obj.status, tenant)
                    if desc is None or desc.role not in ("active", "done"):
                        return
                    try:
                        inv = advance.create_advance_invoice(kind, obj, tenant)
                    except advance.AdvanceError as exc:
                        logger.info("finance: auto advance for %s skipped: %s", kind, exc)
                        return
                if inv.sent_at is None:
                    _mail_advance(inv, obj, tenant, schema)
        except Exception:  # noqa: BLE001
            logger.warning("finance: auto advance for %s failed", kind, exc_info=True)

    transaction.on_commit(_run)


def _mail_advance(invoice, deal, tenant, schema) -> None:
    from apps.notifications.services import notify

    from .services import _invoice_mail_allowed, _send_invoice_email

    email = getattr(getattr(deal, "customer", None), "email", "") or ""
    if not email:
        return
    if not _invoice_mail_allowed(email):
        logger.warning("finance: advance %s mail throttled", invoice.pk)
        return
    _send_invoice_email(
        invoice,
        tenant,
        email,
        schema=schema,
        notify=notify,
        template="advance_invoice_issued",
        dedupe_prefix="advance-issued",
    )
