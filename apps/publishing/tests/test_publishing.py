import pytest

from apps.promotions.models import Promotion
from apps.promotions.state_machine import PromotionSM
from apps.publishing import adapters, tasks
from apps.publishing.models import Channel, Publication
from apps.publishing.state_machine import FAILED, PUBLISHED, QUEUED, REMOVED

pytestmark = pytest.mark.django_db


def _boom(publication):
    raise RuntimeError("boom")


def test_activate_creates_and_enqueues_publication(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: calls.append(kw))
    Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="draft", title={"de": "A"})

    PromotionSM().apply(promo, "active")

    pub = Publication.objects.get(promotion=promo)
    assert pub.status == QUEUED
    assert pub.dedupe_key == f"publish:{promo.id}:{pub.channel_id}"
    assert calls and calls[0]["publication_id"] == str(pub.id)


def test_disabled_channel_creates_no_publication(monkeypatch):
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: None)
    Channel.objects.create(type="log", is_enabled=False)
    promo = Promotion.objects.create(status="draft", title={"de": "A"})

    PromotionSM().apply(promo, "active")

    assert not Publication.objects.filter(promotion=promo).exists()


def test_publish_task_marks_published():
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(
        promotion=promo, channel=ch, dedupe_key=f"publish:{promo.id}:{ch.id}"
    )
    assert tasks._do_publish(str(pub.id)) == "published"
    pub.refresh_from_db()
    assert pub.status == PUBLISHED
    assert pub.external_ref


def test_remove_task_marks_removed():
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(
        promotion=promo, channel=ch, status="published", dedupe_key=f"publish:{promo.id}:{ch.id}"
    )
    assert tasks._do_remove(str(pub.id)) == "removed"
    pub.refresh_from_db()
    assert pub.status == REMOVED


def test_publish_adapter_error_marks_failed(monkeypatch):
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    pub = Publication.objects.create(
        promotion=promo, channel=ch, dedupe_key=f"publish:{promo.id}:{ch.id}"
    )
    monkeypatch.setattr(adapters, "publish", _boom)
    assert tasks._do_publish(str(pub.id)) == "failed"
    pub.refresh_from_db()
    assert pub.status == FAILED
    assert "boom" in pub.last_error


def test_ended_enqueues_removal(monkeypatch):
    removed = []
    monkeypatch.setattr(tasks.remove_from_channel, "delay", lambda **kw: removed.append(kw))
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: None)
    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    Publication.objects.create(
        promotion=promo, channel=ch, status="published", dedupe_key=f"publish:{promo.id}:{ch.id}"
    )

    PromotionSM().apply(promo, "ended")

    assert removed and removed[0]["publication_id"]
