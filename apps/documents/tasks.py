"""Ретеншн досье (MT-2): просроченные документы удаляются вместе с blob.

Паттерн — как у Meldeschein (`stays.tasks.purge_due_registrations`): чистая
функция на схему + beat-обёртка, обходящая все схемы.
"""

from celery import shared_task

from apps.core import tenant_iter

from .services import purge_expired


def _iter_tenant_schemas():
    return tenant_iter.schemas()


@shared_task
def purge_expired_documents():
    """Beat (раз в сутки): удалить документы с истёкшим сроком по всем схемам."""
    total = 0
    for schema in _iter_tenant_schemas():
        with tenant_iter.isolated(schema, "purge_expired_documents"):
            total += purge_expired()
    return total
