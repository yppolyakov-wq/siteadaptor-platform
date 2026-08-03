"""M22a: inbox — ядро (Conversation/Message), сервисы, кабинет."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.inbox import services, views
from apps.inbox.models import Message
from apps.inbox.state_machine import ConversationSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/inbox/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build(disabled_modules=[])  # inbox активен
    return request


# --- сервисы ----------------------------------------------------------------------


def test_start_conversation_creates_thread_message_and_customer():
    conv = services.start_conversation(
        subject="Frage zu Brot",
        body="Habt ihr glutenfrei?",
        name="Anna",
        email="anna@t.de",
        ref_kind="product",
        ref_label="Roggenbrot",
    )
    assert conv.subject == "Frage zu Brot" and conv.status == "open"
    assert conv.customer.email == "anna@t.de"
    assert conv.messages.count() == 1
    msg = conv.messages.get()
    assert msg.author_role == "customer" and conv.unread_for_staff and conv.last_message_at


def test_customer_reply_reopens_resolved_and_marks_unread():
    conv = services.start_conversation(subject="X", body="hi", email="a@t.de")
    ConversationSM().apply(conv, "resolved")
    conv.unread_for_staff = False
    conv.save(update_fields=["unread_for_staff", "updated_at"])
    services.post_message(conv, body="noch da?", author_role=Message.AUTHOR_CUSTOMER)
    conv.refresh_from_db()
    assert conv.status == "open" and conv.unread_for_staff


def test_staff_reply_clears_unread():
    conv = services.start_conversation(subject="X", body="hi", email="a@t.de")
    assert conv.unread_for_staff
    services.post_message(conv, body="Hallo!", author_role=Message.AUTHOR_STAFF)
    conv.refresh_from_db()
    assert not conv.unread_for_staff and conv.messages.count() == 2


# --- кабинет ----------------------------------------------------------------------


def test_inbox_list_renders_and_filters():
    services.start_conversation(subject="Offen", body="hi", email="a@t.de")
    assert "Offen" in views.inbox_list(_req()).content.decode()
    # фильтр по resolved → открытого треда нет
    assert "Offen" not in views.inbox_list(_req(data={"status": "resolved"})).content.decode()


def test_thread_reply_and_status():
    conv = services.start_conversation(subject="Frage", body="hi", email="a@t.de")
    resp = views.thread(
        _req("post", f"/dashboard/inbox/{conv.pk}/", {"action": "reply", "body": "Antwort"}),
        pk=conv.pk,
    )
    assert resp.status_code == 302
    conv.refresh_from_db()
    assert conv.messages.filter(author_role="staff").count() == 1
    views.thread(_req("post", f"/dashboard/inbox/{conv.pk}/", {"action": "resolved"}), pk=conv.pk)
    conv.refresh_from_db()
    assert conv.status == "resolved"


def test_opening_thread_clears_unread():
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    assert conv.unread_for_staff
    views.thread(_req("get", f"/dashboard/inbox/{conv.pk}/"), pk=conv.pk)
    conv.refresh_from_db()
    assert not conv.unread_for_staff


def test_unread_count_endpoint():
    """M22b realtime: эндпоинт отдаёт число тредов с непрочитанным для staff."""
    import json

    services.start_conversation(subject="A", body="hi", email="a@t.de")  # unread
    conv2 = services.start_conversation(subject="B", body="ho", email="b@t.de")
    conv2.unread_for_staff = False
    conv2.save(update_fields=["unread_for_staff", "updated_at"])
    resp = views.unread_count(_req("get", "/dashboard/inbox/unread-count/"))
    assert resp.status_code == 200
    assert json.loads(resp.content)["count"] == 1


def test_thread_poll_returns_messages_and_clears_unread():
    """M22b realtime: кабинет-поллинг отдаёт сообщения треда + сбрасывает бейдж."""
    import json

    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    assert conv.unread_for_staff
    resp = views.thread_poll(_req("get", f"/dashboard/inbox/{conv.pk}/poll/"), pk=conv.pk)
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["messages"][-1]["role"] == "customer" and data["messages"][-1]["body"] == "hi"
    conv.refresh_from_db()
    assert not conv.unread_for_staff  # тред «просмотрен» поллингом


def test_cabinet_poll_and_unread_closed_to_anonymous():
    """Ревью 2026-08-03: поллинг отдаёт ТЕЛА сообщений и пишет unread_for_staff,
    unread-count — счётчик обращений бизнеса. Аноним обязан уйти на логин
    (Membership-гейт middleware анонима не трогает — он рассчитывает на
    `@login_required` во вьюхе; дыра существовала с появления поллинга)."""
    from django.contrib.auth.models import AnonymousUser

    conv = services.start_conversation(subject="Q", body="секретное тело", email="a@t.de")
    for view, args in ((views.thread_poll, (conv.pk,)), (views.unread_count, ())):
        req = _req("get", "/dashboard/inbox/x/")
        req.user = AnonymousUser()
        resp = view(req, *args)
        assert resp.status_code == 302 and "login" in resp["Location"]


def test_cabinet_typing_rejects_get():
    """Пинг мутирует состояние — GET получает 405, а не молчаливую запись."""
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    assert views.thread_typing(_req("get", "/x/"), pk=conv.pk).status_code == 405


def test_cabinet_typing_ping_wired_by_delegation():
    """Тот же регресс-замок, что на витрине: скрипт выше формы, прямой
    querySelector по textarea вернул бы null — пинг не отправлялся бы."""
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    body = views.thread(_req("get", f"/dashboard/inbox/{conv.pk}/"), pk=conv.pk).content.decode()
    assert 'document.addEventListener("input"' in body
    assert "area.addEventListener" not in body


def test_cabinet_typing_ping_and_poll_flag():
    """M22b (оживлено 2026-08-01): staff пингует «печатает» → флаг staff; печать
    клиента видна в кабинетном поллинге."""
    import json

    from django.core.cache import cache

    from apps.inbox.public_views import _typing_key

    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    views.thread_typing(_req("post", f"/dashboard/inbox/{conv.pk}/typing/"), pk=conv.pk)
    assert cache.get(_typing_key(conv.pk, "staff")) is True

    cache.set(_typing_key(conv.pk, "customer"), True, 6)
    resp = views.thread_poll(_req("get", f"/dashboard/inbox/{conv.pk}/poll/"), pk=conv.pk)
    assert json.loads(resp.content)["typing"] is True
