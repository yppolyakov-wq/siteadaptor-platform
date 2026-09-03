"""DL-20: шаблоны страницы категории — общий дефолт сайта + выбор у категории.

Замки написаны ДО правок (характеризация): пустое значение в обоих слоях обязано
давать прежнюю разметку, а свой выбор категории — побеждать дефолт сайта.
План — `docs/dl20-category-templates-plan-2026-09-03.md`.
"""

import itertools
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.catalog import category_styles
from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


_SLUG = itertools.count()


def _cat(name="Backwaren", **kw):
    slug = kw.pop("slug", None) or f"kat-{next(_SLUG)}"
    return Category.objects.create(name={"de": name}, slug=slug, **kw)


def _product(cat, name="Brot", price="4.90"):
    return Product.objects.create(
        name={"de": name}, category=cat, base_price=Decimal(price), is_active=True
    )


def _render(tenant, slug=None, **params):
    request = RequestFactory().get("/sortiment/", params)
    request.tenant = tenant
    request.session = {}
    return public_views.product_list(request, slug=slug)


# ─────────────────────────── реестр ───────────────────────────


def test_registry_keeps_the_six_old_styles_and_adds_five():
    codes = [code for code, _l, _h in category_styles.CATEGORY_PAGE_STYLES]
    assert codes[:6] == ["", "kopfbild", "sets", "preisliste", "regale", "tabs"]
    for new in ("schaufenster", "navigator", "magazin", "mosaik", "kompakt"):
        assert new in codes, new
    # Код обязан влезать в CharField(max_length=20) — иначе DataError на save.
    assert all(len(code) <= 20 for code in codes)


def test_own_choice_beats_the_site_default():
    cat = _cat()
    cat.page_style = "magazin"
    assert category_styles.page_style(cat, "kompakt") == "magazin"


def test_site_default_applies_when_the_category_has_none():
    assert category_styles.page_style(_cat(), "kompakt") == "kompakt"


def test_garbage_in_any_layer_falls_back_to_standard():
    cat = _cat()
    cat.page_style = "was-auch-immer"
    assert category_styles.page_style(cat, "auch-nicht") == ""
    assert category_styles.page_style(cat, "kompakt") == "kompakt"  # свой мусор не блокирует
    assert category_styles.page_style(_cat(), "erfunden") == ""


# ─────────────────────── presence-minimal / golden ───────────────────────


def test_site_default_key_is_presence_minimal():
    assert "category_page_style" not in siteconfig.normalize({})["site_defaults"]
    assert (
        "category_page_style"
        not in siteconfig.normalize({"site_defaults": {"category_page_style": "erfunden"}})[
            "site_defaults"
        ]
    )
    kept = siteconfig.normalize({"site_defaults": {"category_page_style": "magazin"}})
    assert kept["site_defaults"]["category_page_style"] == "magazin"


# ─────────────────────────── рендер ───────────────────────────


def test_empty_in_both_layers_renders_the_old_markup():
    """Инвариант волны: без выбора — страница прежняя (маркеры Standard на месте)."""
    tenant = TenantFactory.build()
    cat = _cat(slug="backwaren")
    _product(cat)
    body = _render(tenant, slug="backwaren").content.decode()
    assert 'data-grid="catalog"' in body
    for marker in ("data-cat-hero", "data-shelf", "data-category-tabs", "data-cat-layout"):
        assert marker not in body, marker


def test_site_default_reaches_the_category_page():
    tenant = TenantFactory.build()
    tenant.site_config = {"site_defaults": {"category_page_style": "kompakt"}}
    cat = _cat(slug="backwaren")
    _product(cat)
    body = _render(tenant, slug="backwaren").content.decode()
    assert 'data-cat-layout="kompakt"' in body


def test_category_choice_wins_over_the_site_default_on_the_page():
    tenant = TenantFactory.build()
    tenant.site_config = {"site_defaults": {"category_page_style": "kompakt"}}
    cat = _cat(slug="backwaren", page_style="magazin")
    _product(cat)
    body = _render(tenant, slug="backwaren").content.decode()
    assert 'data-cat-layout="magazin"' in body
    assert 'data-cat-layout="kompakt"' not in body


def test_site_default_does_not_leak_into_the_full_catalog():
    """`/sortiment/` — не категория: общий дефолт её шаблона там не применяется."""
    tenant = TenantFactory.build()
    tenant.site_config = {"site_defaults": {"category_page_style": "kompakt"}}
    _product(_cat())
    body = _render(tenant).content.decode()
    assert "data-cat-layout" not in body


@pytest.mark.parametrize("style", ["schaufenster", "navigator", "magazin", "mosaik", "kompakt"])
def test_every_new_layout_survives_an_empty_category(style):
    """Класс «шаблон разваливается на реальных данных»: ни товаров, ни фото, ни детей."""
    tenant = TenantFactory.build()
    cat = _cat(page_style=style)
    body = _render(tenant, slug=cat.slug).content.decode()
    assert f'data-cat-layout="{style}"' in body
