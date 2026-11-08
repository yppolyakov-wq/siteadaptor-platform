"""Wegweiser — композиция корня каталога `/sortiment/` по макету S1 (2026-11-08).

План — `docs/sortiment-wegweiser-plan-2026-11-08.md`. Замки написаны ДО кода.
"""

import itertools
import re
from decimal import Decimal

import pytest
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Category, Product
from apps.core import compositions
from apps.core.page_presets import apply_page_preset
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_SLUG = itertools.count()


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cat(name, parent=None):
    return Category.objects.create(name={"de": name}, slug=f"ww-{next(_SLUG)}", parent=parent)


def _product(cat, name, price="9.90", badge=""):
    return Product.objects.create(
        name={"de": name}, category=cat, base_price=Decimal(price), is_active=True, badge=badge
    )


def _tree(roots=3, subs=2, per=2, neu_in_first=0):
    """`roots` направлений, у каждого `subs` подкатегорий по `per` товаров."""
    out = []
    for i in range(roots):
        root = _cat(f"Bereich {i}")
        for j in range(subs):
            sub = _cat(f"Unter {i}-{j}", parent=root)
            for k in range(per):
                badge = "neu" if i == 0 and (j * per + k) < neu_in_first else ""
                _product(sub, f"Artikel {i}-{j}-{k}", badge=badge)
        out.append(root)
    return out


def _get(path="/sortiment/", style="wegweiser", cfg=None):
    tenant = TenantFactory.build()
    config = dict(cfg or {})
    if style:
        config["catalog_page_style"] = style
    tenant.site_config = config
    request = RequestFactory().get(path)
    request.tenant = tenant
    request.session = {}
    return public_views.product_list(request)


def _body(*a, **kw):
    return _get(*a, **kw).content.decode()


# ─────────────────────────── реестр ───────────────────────────


def test_wegweiser_is_a_root_only_composition():
    assert "wegweiser" in compositions.valid_for("catalog")
    assert "wegweiser" not in compositions.valid_for("category")
    assert siteconfig.normalize({"catalog_page_style": "wegweiser"})["catalog_page_style"] == (
        "wegweiser"
    )


def test_standard_root_has_no_wegweiser_markup():
    _tree()
    body = _body(style="")
    # разметка, а не голый маркер: селектор `[data-wegweiser-focus]` живёт в общем JS
    assert not re.search(r"<[^>]+\sdata-wegweiser-", body)


# ─────────────────────────── направления ───────────────────────────


def test_departments_come_before_owner_blocks_and_the_grid():
    """Дефект прода: карусели «Neu»/«Reduziert» пресета стояли НАД направлениями."""
    _tree()
    cfg = {}
    apply_page_preset(cfg, "catalog", "neu_sale")
    body = _body(cfg=cfg)
    deps = body.index("data-wegweiser-departments")
    assert deps < body.index('data-grid="catalog"')
    assert deps < body.index("data-pb-host")
    # плитки направлений не задваиваются старым списком категорий
    assert 'data-grid="categories"' not in body


def test_department_tile_shows_count_subcategories_and_new():
    roots = _tree(roots=2, subs=3, per=2, neu_in_first=2)
    body = _body()
    tile = re.search(
        rf'<article[^>]*data-wegweiser-dept="{roots[0].slug}".*?</article>', body, re.S
    ).group(0)
    assert "Bereich 0" in tile
    assert ">6<" in tile.replace(" ", "")  # 3 подкатегории × 2 товара
    assert "Unter 0-0" in tile and "Unter 0-2" in tile
    assert "data-wegweiser-new" in tile
    other = re.search(
        rf'<article[^>]*data-wegweiser-dept="{roots[1].slug}".*?</article>', body, re.S
    ).group(0)
    assert "data-wegweiser-new" not in other  # «neu: 0» не печатаем


def test_summary_line_counts_articles_departments_and_new():
    _tree(roots=2, subs=1, per=3, neu_in_first=1)
    summary = re.search(r"<p[^>]*data-wegweiser-summary[^>]*>(.*?)</p>", _body(), re.S).group(1)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", summary))
    assert "6" in text and "2" in text and "1" in text
    assert "reduziert" not in text  # нулевые части не печатаем


def test_department_queries_do_not_grow_with_departments():
    _tree(roots=4)
    with CaptureQueriesContext(connection) as small:
        _get()
    _tree(roots=8)
    with CaptureQueriesContext(connection) as big:
        _get()
    assert len(big) == len(small)


