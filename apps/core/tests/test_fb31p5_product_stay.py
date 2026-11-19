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
    # FB-33 M2f: разделы первого экрана и «Zuletzt angesehen» — тоже строки схемы
    assert [r["key"] for r in rows][:12] == [
        "kauf",
        "description",
        "info",
        "sizes",
        "trust",
        "anprobe",
        "waitlist",
        "instore",
        "question",
        "reviews",
        "related",
        "recent",
    ]
    b = Browser(tenant)
    b.post(seite="product", op="down", ref="reviews")
    b.post(seite="product", op="toggle", ref="related")
    b.post(seite="product", op="save")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["product_detail"]["hidden"] == ["related"]
    assert "order" not in cfg["product_detail"]


def test_review_editor_order_matches_the_page_and_hidden_reviews_are_reachable():
    from apps.core import detail_parts

    rows = [
        LEAD,
        {"key": "description"},
        MID,
        {"key": "info"},
        {"key": "reviews"},
        {"key": "related"},
    ]
    items = detail_parts.edit_rows({}, "product_detail", rows)
    keys = [i.get("id") or i["key"] for i in items]
    assert keys[:3] == ["p1", "description", "p2"], "блок «до описания» — первым, как на странице"
    cfg = {"product_detail": {"hidden": ["reviews"]}}
    items = detail_parts.edit_rows(cfg, "product_detail", [MID])
    # из хвоста один шаг вверх — над последним разделом (FB-33 M2f: «Zuletzt angesehen»)
    site_schema.mutate(items, "product", "up", "p2")
    keys = [i.get("id") or i["key"] for i in items]
    assert keys.index("p2") == keys.index("related") + 1


@pytest.mark.parametrize("kind,host", [("product", "product_detail"), ("stay", "stay_detail")])
def test_review_tabs_layout_draws_blocks_under_the_tabs(kind, host):
    rows = [{"key": "reviews"}, MID, {"key": "related" if kind == "product" else "similar"}]
    cfg = {g.RENDER[kind][1]: {"layout": "tabs"}, "page_blocks": {host: [LEAD, *rows]}}
    html = g.RENDER[kind][0](cfg).content.decode()
    assert html.count("Vor-Bewertungen-Q") == 1 and html.count("Nach-Bewertungen-Q") == 1
    assert html.index("Vor-Bewertungen-Q") > html.index("data-pd-tabs")
