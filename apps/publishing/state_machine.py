"""Машина состояний публикации. База — apps.core.fsm.

    queued ──► published ──► removed
      │  │         │
      │  └► failed │
      │     │      │
      │     └► queued (retry)
      └────────────► removed
    removed ──► queued (повторная активация акции)

Смена статуса — только через apply(). Внешние эффекты (адаптер канала) — в задачах
apps.publishing.tasks; здесь только переходы.
"""

from apps.core.fsm import StateMachine, Transition

QUEUED = "queued"
PUBLISHED = "published"
REMOVED = "removed"
FAILED = "failed"


class PublicationSM(StateMachine):
    transitions = [
        Transition(QUEUED, PUBLISHED, "publication.published"),
        Transition(QUEUED, FAILED, "publication.failed"),
        Transition(QUEUED, REMOVED, "publication.removed"),
        Transition(FAILED, QUEUED, "publication.requeued"),
        Transition(FAILED, REMOVED, "publication.removed"),
        Transition(PUBLISHED, REMOVED, "publication.removed"),
        Transition(REMOVED, QUEUED, "publication.requeued"),
        Transition(PUBLISHED, QUEUED, "publication.requeued"),
    ]
