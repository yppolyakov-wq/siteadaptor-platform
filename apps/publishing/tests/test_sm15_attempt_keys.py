"""SM15: повторная публикация/снятие в течение часа больше не теряются.

Ключ дедупа был один на всю жизнь строки (`pub:{id}:publish`, замок 1 ч), а ошибку
адаптера задача глотала — замок не снимался. Повтор «Jetzt überall veröffentlichen»
после починки канала молча отбрасывался, публикация навсегда висела в QUEUED.
"""

import pytest

from apps.promotions.models import Promotion
from apps.publishing import adapters, services, tasks
from apps.publishing.models import Channel, Publication
from apps.publishing.state_machine import FAILED, PUBLISHED, QUEUED

pytestmark = pytest.mark.django_db


def _boom(publication):
    raise RuntimeError("token expired")


def test_republish_after_failure_gets_a_fresh_key(monkeypatch, django_capture_on_commit_callbacks):
    calls = []
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: calls.append(kw))
    Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    with django_capture_on_commit_callbacks(execute=True):
        services.republish_promotion(promo)
    pub = Publication.objects.get(promotion=promo)
    monkeypatch.setattr(adapters, "publish", _boom)
    assert tasks._do_publish(str(pub.id)) == "failed"
    monkeypatch.undo()
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: calls.append(kw))

    with django_capture_on_commit_callbacks(execute=True):
        services.republish_promotion(promo)

    assert len(calls) == 2
    assert calls[0]["dedupe_key"] != calls[1]["dedupe_key"]
    assert all(c["dedupe_key"].startswith(f"pub:{pub.id}:publish:") for c in calls)
    pub.refresh_from_db()
    assert pub.status == QUEUED  # FAILED вернулся в очередь
    assert tasks._do_publish(str(pub.id)) == "published"


def test_second_attempt_on_published_row_is_a_noop():
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(promotion=promo, channel=ch, dedupe_key="x")
    assert tasks._do_publish(str(pub.id)) == "published"
    # повторная доставка той же задачи: строка уже не QUEUED — второй публикации нет
    assert tasks._do_publish(str(pub.id)) == "skip"


def test_remove_is_skipped_when_promotion_was_resumed():
    """Пауза → возобновление раньше, чем отработало снятие: публикацию не трогаем."""
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(promotion=promo, channel=ch, status=PUBLISHED, dedupe_key="x")
    assert tasks._do_remove(str(pub.id)) == "skip"
    pub.refresh_from_db()
    assert pub.status == PUBLISHED


def test_failed_adapter_keeps_row_failed_for_retry(monkeypatch):
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(promotion=promo, channel=ch, dedupe_key="x")
    monkeypatch.setattr(adapters, "publish", _boom)
    assert tasks._do_publish(str(pub.id)) == "failed"
    pub.refresh_from_db()
    assert pub.status == FAILED and "token expired" in pub.last_error