@pytest.mark.parametrize("roots", [0, 1])
def test_too_few_departments_render_without_tiles(roots):
    _tree(roots=roots)
    response = _get()
    assert response.status_code == 200
    assert "data-wegweiser-departments" not in response.content.decode()


def test_search_or_filter_turns_wegweiser_into_a_plain_result():
    """Фильтр = результат (O-7): покупатель ищет — ему нужна выдача, а не витрина."""
    _tree()
    for path in ("/sortiment/?q=Artikel", "/sortiment/?badge=neu", "/sortiment/?sale=1"):
        assert "data-wegweiser-departments" not in _body(path), path


def test_sale_filter_also_dissolves_root_shelves():
    """Та же дыра O-7 у «Regale»: «Nur reduzierte» не считался фильтром — полки стояли."""
    _tree()
    assert "data-shelf" in _body(style="regale")
    body = _body("/sortiment/?sale=1", style="regale")
    assert "data-shelf" not in body


# ─────────────────────────── W-2 «Im Fokus» ───────────────────────────


def _flat(cat, n, prefix, **kw):
    return [_product(cat, f"{prefix} {i}", **kw) for i in range(n)]


def _panel(focus, key):
    start = focus.index(f'data-focus-panel="{key}"')
    nxt = focus.find("data-focus-panel=", start + 1)
    return focus[start : nxt if nxt > 0 else None]


def _focus(body):
    m = re.search(r"<section[^>]*data-wegweiser-focus.*?</section>", body, re.S)
    return m.group(0) if m else ""


def test_focus_tabs_only_for_full_panels():
    a, b = _cat("A"), _cat("B")
    _flat(a, 4, "Neuheit", badge="neu")
    _flat(b, 2, "Liebling", badge="beliebt")  # меньше трёх — вкладки нет
    _flat(b, 6, "Normal")
    focus = _focus(_body())
    assert 'data-focus-panel="neu"' in focus
    assert 'data-focus-panel="beliebt"' not in focus
    assert 'role="tablist"' not in focus  # одна вкладка — без переключателя


def test_focus_link_only_when_trimmed_and_count_matches_the_target():
    a, b = _cat("A"), _cat("B")
    _flat(a, 7, "Neuheit", badge="neu")
    _flat(b, 3, "Liebling", badge="beliebt")
    focus = _focus(_body())
    neu = _panel(focus, "neu")
    assert re.search(r'href="\?badge=neu"[^>]*>Alle 7 ', neu)
    assert "?badge=beliebt" not in _panel(focus, "beliebt")  # 3 из 3 — ссылка никуда не ведёт
    assert _body("/sortiment/?badge=neu").count("Neuheit ") >= 7


def test_grid_never_repeats_focus_items():
    a, b = _cat("A"), _cat("B")
    neu = _flat(a, 5, "Neuheit", badge="neu")
    _flat(b, 30, "Normal")
    body = _body()
    grid = body[body.index('data-grid="catalog"') :]
    for p in neu:
        assert f">{p.name['de']}<" not in grid.replace("\n", ""), p.name
    # курсорная вторая страница — тоже без них
    cursor = re.search(r"cursor=([^&\"]+)", body)
    if cursor:
        page2 = _body(f"/sortiment/?sort=newest&cursor={cursor.group(1)}")
        for p in neu:
            assert p.name["de"] not in page2


def test_focus_without_js_shows_every_panel_with_its_heading():
    a, b = _cat("A"), _cat("B")
    _flat(a, 3, "Neuheit", badge="neu")
    _flat(b, 3, "Liebling", badge="beliebt")
    focus = _focus(_body())
    assert focus.count("data-focus-panel=") == 2
    assert "hidden" not in re.search(r'<div[^>]*data-focus-panel="beliebt"[^>]*>', focus).group(0)
    tablist = re.search(r'<div[^>]*role="tablist"[^>]*>', focus).group(0)
    assert "hidden" in tablist  # переключатель включает скрипт; без JS — полки подряд


def test_grid_heading_says_more_when_focus_is_shown():
    a, b = _cat("A"), _cat("B")
    _flat(a, 3, "Neuheit", badge="neu")
    _flat(b, 5, "Normal")
    assert "data-wegweiser-rest" in _body()
    assert "data-wegweiser-rest" not in _body("/sortiment/?q=Normal")


