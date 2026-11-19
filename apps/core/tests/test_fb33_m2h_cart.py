"""FB-33 M2h-1: оформление строками корзины — позиции, форма, итог с кнопкой неподвижны;
свои блоки над корзиной, «Hinweise» над формой, под сеткой и в хвосте (§ 312j BGB: у кнопки — нет).
"""

import pytest

from apps.core import detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.core.tests.test_fb33_m2h_before import HINT, MID, TAIL, TOP, cart_html

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


ROWS = [
    TOP,
    {"key": "items"},
    HINT,
    {"key": "form"},
    {"key": "summary"},
    MID,
    {"key": "upsell"},
    TAIL,
]


def test_places_on_the_page():
    html = cart_html({"page_blocks": {"cart": ROWS}})
    at = {k: html.index(k) for k in ("BLOCK-TOP", "BLOCK-HINT", "BLOCK-MID", "BLOCK-TAIL")}
    assert at["BLOCK-TOP"] < html.index("Bauernbrot") < at["BLOCK-HINT"]
    assert at["BLOCK-HINT"] < html.index('id="checkout-form"')
    assert html.index("Zahlungspflichtig bestellen") < at["BLOCK-MID"] < html.index("Dazu 0")
    assert html.index("Dazu 0") < at["BLOCK-TAIL"]


def test_block_after_the_strip_is_drawn():
    """FB-32 S4 терял блоки после «Passt dazu», когда выше неё стоял свой блок."""
    html = cart_html({"page_blocks": {"cart": [MID, {"key": "upsell"}, TAIL]}})
    assert html.index("BLOCK-MID") < html.index("Dazu 0") < html.index("BLOCK-TAIL")


def test_block_between_form_and_summary_goes_under_the_grid():
    rows = [{"key": "items"}, {"key": "form"}, HINT, {"key": "summary"}, {"key": "upsell"}]
    parts = detail_parts.cart_parts({"page_blocks": {"cart": rows}})
    assert parts["hint"] == "" and parts["flow"][0] == {"part": "ids:t-hint"}


def test_old_rows_keep_their_place():
    assert detail_parts.cart_flow({"page_blocks": {"cart": [MID, {"key": "upsell"}]}}) == [
        {"part": "ids:t-mid"},
        {"section": "upsell"},
    ]
    assert detail_parts.cart_parts({"page_blocks": {"cart": [MID]}}) == {}


def test_pinned_rows_in_wrong_order_are_read_in_registry_order():
    rows = [{"key": "summary"}, MID, {"key": "items"}, HINT, {"key": "upsell"}]
    a = detail_parts.anchors(rows, "cart", list(detail_parts.flow_section_keys("cart")))
    # неподвижные строки встают в порядке реестра на свои места: блоки не теряются
    assert a["after"] == {"summary": ["t-mid", "t-hint"]} and a["lead"] == []


def _items():
    return [dict(r) for r in ROWS]


@pytest.mark.parametrize("key", ["items", "form", "summary"])
@pytest.mark.parametrize("op", ["up", "down", "toggle"])
def test_pinned_rows_do_not_move_or_hide(key, op):
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(_items(), "cart", op, ref=key)


def test_upsell_does_not_go_above_the_summary():
    items = [{"key": "items"}, {"key": "form"}, {"key": "summary"}, {"key": "upsell"}]
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "cart", "up", ref="upsell")
    assert [i["key"] for i in items] == ["items", "form", "summary", "upsell"]
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "cart", "move", ref="upsell", value="before:items")


def _order(items):
    return [i.get("id") or i["key"] for i in items]


def test_block_steps_over_the_form_and_summary():
    items = _items()
    site_schema.mutate(items, "cart", "down", ref="t-hint")
    assert _order(items).index("t-hint") == _order(items).index("summary") + 1
    site_schema.mutate(items, "cart", "up", ref="t-hint")
    assert _order(items).index("t-hint") == _order(items).index("items") + 1
    site_schema.mutate(items, "cart", "move", ref="t-tail", value="after:form")
    assert _order(items).index("t-tail") == _order(items).index("summary") + 1


def test_schema_shows_the_rows_and_saves_the_hint_place():
    b = Browser(_tenant())
    html = b.get("?seite=cart")
    for key in ("items", "form", "summary", "upsell"):
        assert f'data-schema-block="{key}"' in html
    b.post(seite="cart", op="add", block_type="text")
    rows = (_cfg(b.tenant).get("page_blocks") or {}).get("cart") or []
    assert rows == [] or all(r.get("key") != "items" or not r.get("id") for r in rows)
