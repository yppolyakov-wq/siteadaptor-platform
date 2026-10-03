"""LB-3d-2: блок «Liste» — туры, наборы, категории (план lb-list-blocks §13.4).

Замки написаны ДО кода. Источник описан в реестре (`siteconfig.LIST_SOURCES`):
поле фильтра — по смыслу (страна тура, категория каталога — общая у товаров, наборов
и категорий), карточка — та же, что у листинга источника (`_tour_card` с `tour`,
`_combo_card` с `c`, плитка категории), «Alle N →» — туда, где виден весь список с
тем же фильтром. У наборов и туров сортировок нет (порядок владельца), у категорий
нет и формы карточки — строки редактора скрыты, а не предлагают пустое.
"""

import itertools
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Category, Combo, Product
from apps.core import list_blocks
from apps.core.tests.test_list_block_sources import (
    _all_link,
    _block,
    _builder_html,
    _clean,
    _home,
    _row,
    _section,
    _tenant,
)
from apps.events.models import Event, Tour
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tour(title, country="", published=True, departures=1, **kw):
    tour = Tour.objects.create(
        title=title,
        slug=f"tour-{next(_N)}",
        country=country,
        is_published=published,
        **kw,
    )
    for i in range(departures):
        Event.objects.create(
            title=title,
            tour=tour,
            status=Event.STATUS_PUBLISHED,
            starts_at=timezone.now() + timedelta(days=20 + i),
            capacity=0,
            price_cents=150000 + i,
        )
    return tour


def _category(name, parent=None, active=True, **kw):
    return Category.objects.create(
        name={"de": name},
        slug=kw.pop("slug", None) or f"cat-{next(_N)}",
        parent=parent,
        is_active=active,
        **kw,
    )


def _product(category, name="Ware"):
    return Product.objects.create(
        name={"de": name}, base_price=Decimal("5.00"), is_active=True, category=category
    )


def _combo(name, category=None, **kw):
    kw.setdefault("price", Decimal("19.90"))
    return Combo.objects.create(name=name, category=category, **kw)


# ───────────────────────────── данные блока ─────────────────────────────


def test_tour_block_keeps_only_its_country():
    data = _clean(
        source="tours",
        country="Bosnien & Herzegowina",
        category="kaese",  # фильтр каталога
        collection="damen",  # подборка
        only="soon",  # быстрый фильтр событий
        sort="price_asc",  # у туров сортировок нет — порядок владельца
        card="overlay",
    )
    assert data == {"source": "tours", "country": "Bosnien & Herzegowina", "card": "overlay"}
    assert len(_clean(source="tours", country="x" * 200)["country"]) == 80


def test_combo_block_keeps_only_its_category():
    data = _clean(source="combos", category="torten", collection="z", only="sale", sort="x")
    assert data == {"source": "combos", "category": "torten"}


def test_category_block_keeps_its_parent_and_no_card_form():
    """У плитки категории форм карточки нет — «overlay» не хранится."""
    data = _clean(source="categories", category="kuchen", card="overlay", sort="newest")
    assert data == {"source": "categories", "category": "kuchen"}


def test_country_never_travels_into_a_translation():
    """Страна тура — БАЗОВОЕ значение (ключ группы /touren/), а не текст для перевода."""
    assert "country" in siteconfig.NON_TRANSLATABLE_FIELDS


def test_new_sources_have_no_sort_options():
    for source in ("tours", "combos", "categories"):
        assert not siteconfig.list_sort_keys(source), source
    sorts = list_blocks.sort_options(siteconfig.normalize({}))
    assert not any(
        src in srcs.split() for _k, _l, srcs in sorts for src in ("tours", "combos", "categories")
    )


# ───────────────────────────── туры ─────────────────────────────


def test_tour_block_shows_published_tours_and_filters_by_country():
    _tour("Manali", country="Indien", sort_order=1)
    _tour("Mustang", country="Nepal", sort_order=2)
    _tour("Ladakh", country="Indien", sort_order=3)
    _tour("Entwurf", country="Indien", published=False)
    cfg = siteconfig.normalize({})
    every = list_blocks.resolve(cfg, {"source": "tours"})
    assert [t.title for t in every["items"]] == ["Manali", "Mustang", "Ladakh"]
    india = list_blocks.resolve(cfg, {"source": "tours", "country": "Indien"})
    assert [t.title for t in india["items"]] == ["Manali", "Ladakh"]


