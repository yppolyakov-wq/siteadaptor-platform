"""DL-16.5 — страница категории: K1 крошки + Kopfbild-слайдер, K2 «Regale», K3 «Tabs»."""

from __future__ import annotations

import re
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.category_styles import CATEGORY_PAGE_STYLES, VALID_PAGE_STYLES
from apps.catalog.models import Category
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _get(path, tenant, slug=None):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.product_list(request, slug=slug).content.decode()


def _tree(style):
    parent = Category.objects.create(
        name={"de": "Catering"}, slug="catering", is_active=True, page_style=style
    )
    subs = []
    for i, n in enumerate(("Suppen", "Beilagen", "Ragouts")):
        sub = Category.objects.create(
            name={"de": n}, slug=n.lower(), is_active=True, parent=parent, sort_order=i
        )
        for k in range(2 + i):
            ProductFactory(name={"de": f"{n} {k}"}, category=sub, base_price="4.90")
        subs.append(sub)
    return parent, subs


def test_registry_has_regale_and_tabs():
    assert {"regale", "tabs"} <= VALID_PAGE_STYLES
    assert [c for c, _l, _h in CATEGORY_PAGE_STYLES][:4] == ["", "kopfbild", "sets", "preisliste"]


def test_breadcrumbs_on_category_page_only():
    tenant = TenantFactory(schema_name="public", slug="dl165a", name="A", disabled_modules=[])
    parent, subs = _tree("")
    root = _get("/sortiment/", tenant)
    assert "data-breadcrumbs" not in root and "BreadcrumbList" not in root
    html = _get("/sortiment/suppen/", tenant, slug="suppen")
    nav = re.search(
        r'<nav aria-label="Breadcrumb"[^>]*data-breadcrumbs>(.*?)</nav>', html, re.S
    ).group(1)
    assert 'href="/sortiment/"' in nav and 'href="/sortiment/catering/"' in nav
    assert 'aria-current="page">Suppen<' in nav
    assert "BreadcrumbList" in html and re.search(r'"name":\s*"Suppen"', html)


def test_regale_renders_shelf_per_subcategory_and_hides_tiles():
    tenant = TenantFactory(schema_name="public", slug="dl165b", name="B", disabled_modules=[])
    parent, subs = _tree("regale")
    html = _get("/sortiment/catering/", tenant, slug="catering")
    assert html.count("data-shelf=") == 3
    assert 'data-shelf="suppen"' in html and "· 2</span>" in html and "· 4</span>" in html
    assert html.count("data-sf-slider") >= 3
    # SF-5 (фидбэк 2026-09-03): полка из 2–4 товаров показана целиком → ссылки
    # «Alle anzeigen» нет (она вела бы в тот же набор). Обрезанная полка — в
    # apps/promotions/tests/test_sf5_more_links.py.
    assert 'href="/sortiment/ragouts/"' not in html
    assert "min-h-[4rem]" not in html  # текстовые плитки подкатегорий не дублируются
    assert "Choose a subcategory above." not in html
    # сетка ниже полок — только ПРЯМЫЕ товары направления (дублей карточек полок нет)
    ProductFactory(name={"de": "Direkt"}, category=parent, base_price="1.00")
    html = _get("/sortiment/catering/", tenant, slug="catering")
    grid = html[html.index('data-sf-section="catalog"') :]
    assert "Direkt" in grid and "Suppen 0" not in grid


def test_tabs_on_parent_and_on_child_pages():
    tenant = TenantFactory(schema_name="public", slug="dl165c", name="C", disabled_modules=[])
    parent, subs = _tree("tabs")
    html = _get("/sortiment/catering/", tenant, slug="catering")
    tabs = re.search(r"<nav[^>]*data-category-tabs[^>]*>(.*?)</nav>", html, re.S).group(1)
    assert tabs.count("data-listing-nav") == 4
    assert 'href="/sortiment/catering/" data-listing-nav aria-current="page"' in tabs
    assert "· 9</span>" in tabs and "· 4</span>" in tabs
    assert "min-h-[4rem]" not in html
    child = _get("/sortiment/ragouts/", tenant, slug="ragouts")
    tabs = re.search(r"<nav[^>]*data-category-tabs[^>]*>(.*?)</nav>", child, re.S).group(1)
    assert 'href="/sortiment/ragouts/" data-listing-nav aria-current="page"' in tabs
    assert "· 9</span>" in tabs and "· 2</span>" in tabs  # счётчики соседей — по всем товарам


def test_standard_category_has_no_tabs_or_shelves():
    tenant = TenantFactory(schema_name="public", slug="dl165d", name="D", disabled_modules=[])
    _tree("")
    html = _get("/sortiment/catering/", tenant, slug="catering")
    assert "data-shelf=" not in html and "data-category-tabs" not in html
    assert "min-h-[4rem]" in html  # прежние плитки подкатегорий


def test_kopfbild_slider_when_two_photos_and_no_autoplay():
    tenant = TenantFactory(schema_name="public", slug="dl165e", name="E", disabled_modules=[])
    cat = Category.objects.create(
        name={"de": "Torten"},
        slug="torten",
        is_active=True,
        page_style="kopfbild",
        description={"de": "Feine Torten"},
        images=[{"url": "/a.jpg", "is_primary": True}, {"url": "/b.jpg"}],
    )
    ProductFactory(name={"de": "Sacher"}, category=cat, base_price="3.50")
    html = _get("/sortiment/torten/", tenant, slug="torten")
    assert "data-cat-hero" in html and len(re.findall(r"<img[^>]*data-cat-slide", html)) == 2
    assert len(re.findall(r"<button[^>]*data-cat-dot", html)) == 2 and "data-cat-next" in html
    assert "setInterval" not in html.split("data-cat-hero")[1].split("</script>")[0]
    assert "data-category-gallery" not in html
