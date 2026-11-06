# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS AS-1: помощник — одно поле наверху (план docs/ais-as1-one-field-plan-2026-11-06.md).

Замки: поле вопроса — первая форма вкладки KI, отдельного поиска и кнопки «anlegen» нет; «где
настроить» приходит в ответе (и с правами смотрящего); задачи вместо названий проверок; цвет
диагноза по смыслу; сводка «Status Ihres Shops»; подсказки-кнопки не меняют данных.
"""

import re

import pytest

from apps.core import assistant, assistant_ai, assistant_views, diagnoses, readiness
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _ask,
    _clean,
    _req,
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


def _drawer(tenant, user=None, query=""):
    return assistant_views.assistant_view(
        _req(
            tenant, "get", dict(x.split("=") for x in query.split("&") if x), user=user, drawer=True
        )
    ).content.decode()


def test_ask_field_is_first_and_alone(ai_off, bakery):
    html = _drawer(bakery)
    tab = html[html.index('data-assistant-tab="ki"') :]
    first_form = tab[tab.index("<form") : tab.index("</form>")]
    assert "data-assistant-ask" in first_form and 'name="frage"' in first_form
    assert 'role="search"' not in html and "data-assistant-anlegen" not in html
    assert tab.index("data-assistant-ask") < tab.index("data-assistant-status")


def test_status_card_is_collapsed_with_counts(ai_off, bakery):
    html = _drawer(bakery)
    status = re.search(r"<details[^>]*data-assistant-status[^>]*>", html).group(0)
    assert " open" not in status
    assert "zu erledigen" in html  # у пустого бизнеса нет контактов


def test_status_card_opens_for_heavy_check(ai_off, bakery):
    heavy = next(d.key for d in diagnoses.REGISTRY if d.cost == diagnoses.HEAVY)
    html = _drawer(bakery, query=f"pruefen={heavy}")
    assert re.search(r"<details[^>]*data-assistant-status[^>]* open", html)


def test_chips_are_safe_phrases(ai_off, bakery):
    html = _drawer(bakery)
    chips = re.findall(r'value="([^"]+)" formnovalidate data-assistant-chip', html)
    assert len(chips) == 3
    from apps.core import assistant_router

    keys = {assistant_router.classify(_req(bakery), c) for c in assistant.chips(_req(bakery))}
    assert keys <= {"answer", "escalate"}  # ни одна подсказка не меняет данные


def test_where_comes_with_the_answer(ai_off, bakery):
    user, got = _ask(bakery, "Wo stelle ich die Öffnungszeiten ein?")
    entry = assistant_ai.job_state(_req(bakery, user=user), got["job"])
    assert entry["where"] and all("url" not in w for w in entry["where"])
    ans = assistant_ai.present(_req(bakery, user=user), entry)
    assert ans["where"] and ans["where"][0]["link"].url
    from apps.core.tests.test_a4_actions import _html

    assert "data-assistant-where" in _html(bakery, user, got["job"])


def test_where_for_text_ignores_question_words(bakery):
    assert assistant.where_for_text(_req(bakery), "Wie kann ich das einstellen?") == []


def test_where_links_use_viewer_rights(bakery):
    refs = [{"url_name": "settings", "query": "", "label": "X", "area": ""}, {"url_name": "nope"}]
    got = assistant.where_links(_req(bakery), refs)
    assert [w["text"] for w in got] == ["X"]


def test_readiness_todo_labels():
    by_key = {i.key: i for i in readiness.REGISTRY}
    assert str(by_key["email"].todo) == "E-Mail-Adresse bestätigen"
    assert str(by_key["waren.allergens"].todo) == "Allergene bei allen Gerichten angeben"


@pytest.mark.parametrize(
    "levels,tone",
    [
        (None, "pending"),
        ([diagnoses.OK], "ok"),
        ([diagnoses.OK, diagnoses.PROBLEM], "problem"),
        ([diagnoses.UNKNOWN], "unknown"),
        ([diagnoses.INFO], "info"),
    ],
)
def test_diagnosis_tone(levels, tone):
    found = None if levels is None else [{"level": lv} for lv in levels]
    assert assistant._tone(found) == tone


def test_status_counts_distinct():
    same = {"level": diagnoses.PROBLEM, "text": "E-Mail bestätigen"}
    here = [same, {"level": diagnoses.UNKNOWN, "text": "a"}]
    top = [
        dict(same),
        {"level": diagnoses.INFO, "text": "b"},
        {"level": diagnoses.UNKNOWN, "text": "c"},
    ]
    cards = [{"tone": "problem"}, {"tone": "unknown"}, {"tone": "info"}, {"tone": "ok"}]
    # один и тот же пункт на экране и в «Gerade wichtig» — одна проблема
    assert assistant.status_counts(here, top, cards) == {"fix": 2, "unknown": 3}


def test_where_ignores_filler_words(bakery):
    assert assistant.where_for_text(_req(bakery), "Ich möchte eine Sache bitte") == []