def test_tour_block_renders_tour_cards_and_links_to_the_country_section():
    first = _tour("Manali", country="Indien", sort_order=1)
    _tour("Ladakh", country="Indien", sort_order=2)
    _tour("Mustang", country="Nepal", sort_order=3)
    body = _home(_tenant([_block(source="tours", country="Indien", limit=1)]))
    sec = _section(body, "tours")
    assert f'href="/tour/{first.slug}/"' in sec
    # «Alle N →» — туда, где виден весь список с тем же фильтром: секция страны
    assert _all_link(sec) == "/touren/#land-indien"
    assert "Indien" in sec  # заголовок по выборке — страна


def test_tour_block_queries_do_not_grow_with_cards():
    """Цена «ab» и число дат — из предзагрузки заездов, а не запроса на карточку."""
    counts = []
    for n in (2, 5):
        Tour.objects.all().delete()
        for i in range(n):
            _tour(f"Tour {n}-{i}", departures=2)
        t = _tenant([_block(source="tours")])
        with CaptureQueriesContext(connection) as ctx:
            body = _home(t)
        assert body.count('data-sf-list="tours"') == 1
        counts.append(len(ctx.captured_queries))
    assert counts[0] == counts[1]


def test_tour_block_needs_the_events_module():
    _tour("Manali", country="Indien")
    assert 'data-sf-list="tours"' in _home(_tenant([_block(source="tours")]))
    body = _home(_tenant([_block(source="tours")], disabled=["events"]))
    assert 'data-sf-list="tours"' not in body


# ───────────────────────────── наборы ─────────────────────────────


def test_combo_block_filters_by_category_and_links_to_kombi():
    torten = _category("Torten", slug="torten")
    brunch = _category("Brunch", slug="brunch")
    a = _combo("Torten-Set", category=torten, sort_order=1)
    _combo("Brunch-Set", category=brunch, sort_order=2)
    _combo("Zweites Torten-Set", category=torten, sort_order=3)
    _combo("Aus", category=torten, is_active=False)
    cfg = siteconfig.normalize({})
    items = list_blocks.resolve(cfg, {"source": "combos", "category": "torten"})["items"]
    assert [c.name for c in items] == ["Torten-Set", "Zweites Torten-Set"]
    body = _home(_tenant([_block(source="combos", category="torten", limit=1)]))
    sec = _section(body, "combos")
    assert f'href="/kombi/{a.pk}/"' in sec
    assert _all_link(sec) == "/kombi/?kategorie=torten"
    assert ">Torten<" in sec or "Torten</h2>" in sec  # заголовок — направление


def test_free_pool_combo_card_shows_no_zero_price():
    """Карточка набора — общая `_combo_card` (а не `sellable_card`, которая у
    свободной сборки печатала «0,00 €»)."""
    _combo("Freie Auswahl", price=Decimal("0.00"), free_pool=True)
    sec = _section(_home(_tenant([_block(source="combos")])), "combos")
    assert "data-combo-card" in sec
    assert "0,00" not in sec and "0.00" not in sec


def test_combo_block_title_follows_the_archetype():
    _combo("Menü 1")
    gastro = _tenant([_block(source="combos")])
    gastro.business_type = "cafe"
    gastro.save(update_fields=["business_type"])
    assert "Menü-Pakete" in _section(_home(gastro), "combos")
    shop = _tenant([_block(source="combos")])
    shop.business_type = "online_shop"
    shop.save(update_fields=["business_type"])
    assert "Sets &amp; Pakete" in _section(_home(shop), "combos")


# ───────────────────────────── категории ─────────────────────────────


def test_category_block_shows_directions_with_products_or_children():
    """Без категории — направления, как у /sortiment/ (только с товарами в поддереве,
    без мёртвых плиток); с категорией — её активные подкатегории."""
    a = _category("Alpha", sort_order=1)
    _product(a)
    _category("Leer", sort_order=2)  # без товаров — плитки нет
    c = _category("Charlie", sort_order=3)
    c1 = _category("Charlie Eins", parent=c, sort_order=1)
    _product(c1)
    _category("Charlie Aus", parent=c, active=False)
    _category("Inaktiv", active=False, sort_order=4)
    cfg = siteconfig.normalize({})
    roots = list_blocks.resolve(cfg, {"source": "categories"})["items"]
    assert [str(x) for x in roots] == ["Alpha", "Charlie"]
    kids = list_blocks.resolve(cfg, {"source": "categories", "category": c.slug})["items"]
    assert [str(x) for x in kids] == ["Charlie Eins"]
    gone = list_blocks.resolve(cfg, {"source": "categories", "category": "gibt-es-nicht"})
    assert gone["items"] == []


def test_category_block_of_a_deleted_parent_is_empty():
    parent = _category("Weg")
    child = _category("Kind", parent=parent)
    _product(child)
    slug = parent.slug
    parent.delete()  # мягкое удаление
    cfg = siteconfig.normalize({})
    assert list_blocks.resolve(cfg, {"source": "categories", "category": slug})["items"] == []


