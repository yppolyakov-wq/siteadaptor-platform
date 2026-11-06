"""AIS A-3d: история переписки с помощником (решение владельца: в базе, 90 дней).

Замки:
* хранится вопрос (после scrub) и ТОЛЬКО проверенная запись ответа — отклонённый ответ ИИ
  в историю не попадает текстом; ссылки — идентификаторами (URL при показе заново);
* повтор задачи не дублирует строку (job уникален); сбой записи не ломает ответ;
* видна только своему пользователю; «Verlauf löschen» — POST, только свои строки;
* срок 90 дней (beat) и не больше 200 строк на пользователя;
* показ истории ничего не пишет и перепроверяет права ссылок.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core import assistant_history, assistant_views, setup_assistant
from apps.core.models import AssistantTurn
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    GOOD,
    _answer_html,
    _ask,
    _clean,
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
BAD = {**GOOD, "text": "Rufen Sie uns an: +49 170 1234567"}


@pytest.fixture
def ai_off(settings, isolated_ratelimit):  # noqa: F811
    settings.AI_ENABLED = False
    return settings


def test_good_answer_is_recorded_with_ids_not_urls(ai_task_on, bakery):  # noqa: F811
    gen, run = _model(GOOD)
    with gen, run:
        user, got = _ask(bakery, "Wie liefere ich nur in meine Stadt?")
    turn = AssistantTurn.objects.get(job=got["job"])
    assert turn.user_id == user.pk and turn.kind == "answer"
    assert "Stadt" in turn.question
    assert turn.entry["text"] == GOOD["text"]
    assert "/dashboard/" not in str(turn.entry)  # только идентификаторы


def test_rejected_ai_text_is_not_kept(ai_task_on, bakery):  # noqa: F811
    gen, run = _model(BAD)
    with gen, run:
        _user_, got = _ask(bakery, "Wie erreiche ich den Support?")
    turn = AssistantTurn.objects.get(job=got["job"])
    assert turn.kind == "fallback" and "1234567" not in str(turn.entry)


def test_plan_and_articles_are_recorded(ai_off, bakery):  # noqa: F811
    user, got = _ask(bakery, SAUSAGE)
    assert AssistantTurn.objects.get(job=got["job"]).kind == "plan"
    _user2, got2 = _ask(bakery, "Wie stelle ich die Lieferung ein?", user=user)
    assert AssistantTurn.objects.get(job=got2["job"]).kind == "articles"


def test_replayed_job_does_not_duplicate(ai_off, bakery):  # noqa: F811
    user, got = _ask(bakery, SAUSAGE)
    turn = AssistantTurn.objects.get(job=got["job"])
    assistant_history.record("public", user.pk, got["job"], "x", {"state": "done"})
    assert AssistantTurn.objects.filter(job=got["job"]).count() == 1
    assert AssistantTurn.objects.get(job=got["job"]).question == turn.question


def test_record_failure_does_not_break_the_answer(ai_off, bakery, monkeypatch):  # noqa: F811
    monkeypatch.setattr(AssistantTurn.objects, "get_or_create", mock.Mock(side_effect=RuntimeError))
    user, got = _ask(bakery, SAUSAGE)
    _resp, html = _answer_html(bakery, user, got["job"])
    assert "data-assistant-plan" in html


def test_history_is_private_and_shown(ai_off, bakery):  # noqa: F811
    owner, _got = _ask(bakery, SAUSAGE)
    # уникальная пробная фраза: «Lieferung ein» стоит в подсказке поля (класс MEN)
    other, _got2 = _ask(bakery, "Wie stelle ich die Zustellung Quokka7 ein?")
    html = assistant_views.assistant_view(_req(bakery, user=owner)).content.decode()
    assert "data-assistant-history" in html and "Колбаса" in html
    assert "Quokka7" not in html  # чужой вопрос не виден


def test_history_shows_links_rechecked(ai_off, bakery, monkeypatch):  # noqa: F811
    owner, _got = _ask(bakery, SAUSAGE)
    monkeypatch.setattr(setup_assistant, "reachable", lambda request, name: False)
    html = assistant_views.assistant_view(_req(bakery, user=owner)).content.decode()
    assert "price_eur=50%2C00" not in html and "base_price=50%2C00" not in html


def test_clear_history_post_only_and_own_rows(ai_off, bakery):  # noqa: F811
    from django.http import HttpResponseNotAllowed

    owner, _got = _ask(bakery, SAUSAGE)
    other, _got2 = _ask(bakery, "Wie stelle ich die Lieferung ein?")
    resp = assistant_views.assistant_history_clear(_req(bakery, user=owner))
    assert isinstance(resp, HttpResponseNotAllowed)
    assistant_views.assistant_history_clear(_req(bakery, user=owner, method="post"))
    assert not AssistantTurn.objects.filter(user=owner).exists()
    assert AssistantTurn.objects.filter(user=other).exists()


def test_purge_after_retention(ai_off, bakery):  # noqa: F811
    owner, got = _ask(bakery, SAUSAGE)
    AssistantTurn.objects.filter(job=got["job"]).update(
        created_at=timezone.now() - timedelta(days=assistant_history.RETENTION_DAYS + 1)
    )
    _o, fresh = _ask(bakery, "Wie stelle ich die Lieferung ein?", user=owner)
    assert assistant_history.purge() >= 1
    assert not AssistantTurn.objects.filter(job=got["job"]).exists()
    assert AssistantTurn.objects.filter(job=fresh["job"]).exists()


def test_cap_per_user(ai_off, bakery, monkeypatch):  # noqa: F811
    monkeypatch.setattr(assistant_history, "MAX_PER_USER", 3)
    user = _user()
    for i in range(5):
        assistant_history.record("public", user.pk, f"{i:032x}", f"Frage {i}", {"state": "done"})
    rows = list(AssistantTurn.objects.filter(user=user).order_by("created_at"))
    assert len(rows) == 3 and rows[0].question == "Frage 2"


def test_viewing_history_writes_nothing(ai_off, bakery):  # noqa: F811
    owner, _got = _ask(bakery, SAUSAGE)
    before = AssistantTurn.objects.count()
    assistant_views.assistant_view(_req(bakery, user=owner))
    assert AssistantTurn.objects.count() == before
