# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-4c: «покажи товары списком / 4 в ряд / шаблон …» — настройка страницы (план §12).

Замки: детектор без ИИ (подпись варианта из схемы page_settings или «N pro Reihe»),
вопрос/создание — не наше; недоступный вариант не предлагается; право website.edit;
оптимистичная проверка; откат возвращает прежнее (ключа не было — ключа нет).
"""

import pytest

from apps.core import assistant_pages
from apps.core.models import AssistantChange
from apps.core.tests.test_a4_actions import _apply, _html, _undo
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


def _layout(tenant):
    tenant.refresh_from_db()
    return (tenant.site_config or {}).get("catalog_layout")


def test_preisliste_phrase_sets_the_catalog_grid_and_undo_removes_it(ai_off, bakery):
    user, got = _ask(bakery, "Zeige die Produkte als Preisliste")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-apply-btn" in html and "Preisliste" in html
    assert _layout(bakery) is None  # до клика ничего
    _apply(bakery, user, got["job"], TAKE)
    assert _layout(bakery)["preset"] == "preisliste"
    _undo(bakery, user, got["job"])
    assert _layout(bakery) is None  # ключа не было — откат его убрал


@pytest.mark.parametrize(
    "phrase", ["Produkte 4 pro Reihe anzeigen", "покажи товары 4 в ряд", "show products 4 per row"]
)
def test_per_row_phrase(ai_off, bakery, phrase):
    items = assistant_pages.build(bakery, _user(), phrase)
    assert items and items[0]["target"]["pk"] == "catalog_layout"
    assert items[0]["values"]["value"] == "cols4"


def test_promo_card_form(ai_off, bakery):
    items = assistant_pages.build(bakery, _user(), "Zeige die Aktionen als Coupon")
    assert items[0]["target"]["pk"] == "promo_card_form" and items[0]["values"]["value"] == "coupon"


def test_question_and_create_are_not_page_settings(ai_off, bakery):
    assert not assistant_pages.intent(bakery, _user(), "Wie zeige ich die Produkte als Liste?")
    assert not assistant_pages.intent(bakery, _user(), "lege Produkt Liste an")


def test_unavailable_template_is_not_offered(ai_off, bakery):
    # «Regale» требует подкатегорий — у пустой пекарни недоступно (гейт композиций)
    assert not assistant_pages.build(bakery, _user(), "Zeige das Sortiment als Regale")


def test_no_website_right_no_button(ai_off, bakery, monkeypatch):
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, perm: perm != "website.edit" and real(user, perm)
    )
    user, got = _ask(bakery, "Zeige die Produkte als Preisliste")
    assert "data-assistant-apply-btn" not in _html(bakery, user, got["job"])
    _apply(bakery, user, got["job"], TAKE)
    assert _layout(bakery) is None


def test_changed_after_preview_is_refused(ai_off, bakery):
    from apps.core import page_settings

    user, got = _ask(bakery, "Zeige die Produkte als Preisliste")
    page_settings.write(bakery, "catalog_layout", "cols2")  # поменяли на экране кабинета
    _apply(bakery, user, got["job"], TAKE)
    assert _layout(bakery)["preset"] == "cols2" and not AssistantChange.objects.exists()


def test_ambiguous_match_has_no_button(ai_off, bakery, monkeypatch):
    real = assistant_pages._candidates

    def two(text, ts):
        found = real(text, ts)
        other = next(s for s in ts.settings if s.code == "catalog_page_style")
        return [*found, (found[0][0], other, other.choices[1])]

    monkeypatch.setattr(assistant_pages, "_candidates", two)
    items = assistant_pages.build(bakery, _user(), "Zeige die Produkte als Preisliste")
    assert items[0]["blocked"]


def test_select_offers_only_available_values(ai_off, bakery):
    user, got = _ask(bakery, "Zeige die Produkte als Preisliste")
    _apply(bakery, user, got["job"], {**TAKE, "f_0_value": "nonsense"})
    assert _layout(bakery) is None  # мусорное значение — ошибка поля, ничего не записано
