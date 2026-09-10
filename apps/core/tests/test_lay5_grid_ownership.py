"""LAY-5 — шаблон страницы больше не переписывает сетку владельца молча.

Разведка волны LAY (Д-2): выбор шаблона категории писал в `catalog_layout`
жёсткую плотность (`magazin→cols2`, `mosaik→cols4`, `kompakt→cols6`) и СНИМАЛ
явные колонки владельца, а «Mosaik» вдобавок форсил хвост. Владелец выставлял
сетку, потом выбирал шаблон — и его сетка исчезала. Это и читалось как «каша».

Решение владельца (Р-3): у композиции есть РЕКОМЕНДОВАННАЯ сетка, и она
применяется только там, где владелец сетку не трогал.

Замки написаны ДО правок и краснеют на текущем коде.
"""

import pytest
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _setup(slug, layout, page_style):
    tenant = TenantFactory(schema_name="public", slug=slug, name=slug.upper())
    tenant.site_config = siteconfig.normalize(
        {**(tenant.site_config or {}), "catalog_layout": layout}
    )
    tenant.save(update_fields=["site_config"])
    cat = Category.objects.create(name={"de": "Alles"}, slug="alles", page_style=page_style)
    Product.objects.create(name={"de": "P1"}, category=cat, base_price="1.00", is_active=True)
    return tenant


def _grid_cols(tenant, path="/sortiment/alles/"):
    req = RequestFactory().get(path)
    req.tenant = tenant
    body = public_views.product_list(req, slug="alles").content.decode()
    marker = 'data-grid="catalog"'
    assert marker in body
    chunk = body[body.index(marker) : body.index(marker) + 600]
    return chunk


# ── Р-3: рекомендация композиции не перебивает выбор владельца ───────────────


def test_template_does_not_override_an_explicit_grid():
    """Владелец выставил 5 колонок — «Magazin» их не отбирает."""
    tenant = _setup("lay5a", {"preset": "cols5", "cols": 5}, "magazin")
    chunk = _grid_cols(tenant)
    assert 'data-sf-cols="2/3/5"' in chunk or "lg:grid-cols-5" in chunk, chunk[:300]


def test_template_recommendation_applies_when_grid_untouched():
    """Владелец сетку не трогал — рекомендация композиции действует (как раньше)."""
    tenant = _setup("lay5b", {"preset": "cols3"}, "magazin")
    chunk = _grid_cols(tenant)
    assert "lg:grid-cols-2" in chunk, chunk[:300]


def test_mosaik_no_longer_forces_the_tail_over_the_owner():
    """«Mosaik» ставил tail=show поверх выбора владельца; теперь — только если он пуст."""
    tenant = _setup("lay5c", {"preset": "cols3", "tail": "fill"}, "mosaik")
    chunk = _grid_cols(tenant)
    assert 'data-sf-tail="fill"' in chunk, chunk[:300]


def test_mosaik_still_defaults_the_tail_when_owner_left_it_empty():
    tenant = _setup("lay5d", {"preset": "cols3"}, "mosaik")
    chunk = _grid_cols(tenant)
    assert 'data-sf-tail="show"' in chunk, chunk[:300]


# ── Дубль «Preisliste» на одной поверхности ─────────────────────────────────


def test_preisliste_is_not_offered_twice_on_the_category_page():
    """Прайс-вид задаётся ОСЬЮ СЕТКИ (там их восемь), а не ещё и шаблоном страницы.

    Два контрола, пишущих одно и то же, и есть «каша»: владелец выбирал шаблон
    «Preisliste», а рядом стоял богаче выбор в раскладке.
    """
    from apps.catalog import category_styles

    codes = [c for c, _l, _h in category_styles.CATEGORY_PAGE_STYLES]
    assert "preisliste" not in codes


def test_legacy_preisliste_page_style_still_renders_the_price_list():
    """Обратная совместимость (Р-2): у кого он уже выбран — витрина не меняется."""
    tenant = _setup("lay5e", {"preset": "cols3"}, "preisliste")
    req = RequestFactory().get("/sortiment/alles/")
    req.tenant = tenant
    body = public_views.product_list(req, slug="alles").content.decode()
    assert "data-price-list" in body
