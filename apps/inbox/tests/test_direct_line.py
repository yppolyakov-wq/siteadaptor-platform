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


# --- инкремент 2: канбан has_problem + SLA ------------------------------------------


def test_kanban_marks_problem_cards_batch():
    from apps.core import transactions
    from apps.orders.services import create_order

    tenant = TenantFactory.build(disabled_modules=[])
    good = create_order(items=(), custom_lines=[("A", "5.00", 1)], name="K", email="k@t.de")
    bad = create_order(items=(), custom_lines=[("B", "5.00", 1)], name="K", email="k@t.de")
    services.start_conversation(
        subject="Problem",
        body="!",
        email="k@t.de",
        ref_kind="order",
        ref_id=bad.reference_code,
        priority="high",
    )
    # обычный тред на good — полосы не даёт
    services.start_conversation(
        subject="Frage",
        body="?",
        email="k@t.de",
        ref_kind="order",
        ref_id=good.reference_code,
    )
    section = next(s for s in transactions.manage_sections_for(tenant) if s["kind"] == "order")
    flags = {tx.reference_code: tx.has_problem for tx in section["transactions"]}
    assert flags[bad.reference_code] is True
    assert flags[good.reference_code] is False


def test_kanban_problem_lookup_single_query():
    """N+1-замок: problem-lookup — ОДИН запрос на секцию, не per-card."""
    from django.db import connection as dj_connection
    from django.test.utils import CaptureQueriesContext

    from apps.core import transactions
    from apps.orders.services import create_order

    tenant = TenantFactory.build(disabled_modules=[])
    for i in range(5):
        create_order(items=(), custom_lines=[(f"P{i}", "5.00", 1)], name="K", email="k@t.de")
    with CaptureQueriesContext(dj_connection) as ctx:
        transactions.manage_sections_for(tenant)
    conv_queries = [q for q in ctx.captured_queries if "inbox_conversation" in q["sql"]]
    sections = [s for s in transactions.manage_sections_for(tenant) if s["transactions"]]
    assert len(conv_queries) <= len(sections)  # ≤1 на непустую секцию


def test_sla_reaction_time_computed():
    from apps.inbox.models import Message
    from apps.inbox.views import _thread_reaction

    conv = services.start_conversation(subject="F", body="Hi", email="k@t.de")
    assert _thread_reaction(conv) is None  # ответа staff ещё нет
    services.post_message(conv, body="Antwort", author_role=Message.AUTHOR_STAFF)
    assert _thread_reaction(conv) is not None  # «~1 Min»


# --- инкремент 3: service recovery --------------------------------------------------


def test_resolved_problem_thread_sends_recovery_once():
    from apps.inbox.state_machine import ConversationSM
    from apps.notifications.models import Notification

    conv = services.start_conversation(
        subject="Problem",
        body="!",
        email="rec@t.de",
        ref_kind="order",
        ref_id="O-1",
        priority="high",
    )
    ConversationSM().apply(conv, "resolved")
    n = Notification.objects.get(dedupe_key=f"inbox:conv:{conv.pk}:recovery")
    assert n.recipient == "rec@t.de"
    # reopen → resolve повторно: дедуп держит одно письмо
    ConversationSM().apply(conv, "open")
    ConversationSM().apply(conv, "resolved")
    assert Notification.objects.filter(dedupe_key=f"inbox:conv:{conv.pk}:recovery").count() == 1


def test_resolved_normal_thread_no_recovery():
    from apps.inbox.state_machine import ConversationSM
    from apps.notifications.models import Notification

    conv = services.start_conversation(subject="Frage", body="?", email="n@t.de")
    ConversationSM().apply(conv, "resolved")
    assert not Notification.objects.filter(type="inbox_recovery").exists()


# --- LS-4 «Слой доверия»: лицо в касаниях + публичный бейдж реакции ----------------


def test_staff_name_in_public_thread_and_email(monkeypatch):
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory as RF

    from apps.inbox import notifications as inotif
    from apps.inbox.models import Message
    from apps.notifications.models import Notification

    staff = get_user_model().objects.create_user(
        username="maria", first_name="Maria", email="m@laden.de", password="pw12345678"
    )
    conv = services.start_conversation(subject="F", body="Hi", email="kunde@t.de", name="Kim")
    monkeypatch.setattr(inotif, "_base_url", lambda schema: "https://laden.example")
    services.post_message(
        conv, body="Gern helfe ich!", author_role=Message.AUTHOR_STAFF, author_user=staff
    )
    # письмо клиенту — подпись живым именем
    n = Notification.objects.filter(type="inbox_reply").latest("created_at")
    assert "Maria" in n.payload.get("body", "")
    # публичный тред — имя над staff-пузырём
    request = RF().get("/n/")
    request.tenant = TenantFactory.build(disabled_modules=[])
    html = public_views.thread(request, token=conv.public_token).content.decode()
    assert ">Maria</p>" in html


def test_public_reaction_badge_gated_by_good_value(monkeypatch):
    from apps.inbox import public_views as pv

    def _get(minutes):
        monkeypatch.setattr(pv, "_badge_probe", None, raising=False)
        import apps.inbox.views as iv

        monkeypatch.setattr(iv, "avg_reaction_minutes", lambda **kw: minutes)
        request = RequestFactory().get("/nachricht/")
        request.tenant = TenantFactory.build(disabled_modules=[])
        return pv.contact(request).content.decode()

    assert "Antwortet in der Regel" in _get(15)  # хорошее значение → бейдж
    assert "Antwortet in der Regel" not in _get(600)  # медленно → без бейджа
    assert "Antwortet in der Regel" not in _get(None)  # нет данных → без бейджа