def test_focus_queries_are_constant():
    a, b = _cat("A"), _cat("B")
    _flat(a, 4, "Neuheit", badge="neu")
    _flat(b, 4, "Liebling", badge="beliebt")
    _flat(b, 6, "Normal")  # сетка непустая в обоих замерах — иначе считаем её, а не Fokus
    with CaptureQueriesContext(connection) as small:
        _get()
    _flat(a, 12, "Mehr neu", badge="neu")
    _flat(b, 12, "Mehr lieb", badge="beliebt")
    with CaptureQueriesContext(connection) as big:
        _get()
    assert len(big) - len(small) <= 2  # +count() у двух обрезанных вкладок


# ─────────────────────────── W-3 «Schnell finden» ───────────────────────────


def _guides(body):
    m = re.search(r"<section[^>]*data-wegweiser-guides.*?</section>", body, re.S)
    return m.group(0) if m else ""


def _guide_links(guides):
    return re.findall(r'href="(\?[^"]+)"[^>]*>.*?data-guide-count>(\d+)<', guides, re.S)


def test_guides_lead_to_exactly_the_promised_number_of_items():
    from apps.collections.models import Collection

    a, b = _cat("A"), _cat("B")
    cheap = _flat(a, 4, "Klein", price="4.00")
    _flat(b, 8, "Gross", price="80.00")
    col = Collection.objects.create(name={"de": "Geschenke"}, slug="geschenke", is_active=True)
    col.products.add(*cheap[:3])
    guides = _guides(_body())
    links = _guide_links(guides)
    assert len(links) >= 2, guides
    for href, n in links:
        target = _body("/sortiment/" + href.replace("&amp;", "&"))
        found = re.search(r"data-result-count>(\d+)", target)
        assert found and int(found.group(1)) == int(n), (href, n, found and found.group(1))


def test_guides_hidden_with_fewer_than_two_or_when_filtering():
    a, b = _cat("A"), _cat("B")
    _flat(a, 3, "Gleich", price="5.00")
    _flat(b, 3, "Gleich", price="5.00")  # один ценовой уровень, подборок нет
    assert "data-wegweiser-guides" not in _body()
    assert "data-wegweiser-guides" not in _body("/sortiment/?q=Gleich")


# ─────────────────────────── ревью ECC ───────────────────────────


def test_legacy_category_param_is_a_plain_result_not_wegweiser():
    """django-reviewer: `?kategorie=` на корне рисовал Fokus по ВСЕМУ магазину и выкидывал
    его товары из сетки выбранной категории."""
    a, b = _cat("A"), _cat("B")
    neu = _flat(a, 4, "Neuheit", badge="neu")
    _flat(b, 4, "Normal")
    body = _body(f"/sortiment/?kategorie={a.slug}")
    assert not _focus(body) and "data-wegweiser-departments" not in body
    assert all(p.name["de"] in body for p in neu)


def test_focus_cards_carry_the_same_rating_as_grid_cards():
    from apps.reviews.models import Review

    a, b = _cat("A"), _cat("B")
    neu = _flat(a, 3, "Neuheit", badge="neu")
    _flat(b, 3, "Normal")
    Review.objects.create(
        entity_kind="product",
        entity_id=neu[0].pk,
        rating=5,
        author_name="Ana",
        email="ana@example.com",
        comment="gut",
        is_published=True,
    )
    focus = _focus(_body())
    assert "★" in focus or "5,0" in focus or "5.0" in focus


@pytest.mark.parametrize("n,lg", [(10, 5), (6, 6), (8, 4), (9, 3), (5, 5), (7, 5)])
def test_department_rows_are_full_on_desktop(n, lg):
    """Стенд: 6 направлений в 5 колонок давали одинокую плитку во втором ряду (DL-11)."""
    from apps.catalog import wegweiser

    assert wegweiser.columns(n) == lg


def test_odd_department_count_spans_the_last_tile_on_phones():
    _tree(roots=3)
    body = _body()
    grid = re.search(
        r"<section[^>]*data-wegweiser-departments.*?<div class=\"([^\"]+)\"", body, re.S
    )
    assert "max-md:[&>article:last-child]:col-span-2" in grid.group(1)
    assert "lg:grid-cols-3" in grid.group(1)
