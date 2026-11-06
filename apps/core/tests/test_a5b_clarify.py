# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-5b: уточняющий вопрос вместо тупика (план §2 + правки архитектора §9).

Замки: два одноимённых объекта → вопрос «какой?» с вариантами → выбор → пакет на нужный pk;
«alle Kuchen um 10 %» → «teurer/günstiger?» → цена посчитана правилом; вариант — только из
кэша задачи; двойной тап — один ответ; «Alles übernehmen» во время вопроса не применяет;
вопрос не пишется в историю, готовый пакет — один раз; после двух вопросов — прежний тупик.
"""

from decimal import Decimal

import pytest

from apps.catalog import writers
from apps.catalog.models import Product
from apps.core import assistant_ai, assistant_clarify, assistant_views
from apps.core.models import AssistantTurn
from apps.core.tests.test_a4_actions import _apply, _html
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

TAKE = {"items_present": "1", "take_0": "1"}


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


@pytest.fixture
def twins(bakery):
    kuchen = writers.create_category(bakery, {"name_de": "Kuchen"})
    torten = writers.create_category(bakery, {"name_de": "Torten"})
    a = writers.create_product(
        bakery, {"name_de": "Käsekuchen", "base_price": "3,20", "category": str(kuchen.pk)}
    )
    b = writers.create_product(
        bakery, {"name_de": "Käsekuchen", "base_price": "4,00", "category": str(torten.pk)}
    )
    return a, b


def _reply(tenant, user, job, option):
    return assistant_views.assistant_reply(
        _req(tenant, "post", {"option": option}, user=user, drawer=True), job
    )


def _entry(user, job):
    import django.core.cache as dj_cache  # подменённый фикстурой кэш — в момент вызова

    return dj_cache.cache.get(assistant_ai._job_key("public", user.pk, job))


def test_two_same_names_ask_which(ai_off, bakery, twins):
    a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-clarify" in html and "Torten" in html and "Kuchen" in html
    _reply(bakery, user, got["job"], f"product:{b.pk}")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-apply-btn" in html  # дальше — обычный предпросмотр
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get(pk=b.pk).is_active is False
    assert Product.objects.get(pk=a.pk).is_active is True


def test_price_clarify_keeps_price(ai_off, bakery, twins):
    _a, b = twins
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    _reply(bakery, user, got["job"], f"product:{b.pk}")
    _html(bakery, user, got["job"])
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get(pk=b.pk).base_price == Decimal("3.50")


def test_foreign_option_is_refused(ai_off, bakery, twins):
    other = writers.create_product(bakery, {"name_de": "Brot", "base_price": "2,00"})
    user, got = _ask(bakery, "скрой Käsekuchen")
    _reply(bakery, user, got["job"], f"product:{other.pk}")
    assert _entry(user, got["job"])["outcome"] == "ask"  # вопрос остался, ничего не собрано
    _reply(bakery, user, got["job"], "product:not-a-uuid")
    assert _entry(user, got["job"])["outcome"] == "ask"


def test_apply_during_question_does_nothing(ai_off, bakery, twins):
    a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.filter(is_active=False).count() == 0


def test_double_tap_answers_once(ai_off, bakery, twins):
    a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    _reply(bakery, user, got["job"], f"product:{b.pk}")
    _reply(bakery, user, got["job"], f"product:{a.pk}")  # второй тап по устаревшему вопросу
    entry = _entry(user, got["job"])
    assert entry["outcome"] == "actions"
    assert entry["actions"][0]["target"]["pk"] == str(b.pk)


def test_question_not_in_history_package_once(ai_off, bakery, twins):
    _a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    assert not AssistantTurn.objects.filter(job=got["job"]).exists()
    _reply(bakery, user, got["job"], f"product:{b.pk}")
    turn = AssistantTurn.objects.get(job=got["job"])
    assert turn.question == "скрой Käsekuchen" and "base" not in turn.entry


def test_direction_question_for_bulk(ai_off, bakery):
    cat = writers.create_category(bakery, {"name_de": "Kuchen"})
    p = writers.create_product(
        bakery, {"name_de": "Apfelkuchen", "base_price": "3,00", "category": str(cat.pk)}
    )
    user, got = _ask(bakery, "alle Kuchen um 10 %")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-clarify" in html
    _reply(bakery, user, got["job"], "down")
    _html(bakery, user, got["job"])
    _apply(bakery, user, got["job"], {"items_present": "1", "take_0": "1"})
    assert Product.objects.get(pk=p.pk).base_price == Decimal("2.70")


def test_at_most_two_rounds():
    items = [{"action": "x", "clarify": {"slot": "pick_target", "options": [{"id": 1}, {"id": 2}]}}]
    assert assistant_clarify.wrap("j", items, [], "q", 2) is not None
    assert assistant_clarify.wrap("j", items, [], "q", 3) is None
    done = assistant_clarify.done_entry("j", items, [])
    assert "clarify" not in done["actions"][0]


def test_reply_for_foreign_job_is_expired(ai_off, bakery, twins):
    _a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    stranger = _user()
    _reply(bakery, stranger, got["job"], f"product:{b.pk}")
    assert _entry(user, got["job"])["outcome"] == "ask"


def test_ai_ambiguous_asks_which(settings, isolated_ratelimit, bakery, twins):
    """A-4e: одноимённые в ответе модели — тот же вопрос, модель второй раз не зовётся."""
    from types import SimpleNamespace
    from unittest import mock

    from apps.core import assistant_ai_actions, tasks

    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_FAST = ["fake"]
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, assistant_ai_actions.TASK]
    phrase = "Den Käsekuchen bitte erstmal nicht mehr anbieten"
    user = _user()
    ctx = assistant_ai_actions.wants(_req(bakery, user=user), phrase)
    ref = next(i for i, (k, _p, n) in enumerate(ctx["objects"]) if "Käsekuchen" in n)
    data = {
        "not_action": False,
        "items": [{"action": "product.visibility", "ref": ref, "visible": False}],
    }
    gen = mock.patch.object(
        assistant_ai_actions, "generate", return_value=SimpleNamespace(data=data)
    )
    run = mock.patch.object(
        tasks.assistant_answer_job, "delay", side_effect=lambda **k: tasks.assistant_answer_job(**k)
    )
    with gen as g, run:
        _u, got = _ask(bakery, phrase, user=user)
        html = _html(bakery, user, got["job"])
        _reply(bakery, user, got["job"], f"product:{twins[1].pk}")
    assert "data-assistant-clarify" in html and g.call_count == 1
    assert _entry(user, got["job"])["actions"][0]["target"]["pk"] == str(twins[1].pk)


# ── правки по ревью ECC (django · security · a11y) ───────────────────────────────────


def test_builder_crash_does_not_lock_the_question(ai_off, bakery, twins):
    from unittest import mock

    _a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    with mock.patch.object(assistant_clarify, "answer", side_effect=RuntimeError("db down")):
        _reply(bakery, user, got["job"], f"product:{b.pk}")
    _reply(bakery, user, got["job"], f"product:{b.pk}")  # вторая попытка проходит
    assert _entry(user, got["job"])["outcome"] == "actions"


def test_repeat_after_success_shows_result(ai_off, bakery, twins):
    _a, b = twins
    user, got = _ask(bakery, "скрой Käsekuchen")
    _reply(bakery, user, got["job"], f"product:{b.pk}")
    resp = _reply(bakery, user, got["job"], f"product:{b.pk}")
    assert "data-assistant-apply-btn" in resp.content.decode()


def test_identical_labels_are_numbered(ai_off, bakery):
    cat = writers.create_category(bakery, {"name_de": "Kuchen"})
    for price in ("3,00", "4,00"):
        writers.create_product(
            bakery, {"name_de": "Käsekuchen", "base_price": price, "category": str(cat.pk)}
        )
    user, got = _ask(bakery, "скрой Käsekuchen")
    labels = [o["label"] for o in _entry(user, got["job"])["options"]]
    assert len(set(labels)) == 2 and labels[0].endswith("(1)")


def test_question_has_no_live_region_and_names_group(ai_off, bakery, twins):
    user, got = _ask(bakery, "скрой Käsekuchen")
    html = _html(bakery, user, got["job"])
    clarify = html.split("data-assistant-clarify", 1)[1]
    assert 'role="group"' in clarify and "aria-labelledby" in clarify
    assert 'role="status"' not in clarify.split("</form>")[0]
