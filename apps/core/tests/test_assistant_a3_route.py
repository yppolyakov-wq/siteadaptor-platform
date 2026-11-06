"""AIS A-3a: в шторке «✨ Assistent» просьба создать что-то даёт план с предзаполненной
формой (помощник «Was möchten Sie anlegen?»), а не «Ich bin nicht sicher».

Фидбэк владельца 2026-11-06: «добавь новый товар Колбаса копченая 200 гр 50 евро как услугу»
→ «Я не уверен» + статьи. Модель вопросов (A-2) ничего не создаёт и выбросила бы «50 €» —
поэтому намерение «создать» уходит в план ДО неё и работает без ИИ; обычный вопрос без ИИ
получает статьи A-1, а не «nicht verfügbar».
"""

import pytest

from apps.core import assistant_ai, assistant_views, setup_assistant
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры
    GOOD,
    _answer_html,
    _ask,
    _model,
    _req,
    _urlconf,
    _user,
    ai_task_on,
    bakery,
    isolated_ratelimit,
)

pytestmark = pytest.mark.django_db

SAUSAGE = "добавь новый товар Колбаса копченая 200 гр 50 евро как услугу"


@pytest.fixture
def ai_off(settings, isolated_ratelimit):  # noqa: F811
    settings.AI_ENABLED = False
    return settings


def test_create_phrase_gives_plan_without_ai(ai_off, bakery):  # noqa: F811
    gen, run = _model(GOOD)
    with gen as g, run:
        user, got = _ask(bakery, SAUSAGE)
    assert "job" in got and g.call_count == 0
    resp, html = _answer_html(bakery, user, got["job"])
    assert resp["X-Sf-Answer-State"] == "done"
    assert "data-assistant-plan" in html
    from django.urls import reverse

    assert reverse("booking:service-new") + "?" in html  # форма УСЛУГИ — «как услугу»
    assert "price_eur=50%2C00" in html  # цена «50 евро» дошла до формы
    assert "Ich bin nicht sicher" not in html


def test_create_phrase_does_not_call_the_answer_model(ai_task_on, bakery):  # noqa: F811
    gen, run = _model(GOOD)
    with gen as g, run:
        _user_, got = _ask(bakery, "создай услугу прыжки с парашутом, 200 евро, 60 минут")
    assert g.call_count == 0 and "job" in got


def test_plan_job_is_private_to_its_user(ai_off, bakery):  # noqa: F811
    from django.http import Http404

    _owner, got = _ask(bakery, SAUSAGE)
    with pytest.raises(Http404):
        assistant_views.assistant_answer(_req(bakery, user=_user(), drawer=True), got["job"])


def test_question_never_lands_in_url_or_json(ai_off, bakery):  # noqa: F811
    _user_, got = _ask(bakery, SAUSAGE)
    assert "Колбаса" not in got["url"] and "Колбаса" not in str(got)


def test_plain_question_without_ai_gets_articles_not_unavailable(ai_off, bakery):  # noqa: F811
    user, got = _ask(bakery, "Wie stelle ich die Lieferung ein?")
    assert "job" in got
    _resp, html = _answer_html(bakery, user, got["job"])
    assert "data-help=" in html
    assert "nicht verfügbar" not in html


def test_form_is_shown_without_ai_but_without_ai_hint(ai_off, bakery):  # noqa: F811
    body = assistant_views.assistant_view(_req(bakery)).content.decode()
    assert "data-assistant-ask" in body and 'name="frage"' in body
    assert "Sie chatten mit einer KI" not in body


def test_create_intent_needs_permission(ai_off, bakery, monkeypatch):  # noqa: F811
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: [])
    user, got = _ask(bakery, SAUSAGE)
    _resp, html = _answer_html(bakery, user, got["job"])
    assert "data-assistant-plan" not in html


def test_plan_entry_keeps_no_url_and_is_versioned(ai_off, bakery):  # noqa: F811
    user, got = _ask(bakery, SAUSAGE)
    entry = assistant_ai.job_state(_req(bakery, user=user), got["job"])
    assert entry["outcome"] == "plan" and "url" not in entry


def test_drawer_has_visible_anlegen_button(ai_off, bakery):  # noqa: F811
    from django.urls import reverse

    body = assistant_views.assistant_view(_req(bakery)).content.decode()
    assert "data-assistant-anlegen" in body and reverse("setup-ask") in body


def test_anlegen_button_hidden_without_rights(ai_off, bakery, monkeypatch):  # noqa: F811
    monkeypatch.setattr(setup_assistant, "allowed_entities", lambda t, u: [])
    body = assistant_views.assistant_view(_req(bakery)).content.decode()
    assert "data-assistant-anlegen" not in body


# ── ревью A-3a: план строится ОДИН раз при вопросе, показ его только перепроверяет ──


def test_plan_is_built_once_and_reads_do_not_count(ai_off, bakery, monkeypatch):  # noqa: F811
    calls = []
    real = setup_assistant.build_plan
    monkeypatch.setattr(
        setup_assistant, "build_plan", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    user, got = _ask(bakery, SAUSAGE)
    for _ in range(25):  # F5, повторное открытие шторки, опрос — больше лимита setup-plan
        _resp, html = _answer_html(bakery, user, got["job"])
    assert calls == [1]
    assert "price_eur=50%2C00" in html and "Zu viele Fragen" not in html


def test_plan_entry_does_not_keep_the_question(ai_off, bakery):  # noqa: F811
    user, got = _ask(bakery, SAUSAGE)
    entry = assistant_ai.job_state(_req(bakery, user=user), got["job"])
    assert "Колбаса копченая 200 гр 50 евро" not in str(entry.get("q", ""))


def test_plan_rights_rechecked_on_display(ai_off, bakery, monkeypatch):  # noqa: F811
    user, got = _ask(bakery, SAUSAGE)
    monkeypatch.setattr(setup_assistant, "reachable", lambda request, name: False)
    _resp, html = _answer_html(bakery, user, got["job"])
    assert "data-setup-unreachable" in html and "price_eur=50%2C00" not in html


def test_plan_storage_failure_is_a_calm_message(ai_off, bakery, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(assistant_ai, "_put", boom)
    _user_, got = _ask(bakery, SAUSAGE)
    assert got.get("code") and "message" in got
