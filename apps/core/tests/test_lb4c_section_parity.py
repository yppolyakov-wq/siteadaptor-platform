"""LB-4c: характеризация разметки списочных секций главной ДО выноса композиций.

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §6/§11. Композиции секций
(прайс-лист товаров, spotlight/banner/rows акций, строки-плитки категорий) выносятся в
общие партиалы, которыми рисуются и секции, и блок «Liste». Чтобы вынос не изменил
главные живых сайтов, разметка каждой секции в каждом виде снята ЭТАЛОНОМ до правок
(`golden_lb4c/*.html`) и сравнивается байт-в-байт после нормализации (uuid, даты,
пробелы). Переснять эталоны осознанно: `LB4C_WRITE=1 pytest <этот файл>`.
"""

import os
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_lb4c"
WRITE = os.environ.get("LB4C_WRITE") == "1"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[+-]\d{2}:\d{2}|Z)?")
_TIME = re.compile(r"\b\d{2}:\d{2}\b")
_DATE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
_CSRF = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _normalize(html: str) -> str:
    html = _CSRF.sub('name="csrfmiddlewaretoken" value="<csrf>"', html)
    html = _UUID.sub("<uuid>", html)
    html = _ISO.sub("<iso>", html)
    html = _DATE.sub("<date>", html)
    html = _TIME.sub("<time>", html)
    return re.sub(r"\s+", " ", html).strip()


def _home(row, **cfg):
    keys = {row["key"]}
    sections = [{"enabled": True, **row}]
    sections += [
        {"key": k, "enabled": False} for k, _l, _on in siteconfig.SECTIONS if k not in keys
    ]
    tenant = TenantFactory(slug=f"lb4c{row['key']}", name="LB4C", disabled_modules=[])
    tenant.site_config = {"sections": sections, **cfg}
    tenant.save(update_fields=["site_config"])
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _section(body, key):
    i = body.index(f'data-edit="section_titles.{key}"')
    start = body.rindex("<section", 0, i)
    return body[start : body.index("</section>", i) + len("</section>")]


def _catalog():
    """Два направления по две позиции, одна подкатегория — детерминированно."""
    brot = Category.objects.create(name={"de": "Brot"}, slug="brot", sort_order=1, is_active=True)
    kuchen = Category.objects.create(
        name={"de": "Kuchen"}, slug="kuchen", sort_order=2, is_active=True
    )
    torte = Category.objects.create(
        name={"de": "Torten"}, slug="torten", sort_order=3, is_active=True, parent=kuchen
    )
    rows = [
        ("Roggenbrot", brot, "3.20", 5, True),
        ("Bauernbrot", brot, "3.80", 4, False),
        ("Apfelkuchen", kuchen, "2.40", 3, False),
        ("Sachertorte", torte, "24.90", 2, True),
    ]
    for name, cat, price, days, featured in rows:
        p = Product.objects.create(
            name={"de": name},
            description={"de": f"{name} aus dem Ofen."},
            base_price=Decimal(price),
            category=cat,
            is_active=True,
            is_featured=featured,
        )
        Product.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=days))


def _promotions():
    now = timezone.now()
    specs = [
        ("Brot-Deal", 6, 2, 20),
        ("Kuchen-Woche", 5, 10, 15),
        ("Torten-Sale", 4, 1, 30),
        ("Kaffee gratis", 3, 20, 10),
        ("Wochenend-Brötchen", 2, 30, 25),
    ]
    for title, days, ends, pct in specs:
        p = Promotion.objects.create(
            title={"de": title},
            status="active",
            discount_percent=pct,
            ends_at=now + timedelta(days=ends),
        )
        Promotion.objects.filter(pk=p.pk).update(created_at=now - timedelta(days=days))


CASES = {
    "products_grid": ({"key": "products"}, _catalog),
    **{
        f"products_{style}": ({"key": "products", "style": style}, _catalog)
        for style in siteconfig.SECTION_STYLES["products"]
    },
    "products_preisliste_rows1": ({"key": "products", "style": "preisliste", "rows": 1}, _catalog),
    "promotions_grid": ({"key": "promotions"}, _promotions),
    **{
        f"promotions_{style}": ({"key": "promotions", "style": style}, _promotions)
        for style in siteconfig.SECTION_STYLES["promotions"]
    },
    "categories_grid": ({"key": "categories"}, _catalog),
    **{
        f"categories_{style}": ({"key": "categories", "style": style}, _catalog)
        for style in siteconfig.SECTION_STYLES["categories"]
    },
    "categories_tile_info": (
        {"key": "categories", "tile_info": ["price", "count"], "img_h": 160},
        _catalog,
    ),
    "categories_compact_cols": (
        {"key": "categories", "style": "compact", "layout": {"preset": "cols2"}},
        _catalog,
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_section_markup_matches_the_snapshot_taken_before_lb4c(name):
    row, seed = CASES[name]
    seed()
    html = _normalize(_section(_home(row), row["key"]))
    path = GOLDEN / f"{name}.html"
    if WRITE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(html + "\n", encoding="utf-8")
    expected = path.read_text(encoding="utf-8").strip()
    assert html == expected, f"разметка секции {name} изменилась"
