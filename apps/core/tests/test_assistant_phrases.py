# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-6a: эталонные фразы — каждая уходит в ожидаемый обработчик роутера (план A-6 §3).

Замки: у каждого обработчика есть фраза на каждом из 5 языков; дублей нет; маршрут
совпадает — без ИИ для правил, с включённой задачей для ИИ-веток, после хода для продолжений.
"""

import pytest

from apps.catalog import writers
from apps.core import assistant_router
from apps.core.assistant_phrases import LANGS, PHRASES, PREV
from apps.core.tests.test_a4e_ai_actions import ai_on  # noqa: F401
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
def shop(bakery):
    kuchen = writers.create_category(bakery, {"name_de": "Kuchen"})
    writers.create_product(
        bakery, {"name_de": "Käsekuchen", "base_price": "3,20", "category": str(kuchen.pk)}
    )
    writers.create_product(bakery, {"name_de": "Apfelstrudel", "base_price": "3,00"})
    return bakery


def test_every_handler_has_every_language():
    keys = {h.key for h in assistant_router.HANDLERS}
    have = {(p.route, p.lang) for p in PHRASES}
    missing = sorted((k, lang) for k in keys for lang in LANGS if (k, lang) not in have)
    assert not missing


def test_no_duplicate_phrases():
    texts = [p.text.casefold() for p in PHRASES]
    assert len(texts) == len(set(texts))


@pytest.mark.parametrize("phrase", [p for p in PHRASES if p.mode == "rules"], ids=lambda p: p.text)
def test_rules_route(settings, isolated_ratelimit, shop, phrase):
    settings.AI_ENABLED = False
    assert assistant_router.classify(_req(shop), phrase.text) == phrase.route


@pytest.mark.parametrize("phrase", [p for p in PHRASES if p.mode == "ai"], ids=lambda p: p.text)
def test_ai_route(ai_on, shop, phrase):
    assert assistant_router.classify(_req(shop), phrase.text) == phrase.route


@pytest.mark.parametrize(
    "phrase", [p for p in PHRASES if p.mode == "followup"], ids=lambda p: p.text
)
def test_followup_route(settings, isolated_ratelimit, shop, phrase):
    settings.AI_ENABLED = False
    user, _got = _ask(shop, PREV)
    assert assistant_router.classify(_req(shop, user=user), phrase.text) == phrase.route


def test_eval_command_rules_path(settings, isolated_ratelimit, bakery):
    """Команда прогоняет набор в схеме бизнеса и ничего не оставляет в базе."""
    from io import StringIO

    from django.core.management import call_command

    from apps.catalog.models import Product
    from apps.core.models import Membership

    settings.AI_ENABLED = False
    Membership.objects.filter(user=_user()).update(role=Membership.ROLE_OWNER)
    out = StringIO()
    call_command("assistant_eval", "--schema", bakery.schema_name, stdout=out)
    text = out.getvalue()
    assert "Итого: 100%" in text and "bulk" in text
    assert not Product.objects.exists()  # тестовые товары откатились


def test_eval_command_ai_needs_key(settings, isolated_ratelimit, bakery):
    from django.core.management import CommandError, call_command

    settings.AI_ENABLED = False
    with pytest.raises(CommandError):
        call_command("assistant_eval", "--schema", bakery.schema_name, "--ai")


def test_eval_refuses_name_collision(settings, isolated_ratelimit, shop):
    from django.core.management import CommandError, call_command

    settings.AI_ENABLED = False
    with pytest.raises(CommandError):
        call_command("assistant_eval", "--schema", shop.schema_name)


def test_eval_min_is_command_error(settings, isolated_ratelimit, bakery, monkeypatch):
    from django.core.management import CommandError, call_command

    from apps.core import assistant_router
    from apps.core.models import Membership

    settings.AI_ENABLED = False
    Membership.objects.filter(user=_user()).update(role=Membership.ROLE_OWNER)
    monkeypatch.setattr(assistant_router, "classify", lambda request, raw: "answer")
    with pytest.raises(CommandError):
        call_command("assistant_eval", "--schema", bakery.schema_name, "--min", "0.99")


def test_eval_ai_calls_model_outside_rollback(ai_on, bakery, monkeypatch):
    """--ai: модель зовётся после отката (учёт AIUsage не теряется), ответ проверяется без базы."""
    from io import StringIO
    from types import SimpleNamespace

    from django.core.management import call_command

    from apps.core.models import Membership

    Membership.objects.filter(user=_user()).update(role=Membership.ROLE_OWNER)
    calls = []

    def fake(task, prompt, **kw):
        from django.db import connection

        calls.append(connection.in_atomic_block)
        return SimpleNamespace(data={"not_action": False, "items": []})

    monkeypatch.setattr("apps.ai.api.generate", fake)
    out = StringIO()
    call_command(
        "assistant_eval",
        "--schema",
        bakery.schema_name,
        "--ai",
        "--route",
        "ai_actions",
        stdout=out,
    )
    assert calls and "0 Punkte" in out.getvalue()
