"""DS-7: лендинги направлений /bereich/<slug>/ + тумблер цен в меню.
План docs/ds7-category-landings-plan-2026-08-12.md."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/"):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    return request


def _seed(desc=True, photo=True):
    cat = Category.objects.create(
        name={"de": "Hochzeits-Catering"},
        description={"de": "Ihr Buffet ohne Stress."} if desc else {},
        slug="cl-hochzeit",
        images=[{"id": "i1", "url": "/media/wed.jpg", "is_primary": True}] if photo else [],
    )
    Product.objects.create(
        name={"de": "Hochzeitsbuffet Klassik"},
        description={"de": "Drei Gänge als Buffet"},
        base_price="39.00",
        category=cat,
        is_active=True,
    )
    return cat


def test_normalize_toggles_presence_minimal():
    assert "category_landings" not in siteconfig.normalize({})
    assert siteconfig.normalize({"category_landings": True})["category_landings"] is True
    assert "menu_show_prices" not in siteconfig.normalize({})
    assert "menu_show_prices" not in siteconfig.normalize({"menu_show_prices": True})
    assert siteconfig.normalize({"menu_show_prices": False})["menu_show_prices"] is False


def test_landing_gates_and_content():
    cat = _seed()
    # тумблер выкл → 404 даже с контентом
    req = _req()
    req.tenant = TenantFactory.build()
    with pytest.raises(Http404):
        public_views.category_landing(req, cat.slug)
    # тумблер вкл + контент → 200, примеры БЕЗ цен, CTA с прицелом
    on = _req()
    on.tenant = TenantFactory.build(site_config={"category_landings": True})
    html = public_views.category_landing(on, cat.slug).content.decode()
    assert "data-landing-hero" in html and "Hochzeits-Catering" in html
    assert "Ihr Buffet ohne Stress." in html
    assert "Hochzeitsbuffet Klassik" in html
    # DS-7c (фидбэк): блюда мини-плитками, цена по тумблеру меню — дефолт ПОКАЗАТЬ
    examples = html[html.find("data-landing-examples") :].split("</section>")[0]
    assert "39,00" in examples
    assert "betreff=Hochzeits-Catering" in html
    # тумблер выключен + browse-only → цены на плитках скрыты («с ценой и без»)
    off_prices = _req()
    off_prices.tenant = TenantFactory.build(
        site_config={"category_landings": True, "menu_show_prices": False},
        disabled_modules=["orders"],
    )
    html2 = public_views.category_landing(off_prices, cat.slug).content.decode()
    ex2 = html2[html2.find("data-landing-examples") :].split("</section>")[0]
    assert "39,00" not in ex2 and "Hochzeitsbuffet Klassik" in ex2
    # пустая категория (без описания и фото) → 404 (контент-гейт)
    empty = Category.objects.create(name={"de": "Leer"}, slug="cl-leer")
    with pytest.raises(Http404):
        public_views.category_landing(on, empty.slug)


def test_tiles_link_to_landing_when_enabled():
    cat = _seed()
    on = _req()
    on.tenant = TenantFactory.build(
        site_config={
            "category_landings": True,
            "sections": [{"key": "categories", "enabled": True}],
        }
    )
    html = public_views.storefront_home(on).content.decode()
    assert f"/bereich/{cat.slug}/" in html
    off = _req()
    off.tenant = TenantFactory.build(
        site_config={"sections": [{"key": "categories", "enabled": True}]}
    )
    html_off = public_views.storefront_home(off).content.decode()
    assert "/bereich/" not in html_off  # выкл → прежний фильтр каталога


def test_menu_prices_toggle_browse_only():
    _seed()
    base = {
        "sections": [{"key": "products", "enabled": True, "style": "preisliste"}],
        "menu_show_prices": False,
    }
    # browse-only (orders выключен) → цены скрыты
    t1 = TenantFactory.build(site_config=base, disabled_modules=["orders"])
    r1 = _req()
    r1.tenant = t1
    h1 = public_views.storefront_home(r1).content.decode()
    pl1 = h1[h1.find("data-price-list") : h1.find("data-price-list") + 3000]
    assert "39,00" not in pl1 and "Hochzeitsbuffet Klassik" in pl1
    # продажа активна → PAngV: цены показываются несмотря на ключ
    t2 = TenantFactory.build(site_config=base)
    r2 = _req()
    r2.tenant = t2
    h2 = public_views.storefront_home(r2).content.decode()
    pl2 = h2[h2.find("data-price-list") : h2.find("data-price-list") + 3000]
    assert "39,00" in pl2
