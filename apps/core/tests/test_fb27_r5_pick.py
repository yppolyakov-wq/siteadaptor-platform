"""FB-27 R5: «Einzeln» — ручной состав блока «Liste» с порядком."""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.tests.factories import ProductFactory
from apps.core import list_blocks, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _data(tenant, host="info"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return next(b for b in cfg["page_blocks"][host] if b.get("id"))["data"]


def _products(n):
    return [ProductFactory(name={"de": f"Ware {i}"}) for i in range(n)]


def _block(tenant, **fields):
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    site_schema.apply(tenant, "text", "update", ref=ref, fields={"source": "products", **fields})
    return ref


# ───────────── R5a: данные и выборка ─────────────


def test_rubbish_in_pick_never_reaches_the_config():
    good = str(uuid.uuid4())
    raw = {"source": "products", "pick": [good, good, "<x>", 7, None, "nope"]}
    assert siteconfig._clean_list_block(raw)["pick"] == [good]
    many = {"source": "products", "pick": [str(uuid.uuid4()) for _ in range(100)]}
    assert len(siteconfig._clean_list_block(many)["pick"]) == siteconfig.LIST_LIMIT_MAX
    assert "pick" not in siteconfig._clean_list_block({"source": "products", "pick": []})
    assert "pick" not in siteconfig._clean_list_block({"source": "products", "pick": "abc"})


def test_sources_without_manual_choice_drop_the_pick():
    raw = {"source": "reviews", "pick": [str(uuid.uuid4())]}
    assert "pick" not in siteconfig._clean_list_block(raw)


def test_storefront_shows_exactly_the_pick_in_its_order():
    a, b, c = _products(3)
    data = {"source": "products", "pick": [str(c.pk), str(a.pk)]}
    res = list_blocks.resolve({}, data)
    assert [p.pk for p in res["items"]] == [c.pk, a.pk]
    assert res["more"] is False and b.pk not in [p.pk for p in res["items"]]


def test_hidden_or_deleted_entries_fall_out_and_the_rest_stays():
    a, b = _products(2)
    b.is_active = False
    b.save(update_fields=["is_active"])
    data = {"source": "products", "pick": [str(b.pk), str(uuid.uuid4()), str(a.pk)]}
    assert [p.pk for p in list_blocks.resolve({}, data)["items"]] == [a.pk]


def test_query_count_does_not_grow_with_the_pick():
    items = _products(8)

    def count(n):
        data = {"source": "products", "pick": [str(p.pk) for p in items[:n]]}
        with CaptureQueriesContext(connection) as ctx:
            list_blocks.resolve({}, data)
        return len(ctx)

    assert count(8) == count(2)


# ───────────── R5b: операции черновика ─────────────


def test_pick_goes_through_the_draft_and_keeps_the_rule():
    tenant = _tenant()
    a, b = _products(2)
    ref = _block(tenant, only="sale")
    browser = Browser(tenant)
    browser.post(seite="text", op="pick_add", ref=ref, value=str(a.pk))
    browser.post(seite="text", op="pick_add", ref=ref, value=str(b.pk))
    assert "pick" not in _data(tenant)  # пока черновик
    browser.post(seite="text", op="save")
    data = _data(tenant)
    assert data["pick"] == [str(a.pk), str(b.pk)] and data["only"] == "sale"


def test_pick_order_and_removal():
    tenant = _tenant()
    a, b, c = _products(3)
    ref = _block(tenant)
    for p in (a, b, c):
        site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(p.pk))
    site_schema.apply(tenant, "text", "pick_up", ref=ref, value=str(c.pk))
    assert _data(tenant)["pick"] == [str(a.pk), str(c.pk), str(b.pk)]
    site_schema.apply(tenant, "text", "pick_down", ref=ref, value=str(a.pk))
    assert _data(tenant)["pick"] == [str(c.pk), str(a.pk), str(b.pk)]
    site_schema.apply(tenant, "text", "pick_remove", ref=ref, value=str(a.pk))
    assert _data(tenant)["pick"] == [str(c.pk), str(b.pk)]
    site_schema.apply(tenant, "text", "pick_clear", ref=ref)
    assert "pick" not in _data(tenant)


def test_only_a_live_entry_of_the_blocks_source_can_be_added():
    tenant = _tenant()
    (a,) = _products(1)
    hidden = ProductFactory(is_active=False)
    ref = _block(tenant)
    for bad in (str(uuid.uuid4()), str(hidden.pk), "<script>", ""):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(tenant, "text", "pick_add", ref=ref, value=bad)
    site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(a.pk))
    site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(a.pk))  # повтор — не дубль
    assert _data(tenant)["pick"] == [str(a.pk)]


def test_changing_the_source_resets_the_pick():
    tenant = _tenant()
    (a,) = _products(1)
    ref = _block(tenant)
    site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(a.pk))
    site_schema.apply(tenant, "text", "update", ref=ref, fields={"source": "promotions"})
    assert "pick" not in _data(tenant)


def test_pick_is_full_at_the_limit():
    tenant = _tenant()
    items = _products(siteconfig.LIST_LIMIT_MAX + 1)
    ref = _block(tenant)
    for p in items[:-1]:
        site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(p.pk))
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(items[-1].pk))


# ───────────── R5c: панель ─────────────


def test_panel_lists_the_pick_and_marks_what_is_gone():
    tenant = _tenant()
    a, b = _products(2)
    ref = _block(tenant)
    for p in (a, b):
        site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(p.pk))
    b.is_active = False
    b.save(update_fields=["is_active"])
    html = Browser(tenant).get(f"?seite=text&block={ref}")
    assert "data-schema-pick" in html and "Ware 0" in html
    assert html.count("data-schema-pick-item") == 2
    assert "nicht mehr verfügbar" in html
    assert 'name="f_sort"' not in html and 'name="f_limit"' not in html  # при ручном составе


def test_lookup_offers_live_entries_that_are_not_picked_yet():
    tenant = _tenant()
    a, b = _products(2)
    ProductFactory(name={"de": "Ware versteckt"}, is_active=False)
    ref = _block(tenant)
    site_schema.apply(tenant, "text", "pick_add", ref=ref, value=str(a.pk))
    html = Browser(tenant).get(f"?seite=text&block={ref}&lookup=Ware")
    offers = html[html.index("data-schema-pick-offers") :]
    offers = offers[: offers.index("</ul>")]
    assert str(b.pk) in offers and str(a.pk) not in offers and "versteckt" not in offers


def test_panel_without_pick_offers_to_choose_by_hand():
    tenant = _tenant()
    _products(1)
    ref = _block(tenant)
    html = Browser(tenant).get(f"?seite=text&block={ref}")
    assert "data-schema-pick" in html and "data-schema-pick-item" not in html
    assert 'name="f_sort"' in html
