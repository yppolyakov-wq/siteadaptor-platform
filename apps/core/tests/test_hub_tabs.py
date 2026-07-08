"""S1/S2 (упрощение кабинета): хаб-табы Sortiment/Verkäufe + свод nav 5→1 и продаж."""

from types import SimpleNamespace

import pytest
from django.template import Context, Template

from apps.core import modules


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- S1: хаб «Sortiment» (каталог) ------------------------------------------
def test_catalog_nav_collapsed_to_one_hub():
    cat = modules.get_module("catalog")
    assert len(cat.nav_items) == 1  # 5 пунктов → 1 хаб
    assert cat.nav_items[0].nav_key == "catalog"
    assert modules.nav_task_label("catalog") == "Sortiment"


def _render(nav):
    return Template('{% load cabinet %}{% hub_tabs "catalog" %}').render(Context({"nav": nav}))


def test_hub_tabs_renders_all_five_subpages():
    html = _render("catalog")
    for lbl in ("Produkte", "Kategorien", "Lager", "Kombi", "Import"):
        assert lbl in html


def test_hub_tabs_marks_exactly_one_active():
    html = _render("stock")  # Lager активен
    assert html.count('aria-selected="true"') == 1
    # активный таб — именно Lager (ссылка на stock, подсвечена)
    assert 'aria-selected="true"' in html and "Lager" in html


def test_hub_tabs_empty_for_unknown_hub():
    assert (
        Template('{% load cabinet %}{% hub_tabs "nope" %}').render(Context({"nav": "x"})).strip()
        == ""
    )


# --- S2: хаб «Verkäufe» (доска + продажные списки/календари) -----------------
def _fake_tenant(disabled=()):
    return SimpleNamespace(disabled_modules=list(disabled), enabled_modules=[])


def _render_board(nav, tenant=None):
    ctx = {"nav": nav}
    if tenant is not None:
        ctx["request"] = SimpleNamespace(tenant=tenant)
    return Template('{% load cabinet %}{% hub_tabs "board" %}').render(Context(ctx))


def test_sales_nav_collapsed_into_verkauefe():
    # 5 продажных пунктов сайдбара убраны (доступны табами хаба «Verkäufe»).
    for key in ("orders", "booking", "stays", "events", "jobs"):
        assert modules.get_module(key).nav_items == (), key
    assert modules.nav_task_label("board") == "Verkäufe"


def test_board_hub_all_tabs_when_active():
    html = _render_board("board", _fake_tenant())  # ничего не выключено
    for lbl in ("Board", "Bestellungen", "Termine", "Übernachtungen", "Tickets", "Aufträge"):
        assert lbl in html, lbl
    assert html.count('aria-selected="true"') == 1  # активна вкладка Board


def test_board_hub_gates_inactive_modules():
    # Тенант без Übernachtung/Tickets — эти вкладки скрыты, остальные видны.
    html = _render_board("orders", _fake_tenant(disabled=["stays", "events"]))
    assert "Übernachtungen" not in html
    assert "Tickets" not in html
    for lbl in ("Board", "Bestellungen", "Termine", "Aufträge"):
        assert lbl in html, lbl
    assert html.count('aria-selected="true"') == 1  # активна вкладка Bestellungen


def test_board_hub_fail_open_without_request():
    # Без request/tenant в контексте (простой рендер) — гейт fail-open, все вкладки.
    html = _render_board("board")
    for lbl in ("Board", "Bestellungen", "Termine", "Übernachtungen", "Tickets", "Aufträge"):
        assert lbl in html, lbl
