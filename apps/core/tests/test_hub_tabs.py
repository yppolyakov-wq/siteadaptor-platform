"""S1 (упрощение кабинета): хаб-табы Sortiment + свод nav каталога 5→1."""

import pytest
from django.template import Context, Template

from apps.core import modules


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


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
