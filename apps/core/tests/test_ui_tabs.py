"""KA-12 E9 (2026-10-30): вкладки кабинета — один стиль `ui-tab`.

Вкладки-ссылки — навигация (`<nav>` + `aria-current="page"`), не `role="tablist"`:
tablist требует `role="tab"`-детей с управляемыми панелями. Настоящие вкладки
(доска переключает панели JS) — `role="tab"` + `aria-selected`.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3] / "templates"

LINK_TABS = [
    "finance/_finance_tabs.html",
    "reviews/review_list.html",
    "inbox/list.html",
    "promotions/reservation_list.html",
    "tenant/media_library.html",
    "tenant/ablaeufe.html",
    "core/verkaeufe.html",
]


@pytest.mark.parametrize("name", LINK_TABS)
def test_link_tabs_use_ui_tab_and_aria_current(name):
    src = (ROOT / name).read_text()
    assert 'class="ui-tabs' in src
    assert 'class="ui-tab' in src
    assert 'aria-current="page"' in src
    # старые варианты заливки активной вкладки ушли
    assert "bg-indigo-600 text-white border-indigo-600" not in src
    assert not re.search(r'role="tablist"[^>]*>\s*(\{%[^%]*%\}\s*)*<a ', src)


def test_board_tabs_are_real_tabs():
    src = (ROOT / "core/_board_body.html").read_text()
    assert 'role="tab"' in src and "aria-selected=" in src and "aria-controls=" in src
    assert 'role="tabpanel"' in src
    # JS переключает состояние атрибутом, а не классами подчёркивания
    assert "border-indigo-600" not in src
    assert 'setAttribute("aria-selected"' in src
    assert "ArrowRight" in src


def test_finance_tabs_render_one_active():
    from django.template.loader import render_to_string

    html = render_to_string("finance/_finance_tabs.html", {"fin_tab": "bank"})
    assert html.count('aria-current="page"') == 1
    assert html.count('class="ui-tab"') == 6


def test_stays_toggle_tabs_use_ui_tab_and_aria_pressed():
    """Батч 2: JS-вкладки страницы номеров — тот же `ui-tab`; активное состояние
    несёт `aria-pressed`, JS больше не переключает цветовые классы."""
    src = (ROOT / "stays/units.html").read_text()
    for hook in ("data-pt-tab", "data-ut-tab", "data-st-tab"):
        assert re.search(hook + r'="[^"]+" aria-pressed="[^"]*"[^>]*class="ui-tab', src), hook
    assert 'classList.toggle("bg-indigo-600"' not in src
    css = (Path(__file__).resolve().parents[3] / "static/src/app.css").read_text()
    assert '.ui-tab[aria-pressed="true"]' in css
