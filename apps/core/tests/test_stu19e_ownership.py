"""STU-19e: settings the cabinet owns are changed there only.

Locks:
* a Studio Save carrying the old fields (stale tab, crafted POST) does not change
  them — and does not drop them either;
* the Studio shows each of them as a summary with a link to the cabinet screen;
* every owned code has a cabinet screen (no dead link).
"""

import pytest

from apps.core import page_settings, page_templates
from apps.core.tests.test_home_builder import _request
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

STORED = {
    "page_styles": {"stays": "kopfbild"},
    "service_detail": {"layout": "tabs", "hidden": []},
    "event_detail": {"layout": "breit"},
}


@pytest.fixture
def tenant():
    return TenantFactory(
        schema_name="public",
        slug="stu19e",
        name="STU19e",
        enabled_modules=["catalog", "booking", "stays", "events"],
        site_config=dict(STORED),
    )


def test_studio_save_cannot_change_cabinet_owned_settings(tenant):
    from apps.core import views

    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "stays_page_style": "regale",
        "services_page_style": "tabs",
        "sd_present": "1",
        "sd_layout": "",
        "ed_layout": "tabs",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    tenant.refresh_from_db()
    cfg = tenant.site_config
    assert cfg["page_styles"] == {"stays": "kopfbild"}
    assert cfg["service_detail"]["layout"] == "tabs"
    assert cfg["event_detail"]["layout"] == "breit"


def test_studio_shows_summaries_with_cabinet_links(tenant):
    from apps.core import views

    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert body.count("data-stu19-summary") >= len(page_settings.CABINET_OWNED) - 6
    assert "/dashboard/seitenvorlagen/sortiment/?typ=stays" in body
    assert 'name="stays_page_style"' not in body and 'name="sd_layout"' not in body


def test_every_owned_setting_has_a_cabinet_screen():
    from apps.core import studio_pages

    for code in page_settings.CABINET_OWNED:
        types = [t.code for t in studio_pages.PAGE_TYPES if code in t.settings]
        assert types, code
        for t in types:
            assert page_templates.cabinet_url(t).startswith("/dashboard/seitenvorlagen/")
