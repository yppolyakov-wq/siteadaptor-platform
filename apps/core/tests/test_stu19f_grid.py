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
    request = getattr(RequestFactory(), method)("/dashboard/seitenvorlagen/", data or {})
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


def test_output_payload_collects_only_filled_fields():
    post = QueryDict(
        "f_mode=slider&f_rows=2&f_page_size=24&f_speed=6&f_tail=spread&junk=1", mutable=False
    )
    assert page_settings.output_payload(post, "f") == {
        "scroll": True,
        "rows": "2",
        "page_size": "24",
        "speed": "6",
        "tail": "spread",
    }
    empty = QueryDict("f_mode=grid&f_rows=&f_tail=", mutable=False)
    assert page_settings.output_payload(empty, "f") == {}


def test_cabinet_post_writes_the_output_block(tenant):
    resp = page_templates.page_templates_website(
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
    page_templates.page_templates_website(
        _req(tenant, "post", {"setting": "catalog_layout", "typ": "catalog", "value": "cols2"})
    )
    layout = _layout(tenant)
    assert layout["preset"] == "cols2" and int(layout["rows"]) == 3


def test_screen_shows_the_block_for_grids_and_page_size_only_when_paginated(tenant):
    body = page_templates.page_templates_website(_req(tenant, data={"typ": "catalog"}))
    html = body.content.decode()
    form = html.split('data-pt-setting="catalog_layout"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_mode"' in form and 'name="out_page_size"' in form
    sort_form = html.split('data-pt-setting="catalog_sort"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_mode"' not in sort_form
    detail = page_templates.page_templates_website(_req(tenant, data={"typ": "product"}))
    related = detail.content.decode().split('data-pt-setting="product_related"', 1)[1]
    related = related.split("</form>", 1)[0]
    assert 'name="out_mode"' in related and 'name="out_page_size"' not in related


# ───────────── 19f-2: the Studio no longer writes grids ─────────────


def test_studio_save_cannot_change_a_grid():
    from apps.core.tests.test_home_builder import _request

    stored = {"preset": "cols3", "rows": 2, "scroll": True}
    t = TenantFactory(
        schema_name="public",
        slug="stu19f",
        name="STU19f",
        enabled_modules=["catalog", "events"],
        site_config={"catalog_layout": dict(stored), "events_index_layout": {"preset": "list"}},
    )
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "catalog_preset": "cols6",
        "catalog_preset_mode": "grid",
        "catalog_preset_rows": "",
        "events_preset": "cols4",
        "related_preset": "cols2",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, t))
    t.refresh_from_db()
    assert t.site_config["catalog_layout"]["preset"] == "cols3"
    assert t.site_config["catalog_layout"].get("scroll") is True
    assert t.site_config["events_index_layout"]["preset"] == "list"


def test_studio_shows_grid_summaries_not_controls():
    from apps.core.tests.test_home_builder import _request

    t = TenantFactory(
        schema_name="public", slug="stu19f2", name="STU19f2", enabled_modules=["catalog"]
    )
    page_settings.write(t, "catalog_layout", "cols4", output={"scroll": True})
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=t)
    ).content.decode()
    assert 'name="catalog_preset"' not in body and 'name="catalog_preset_mode"' not in body
    assert 'name="related_preset"' not in body
    row = body.split('data-stu-setting="catalog_layout"', 1)[1].split("</div>\n", 2)
    assert "data-stu19-summary" in "".join(row[:2]) and "Slider" in "".join(row[:2])


def test_apply_all_copies_the_grid_to_the_other_lists():
    t = TenantFactory(business_type="bakery", enabled_modules=["catalog", "events", "stays"])
    page_templates.page_templates_website(
        _req(
            t,
            "post",
            {
                "setting": "catalog_layout",
                "typ": "catalog",
                "value": "cols4",
                "out_mode": "slider",
                "apply_all": "1",
            },
        )
    )
    t.refresh_from_db()
    for key in ("catalog_layout", "events_index_layout", "stay_index_layout"):
        assert t.site_config[key]["preset"] == "cols4", key
        assert t.site_config[key].get("scroll") is True, key


# ───────────── review 19f ─────────────


