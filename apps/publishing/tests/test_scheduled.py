"""CM-2: контент-календарь — SocialPost поверх Publication-доставки +
отложенная публикация блога (helpers beat send_due_content)."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.publishing import adapters, tasks
from apps.publishing.models import Channel, Publication, SocialPost
from apps.publishing.state_machine import PUBLISHED, QUEUED

pytestmark = pytest.mark.django_db


def _post(**kw):
    kw.setdefault("text", "Herbst-Aktion!\nAlle Farben -10 %.")
    return SocialPost.objects.create(**kw)


def test_publish_post_creates_publications_for_enabled_channels(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: calls.append(kw))
    ch = Channel.objects.create(type="log", is_enabled=True)
    Channel.objects.create(type="telegram", is_enabled=False)
    post = _post()

    from apps.publishing.services import publish_post

    assert publish_post(post) == 1  # только включённый канал
    pub = Publication.objects.get(post=post)
    assert pub.channel == ch and pub.status == QUEUED
    assert pub.dedupe_key == f"publish:post:{post.id}:{ch.id}"
    assert calls and calls[0]["publication_id"] == str(pub.id)


def test_send_due_posts_sends_only_due(monkeypatch):
    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: None)
    Channel.objects.create(type="log", is_enabled=True)
    now = timezone.now()
    due = _post(status=SocialPost.SCHEDULED, scheduled_at=now - timedelta(minutes=1))
    future = _post(status=SocialPost.SCHEDULED, scheduled_at=now + timedelta(hours=2))
    draft = _post(status=SocialPost.DRAFT)

    assert tasks.send_due_posts(now) == 1
    due.refresh_from_db()
    future.refresh_from_db()
    draft.refresh_from_db()
    assert due.status == SocialPost.SENT
    assert future.status == SocialPost.SCHEDULED and draft.status == SocialPost.DRAFT
    assert Publication.objects.filter(post=due).exists()
    assert not Publication.objects.filter(post=future).exists()


def test_publish_due_blog_flips_flag():
    from apps.events.models import BlogPost

    now = timezone.now()
    due = BlogPost.objects.create(
        title="Geplant", slug="geplant", is_published=False, published_at=now - timedelta(hours=1)
    )
    future = BlogPost.objects.create(
        title="Später", slug="spaeter", is_published=False, published_at=now + timedelta(days=1)
    )
    plain_draft = BlogPost.objects.create(title="Entwurf", slug="entwurf", is_published=False)

    assert tasks.publish_due_blog(now) == 1
    due.refresh_from_db()
    future.refresh_from_db()
    plain_draft.refresh_from_db()
    assert due.is_published and not future.is_published and not plain_draft.is_published


def test_publication_source_xor_constraint():
    """Ровно один источник: и оба, и ни одного — запрещены БД."""
    from apps.promotions.models import Promotion

    ch = Channel.objects.create(type="log", is_enabled=True)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    post = _post()
    with pytest.raises(IntegrityError), transaction.atomic():
        Publication.objects.create(promotion=promo, post=post, channel=ch, dedupe_key="x1")
    with pytest.raises(IntegrityError), transaction.atomic():
        Publication.objects.create(channel=ch, dedupe_key="x2")


def test_content_for_post_branch():
    ch = Channel.objects.create(type="log", is_enabled=True)
    post = _post(
        text="Erste Zeile\nZweiter Absatz.",
        link_url="https://shop.example/aktion/",
        image={"url": "https://cdn.example/x.jpg"},
    )
    pub = Publication.objects.create(post=post, channel=ch, dedupe_key="c1")
    content = adapters.content_for(pub)
    assert content.title == "Erste Zeile"
    assert content.caption == "Erste Zeile\nZweiter Absatz."
    assert content.link_url == "https://shop.example/aktion/"
    assert content.image_url == "https://cdn.example/x.jpg"  # абсолютный — как есть


def test_publish_task_publishes_post_publication():
    """End-to-end: _do_publish с post-источником на log-канале → published."""
    ch = Channel.objects.create(type="log", is_enabled=True)
    post = _post()
    pub = Publication.objects.create(post=post, channel=ch, dedupe_key="e2e")
    assert tasks._do_publish(str(pub.id)) == "published"
    pub.refresh_from_db()
    assert pub.status == PUBLISHED


def test_posts_view_create_schedule_and_send_now(monkeypatch):
    """Кабинет «Beiträge»: создание с датой → scheduled; send_now → sent+Publications."""
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.publishing import views

    monkeypatch.setattr(tasks.publish_to_channel, "delay", lambda **kw: None)
    Channel.objects.create(type="log", is_enabled=True)

    def _req(data=None):
        request = RequestFactory().post("/dashboard/posts/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        owner = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
        )
        return request

    resp = views.posts(
        _req({"action": "schedule", "text": "Bald!", "scheduled_at": "2030-01-01T10:00"})
    )
    assert resp.status_code == 302
    post = SocialPost.objects.get(text="Bald!")
    assert post.status == SocialPost.SCHEDULED and post.scheduled_at is not None

    resp = views.posts(_req({"action": "send_now", "pk": str(post.pk)}))
    assert resp.status_code == 302
    post.refresh_from_db()
    assert post.status == SocialPost.SENT
    assert Publication.objects.filter(post=post).exists()
