# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-5c: «und den Käsekuchen auch» (план §3 + правки архитектора §9 п. 7–8).

Замки: продолжение повторяет КОД действия прошлого хода этого же пользователя на новом
объекте; без прошлого хода, чужой ход, ход старше 15 минут, массовый ход, вопрос с «auch»,
два одноимённых — не продолжение; из прошлого хода не берутся ни цена, ни пункты.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog import writers
from apps.catalog.models import Product
from apps.core import assistant_router
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
FOLLOW = "und den Käsekuchen auch"


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


@pytest.fixture
def shop(bakery):
    a = writers.create_product(bakery, {"name_de": "Apfelstrudel", "base_price": "3,00"})
    k = writers.create_product(bakery, {"name_de": "Käsekuchen", "base_price": "3,20"})
    return a, k


@pytest.mark.parametrize(
    "phrase", [FOLLOW, "Käsekuchen тоже", "и Käsekuchen тоже", "Käsekuchen too"]
)
def test_hide_then_also(ai_off, bakery, shop, phrase):
    _a, k = shop
    user, _first = _ask(bakery, "скрой Apfelstrudel")
    assert assistant_router.classify(_req(bakery, user=user), phrase) == "followup"
    _u, got = _ask(bakery, phrase, user=user)
    _html(bakery, user, got["job"])
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get(pk=k.pk).is_active is False


def test_without_previous_turn_is_ordinary(ai_off, bakery, shop):
    assert assistant_router.classify(_req(bakery), FOLLOW) != "followup"


def test_other_users_turn_is_not_used(ai_off, bakery, shop):
    _ask(bakery, "скрой Apfelstrudel")
    assert assistant_router.classify(_req(bakery, user=_user()), FOLLOW) != "followup"


def test_old_turn_is_not_used(ai_off, bakery, shop):
    user, _first = _ask(bakery, "скрой Apfelstrudel")
    AssistantTurn.objects.update(created_at=timezone.now() - timedelta(minutes=20))
    assert assistant_router.classify(_req(bakery, user=user), FOLLOW) != "followup"


def test_question_with_auch_is_not_followup(ai_off, bakery, shop):
    user, _first = _ask(bakery, "скрой Apfelstrudel")
    phrase = "Kann ich den Käsekuchen auch als Gutschein verkaufen?"
    assert assistant_router.classify(_req(bakery, user=user), phrase) != "followup"


def test_price_followup_does_not_copy_price(ai_off, bakery, shop):
    user, _first = _ask(bakery, "Preis Apfelstrudel auf 3,50 €")
    _u, got = _ask(bakery, FOLLOW, user=user)
    html = _html(bakery, user, got["job"])
    assert "3,50" not in html.split("data-assistant-apply")[1]  # цена прошлого хода не взята


def test_bulk_turn_has_no_followup(ai_off, bakery, shop):
    cat = writers.create_category(bakery, {"name_de": "Kuchen"})
    writers.create_product(
        bakery, {"name_de": "Mohnkuchen", "base_price": "2", "category": str(cat.pk)}
    )
    user, _first = _ask(bakery, "скрой все товары категории Kuchen")
    assert assistant_router.classify(_req(bakery, user=user), FOLLOW) != "followup"
