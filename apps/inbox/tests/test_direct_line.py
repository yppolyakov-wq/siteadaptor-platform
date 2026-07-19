"""LS-6 «Прямая линия» инкремент 1: problem-CTA → high-тред + Telegram-пуш.

План ls6-direct-line-plan-2026-07-19.md: high выставляет ТОЛЬКО доверенный
problem-гейт (problem=1 + непустой ref) — сырой priority не принимается;
пуш владельцу — best-effort с dedupe на тред.
"""

import pytest
from django.test import RequestFactory

from apps.inbox import public_views, services
from apps.inbox.models import Conversation
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _post(data, tenant=None):
    # Уникальный IP на вызов — rl:*-счётчики в Redis переживают прогоны (грабля CLAUDE.md §3).
    import uuid as _uuid

    request = RequestFactory().post(
        "/nachricht/", data, REMOTE_ADDR=f"10.7.{_uuid.uuid4().int % 250}.{_uuid.uuid4().int % 250}"
    )
    request.tenant = tenant if tenant is not None else TenantFactory.build(disabled_modules=[])
    return public_views.contact(request)


BASE = {"subject": "Problem: O-1", "body": "Bestellung kalt angekommen", "email": "k@t.de"}


def test_problem_marker_with_ref_creates_high_thread():
    _post({**BASE, "problem": "1", "ref_kind": "order", "ref_id": "O-ABC123"})
    conv = Conversation.objects.get()
    assert conv.priority == Conversation.PRIORITY_HIGH
    assert (conv.ref_kind, conv.ref_id) == ("order", "O-ABC123")


def test_problem_without_ref_stays_normal():
    _post({**BASE, "problem": "1"})  # нет ref → обычный тред (гейт)
    assert Conversation.objects.get().priority == Conversation.PRIORITY_NORMAL


def test_raw_priority_param_ignored():
    _post({**BASE, "priority": "high", "ref_kind": "order", "ref_id": "O-X"})
    assert Conversation.objects.get().priority == Conversation.PRIORITY_NORMAL


def test_high_thread_pushes_owner_telegram(monkeypatch):
    calls = []
    import apps.inbox.services as svc

    def _fake_notify(conversation):
        calls.append(conversation.pk)

    monkeypatch.setattr(svc, "_notify_owner_problem", _fake_notify)
    conv = services.start_conversation(
        subject="Problem",
        body="Hilfe",
        email="k@t.de",
        ref_kind="order",
        ref_id="O-1",
        priority="high",
    )
    assert calls == [conv.pk]
    # обычный тред пуш не зовёт
    services.start_conversation(subject="Frage", body="Hi", email="k2@t.de")
    assert calls == [conv.pk]


def test_notify_owner_problem_is_failsafe():
    conv = services.start_conversation(
        subject="Problem",
        body="Hilfe",
        email="k@t.de",
        ref_kind="order",
        ref_id="O-1",
        priority="high",
    )  # реальный путь: _tenant → None в тестах → тихий no-op, тред создан
    assert conv.priority == "high"


def test_confirmation_page_shows_problem_cta():
    from importlib import import_module

    from django.conf import settings as dj_settings

    from apps.orders import public_views as orders_public
    from apps.orders.services import create_order

    order = create_order(items=(), custom_lines=[("X", "5.00", 1)], name="K", email="k@t.de")
    request = RequestFactory().get(f"/bestellung/{order.reference_code}/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = TenantFactory.build(disabled_modules=[])
    html = orders_public.order_confirmation(request, code=order.reference_code).content.decode()
    assert "Etwas stimmt nicht?" in html
    assert f"problem=1&ref_kind=order&ref_id={order.reference_code}" in html


def test_confirmed_email_contains_problem_url(monkeypatch):
    from apps.notifications.models import Notification
    from apps.orders import notifications as onotif
    from apps.orders.services import create_order
    from apps.orders.state_machine import OrderSM

    monkeypatch.setattr(onotif, "_base_url", lambda schema: "https://shop.example")
    order = create_order(items=(), custom_lines=[("X", "5.00", 1)], name="K", email="k@t.de")
    OrderSM().apply(order, "confirmed")
    n = Notification.objects.get(dedupe_key=f"order:{order.id}:confirmed:customer")
    body = n.payload.get("body", "")
    assert f"problem=1&ref_kind=order&ref_id={order.reference_code}" in body
