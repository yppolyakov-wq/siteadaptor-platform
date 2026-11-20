"""FB-33 M3-5b: плашки блока «Schnellzugriff» — скрыть и переименовать (ядро).

Замки: для КАЖДОГО набора (рукописные gastro/bakery/butcher/mode и реестр) и каждой плашки —
скрыть → плашка пропала, своя подпись → видна вместо стандартной, стандартная подпись
реестра == отрисованной; все скрыты — блока нет; данные чистятся (ключи набора, пустая и
стандартная подпись не хранятся, длина, мусор); смена набора сбрасывает скрытие и подписи;
осиротевшие подписи перевода не показываются; подписи экранированы.
"""

import pytest
from django.utils.html import escape

from apps.core import hero_tiles
from apps.core.tests.test_fb33_m35b_before import (
    DEAL_PK,
    block_html,
    make_deal,
    modules_on,
)
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
CASES = [(name, key) for name in hero_tiles.QUICK_LINK_SETS for key in hero_tiles.tile_keys(name)]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def live(monkeypatch):
    modules_on(monkeypatch, True)
    from apps.promotions.models import Promotion

    if not Promotion._base_manager.filter(pk=DEAL_PK).exists():
        make_deal()


def _tiles(html):
    return html.count("<a ")


def test_every_set_has_registered_tiles():
    assert set(hero_tiles.QUICK_LINK_TILES) == set(hero_tiles.QUICK_LINK_SETS)
    for name in hero_tiles.QUICK_LINK_SETS:
        keys = hero_tiles.tile_keys(name)
        assert keys and len(set(keys)) == len(keys), name
    for name, tiles in hero_tiles.HERO_TILE_SETS.items():
        assert [t["key"] for t in tiles] == list(hero_tiles.tile_keys(name))


@pytest.mark.parametrize("name,key", CASES)
def test_hide_and_rename_each_tile(live, name, key):
    full = block_html({"set": name}, True)
    label = dict((k, lab) for k, lab, _h in hero_tiles.QUICK_LINK_TILES[name])[key]
    # `{% trans %}` рукописных веток не экранирует «&», `{{ }}` реестра — экранирует
    assert escape(str(label)) in full or str(label) in full, (name, key)
    renamed = block_html({"set": name, "labels": {key: f"Eigen-{key}"}}, True)
    assert f"Eigen-{key}" in renamed and _tiles(renamed) == _tiles(full)
    hidden = block_html({"set": name, "hidden": [key]}, True)
    assert _tiles(hidden) == _tiles(full) - 1, (name, key)
    gone = block_html({"set": name, "hidden": [key], "labels": {key: f"Eigen-{key}"}}, True)
    assert f"Eigen-{key}" not in gone


@pytest.mark.parametrize("name", hero_tiles.QUICK_LINK_SETS)
def test_all_hidden_draws_no_block(live, name):
    html = block_html({"set": name, "hidden": list(hero_tiles.tile_keys(name))}, True)
    assert "data-block-quick-links" not in html


def test_gastro_grid_follows_the_visible_tiles(live):
    three = block_html({"set": "gastro"}, True)
    assert "sm:grid-cols-3" in three
    two = block_html({"set": "gastro", "hidden": ["menu"]}, True)
    assert "sm:grid-cols-2" in two and _tiles(two) == 2
    one = block_html({"set": "gastro", "hidden": ["menu", "deal"]}, True)
    assert "sm:max-w-sm" in one and _tiles(one) == 1


def test_clean_keeps_only_own_keys_and_custom_labels():
    clean = siteconfig._clean_cblock_data
    data = {
        "set": "aktionsmarkt",
        "hidden": ["newsletter", "evil", "deals", 5],
        "labels": {
            "deals": "Aktuelle Deals",
            "sortiment": "  Alles   ansehen ",
            "x": "y",
            "loyalty": "",
        },
    }
    assert clean("quick_links", data) == {
        "set": "aktionsmarkt",
        "hidden": ["deals", "newsletter"],  # порядок набора
        "labels": {"sortiment": "Alles ansehen"},  # стандартная и пустая не хранятся
    }
    assert clean("quick_links", {"set": "shop", "labels": {"deals": "x" * 99}})["labels"] == {
        "deals": "x" * hero_tiles.LABEL_MAX
    }
    assert clean("quick_links", {"set": "shop", "hidden": "deals", "labels": "x"}) == {
        "set": "shop"
    }
    assert clean("quick_links", {"set": "evil", "hidden": ["deals"]}) == {}


def test_update_from_window_and_set_change_resets():
    data = {"set": "aktionsmarkt"}
    fields = {
        "set": "aktionsmarkt",
        "show_deals": "1",
        "show_sortiment": "1",
        "label_loyalty": "Punkte",
    }
    got = hero_tiles.update_data(data, fields)
    assert got == {
        "set": "aktionsmarkt",
        "hidden": ["loyalty", "newsletter"],
        "labels": {"loyalty": "Punkte"},
    }
    # смена набора — присланные поля прежнего набора не применяются
    switched = hero_tiles.update_data(got, {**fields, "set": "shop", "show_loyalty": ""})
    assert switched == {"set": "shop"}


def test_orphan_translated_labels_are_not_shown(live):
    """Перевод подписи прежнего набора, оставшийся в оверлее, — не показывается."""
    html = block_html({"set": "shop", "labels": {"newsletter": "Сирота", "deals": "Скидки"}}, True)
    assert "Сирота" not in html and "Скидки" in html


def test_labels_are_escaped(live):
    html = block_html({"set": "shop", "labels": {"sortiment": "<script>x</script>"}}, True)
    assert "<script>x" not in html and "&lt;script&gt;" in html


def test_hidden_is_not_a_translation():
    assert "hidden" in siteconfig.NON_TRANSLATABLE_FIELDS


def test_studio_save_keeps_hidden_and_labels():
    from apps.core import site_schema

    saved = [{"key": "quick_links", "id": "q1", "data": {"set": "shop", "hidden": ["deals"]}}]
    posted = [{"key": "quick_links", "id": "q1", "data": {}}]
    assert site_schema.merge_structure(saved, posted)[0]["data"] == {
        "set": "shop",
        "hidden": ["deals"],
    }
