"""C1/C2/C3 (план deal-comms-plan-2026-08-25): общение с клиентом из сделки.

C1 — owner-first тред с карточки сделки (существующий открывается, новый
создаётся и шлёт клиенту письмо); C2 — склейка «запрос с сайта → сделка» при
однозначности + подпись сделки в CRM; C3 — Telegram-дубль ответа и wa.me-ссылка.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.inbox import services, views
from apps.inbox.deal_threads import adopt_open_thread, deal_ref_label, find_thread
from apps.inbox.models import Conversation, Message
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
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _order(email="kunde@test.de"):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price="10.00", stock_quantity=50)
    return create_order(items=[(product, 1)], name="Kunde", email=email)


# --- C1: owner-first тред с карточки сделки ---------------------------------------


def test_deal_thread_creates_owner_first_conversation():
    order = _order()
    request = _req("post", data={"body": "Ihre Bestellung ist fertig."})
    response = views.deal_thread(request, "order", order.pk)
    assert response.status_code == 302
    conv = Conversation.objects.get(ref_kind="order")
    assert conv.ref_id == order.reference_code
    assert conv.ref_label == deal_ref_label("order", order.reference_code)
    assert conv.customer_id == order.customer_id
    msg = conv.messages.get()
    assert msg.author_role == Message.AUTHOR_STAFF
    assert not conv.unread_for_staff  # ответ владельца — не «непрочитано» у него


def test_deal_thread_opens_existing_thread_instead_of_second():
    """Тред уже заведён клиентом («⚠️ Etwas stimmt nicht») — открываем его."""
    order = _order()
    existing = services.start_conversation(
        subject="Problem",
        body="Etwas fehlt",
        email=order.customer.email,
        ref_kind="order",
        ref_id=order.reference_code,
    )
    response = views.deal_thread(_req(), "order", order.pk)
    assert response.status_code == 302 and str(existing.pk) in response["Location"]
    assert Conversation.objects.count() == 1


def test_deal_thread_finds_legacy_uuid_ref():
    """Легаси LS-3-треды писали ref_id = UUID заказа — фолбэк их находит."""
    order = _order()
    legacy = services.start_conversation(
        subject="Angebot", body="…", email=order.customer.email, ref_kind="order", ref_id=order.pk
    )
    assert find_thread("order", order.reference_code, pk=order.pk).pk == legacy.pk


def test_deal_thread_without_email_refuses():
    order = _order(email="")
    request = _req("post", data={"body": "Hallo"})
    response = views.deal_thread(request, "order", order.pk)
    assert response.status_code == 200  # остались на композере
    assert not Conversation.objects.exists()


def test_deal_thread_unknown_kind_404():
    from django.http import Http404

    with pytest.raises(Http404):
        views.deal_thread(_req(), "quatsch", uuid.uuid4())


# --- C2: склейка «запрос → сделка» -------------------------------------------------


def test_open_thread_without_ref_adopts_new_deal():
    conv = services.start_conversation(subject="Frage", body="Habt ihr X?", email="k@test.de")
    order = _order(email="k@test.de")
    conv.refresh_from_db()
    assert (conv.ref_kind, conv.ref_id) == ("order", order.reference_code)
    assert conv.ref_label == deal_ref_label("order", order.reference_code)
    # Отметка в ленте — system-роль (письма не порождает).
    assert conv.messages.filter(author_role=Message.AUTHOR_SYSTEM).exists()


def test_two_open_threads_stay_untouched():
    """Неоднозначность — не гадаем: обе беседы остаются без привязки."""
    services.start_conversation(subject="A", body="1", email="k2@test.de")
    services.start_conversation(subject="B", body="2", email="k2@test.de")
    _order(email="k2@test.de")
    assert not Conversation.objects.filter(ref_kind="order").exists()


def test_thread_with_ref_not_readopted():
    conv = services.start_conversation(
        subject="Problem", body="x", email="k3@test.de", ref_kind="stay", ref_id="S-1"
    )
    _order(email="k3@test.de")
    conv.refresh_from_db()
    assert (conv.ref_kind, conv.ref_id) == ("stay", "S-1")


def test_adopt_is_fail_soft_on_none_customer():
    adopt_open_thread(None, ref_kind="order", ref_id="X-1")  # не падает


def test_customer360_labels_threads_by_deal():
    from apps.crm import customer360

    tenant = TenantFactory.build(disabled_modules=[])
    order = _order(email="c360@test.de")
    conv = services.start_conversation(
        subject="Wann fertig?",
        body="?",
        customer=order.customer,
        ref_kind="order",
        ref_id=order.reference_code,
        ref_label=deal_ref_label("order", order.reference_code),
    )
    sections = {s["key"]: s for s in customer360.sections(tenant, order.customer)}
    items = sections["conversations"]["items"]
    assert items[0]["title"] == conv.ref_label  # подпись = сделка, не тема
    assert "Wann fertig?" in items[0]["sub"]


# --- C3: внешние каналы ------------------------------------------------------------


def test_thread_context_exposes_channels(monkeypatch):
    order = _order()
    order.customer.phone = "+49 170 1234567"
    order.customer.save(update_fields=["phone", "updated_at"])
    conv = services.start_conversation(
        subject="X", body="hi", customer=order.customer, ref_label="Bestellung"
    )
    response = views.thread(_req(path=f"/dashboard/inbox/{conv.pk}/"), conv.pk)
    html = response.content.decode()
    assert "wa.me/491701234567" in html
    # Без привязки к боту чекбокса Telegram нет (канала не существует).
    assert "via_telegram" not in html


def test_reply_via_telegram_pushes_same_text(monkeypatch):
    sent = {}

    def _fake(customer, *, type, dedupe_key, text):
        sent.update({"customer": customer, "type": type, "key": dedupe_key, "text": text})

    monkeypatch.setattr("apps.telegram.notify.send_to_customer", _fake)
    conv = services.start_conversation(subject="X", body="hi", email="tg@test.de")
    request = _req(
        "post",
        path=f"/dashboard/inbox/{conv.pk}/",
        data={"action": "reply", "body": "Fertig!", "via_telegram": "1"},
    )
    views.thread(request, conv.pk)
    assert sent["text"] == "Fertig!" and sent["key"].endswith(":telegram")


def test_reply_without_checkbox_does_not_push(monkeypatch):
    called = []
    monkeypatch.setattr(
        "apps.telegram.notify.send_to_customer",
        lambda *a, **kw: called.append(1),
    )
    conv = services.start_conversation(subject="X", body="hi", email="tg2@test.de")
    request = _req(
        "post", path=f"/dashboard/inbox/{conv.pk}/", data={"action": "reply", "body": "Ok"}
    )
    views.thread(request, conv.pk)
    assert not called


# --- ревью 2026-08-25: три правки склейки C2 ------------------------------------


def test_adopt_keeps_unread_question_visible():
    """Вопрос клиента остаётся непрочитанным: system-отметка о сделке не должна
    гасить бейдж — иначе неотвеченный вопрос исчезал из инбокса и дайджеста."""
    conv = services.start_conversation(subject="Frage", body="Habt ihr X?", email="unread@test.de")
    assert conv.unread_for_staff
    _order(email="unread@test.de")
    conv.refresh_from_db()
    assert conv.ref_kind == "order"  # склейка произошла
    assert conv.unread_for_staff is True  # и вопрос всё ещё «непрочитан»


def test_adopt_skips_high_priority_thread():
    """High-тред (жалоба «вообще») не привязывается к свежей сделке — иначе доска
    рисует «Problem — Kunde wartet» на беспроблемном заказе."""
    conv = services.start_conversation(
        subject="Beschwerde",
        body="Sehr unzufrieden",
        email="high@test.de",
        ref_kind="order",
        ref_id="ALT-1",
        priority=Conversation.PRIORITY_HIGH,
    )
    Conversation.objects.filter(pk=conv.pk).update(ref_kind="", ref_id="", ref_label="")
    _order(email="high@test.de")
    conv.refresh_from_db()
    assert conv.ref_kind == ""  # high остался без привязки


def test_adopt_skips_offer_thread_no_duplicate_note():
    """Тред с предложением ref проставляет accept_offer — склейка не должна
    писать вторую системную отметку про тот же заказ."""
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import offers

    conv = services.start_conversation(subject="Torten?", body="Preis?", email="offer@test.de")
    product = ProductFactory(base_price="8.50", stock_quantity=5)
    offer = offers.send_offer(
        conv,
        lines=[
            {
                "kind": "product",
                "ref_id": str(product.id),
                "title": "Torte",
                "unit_price": "8.50",
                "qty": 1,
            }
        ],
    )
    order = offers.accept_offer(offer, payment_method="on_site")
    bodies = list(
        conv.messages.filter(author_role=Message.AUTHOR_SYSTEM).values_list("body", flat=True)
    )
    assert sum(1 for b in bodies if order.reference_code in b) == 1, bodies
