# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-5a: роутер помощника (план §1).

Замки: каждая класса фраз попадает ровно в ту ветку, что и при прежней цепочке if/elif во
вьюхе (паритет), порядок реестра = приоритет, во вьюхе нет вызовов `*.intent(` — новая ветка
добавляется только в `HANDLERS`.
"""

import ast
import inspect

import pytest

from apps.catalog import writers
from apps.core import assistant_router, assistant_views
from apps.core.tests.test_a4e_ai_actions import ai_on  # noqa: F401
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
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


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


RULES = [
    ("alle Kuchen 10 % teurer", "bulk"),
    ("скрой все товары категории Kuchen", "bulk"),
    ("Preis Käsekuchen auf 3,50 €", "changes"),
    ("скрой Käsekuchen", "changes"),
    ("blende Kuchen aus", "changes"),
    ("verschiebe Apfelstrudel nach Kuchen", "changes"),
    ("Produkte 4 pro Reihe anzeigen", "pages"),
    ("покажи товары 4 в ряд", "pages"),
    ("Kategorie Torten anlegen", "create"),
    ("neues Produkt Sachertorte 4,20 €", "create"),
    ("Wie ändere ich den Preis von Käsekuchen?", "answer"),
    ("Mein Shop wird nicht angezeigt", "answer"),
    ("", "answer"),
]


@pytest.mark.parametrize(("phrase", "key"), RULES)
def test_rules_routing_parity_without_ai(ai_off, shop, phrase, key):
    assert assistant_router.classify(_req(shop), phrase) == key


AI = [
    ("Den Apfelstrudel bitte erstmal nicht mehr anbieten", "ai_actions"),
    ("Kategorie Torten anlegen und Apfelstrudel ausblenden", "mixed"),
    ("Kategorie Torten anlegen", "create"),  # чистое создание — по-прежнему правила
    ("Preis Käsekuchen auf 3,50 €", "changes"),  # правила сильнее ИИ
    ("Mein Shop wird nicht angezeigt", "answer"),  # без признака действия — вопрос
]


@pytest.mark.parametrize(("phrase", "key"), AI)
def test_routing_with_ai(ai_on, shop, phrase, key):
    assert assistant_router.classify(_req(shop), phrase) == key


def test_answer_is_last_and_keys_unique():
    keys = [h.key for h in assistant_router.HANDLERS]
    assert keys[-1] == "answer" and len(keys) == len(set(keys))


def test_first_match_wins(ai_off, shop, monkeypatch):
    """Ровно один обработчик на фразу: дальше первого попадания роутер не спрашивает."""
    asked = []

    def spy(key, result):
        def intent(request, q):
            asked.append(key)
            return result

        return intent

    handlers = tuple(
        assistant_router.Handler(h.key, spy(h.key, True if h.key == "pages" else None), h.handle)
        for h in assistant_router.HANDLERS
    )
    monkeypatch.setattr(assistant_router, "HANDLERS", handlers)
    assert assistant_router.classify(_req(shop), "irgendwas") == "pages"
    assert asked == ["bulk", "changes", "pages"]


def test_view_has_no_intent_calls():
    """Ветки — только в реестре: вьюха не зовёт детекторы сама."""
    tree = ast.parse(inspect.getsource(assistant_views.assistant_ask))
    calls = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert not [c for c in calls if c in ("intent", "create_intent", "wants", "mixed")]