def test_changing_the_preset_really_changes_the_columns(tenant):
    """normalize stores cols/mobile/tablet/gap and reads them BEFORE the preset — kept,
    they made "4 per row" after "3 per row" a no-op."""
    page_settings.write(tenant, "catalog_layout", "cols3")
    page_settings.write(tenant, "catalog_layout", "cols4")
    tenant.refresh_from_db()
    from apps.tenants import siteconfig

    assert siteconfig.normalize(tenant.site_config)["catalog_layout"]["cols"] == 4


def test_output_block_is_hidden_while_standard(tenant):
    t = TenantFactory(business_type="bakery", enabled_modules=["catalog", "booking"])
    body = page_templates.page_templates_website(_req(t, data={"typ": "services"}))
    form = body.content.decode().split('data-pt-setting="service_layout"', 1)[1]
    form = form.split("</form>", 1)[0]
    i = form.index("<fieldset", form.index("data-pt-output") - 120)
    opening = form[i : form.index(">", i)]
    assert "data-pt-output" in opening and " hidden" in opening, opening


def test_apply_all_names_the_lists_it_skipped():
    from django.contrib.messages import get_messages

    t = TenantFactory(business_type="bakery", enabled_modules=["catalog", "events"])
    req = _req(
        t,
        "post",
        {
            "setting": "catalog_layout",
            "typ": "catalog",
            "value": "preisliste",
            "out_mode": "grid",
            "apply_all": "1",
        },
    )
    page_templates.page_templates_website(req)
    texts = [str(m) for m in get_messages(req)]
    assert any("Nicht übernommen" in m for m in texts), texts


# ───────────── 19f-4: page content settings live in the cabinet ─────────────

CONTENT_FIELDS = (
    "catalog_sort",
    "catalog_show_filters",
    "catalog_subcats_first",
    "menu_show_prices",
    "menu_labels",
    "promo_grouping",
    "cart_show_upsell",
    "services_sort",
    "stays_sort",
    "events_sort",
    "sd_text_width",
)


def test_studio_has_no_page_content_controls():
    from apps.core.tests.test_home_builder import _request

    t = TenantFactory(schema_name="public", slug="stu19c", name="STU19c", disabled_modules=[])
    body = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=t))
    html = body.content.decode()
    for field in CONTENT_FIELDS:
        assert f'name="{field}"' not in html, field


def test_studio_save_cannot_change_page_content():
    from apps.core.tests.test_home_builder import _request

    t = TenantFactory(schema_name="public", slug="stu19c2", name="STU19c2", disabled_modules=[])
    page_settings.write(t, "catalog_sort", "price_asc")
    page_settings.write(t, "text_width", "wide")
    page_settings.write(t, "promo_grouping", "time")
    views.home_builder_view(
        _request(
            "post",
            "/dashboard/site/home/",
            {
                "cf_present": "1",
                "catalog_sort": "newest",
                "tw_present": "1",
                "sd_text_width": "",
                "promo_grouping": "",
            },
            t,
        )
    )
    t.refresh_from_db()
    assert t.site_config["catalog_sort"] == "price_asc"
    assert t.site_config["site_defaults"]["text_width"] == "wide"
    assert t.site_config["promo_grouping"] == "time"


@pytest.mark.parametrize("profile,shown", [("aktionen", False), ("", True)])
def test_nur_aktionen_studio_has_no_empty_catalog_rows(profile, shown):
    """A "Nur Aktionen" shop has no catalog/cart pages: their Studio rows would be empty
    shells with a lone "Cart page" label (STU-19 review)."""
    import uuid

    from apps.core.tests.test_home_builder import _request

    slug = f"na{uuid.uuid4().hex[:8]}"
    t = TenantFactory(
        schema_name="public",
        slug=slug,
        name=slug,
        disabled_modules=[],
        site_config={"profile": profile} if profile else {},
    )
    html = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=t))
    html = html.content.decode()
    for marker in (
        '<div class="page-block" data-page-key="cart"',
        '<div class="page-block" data-page-key="catalog"',
        'data-stu-setting="product_card_form"',
    ):
        assert (marker in html) is shown, marker
