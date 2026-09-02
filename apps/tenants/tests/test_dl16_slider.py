"""DL-16.1 — S1 слайдер-примитив ([data-sf-slider]) + S4 фиксы."""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.template import Context, Template
from django.test import RequestFactory

from apps.catalog.models import Category
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


def _get(view, path, tenant, **kw):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request, **kw).content.decode()


def test_scroll_layout_carries_slider_marker_and_no_row_rules():
    attrs = siteconfig.grid_attr_string({"preset": "cols4", "scroll": True})
    assert attrs == 'data-sf-slider="1"'
    assert "data-sf-cols" not in attrs
    html = Template("{% load siteui %}<div {% grid_attrs site 'products' %}></div>").render(
        Context(
            {
                "site": siteconfig.normalize(
                    {"sections": [{"key": "products", "enabled": True, "layout": {"scroll": True}}]}
                )
            }
        )
    )
    assert html == '<div data-sf-slider="1"></div>'


def test_home_scroll_section_renders_slider_marker():
    tenant = TenantFactory(schema_name="public", slug="dl161a", name="A", disabled_modules=[])
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": True, "layout": {"scroll": True}}]}
    )
    tenant.save()
    for i in range(6):
        Category.objects.create(name={"de": f"Kat {i}"}, slug=f"kat-{i}", is_active=True)
    html = _get(public_views.storefront_home, "/", tenant)
    assert re.search(
        r'data-grid="categories"[^>]*sf-scroll-grid[^>]*data-sf-slider="1"', html
    ) or re.search(r'data-grid="categories"[^>]*data-sf-slider="1"[^>]*sf-scroll-grid', html)
    # скрипт-примитив подключён в базовом шаблоне; автопрокрутки нет
    assert (
        "__sfSliderInit" in html
        and "setInterval" not in html.split("__sfSliderInit")[1].split("</script>")[0]
    )


def test_strip_gallery_and_combo_related_are_sliders():
    gal = (ROOT / "templates/storefront/sections/_gallery.html").read_text(encoding="utf-8")
    assert 'overflow-x-auto pb-2" data-sf-slider>' in gal
    combo = (ROOT / "templates/storefront/combo_detail.html").read_text(encoding="utf-8")
    assert 'overflow-x-auto pb-2" data-sf-slider>' in combo


def test_slider_css_arrows_only_on_hover_devices():
    css = (ROOT / "static/src/app.css").read_text(encoding="utf-8")
    block = css[css.index(".sf-slider {") :]
    assert "@media (hover: hover) and (pointer: fine)" in block
    # вне hover-медиа стрелка скрыта (display:none) — на таче только свайп + точки
    base = block[: block.index("@media (hover: hover)")]
    assert re.search(r"\.sf-slider-arrow \{[^}]*display: none", base)
    assert ".sf-slider:hover .sf-slider-arrow:not(:disabled)" in block


def test_archetype_cover_has_mobile_and_hover_guards():
    src = (ROOT / "templates/storefront/_archetype_cover.html").read_text(encoding="utf-8")
    assert "(max-width: 767px)" in src and "prefers-reduced-motion" in src
    assert 'addEventListener("mouseenter", stop)' in src


def test_category_header_photos_open_lightbox():
    src = (ROOT / "templates/storefront/_category_header.html").read_text(encoding="utf-8")
    assert src.count("data-lightbox=") == 2


def test_sortiment_context_has_site_so_price_gate_works():
    """S4: `site.menu_show_prices=False` раньше молча игнорировался на /sortiment/ — `site`
    в контексте не было. Теперь прайс-строки уважают гейт (без orders-модуля)."""
    from apps.catalog.tests.factories import ProductFactory

    tenant = TenantFactory(
        schema_name="public",
        slug="dl161b",
        name="B",
        disabled_modules=["orders"],
        site_config={"catalog_layout": {"preset": "preisliste"}, "menu_show_prices": False},
    )
    ProductFactory(name={"de": "Suppe"}, base_price="4.90")
    html = _get(public_views.product_list, "/sortiment/", tenant)
    assert "Suppe" in html and "4,90" not in html
