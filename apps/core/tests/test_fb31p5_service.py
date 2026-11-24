"""FB-31 P5 (услуга): порядок разделов задаёт «Seitenaufbau» (ключ только если задан), свои
блоки встают между разделами, «Kauf» закреплён (у услуги — над разделами)."""

import pytest

from apps.core import site_schema
from apps.core.tests import test_fb31p5_detail_golden as g
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
B1 = {"key": "text", "id": "s1", "data": {"title": "Zwischen-Service", "body": "x"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_order_is_presence_minimal():
    assert "order" not in siteconfig.normalize({})["service_detail"]
    got = siteconfig.normalize({"service_detail": {"order": ["reviews", "evil", "description"]}})
    assert got["service_detail"]["order"] == ["reviews", "description"]


def test_order_and_block_between_sections_render():
    cfg = {
        "service_detail": {"order": ["faq", "description"]},
        "page_blocks": {"service_detail": [{"key": "description"}, B1, {"key": "upsell"}]},
    }
    html = g.RENDER["service"][0](cfg).content.decode()
    assert "Waschen, schneiden" in html
    assert html.count("Zwischen-Service") == 1
    assert html.index("Waschen, schneiden") < html.index("Zwischen-Service")


def test_panel_moves_service_sections_and_saves_the_order():
    tenant = TenantFactory(business_type="friseur", site_config={})
    b = Browser(tenant)
    rows = site_schema.blocks_for(siteconfig.normalize({}), "service", tenant=None)
    assert [r["key"] for r in rows][:3] == ["kauf", "description", "video"], "покупка — первой"
    b.post(seite="service", op="down", ref="description")
    b.post(seite="service", op="save")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["service_detail"]["order"][:2] == ["video", "description"]


def test_review_studio_save_and_preview_keep_the_service_order():
    from apps.core import detail_parts

    cfg = {"service_detail": {"order": ["faq", "description"]}}
    siteconfig.apply_page_payload(cfg, {"service_detail": {"hidden": ["video"]}})
    assert cfg["service_detail"]["order"] == ["faq", "description"]
    rows = siteconfig.page_inspector(cfg, "service_detail")
    assert [r["key"] for r in rows][:2] == ["faq", "description"], "инспектор = страница"
    fresh = {}
    items = detail_parts.edit_rows(fresh, "service_detail", [])
    items.insert(0, items.pop(1))  # video первым
    detail_parts.lift(fresh, "service_detail", items)
    assert fresh["service_detail"]["order"][0] == "video", "порядок записан и без скрытых"
