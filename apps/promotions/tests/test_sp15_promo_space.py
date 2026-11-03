"""SP-15 (решение владельца 2026-11-03, «делай 1–6, по 7–10 по рекомендации»).

1. «Endet bald» из трёх акций — ровный ряд из трёх на десктопе (было 2 + одна
   во всю ширину): сетка несёт data-count, правило CSS — в app.css.
2. Категории без НАСТОЯЩЕГО фото — чипы: демо-заглушка `/medien/demo.svg` рисует
   эмодзи и ту же подпись, что плитка печатает ниже.
7. Акция из полосы «Endet bald» не повторяется в общем остатке «Weitere Angebote»;
   тематические секции не трогаем.
"""

from __future__ import annotations

import re
from datetime import timedelta
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import Category
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.demo_images import is_placeholder
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


def _get(view, path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request).content.decode()


def _promo(title, **kw):
    return Promotion.objects.create(title={"de": title}, status="active", discount_percent=20, **kw)


# ── 1. «Endet bald» ровным рядом ─────────────────────────────────────────────


def test_ending_grid_carries_count_for_even_row():
    tenant = TenantFactory(schema_name="public", slug="sp15a", name="A", disabled_modules=[])
    soon = timezone.now() + timedelta(days=1)
    for i in range(3):
        _promo(f"Bald {i}", ends_at=soon)
    _promo("Lang")
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    assert re.search(r'data-ending-grid data-count="3"', html), html[:400]


def test_css_three_in_a_row_rule_present():
    css = (ROOT / "static" / "src" / "app.css").read_text()
    assert '[data-ending-grid][data-count="3"] { grid-template-columns: repeat(3' in css
    built = (ROOT / "static" / "css" / "app.css").read_text()
    assert 'data-count="3"' in built


# ── 7. без повтора в «Weitere Angebote» ──────────────────────────────────────


def _rest_section(html):
    """Секции акций без группы — остаток «More offers» (последняя секция)."""
    return html.split("data-ending-soon", 1)[-1]


def test_remainder_skips_promos_already_in_ending_strip():
    tenant = TenantFactory(schema_name="public", slug="sp15b", name="B", disabled_modules=[])
    soon = timezone.now() + timedelta(days=1)
    # группа с двумя акциями → секция; остаток — безгрупповые
    _promo("Woche A", group="Wochenangebote")
    _promo("Woche B", group="Wochenangebote")
    _promo("Bald frei", ends_at=soon)  # безгрупповая и в полосе
    _promo("Frei lang")
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    strip, below = html.split("data-ending-grid", 1)[1].split("</section>", 1)
    assert "Bald frei" in strip
    assert "Bald frei" not in below, "акция полосы повторилась в остатке"
    assert "Frei lang" in below


def test_thematic_section_keeps_its_promo_even_if_in_strip():
    tenant = TenantFactory(schema_name="public", slug="sp15c", name="C", disabled_modules=[])
    soon = timezone.now() + timedelta(days=1)
    _promo("Räumung A", group="Räumung", ends_at=soon)
    _promo("Räumung B", group="Räumung")
    _promo("Frei lang")
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    below = html.split("data-ending-grid", 1)[1].split("</section>", 1)[1]
    assert "Räumung A" in below, "тематическая секция потеряла свою акцию"


def test_remainder_section_disappears_when_fully_in_strip():
    tenant = TenantFactory(schema_name="public", slug="sp15d", name="D", disabled_modules=[])
    soon = timezone.now() + timedelta(days=1)
    _promo("Woche A", group="Wochenangebote")
    _promo("Woche B", group="Wochenangebote")
    _promo("Nur bald", ends_at=soon)
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    below = html.split("data-ending-grid", 1)[1].split("</section>", 1)[1]
    assert "Nur bald" not in below
    assert "Weitere Angebote" not in below and "More offers" not in below


# ── 2. категории без настоящего фото — чипы ─────────────────────────────────


def test_placeholder_detection():
    assert is_placeholder("/medien/demo.svg?kw=pizza&cap=Pizza")
    assert not is_placeholder("/media/kat.jpg")
    assert not is_placeholder("")


def test_tile_image_url_ignores_demo_placeholder():
    cat = Category(name={"de": "Vorspeisen"}, images=[{"url": "/medien/demo.svg?kw=x&cap=V"}])
    assert cat.image_url and cat.tile_image_url == ""
    real = Category(name={"de": "Brot"}, images=[{"url": "/media/brot.jpg"}])
    assert real.tile_image_url == "/media/brot.jpg"


def _home(tenant):
    return _get(public_views.storefront_home, "/", tenant)


def _home_tenant(schema):
    tenant = TenantFactory(schema_name=schema)
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": True}]}
    )
    tenant.save()
    return tenant


def test_home_placeholder_category_is_a_compact_text_tile():
    """На главной заглушка не рисуется: плитка без настоящего фото — текстовая
    (≈80 px), имя один раз. Тенанты вовсе без фото — как раньше (эталоны LB-4)."""
    tenant = _home_tenant("sp15home1")
    cat = Category.objects.create(
        name={"de": "Vorspeisen"},
        slug="vorspeisen",
        is_active=True,
        images=[{"url": "/medien/demo.svg?kw=v&cap=Vorspeisen"}],
    )
    ProductFactory(category=cat)
    html = _home(tenant)
    grid = html.split('data-grid="categories"', 1)[1].split("</section>", 1)[0]
    assert "/medien/demo.svg" not in grid
    assert "min-h-[5rem]" in grid


def test_home_categories_with_real_photo_keep_photo_tiles():
    tenant = _home_tenant("sp15home2")
    cat = Category.objects.create(
        name={"de": "Brot"}, slug="brot", is_active=True, images=[{"url": "/media/brot.jpg"}]
    )
    ProductFactory(category=cat)
    html = _home(tenant)
    grid = html.split('data-grid="categories"', 1)[1].split("</section>", 1)[0]
    assert "/media/brot.jpg" in grid


def test_sortiment_placeholder_categories_render_chips():
    tenant = TenantFactory(schema_name="public", slug="sp15s", name="S", disabled_modules=[])
    cat = Category.objects.create(
        name={"de": "Vorspeisen"},
        slug="vorspeisen",
        is_active=True,
        images=[{"url": "/medien/demo.svg?kw=v&cap=Vorspeisen"}],
    )
    ProductFactory(category=cat)
    html = _get(public_views.product_list, "/sortiment/", tenant)
    assert "/medien/demo.svg?kw=v" not in html
