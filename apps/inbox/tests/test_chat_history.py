"""Чат-фикс 2026-10-23: история переписки видна (кто/когда), беседу можно продолжить,
известную почту клиента не спрашиваем заново; пункт «Nachrichten» в нижнем меню
имеет иконку (раньше — пустой круг в Mini App)."""

import json
import re
import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.inbox import public_views, services, views
from apps.inbox.display import author_label
from apps.inbox.models import Conversation, Message
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pub(method="post", path="/nachricht/", data=None, cookies=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    request.COOKIES.update(cookies or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _cookies_from(resp):
    morsel = resp.cookies.get(public_views.THREADS_COOKIE)
    assert morsel is not None, "беседа не запомнена браузером"
    return {public_views.THREADS_COOKIE: morsel.value}


def _staff():
    o = uuid.uuid4().hex[:8]
    return get_user_model().objects.create_user(
        username=f"st-{o}", password="pw12345678", first_name="Mia", last_name="Bäcker"
    )


# --- нижнее меню ---------------------------------------------------------------------


def test_every_tabbar_nav_key_has_an_icon():
    """Таб-бар рисует `#ic-nav-<nav_key>`; без символа — пустой круг (пропавший чат)."""
    from apps.core import lite_cabinet, nav_registry

    icons = Path("templates/tenant/_icons.html").read_text()
    have = set(re.findall(r'id="ic-nav-([a-z_-]+)"', icons))
    keys = {a.nav_key for a in nav_registry.ANCHORS}
    keys |= {i[1] for i in lite_cabinet.LITE_NAV + lite_cabinet.EINTRAG_NAV}
    assert keys <= have, f"нет иконки для {sorted(keys - have)}"


# --- кто писал -----------------------------------------------------------------------


def test_author_label_by_side():
    conv = services.start_conversation(subject="Q", body="hi", name="Anna K.", email="a@t.de")
    staff = _staff()
    reply = services.post_message(
        conv, body="Gern", author_role=Message.AUTHOR_STAFF, author_user=staff
    )
    first = conv.messages.order_by("created_at").first()
    assert author_label(first, conv, viewer="staff") == "Anna K."
    assert author_label(first, conv, viewer="customer") == "Sie"
    assert author_label(reply, conv, viewer="staff") == "Mia Bäcker"
    # клиент видит только имя (username бывает e-mail'ом)
    assert author_label(reply, conv, viewer="customer") == "Mia"


# --- клиент: память беседы и почты ---------------------------------------------------


def test_contact_remembers_thread_and_lists_it_with_known_email():
    resp = public_views.contact(
        _pub(data={"subject": "Torte", "body": "Torte am Samstag?", "email": "anna@t.de"})
    )
    cookies = _cookies_from(resp)
    page = public_views.contact(_pub("get", cookies=cookies)).content.decode()
    assert "data-my-threads" in page and "Torte" in page
    assert "data-known-contact" in page and 'value="anna@t.de"' in page


def test_second_question_without_email_reuses_known_customer():
    resp = public_views.contact(_pub(data={"body": "Erste Frage", "email": "anna@t.de"}))
    cookies = _cookies_from(resp)
    public_views.contact(_pub(data={"subject": "Neu", "body": "Zweite Frage"}, cookies=cookies))
    convs = Conversation.objects.order_by("created_at")
    assert convs.count() == 2
    assert convs[0].customer_id == convs[1].customer_id is not None


def test_same_ref_open_thread_is_continued_not_duplicated():
    ref = {"ref_kind": "promotion", "ref_id": "p1", "ref_label": "Tüte"}
    resp = public_views.contact(_pub(data={"body": "Noch da?", "email": "a@t.de", **ref}))
    cookies = _cookies_from(resp)
    public_views.contact(_pub(data={"body": "Und morgen?", **ref}, cookies=cookies))
    conv = Conversation.objects.get()
    assert conv.messages.count() == 2


def test_forged_cookie_reveals_nothing():
    services.start_conversation(subject="Geheim", body="x", email="b@t.de")
    page = public_views.contact(
        _pub("get", cookies={public_views.THREADS_COOKIE: json.dumps(["x"])})
    ).content.decode()
    assert "data-my-threads" not in page and "Geheim" not in page


def test_thread_view_shows_authors_and_reply_remembers_it():
    conv = services.start_conversation(subject="Q", body="Hallo", email="c@t.de")
    services.post_message(conv, body="Antwort", author_role=Message.AUTHOR_STAFF)
    path = f"/nachricht/{conv.public_token}/"
    resp = public_views.thread(_pub("get", path), conv.public_token)
    html = resp.content.decode()
    assert html.count("data-msg-author") == 2 and "Sie" in html
    # Просмотр чужой (пересланной) ссылки не делает беседу «своей» для браузера.
    assert public_views.THREADS_COOKIE not in resp.cookies
    reply = public_views.thread(_pub("post", path, {"body": "Danke"}), conv.public_token)
    assert public_views.THREADS_COOKIE in reply.cookies


def test_knowing_someones_email_reveals_no_name_or_phone():
    """Ревью безопасности: контакт для предзаполнения — только то, что ввёл ЭТОТ браузер."""
    services.start_conversation(
        subject="Bestellung", body="x", name="Opfer Name", email="victim@t.de", phone="0171 999"
    )
    resp = public_views.contact(_pub(data={"body": "hi", "email": "victim@t.de"}))
    page = public_views.contact(_pub("get", cookies=_cookies_from(resp))).content.decode()
    assert "Opfer Name" not in page and "0171 999" not in page


def test_same_ref_with_other_email_starts_new_thread():
    ref = {"ref_kind": "promotion", "ref_id": "p1", "ref_label": "Tüte"}
    resp = public_views.contact(_pub(data={"body": "Noch da?", "email": "a@t.de", **ref}))
    public_views.contact(
        _pub(
            data={"body": "Ich bin wer anders", "email": "z@t.de", **ref},
            cookies=_cookies_from(resp),
        )
    )
    assert Conversation.objects.count() == 2


def test_forget_clears_device_memory():
    resp = public_views.contact(_pub(data={"body": "x", "email": "a@t.de"}))
    out = public_views.contact(_pub(data={"action": "forget"}, cookies=_cookies_from(resp)))
    assert out.cookies[public_views.THREADS_COOKIE].value == ""


def test_public_poll_carries_author():
    conv = services.start_conversation(subject="Q", body="Hallo", email="d@t.de")
    data = json.loads(
        public_views.thread_poll(_pub("get"), token=conv.public_token).content.decode()
    )
    assert data["messages"][0]["author"] == "Sie"


# --- кабинет -------------------------------------------------------------------------


def _staff_req(path, user):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def test_owner_list_shows_last_message_and_thread_shows_history():
    staff = _staff()
    old = services.start_conversation(subject="Alt", body="Früher", name="Ben", email="ben@t.de")
    conv = services.start_conversation(subject="Neu", body="Hallo", name="Ben", email="ben@t.de")
    services.post_message(conv, body="Gern geschehen", author_role="staff", author_user=staff)
    listing = views.inbox_list(_staff_req("/dashboard/inbox/", staff)).content.decode()
    assert "data-last-message" in listing and "Gern geschehen" in listing
    page = views.thread(_staff_req(f"/dashboard/inbox/{conv.pk}/", staff), pk=conv.pk)
    html = page.content.decode()
    assert "data-customer-threads" in html and "Alt" in html and str(old.pk) in html
    assert "Mia Bäcker" in html and "Ben" in html


def test_demo_threads_seed_history_with_times():
    from apps.tenants import demo_kits

    kit = demo_kits.LITE_BAKERY
    assert kit.inbox_threads, "лёгкое демо должно показывать переписку"
    demo_kits._seed_kit_threads(kit)
    conv = Conversation.objects.get(subject=kit.inbox_threads[0]["subject"])
    msgs = list(conv.messages.order_by("created_at"))
    assert [m.body for m in msgs] == [m[1] for m in kit.inbox_threads[0]["messages"]]
    assert msgs[0].created_at < msgs[-1].created_at
    assert all(t["email"].endswith("@example.com") for t in kit.inbox_threads)