def test_category_block_renders_tiles_in_the_home_tile_shape():
    parent = _category("Kuchen", slug="kuchen")
    kid = _category(
        "Torten",
        parent=parent,
        slug="torten-x",
        sort_order=1,
        images=[{"url": "/media/t.jpg", "is_primary": True}],
    )
    _product(kid)
    _category("Tartes", parent=parent, slug="tartes-x", sort_order=2)
    t = _tenant([_block(source="categories", category="kuchen", limit=1)])
    cfg = dict(t.site_config)
    # стиль плитки секции «Kategorien» главной (сама секция выключена)
    for row in cfg["sections"]:
        if row.get("key") == "categories":
            row["style"] = "square"
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    sec = _section(_home(t), "categories")
    assert 'href="/sortiment/torten-x/"' in sec
    assert "aspect-square" in sec  # форма плитки — как у секции «Kategorien» главной
    assert "data-cat-edit" not in sec  # не редакторская плитка
    assert _all_link(sec) == "/sortiment/kuchen/"
    assert "Kuchen" in sec  # заголовок — родитель


def test_directions_block_links_to_the_catalog():
    a = _category("Alpha")
    _product(a)
    _category("Beta")
    b2 = _category("Beta Zwei", parent=Category.objects.get(name__de="Beta"))
    _product(b2)
    sec = _section(_home(_tenant([_block(source="categories", limit=1)])), "categories")
    assert _all_link(sec) == "/sortiment/"


# ───────────────────────────── редактор ─────────────────────────────


def test_source_select_offers_the_new_sources():
    _tour("Manali", country="Indien")
    block = _block(source="tours")
    row = _row(_builder_html(_tenant([block])), block["id"])
    select = row[row.index(f'name="cb_{block["id"]}_source"') :]
    select = select[: select.index("</select>")]
    for key in ("tours", "combos", "categories"):
        assert f'value="{key}"' in select, key
    assert re.search(r'value="tours"[^>]*selected', select)
    # без модуля событий туров не предлагаем
    other = _block(source="combos")
    row2 = _row(_builder_html(_tenant([other], disabled=["events"])), other["id"])
    assert 'value="tours"' not in row2[: row2.index("</select>")]


def test_editor_offers_countries_of_published_tours():
    _tour("Manali", country="Indien")
    _tour("Mustang", country="Nepal")
    _tour("Entwurf", country="Bhutan", published=False)
    block = _block(source="tours", country="Island")  # тура в Исландии больше нет
    row = _row(_builder_html(_tenant([block])), block["id"])
    select = row[row.index(f'name="cb_{block["id"]}_country"') :]
    select = select[: select.index("</select>")]
    assert 'value="Indien"' in select and 'value="Nepal"' in select
    assert 'value="Bhutan"' not in select  # неопубликованный тур — не вариант
    # значение блока остаётся выбранным (W0), с пометкой
    assert re.search(r'value="Island"[^>]*selected', select)


def test_category_select_serves_products_combos_and_categories():
    """Одно поле «Kategorie» на три источника; пустой пункт у категорий — свой
    («Hauptkategorien»: блок покажет направления, а не «все»)."""
    block = _block(source="categories")
    row = _row(_builder_html(_tenant([block])), block["id"])
    i = row.index(f'name="cb_{block["id"]}_category"')
    box = row[row.rindex("data-lb-src=", 0, i) : i]
    for src in ("products", "combos", "categories"):
        assert src in box[: box.index(">")], src
    select = row[i : row.index("</select>", i)]
    empties = re.findall(r'<option value=""([^>]*)>([^<]*)<', select)
    assert len(empties) == 2
    own = [label for attrs, label in empties if "selected" in attrs]
    assert own and "Hauptkategorien" in own[0]


def test_rows_without_choices_are_hidden_for_the_source():
    """Сортировки нет у туров/наборов/категорий, формы карточки — у категорий: строки
    скрыты по реестру (STU-9 — не предлагать пустого), а поля остаются в DOM (W0)."""
    block = _block(source="categories")
    row = _row(_builder_html(_tenant([block])), block["id"])
    bid = block["id"]

    def box_of(name):
        i = row.index(f'name="cb_{bid}_{name}"')
        start = row.rindex("data-lb-src=", 0, i)
        return row[start : row.index(">", start)]

    sort_box = box_of("sort")
    assert "categories" not in sort_box and "products" in sort_box and "hidden" in sort_box
    card_box = box_of("card")
    assert "categories" not in card_box and "tours" in card_box and "hidden" in card_box
    hint = list_blocks.view_hint(siteconfig.normalize({}), {"source": "categories"})
    assert "categories" not in hint["card_sources"].split()
    assert "categories" not in hint["sort_sources"].split()
