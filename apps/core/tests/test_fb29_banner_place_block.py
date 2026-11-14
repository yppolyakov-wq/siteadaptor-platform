"""FB-29.2 S6 (решение владельца 2026-11-14): место баннеров на странице задаёт структура —
блок «Banner» с источником «Banner dieser Seite». Баннеры, которым страница задана в
«Wo zeigen», встают там, где стоит блок; место по умолчанию — только пока блока нет."""

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.core import banners, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


PLACE = {"key": "banner", "id": "bp1", "enabled": True, "data": {"from_page": True}}
TEXT = {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Info"}}


def _tenant(page_blocks=None):
    tenant = TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config={"page_blocks": page_blocks or {}},
    )
    connection.tenant = tenant
    return tenant


def _product(name="Darjeeling"):
    return Product.objects.create(name={"de": name, "en": ""}, base_price="9.90")


def _banner_on(product, title="Nur hier"):
    b = banners.create({"title": title, "image": {"url": "/media/hero/a.jpg"}})
    key = f"product:{product.pk}"
    banners.set_show_on(b, keep=[], add=[key], allowed={key})
    return b


def _render(tenant, source, **ctx):
    request = RequestFactory().get("/")
    request.tenant = Tenant.objects.get(pk=tenant.pk)
    return Template("{% load siteui %}" + source).render(Context({"request": request, **ctx}))


def test_from_page_survives_the_cleaner_and_is_presence_minimal():
    assert siteconfig.clean_banner_choice({"from_page": "1"}) == {"from_page": True}
    assert siteconfig.clean_banner_choice({"from_page": "0", "pick": []}) == {}
    data = siteconfig._clean_cblock_data("banner", {"from_page": True})
    assert data.get("from_page") is True


def test_place_block_shows_the_banners_assigned_to_this_page():
    p, other = _product("Darjeeling"), _product("Assam")
    _banner_on(p)
    tenant = _tenant({"product_detail": [TEXT, PLACE]})
    html = _render(tenant, '{% page_blocks "product_detail" %}', product=p)
    assert "Nur hier" in html and html.index("Info") < html.index("Nur hier"), "на месте блока"
    assert "Nur hier" not in _render(tenant, '{% page_blocks "product_detail" %}', product=other)


def test_default_place_steps_aside_when_the_structure_has_a_place_block():
    p = _product()
    _banner_on(p)
    with_block = _tenant({"product_detail": [PLACE]})
    assert _render(with_block, '{% place_banners "product" product %}', product=p).strip() == ""
    without = _tenant({"product_detail": [TEXT]})
    assert "Nur hier" in _render(without, '{% place_banners "product" product %}', product=p)


def test_hidden_place_block_does_not_swallow_the_banners():
    p = _product()
    _banner_on(p)
    tenant = _tenant({"product_detail": [{**PLACE, "enabled": False}]})
    assert "Nur hier" in _render(tenant, '{% place_banners "product" product %}', product=p)


def test_place_block_in_the_objects_own_blocks_counts_too():
    p = _product()
    _banner_on(p)
    tenant = _tenant({f"product:{p.pk.hex}": [PLACE]})
    assert _render(tenant, '{% place_banners "product" product %}', product=p).strip() == ""
    assert "Nur hier" in _render(tenant, '{% object_blocks "product" product %}', product=p)


def test_panel_switches_the_source_through_the_draft():
    tenant = _tenant(
        {"product_detail": [{"key": "banner", "id": "bp1", "enabled": True, "data": {}}]}
    )
    b = Browser(tenant)
    html = b.get("?seite=product&block=bp1")
    assert 'name="f_from_page"' in html
    b.post(seite="product", ref="bp1", op="update", f_from_page="1", panel_present="1")
    b.post(seite="product", op="save")
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert cfg["page_blocks"]["product_detail"][0]["data"].get("from_page") is True
    html = b.get("?seite=product&block=bp1")
    assert "data-schema-banner-offers" not in html, (
        "при «Banner dieser Seite» выбор плитками не нужен"
    )


def test_home_banner_block_does_not_offer_the_page_source():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "home", "add", block_type="banner")
    html = Browser(tenant).get(f"?seite=home&block={ref}")
    assert 'name="f_from_page"' not in html, "у главной нет страниц объектов"


def test_studio_save_keeps_the_source():
    saved = [{"key": "banner", "id": "b1", "enabled": True, "data": {"from_page": True}}]
    posted = [{"key": "banner", "id": "b1", "enabled": True, "data": {"title": "Neu"}}]
    assert site_schema.merge_structure(saved, posted)[0]["data"].get("from_page") is True
