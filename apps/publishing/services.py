"""Связь PromotionSM ↔ публикации.

На активации акции ставим публикации во все включённые каналы (queued + задача),
на завершении/паузе/архиве — снимаем. Всё через очередь с dedupe_key. Вызывается
из PromotionSM.on_transition (в schema_context арендатора).
"""

from django.db import connection

from .models import Channel, Publication
from .state_machine import FAILED, QUEUED, REMOVED, PublicationSM
from .tasks import publish_to_channel, remove_from_channel


def on_promotion_transition(promotion, dst: str) -> None:
    if dst == "active":
        _publish_all(promotion)
    elif dst in ("ended", "paused", "archived"):
        _remove_all(promotion)


def _publish_all(promotion) -> None:
    schema = connection.schema_name
    sm = PublicationSM()
    for channel in Channel.objects.filter(is_enabled=True):
        pub, _ = Publication.objects.get_or_create(
            promotion=promotion,
            channel=channel,
            defaults={
                "dedupe_key": f"publish:{promotion.id}:{channel.id}",
                "status": QUEUED,
            },
        )
        # повторная активация: вернуть removed/failed в очередь
        if pub.status in (REMOVED, FAILED):
            sm.apply(pub, QUEUED)
        publish_to_channel.delay(
            dedupe_key=f"pub:{pub.id}:publish",
            tenant_schema=schema,
            publication_id=str(pub.id),
        )


def publish_post(post) -> int:
    """CM-2: разослать SocialPost по включённым каналам — та же механика, что у
    акции (get_or_create + requeue removed/failed + очередь с dedupe). Статус
    поста НЕ трогаем (вызывающий переводит через SocialPostSM). Возвращает
    число каналов."""
    schema = connection.schema_name
    sm = PublicationSM()
    count = 0
    for channel in Channel.objects.filter(is_enabled=True):
        pub, _ = Publication.objects.get_or_create(
            post=post,
            channel=channel,
            defaults={
                "dedupe_key": f"publish:post:{post.id}:{channel.id}",
                "status": QUEUED,
            },
        )
        if pub.status in (REMOVED, FAILED):
            sm.apply(pub, QUEUED)
        publish_to_channel.delay(
            dedupe_key=f"pub:{pub.id}:publish",
            tenant_schema=schema,
            publication_id=str(pub.id),
        )
        count += 1
    return count


def draft_from_source(*, kind: str, source_id, text: str, link_url: str = "", image=None):
    """CM-3: авто-черновик поста из сущности платформы (blog/event/…) — один на
    источник (source_kind+source_id), повтор — no-op. Черновик не шлётся сам:
    владелец решает на «Beiträge» (1 клик «Jetzt senden» или планирование)."""
    from .models import SocialPost

    if SocialPost.objects.filter(source_kind=kind, source_id=str(source_id)).exists():
        return None
    return SocialPost.objects.create(
        text=text,
        link_url=link_url,
        image=image if isinstance(image, dict) else {},
        source_kind=kind,
        source_id=str(source_id),
    )


def blog_share_draft(blog_post) -> None:
    """CM-3: при публикации записи блога — авто-черновик поста в каналы
    (заголовок + анонс + абсолютная ссылка + обложка). Идемпотентно по slug."""
    from .adapters import _absolute_media_url

    text = blog_post.title
    if blog_post.excerpt:
        text = f"{text}\n\n{blog_post.excerpt}"
    draft_from_source(
        kind="blog",
        source_id=blog_post.slug,
        text=text,
        link_url=_absolute_media_url(f"/blog/{blog_post.slug}/"),
        image=blog_post.cover,
    )


def event_share_draft(event) -> None:
    """CM-3: при публикации события — авто-черновик поста в каналы
    (заголовок + дата + абсолютная ссылка + фото). Идемпотентно по pk."""
    from django.utils import timezone

    from .adapters import _absolute_media_url

    text = event.title_text
    if event.starts_at:
        when = timezone.localtime(event.starts_at).strftime("%d.%m.%Y %H:%M")
        text = f"{text}\n\n📅 {when}"
    draft_from_source(
        kind="event",
        source_id=event.pk,
        text=text,
        link_url=_absolute_media_url(f"/veranstaltung/{event.pk}/"),
        image={"url": event.image_url} if event.image_url else {},
    )


def _remove_all(promotion) -> None:
    schema = connection.schema_name
    for pub in Publication.objects.filter(promotion=promotion).exclude(status=REMOVED):
        remove_from_channel.delay(
            dedupe_key=f"pub:{pub.id}:remove",
            tenant_schema=schema,
            publication_id=str(pub.id),
        )
