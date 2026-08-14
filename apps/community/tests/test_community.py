"""MT-3: пространство поездки — доступ, лента, чат, модерация, Telegram-мост.

Замки, ради которых модуль и писался:
* группа поездки закрыта для посторонних (404, не 403);
* скрытая модерацией запись не уезжает ни в HTML, ни в поллинг;
* мост с Telegram не зацикливается и не двоит сообщения.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.account.auth import SESSION_KEY
from apps.community import access, services, telegram_bridge, views
from apps.community.models import FeedPost, FeedSpace
from apps.core.models import Membership
from apps.events.models import Event, Ticket
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _event(**kwargs):
    kwargs.setdefault("title", "Manali – Leh · Juni")
    kwargs.setdefault("starts_at", timezone.now() + timezone.timedelta(days=30))
    return Event.objects.create(**kwargs)


def _customer(email="rider@example.de"):
    return Customer.objects.create(name="Rider", email=email)


def _ticket(event, customer, **kwargs):
    return Ticket.objects.create(event=event, customer=customer, quantity=1, **kwargs)


def _request(method="get", data=None, customer=None, user=None, invite_space=None):
    request = getattr(RequestFactory(), method)("/reisegruppe/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Himalaya Riders", enabled_modules=["events"])
    if customer is not None:
        request.session[SESSION_KEY] = str(customer.pk)
    if invite_space is not None:
        request.session[access.invite_session_key(invite_space)] = True
    if user is not None:
        request.user = user
    return request


def _staff_user():
    suffix = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"g-{suffix}", email=f"g-{suffix}@test.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


class TestAccess:
    def test_participant_reads_space(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        response = views.space_view(_request(customer=customer), pk=space.pk)
        assert response.status_code == 200

    def test_stranger_gets_404(self):
        space = services.space_for_event(_event())
        with pytest.raises(Http404):
            views.space_view(_request(), pk=space.pk)

    def test_cancelled_ticket_loses_access(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer, status=Ticket.STATUS_CANCELLED)
        with pytest.raises(Http404):
            views.space_view(_request(customer=customer), pk=space.pk)

    def test_invited_companion_reads_without_ticket(self):
        space = services.space_for_event(_event())
        response = views.space_view(_request(invite_space=space), pk=space.pk)
        assert response.status_code == 200

    def test_join_link_grants_access(self):
        space = services.space_for_event(_event())
        request = _request()
        views.space_join(request, token=space.invite_token)
        assert request.session[access.invite_session_key(space)] is True

    def test_guide_reads_and_posts(self):
        space = services.space_for_event(_event())
        role = access.role_of(_request(user=_staff_user()), space)
        assert role == access.STAFF
        assert access.can_post(role, space)

    def test_members_cannot_post_when_disabled(self):
        event = _event()
        space = services.space_for_event(event)
        space.members_can_post = False
        space.save(update_fields=["members_can_post"])
        assert not access.can_post(access.MEMBER, space)
        assert access.can_post(access.STAFF, space)

    def test_closed_space_is_read_only_for_members(self):
        space = services.space_for_event(_event())
        space.is_open = False
        space.save(update_fields=["is_open"])
        assert not access.can_post(access.MEMBER, space)


class TestFeed:
    def test_participant_post_appears(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        views.space_post(
            _request("post", data={"body": "Wer fährt Enduro?"}, customer=customer), pk=space.pk
        )
        post = FeedPost.objects.get()
        assert post.author_customer_id == customer.pk
        assert post.by_staff is False

    def test_hidden_post_is_invisible_to_members(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        post = services.add_post(space, body="Interner Hinweis", user=_staff_user())
        services.toggle_hidden(post)
        body = views.space_view(_request(customer=customer), pk=space.pk).content.decode()
        assert "Interner Hinweis" not in body
        # гид видит скрытое (чтобы вернуть обратно)
        staff_body = views.space_view(_request(user=_staff_user()), pk=space.pk).content.decode()
        assert "Interner Hinweis" in staff_body

    def test_only_guide_can_hide(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        post = services.add_post(space, body="Foto", customer=customer)
        with pytest.raises(Http404):
            views.post_toggle(_request("post", customer=customer), pk=space.pk, post_id=post.pk)


class TestChatPoll:
    def test_poll_returns_messages_for_member(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        services.add_post(space, body="Servus", kind=FeedPost.KIND_MESSAGE, customer=customer)
        response = views.space_poll(_request(customer=customer), pk=space.pk)
        assert b"Servus" in response.content

    def test_poll_hides_moderated_message(self):
        event = _event()
        space = services.space_for_event(event)
        customer = _customer()
        _ticket(event, customer)
        post = services.add_post(space, body="Spam", kind=FeedPost.KIND_MESSAGE, customer=customer)
        services.toggle_hidden(post)
        response = views.space_poll(_request(customer=customer), pk=space.pk)
        assert b"Spam" not in response.content

    def test_poll_is_closed_for_strangers(self):
        space = services.space_for_event(_event())
        with pytest.raises(Http404):
            views.space_poll(_request(), pk=space.pk)


class TestTelegramBridge:
    def _group(self, chat_id="-100500", text="Hallo Gruppe", message_id=11):
        return {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "supergroup", "title": "Manali"},
            "from": {"id": 777, "first_name": "Vikram"},
            "text": text,
        }

    def test_link_command_binds_group(self):
        space = services.space_for_event(_event())
        reply = telegram_bridge.try_link(None, self._group(text=f"/link {space.tg_link_code}"))
        space.refresh_from_db()
        assert space.tg_chat_id == "-100500"
        assert "✅" in reply

    def test_link_with_bot_suffix_works(self):
        """В группе команда приходит как «/link@botname <код>»."""
        space = services.space_for_event(_event())
        telegram_bridge.try_link(None, self._group(text=f"/link@moto_bot {space.tg_link_code}"))
        space.refresh_from_db()
        assert space.tg_chat_id == "-100500"

    def test_wrong_code_does_not_bind(self):
        space = services.space_for_event(_event())
        reply = telegram_bridge.try_link(None, self._group(text="/link falsch"))
        space.refresh_from_db()
        assert space.tg_chat_id == ""
        assert "Kein passender Code" in reply

    def test_group_message_becomes_chat_post(self):
        space = services.space_for_event(_event())
        space.tg_chat_id = "-100500"
        space.save(update_fields=["tg_chat_id"])
        assert telegram_bridge.ingest_group_message(None, self._group()) is True
        post = FeedPost.objects.get()
        assert post.kind == FeedPost.KIND_MESSAGE
        assert post.source == FeedPost.SOURCE_TELEGRAM
        assert post.author_name == "Vikram"

    def test_repeated_update_does_not_duplicate(self):
        """Telegram ретраит апдейты — второй раз дубля быть не должно."""
        space = services.space_for_event(_event())
        space.tg_chat_id = "-100500"
        space.save(update_fields=["tg_chat_id"])
        telegram_bridge.ingest_group_message(None, self._group())
        telegram_bridge.ingest_group_message(None, self._group())
        assert FeedPost.objects.count() == 1

    def test_unbound_group_is_ignored(self):
        services.space_for_event(_event())
        assert telegram_bridge.ingest_group_message(None, self._group()) is False
        assert FeedPost.objects.count() == 0

    def test_message_from_telegram_is_not_pushed_back(self):
        """Эхо-петля: пришедшее из группы обратно не отправляем."""
        space = services.space_for_event(_event())
        space.tg_chat_id = "-100500"
        space.save(update_fields=["tg_chat_id"])
        post = services.add_post(
            space, body="Aus der Gruppe", source=FeedPost.SOURCE_TELEGRAM, external_ref="42"
        )
        assert telegram_bridge.push_to_group(post) is False

    def test_private_chat_is_not_treated_as_group(self):
        message = self._group()
        message["chat"]["type"] = "private"
        assert telegram_bridge.try_link(None, message) == ""
        assert telegram_bridge.ingest_group_message(None, message) is False


class TestSpaceLifecycle:
    def test_space_is_created_once_per_departure(self):
        event = _event()
        first = services.space_for_event(event)
        second = services.space_for_event(event)
        assert first.pk == second.pk
        assert FeedSpace.objects.count() == 1

    def test_link_code_is_generated(self):
        space = services.space_for_event(_event())
        assert space.tg_link_code
