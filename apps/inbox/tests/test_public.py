"""M22b: витрина — форма «Frage stellen», публичный тред, письмо клиенту."""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.inbox import public_views, services
from apps.inbox.models import Conversation, Message
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pub(method="post", path="/nachricht/", data=None, disabled=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.5"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=disabled if disabled is not None else [])
    return request


def test_contact_creates_conversation_and_redirects():
    resp = public_views.contact(
        _pub(
            "post",
            data={
                "subject": "Frage",
                "body": "Habt ihr X?",
                "name": "Anna",
                "email": "anna@t.de",
                "ref_kind": "product",
                "ref_id": "p1",
                "ref_label": "Brot",
            },
        )
    )
    conv = Conversation.objects.get()
    assert conv.customer.email == "anna@t.de" and conv.ref_label == "Brot"
    assert conv.messages.get().author_role == "customer"
    assert resp.status_code == 302 and str(conv.public_token) in resp.url


def test_contact_gated_when_module_off():
    with pytest.raises(Http404):
        public_views.contact(_pub("get", "/nachricht/", disabled=["inbox"]))


def test_contact_honeypot_and_empty_body():
    public_views.contact(_pub("post", data={"website": "bot", "body": "x"}))  # honeypot
    assert not Conversation.objects.exists()
    public_views.contact(_pub("post", data={"body": "  "}))  # пустое тело
    assert not Conversation.objects.exists()


def test_public_thread_customer_reply():
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    resp = public_views.thread(
        _pub("post", f"/nachricht/{conv.public_token}/", {"body": "noch da?"}),
        token=conv.public_token,
    )
    assert resp.status_code == 302
    assert conv.messages.filter(author_role="customer").count() == 2


def test_thread_poll_returns_new_messages_since():
    """M22b realtime: поллинг отдаёт сообщения с id > since (ответ бизнеса)."""
    import json

    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    staff = services.post_message(conv, body="Hallo!", author_role=Message.AUTHOR_STAFF)
    resp = public_views.thread_poll(
        _pub("get", f"/nachricht/{conv.public_token}/poll/"), token=conv.public_token
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    ids = [m["id"] for m in data["messages"]]
    assert str(staff.pk) in ids  # ответ бизнеса виден поллингу
    # хронологический порядок: ответ бизнеса — последним
    assert data["messages"][-1]["role"] == "staff" and data["messages"][-1]["body"] == "Hallo!"


def test_thread_poll_gated_when_module_off():
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    with pytest.raises(Http404):
        public_views.thread_poll(
            _pub("get", "/nachricht/x/poll/", disabled=["inbox"]), token=conv.public_token
        )


def test_staff_reply_enqueues_customer_email():
    conv = services.start_conversation(subject="Q", body="hi", email="a@t.de")
    msg = services.post_message(conv, body="Hallo!", author_role=Message.AUTHOR_STAFF)
    assert Notification.objects.filter(dedupe_key=f"inbox:msg:{msg.id}:customer").exists()
