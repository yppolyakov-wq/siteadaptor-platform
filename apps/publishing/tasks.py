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


# --- CM-2: отложенный контент (посты календаря + запланированный блог) ----------


def send_due_posts(now) -> int:
    """Разослать созревшие посты: scheduled & scheduled_at<=now → Publications
    по включённым каналам + status=sent. Чистая логика — тестируется напрямую."""
    from .models import SocialPost
    from .services import publish_post
    from .state_machine import POST_SENT, SocialPostSM

    sm = SocialPostSM()
    count = 0
    for post in SocialPost.objects.filter(
        status=SocialPost.SCHEDULED, scheduled_at__isnull=False, scheduled_at__lte=now
    ):
        publish_post(post)
        sm.apply(post, POST_SENT)
        count += 1
    return count


def publish_due_blog(now) -> int:
    """CM-2: отложенная публикация блога — черновик с датой в published_at
    включается при её наступлении (семантика поля расширена: у черновика это
    «когда опубликовать», у опубликованного — как было). CM-3: на каждую
    включённую запись — авто-черновик поста в каналы (идемпотентно)."""
    from apps.events.models import BlogPost

    from .services import blog_share_draft

    due = list(
        BlogPost.objects.filter(
            is_published=False, published_at__isnull=False, published_at__lte=now
        )
    )
    if not due:
        return 0
    BlogPost.objects.filter(pk__in=[p.pk for p in due]).update(is_published=True)
    for post in due:
        blog_share_draft(post)
    return len(due)


@idempotent_task()
def send_due_content():
    """Beat (300с): по всем схемам разослать созревшие посты + включить
    запланированный блог; при изменениях — сброс кэша витрины схемы."""
    from django.utils import timezone

    from apps.core.pagecache import bump_storefront_cache

    now = timezone.now()
    totals = {"posts": 0, "blog": 0}
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            posts = send_due_posts(now)
            blog = publish_due_blog(now)
        if blog:
            bump_storefront_cache(schema)
        totals["posts"] += posts
        totals["blog"] += blog
    return totals


def _iter_tenant_schemas():
    from apps.tenants.models import Tenant

    return list(Tenant.objects.exclude(schema_name="public").values_list("schema_name", flat=True))
