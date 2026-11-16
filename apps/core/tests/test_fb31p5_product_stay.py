"""FB-31 P5 (товар, номер): разделы — строки со «скрыть», порядок постоянный; свои блоки —
перед отзывами, между отзывами и «Ähnliche», в конце (решение владельца)."""

import pytest

from apps.core import site_schema
from apps.core.tests import test_fb31p5_detail_golden as g
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
LEAD = {"key": "text", "id": "p1", "data": {"title": "Vor-Bewertungen-Q", "body": "x"}}
MID = {"key": "text", "id": "p2", "data": {"title": "Nach-Bewertungen-Q", "body": "y"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.mark.parametrize("kind,host", [("product", "product_detail"), ("stay", "stay_detail")])
def test_blocks_render_before_and_after_reviews(kind, host):
    first = "info" if kind == "product" else "amenities"
    rows = [
        {"key": first},
        LEAD,
        {"key": "reviews"},
        MID,
        {"key": "related" if kind == "product" else "similar"},
    ]
    html = g.RENDER[kind][0]({"page_blocks": {host: rows}}).content.decode()
    assert html.count("Vor-Bewertungen-Q") == 1 and html.count("Nach-Bewertungen-Q") == 1
    assert html.index("Vor-Bewertungen-Q") < html.index("Nach-Bewertungen-Q")


def test_product_rows_toggle_but_do_not_move():
    tenant = TenantFactory(site_config={})
    rows = site_schema.blocks_for(siteconfig.normalize({}), "product")
    assert [r["key"] for r in rows][:5] == ["kauf", "description", "info", "reviews", "related"]
    b = Browser(tenant)
    b.post(seite="product", op="down", ref="reviews")
    b.post(seite="product", op="toggle", ref="related")
    b.post(seite="product", op="save")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["product_detail"]["hidden"] == ["related"]
    assert "order" not in cfg["product_detail"]
