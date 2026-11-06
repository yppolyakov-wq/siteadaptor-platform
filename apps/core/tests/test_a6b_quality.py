# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-6b: журнал маршрута, счётчики исходов (только коды) и отчёт `assistant_report`.

Замки (план docs/ais-a6-quality-plan-2026-11-06.md §5): неизвестный код/маршрут → other, в ключе
нет текста фразы, сбой Redis не бросает; запись задачи несёт `route`; отчёт считает доли и пакеты
точно; samples чистит контакты и не берёт ответы ИИ; `--samples` без `--schema` — отказ.
"""

import io
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.core import assistant_ai, assistant_quality, assistant_stats
from apps.core.models import AssistantChange, AssistantTurn
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _ask,
    _clean,
    _urlconf,
    _user,
    bakery,
    isolated_ratelimit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


def _cache():
    import django.core.cache as dj_cache

    return dj_cache.cache


def test_bump_whitelists_route_and_code_without_text():
    assistant_stats.bump("s1", "Käsekuchen ausblenden", "Mein Passwort")
    assistant_stats.bump("s1", "bulk", "quota")
    assistant_stats.bump("s1", "bulk", "quota")
    got = assistant_stats.read("s1", days=1)
    assert got == {("other", "other"): 1, ("bulk", "quota"): 2}
    keys = [k for k in _cache()._cache if "asst:st:" in str(k)]
    assert keys and not any("Käse" in str(k) or "Passwort" in str(k) for k in keys)


def test_bump_and_read_never_raise_when_redis_fails():
    broken = mock.Mock(**{"add.side_effect": OSError, "get_many.side_effect": OSError})
    with mock.patch("django.core.cache.cache", broken):
        assistant_stats.bump("s1", "bulk", "ok")
        assert assistant_stats.read("s1") == {}


def test_read_is_per_schema():
    assistant_stats.bump("s1", "answer", "quota")
    assert assistant_stats.read("s2", days=1) == {}


def test_route_goes_into_job_entry_and_counter(ai_off, bakery):
    user, got = _ask(bakery, "Ich möchte mit einem Menschen sprechen")
    entry = _cache().get(assistant_ai._job_key(assistant_ai._schema_name(), user.pk, got["job"]))
    assert entry["route"] == "escalate"
    assert assistant_stats.read(assistant_ai._schema_name(), days=1) == {("escalate", "ok"): 1}


def test_route_is_reset_after_handler(ai_off, bakery):
    _ask(bakery, "Ich möchte mit einem Menschen sprechen")
    assert assistant_ai.ROUTE.get() == ""


def _turn(user, kind, entry, q="Frage", job=None, days_ago=0):
    t = AssistantTurn.objects.create(
        user=user,
        job=job or timezone.now().strftime("%f") + kind,
        kind=kind,
        question=q,
        entry=entry,
    )
    if days_ago:
        AssistantTurn.objects.filter(pk=t.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return t


def test_summarize_counts_routes_and_packages(bakery):
    user = _user()
    _turn(user, "actions", {"route": "changes", "dropped": 2, "clarify_rounds": 1}, job="j1")
    _turn(user, "actions", {"route": "changes"}, job="j2")
    _turn(user, "fallback", {"route": "ai_actions", "code": "unclear"}, job="j3")
    _turn(user, "answer", {"route": "answer"}, job="j4", days_ago=40)  # вне периода
    now = timezone.now()
    AssistantChange.objects.create(user=user, job="j1", undo_until=now, undone_at=now)
    AssistantChange.objects.create(user=user, job="j2", undo_until=now)
    rep = assistant_quality.summarize("public", now - timedelta(days=30))
    assert rep["turns"] == 3 and rep["misses"] == 1
    assert rep["routes"] == {"ai_actions": {"unclear": 1}, "changes": {"actions": 2}}
    assert rep["actions"] == {"proposed": 2, "applied": 2, "undone": 1}
    assert rep["avg_dropped"] == 1.0 and rep["clarify_rounds"] == 1


def test_samples_scrub_contacts_and_skip_ai_answers(bakery):
    user = _user()
    _turn(user, "fallback", {"code": "unknown"}, q="Mail an max@example.com bitte", job="s1")
    _turn(user, "answer", {"code": "unknown"}, q="Antwort-Frage", job="s2")
    _turn(user, "actions", {}, q="verstanden", job="s3")
    got = assistant_quality.samples("public", timezone.now() - timedelta(days=1), 10)
    assert len(got) == 1 and "max@example.com" not in got[0]
    assert all(len(s) <= assistant_quality.SAMPLE_MAX for s in got)


def test_report_samples_need_schema():
    with pytest.raises(CommandError):
        call_command("assistant_report", samples=5)


def test_report_json(bakery):
    _turn(_user(), "fallback", {"route": "answer", "code": "unknown"}, job="r1")
    out = io.StringIO()
    call_command("assistant_report", schema="public", json=True, stdout=out)
    data = json.loads(out.getvalue())
    assert data[0]["turns"] == 1 and data[0]["routes"] == {"answer": {"unknown": 1}}


def test_report_unknown_schema():
    with pytest.raises(CommandError):
        call_command("assistant_report", schema="nope")


def test_background_answer_keeps_route_and_counts_final_code(bakery):
    """Фоновая задача пишет итог вне `route()`: маршрут берётся из pending-записи."""
    from apps.ai.errors import AIUnavailable

    schema, job, pk = "public", "a" * 32, _user().pk
    entry = {
        "state": "pending",
        "route": "answer",
        "ctx": {},
        "lang": "de",
        "q": "x",
        "prompt": "p",
        "schema": {},
        "system": "s",
        "v": assistant_ai.ENTRY_V,
    }
    _cache().set(assistant_ai._job_key(schema, pk, job), entry, 60)
    with mock.patch.object(assistant_ai, "generate", side_effect=AIUnavailable()):
        assistant_ai.run_job(schema=schema, user_pk=pk, job=job)
    stored = _cache().get(assistant_ai._job_key(schema, pk, job))
    assert stored["route"] == "answer" and stored["code"] == AIUnavailable.code
    assert assistant_stats.read(schema, days=1) == {("answer", AIUnavailable.code): 1}


def test_timeout_keeps_route(ai_off, bakery):
    from apps.core.tests.test_assistant_a2 import _req

    user = _user()
    schema, job = assistant_ai._schema_name(), "b" * 32
    _cache().set(
        assistant_ai._job_key(schema, user.pk, job),
        {"state": "pending", "deadline": 1, "route": "answer", "v": assistant_ai.ENTRY_V},
        60,
    )
    got = assistant_ai.job_state(_req(bakery, user=user), job)
    assert got["code"] == "timeout" and got["route"] == "answer"
    assert assistant_stats.read(schema, days=1) == {("answer", "timeout"): 1}


def test_report_skips_tenants_without_history_when_listing_all(bakery):
    out = io.StringIO()
    with mock.patch.object(assistant_stats, "read") as read:
        call_command("assistant_report", json=True, stdout=out)
    read.assert_not_called()
