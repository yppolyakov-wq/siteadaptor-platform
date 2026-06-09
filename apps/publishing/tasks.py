"""Celery: публикация/снятие акций в каналы (per-tenant, идемпотентно).

Работают в schema_context арендатора, вызывают адаптер канала и двигают
PublicationSM. Ошибка адаптера → failed + last_error (повторная активация вернёт
в queued). Чистая логика — в _do_publish/_do_remove (их и тестируем напрямую).
"""

from django_tenants.utils import schema_context

from apps.core.jobs import idempotent_task

from . import adapters
from .state_machine import FAILED, PUBLISHED, QUEUED, REMOVED, PublicationSM


def _do_publish(publication_id) -> str:
    from .models import Publication

    pub = Publication.objects.filter(id=publication_id).select_related("channel").first()
    if pub is None or pub.status != QUEUED:
        return "skip"  # идемпотентно: публикуем только из queued
    sm = PublicationSM()
    try:
        ref = adapters.publish(pub)
    except Exception as exc:  # noqa: BLE001 — ошибку адаптера фиксируем в last_error
        pub.last_error = str(exc)[:500]
        pub.save(update_fields=["last_error", "updated_at"])
        sm.apply(pub, FAILED)
        return "failed"
    pub.external_ref = ref
    pub.last_error = ""
    pub.save(update_fields=["external_ref", "last_error", "updated_at"])
    sm.apply(pub, PUBLISHED)
    return "published"


def _do_remove(publication_id) -> str:
    from .models import Publication

    pub = Publication.objects.filter(id=publication_id).select_related("channel").first()
    if pub is None or pub.status == REMOVED:
        return "skip"
    try:
        adapters.remove(pub)
    except Exception as exc:  # noqa: BLE001
        pub.last_error = str(exc)[:500]
        pub.save(update_fields=["last_error", "updated_at"])
        return "error"
    PublicationSM().apply(pub, REMOVED)
    return "removed"


@idempotent_task()
def publish_to_channel(*, tenant_schema, publication_id):
    with schema_context(tenant_schema):
        return {"result": _do_publish(publication_id)}


@idempotent_task()
def remove_from_channel(*, tenant_schema, publication_id):
    with schema_context(tenant_schema):
        return {"result": _do_remove(publication_id)}
