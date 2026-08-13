"""Ретеншн досье (MT-2): просроченные документы удаляются вместе с blob.

Паттерн — как у Meldeschein (`stays.tasks.purge_due_registrations`): чистая
функция на схему + beat-обёртка, обходящая все схемы.
"""

from celery import shared_task
from django_tenants.utils import get_tenant_model, schema_context

from .services import purge_expired


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


@shared_task
def purge_expired_documents():
    """Beat (раз в сутки): удалить документы с истёкшим сроком по всем схемам."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += purge_expired()
    return total
