"""DL-21.1: шаблоны КОРНЕВОЙ страницы каталога `/sortiment/` — свой ключ
`catalog_page_style` (та же механика, что у категории; корневые категории играют
роль подкатегорий). Замки написаны ДО правок (характеризация).

План — `docs/dl21-root-and-overview-templates-plan-2026-09-03.md`.
"""

import itertools
import re
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.catalog import category_styles
from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_SLUG = itertools.count()


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cat(name="Backwaren", **kw):
    slug = kw.pop("slug", None) or f"root-{next(_SLUG)}"
    return Category.objects.create(name={"de": name}, slug=slug, **kw)


def _product(cat, name="Brot", price="4.90"):
    return Product.objects.create(
        name={"de": name}, category=cat, base_price=Decimal(price), is_active=True
    )


def _root(style="", roots=2, products=3, cfg=None):
    tenant = TenantFactory.build()
    config = dict(cfg or {})
    if style:
        config["catalog_page_style"] = style
    tenant.site_config = config
    for i in range(roots):
        c = _cat(name=f"Richtung {i}")
        for j in range(products):
            _product(c, name=f"Artikel {i}-{j}")
    request = RequestFactory().get("/sortiment/")
    request.tenant = tenant
    request.session = {}
    return public_views.product_list(request).content.decode()


# ─────────────────────────── реестр и ключ ───────────────────────────


def test_root_registry_is_the_category_registry_without_preisliste():
    """Прайс-вид на корне уже даёт catalog_preset в той же строке Studio —
    второй переключатель того же (урок DL-9) не заводим."""
    keys = [k for k, _l, _h in category_styles.root_styles()]
    assert "preisliste" not in keys
    assert keys[0] == ""
    for k in ("kopfbild", "regale", "tabs", "schaufenster", "navigator", "kompakt"):
        assert k in keys, k


def test_root_key_is_presence_minimal_and_validated():
    assert "catalog_page_style" not in siteconfig.normalize({})
    assert "catalog_page_style" not in siteconfig.normalize({"catalog_page_style": "erfunden"})
    # preisliste — не шаблон корня (ось catalog_preset)
    assert "catalog_page_style" not in siteconfig.normalize({"catalog_page_style": "preisliste"})
    assert siteconfig.normalize({"catalog_page_style": "regale"})["catalog_page_style"] == "regale"


def test_root_style_does_not_inherit_the_category_default():
    """Р-2: «поставил категориям Navigator — корень стал Navigator» — сюрприз."""
    body = _root(cfg={"site_defaults": {"category_page_style": "navigator"}})
    assert "data-cat-layout" not in body


# ─────────────────────────── рендер ───────────────────────────


def test_root_standard_is_unchanged():
    body = _root()
    assert "data-cat-layout" not in body
    assert 'data-grid="catalog"' in body
    for marker in ("data-shelf", "data-category-tabs", "data-cat-side", "data-subcat-index"):
        assert marker not in body, marker


def test_root_regale_puts_root_directions_on_shelves():
    body = _root("regale")
    assert 'data-cat-layout="regale"' in body
    assert body.count("data-shelf=") == 2
    # верхние плитки направлений в общий поток не идут (они на полках)
    assert "Richtung 0" in body


def test_root_tabs_show_all_plus_directions():
    body = _root("tabs")
    assert "data-category-tabs" in body
    assert body.count("data-listing-nav") >= 3  # Alle + 2 направления


def test_root_navigator_lists_directions_in_the_side_column():
    body = _root("navigator")
    assert "data-cat-side" in body
    side = body[body.index("data-cat-side") :]
    assert "Richtung 0" in side[: side.index("data-grid")]


def test_root_kompakt_indexes_directions():
    body = _root("kompakt")
    assert "data-subcat-index" in body


def test_root_schaufenster_and_magazin_and_mosaik():
    assert "data-cat-hero-product" in _root("schaufenster")
    assert "data-cat-magazin-item" in _root("magazin")
    grid = re.search(r'<div data-grid="catalog"[^>]*>', _root("mosaik")).group(0)
    assert "data-cat-bento" in grid and 'data-sf-tail="show"' in grid


def test_root_kopfbild_shows_the_catalog_header():
    body = _root("kopfbild", cfg={"catalog_intro": "Alles aus eigener Herstellung."})
    assert 'data-cat-layout="kopfbild"' in body
    assert "Alles aus eigener Herstellung." in body


@pytest.mark.parametrize("style", [k for k, _l, _h in category_styles.root_styles() if k])
def test_every_root_layout_survives_an_empty_catalog(style):
    body = _root(style, roots=0, products=0)
    assert f'data-cat-layout="{style}"' in body
