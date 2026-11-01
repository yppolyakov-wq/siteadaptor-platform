"""STU-19f-1: the cabinet writes the WHOLE grid — preset AND output axis.

Before the Studio grid controls can become summaries (19f-2), the cabinet must offer
everything they offered: grid/slider, rows, page size, last row, speed. Locks:
* `write(..., output=)` replaces the output fields, `output=None` keeps them;
* the Studio and the cabinet parse the output axis with ONE function;
* the cabinet POST carries the output block; a form without it keeps the stored axis;
* the screen shows the block for grid settings only, "Pro Seite" only where the page
  paginates.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import QueryDict
from django.test import RequestFactory

from apps.core import page_settings, page_templates, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="bakery")


def _req(tenant, method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/seitenvorlagen/sortiment/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"g-{o}", email=f"g-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def _layout(tenant):
    tenant.refresh_from_db()
    return tenant.site_config.get("catalog_layout") or {}


def test_write_with_output_stores_the_axis(tenant):
    page_settings.write(
        tenant, "catalog_layout", "cols4", output={"scroll": True, "rows": "2", "tail": "fill"}
    )
    layout = _layout(tenant)
    assert layout["preset"] == "cols4"
    assert layout.get("scroll") is True
    assert int(layout.get("rows")) == 2
    assert layout.get("tail") == "fill"


def test_empty_output_clears_and_none_keeps(tenant):
    page_settings.write(tenant, "catalog_layout", "cols4", output={"rows": "3", "speed": "5"})
    page_settings.write(tenant, "catalog_layout", "cols3")  # output=None: axis kept
    layout = _layout(tenant)
    assert layout["preset"] == "cols3" and int(layout["rows"]) == 3
    page_settings.write(tenant, "catalog_layout", "cols3", output={})  # all "as before"
    layout = _layout(tenant)
    assert "rows" not in layout and "speed" not in layout and not layout.get("scroll")


def test_output_on_a_non_grid_setting_is_refused(tenant):
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "catalog_sort", "newest", output={"rows": "2"})


def test_studio_and_cabinet_parse_the_axis_with_one_function():
    post = QueryDict(
        "f_mode=slider&f_rows=2&f_page_size=24&f_speed=6&f_tail=spread&junk=1", mutable=False
    )
    assert views._page_layout_payload(post, "f", "cols4") == {
        "preset": "cols4",
        **page_settings.output_payload(post, "f"),
    }
    assert page_settings.output_payload(post, "f") == {
        "scroll": True,
        "rows": "2",
        "page_size": "24",
        "speed": "6",
        "tail": "spread",
    }


def test_cabinet_post_writes_the_output_block(tenant):
    resp = page_templates.page_templates_sortiment(
        _req(
            tenant,
            "post",
            {
                "setting": "catalog_layout",
                "typ": "catalog",
                "value": "cols4",
                "out_mode": "slider",
                "out_rows": "2",
                "out_tail": "",
                "out_page_size": "",
                "out_speed": "7",
            },
        )
    )
    assert resp.status_code == 302
    layout = _layout(tenant)
    assert layout.get("scroll") is True and int(layout["rows"]) == 2 and int(layout["speed"]) == 7


def test_cabinet_post_without_the_block_keeps_the_axis(tenant):
    page_settings.write(tenant, "catalog_layout", "cols4", output={"rows": "3"})
    page_templates.page_templates_sortiment(
        _req(tenant, "post", {"setting": "catalog_layout", "typ": "catalog", "value": "cols2"})
    )
    layout = _layout(tenant)
    assert layout["preset"] == "cols2" and int(layout["rows"]) == 3


def test_screen_shows_the_block_for_grids_and_page_size_only_when_paginated(tenant):
    body = page_templates.page_templates_sortiment(_req(tenant, data={"typ": "catalog"}))
    html = body.content.decode()
    form = html.split('data-pt-setting="catalog_layout"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_mode"' in form and 'name="out_page_size"' in form
    sort_form = html.split('data-pt-setting="catalog_sort"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_mode"' not in sort_form
    detail = page_templates.page_templates_sortiment(_req(tenant, data={"typ": "product"}))
    related = detail.content.decode().split('data-pt-setting="product_related"', 1)[1]
    related = related.split("</form>", 1)[0]
    assert 'name="out_mode"' in related and 'name="out_page_size"' not in related
