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


def _remove_all(promotion) -> None:
    schema = connection.schema_name
    for pub in Publication.objects.filter(promotion=promotion).exclude(status=REMOVED):
        remove_from_channel.delay(
            dedupe_key=f"pub:{pub.id}:remove",
            tenant_schema=schema,
            publication_id=str(pub.id),
        )
