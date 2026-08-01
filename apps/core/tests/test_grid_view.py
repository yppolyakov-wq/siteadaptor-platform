"""Фидбэк владельца 2026-08-01: переключатель вида «список ↔ плитка» — на ВСЕХ
сетках витрины (главная, акции, услуги, каталог/категории, номера, события).

Замок держит связку: у сетки есть `data-grid="<ключ>"`, а рядом — кнопки с тем же
ключом. Без пары переключатель молча ничего не переключает.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "storefront"

# файл → ключи сеток, которые обязаны быть переключаемыми
EXPECTED = {
    "sections/_promotions.html": {"promotions"},
    "sections/_products.html": {"products"},
    "sections/_services.html": {"services"},
    "sections/_categories.html": {"categories"},
    "sections/_stay_rooms.html": {"stay_rooms"},
    "sections/_events.html": {"events"},
    "sections/_blog.html": {"blog"},
    "promotions_list.html": {"promo_list"},
    "service_index.html": {"services"},
    "products.html": {"catalog"},
    "stay_index.html": {"stay_rooms"},
    "event_index.html": {"events"},
}


@pytest.mark.parametrize("name,keys", sorted(EXPECTED.items()))
def test_grid_has_matching_view_switcher(name, keys):
    body = (TEMPLATES / name).read_text(encoding="utf-8")
    grids = set(re.findall(r'data-grid="([a-z_]+)"', body))
    switched = set(re.findall(r'_grid_view\.html" with grid_key="([a-z_]+)"', body))
    assert keys <= grids, f"{name}: сетка без data-grid {keys - grids}"
    assert keys <= switched, f"{name}: нет переключателя для {keys - switched}"


def test_switcher_and_script_exist():
    """Партиал кнопок и общий обработчик — на месте, обработчик подключён в _base."""
    assert (TEMPLATES / "_grid_view.html").exists()
    assert (TEMPLATES / "_grid_view_script.html").exists()
    base = (TEMPLATES / "_base.html").read_text(encoding="utf-8")
    assert "_grid_view_script.html" in base


def test_list_mode_class_is_defined_in_css():
    """Режим списка держится на одном CSS-классе поверх любых grid-cols-*."""
    css = (TEMPLATES.parents[1] / "static" / "src" / "app.css").read_text(encoding="utf-8")
    assert "[data-grid].is-list" in css
