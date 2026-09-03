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
    # products.html (каталог) — ОСОЗНАННО не здесь: вид переключает СЕРВЕРНЫЙ
    # ?ansicht= (MEN-24d), клиентский свитчер убран по фидбэку 2026-08-18
    # (на мобильном стоял вторым переключателем) — замок ниже.
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


def test_catalog_view_switching_is_server_side():
    """Фидбэк 2026-08-18: на каталоге вид переключает ТОЛЬКО серверный ?ansicht=
    (_price_view_links) — клиентского «список/плитка» рядом с ним быть не должно
    (на мобильном это был второй переключатель того же самого)."""
    body = (TEMPLATES / "products.html").read_text(encoding="utf-8")
    assert '_price_view_links.html" %}' in body  # серверный переключатель на месте
    assert "_grid_view.html" not in body  # клиентский дубль не вернулся


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


# --- фидбэк 2026-08-01: кнопка «Фильтры» и наплывание контента на карточке -------
def test_catalog_filter_panel_is_collapsible():
    """Панель фасетов каталога занимала на телефоне весь первый экран — у неё
    должна быть кнопка сворачивания, связанная с панелью по ключу."""
    body = (TEMPLATES / "products.html").read_text(encoding="utf-8")
    assert '_filter_toggle.html" with filter_key="catalog"' in body
    # DL-20: сама панель вынесена в партиал (рендерится над сеткой ИЛИ в боковой
    # колонке «Navigator»); связь по ключу держит партиал, страница его включает.
    assert 'include "storefront/_catalog_filters.html"' in body
    panel = (TEMPLATES / "_catalog_filters.html").read_text(encoding="utf-8")
    assert 'data-filter-panel="catalog"' in panel
    assert (TEMPLATES / "_filter_toggle.html").exists()


def test_product_card_reserves_room_for_the_floating_button():
    """Overlay-карточка: круглая кнопка добавления не должна срезать название и
    цену — под неё зарезервировано место справа."""
    body = (TEMPLATES / "_product_card.html").read_text(encoding="utf-8")
    overlay = body[body.index('storefront_card_style == "overlay"') : body.rindex("{% else %}")]
    assert "bottom-3 right-3" in overlay  # кнопка на месте
    assert "pr-16" in overlay  # и текст её обходит


def test_product_card_badge_clears_the_wishlist_heart():
    """Сердечко «отложить» и бейдж оба в левом верхнем углу — бейдж сдвигается,
    иначе читалось «♡опулярные»."""
    body = (TEMPLATES / "_product_card.html").read_text(encoding="utf-8")
    assert body.count('{% if storefront_wishlist_enabled %}{% firstof "left-12"') == 2
    assert "top-3 left-3 bg-amber-400" not in body  # жёсткой позиции не осталось


def test_listing_bar_view_block_present_in_all_listings():
    """DS-10: переключатель вида переехал из `listing_view` в `listing_bar_view`.

    Django МОЛЧА отбрасывает блок наследника, имени которого нет в родителе —
    забытый шаблон потерял бы переключатель без единой ошибки.
    """
    for name in ("products.html", "service_index.html", "stay_index.html", "event_index.html"):
        body = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "{% block listing_bar_view %}" in body, name
        assert "{% block listing_view %}" not in body, f"{name}: осиротевший блок"
    scaffold = (TEMPLATES / "listing.html").read_text(encoding="utf-8")
    assert "{% block listing_bar_view %}" in scaffold
    assert "{% block listing_bar_filters %}" in scaffold
