"""FB-32 S4: корзина блоками — «Passt gut dazu» строкой схемы «Seitenaufbau» (двигается,
скрывается, свои блоки выше/ниже), как разделы детальных страниц. Видимость — прежний
`cart_show_upsell`; без своих блоков выше полосы страница рисуется прежней разметкой."""

import pytest

from apps.core import detail_parts
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.core.tests.test_fb31p5_detail_golden import _req

pytestmark = pytest.mark.django_db

TEXT = {
    "key": "text",
    "id": "t-cart",
    "enabled": True,
    "data": {"title": "Abholung", "body": "Ab 8 Uhr"},
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cart_html(cfg):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views

    item = ProductFactory(name={"de": "Bauernbrot"})
    for i in range(4):
        ProductFactory(name={"de": f"Dazu {i}"})
    req = _req("/warenkorb/", cfg)
    req.session["cart"] = {str(item.pk): 1}
    return public_views.cart_view(req).content.decode()


def test_cart_schema_has_the_upsell_row_and_own_blocks():
    b = Browser(_tenant())
    html = b.get("?seite=cart")
    assert 'data-schema-block="upsell"' in html
    assert 'data-schema-block="__kauf"' not in html, "у корзины нет строки покупки"


def test_hide_writes_the_old_switch_and_position_is_kept_only_when_needed():
    b = Browser(_tenant())
    b.post(seite="cart", op="toggle", ref="upsell")
    b.post(seite="cart", op="save")
    assert _cfg(b.tenant)["cart_show_upsell"] is False
    b.post(seite="cart", op="toggle", ref="upsell")
    b.post(seite="cart", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["cart_show_upsell"] is True
    assert not [
        r for r in (cfg.get("page_blocks") or {}).get("cart", []) if r.get("key") == "upsell"
    ]


def test_own_block_above_the_strip_is_drawn_above_it():
    cfg = {"page_blocks": {"cart": [TEXT, {"key": "upsell"}]}}
    assert detail_parts.cart_flow(cfg)[0]["part"] == "ids:t-cart"
    html = _cart_html(cfg)
    assert html.index("Ab 8 Uhr") < html.index("Dazu")
    html = _cart_html({"page_blocks": {"cart": [TEXT]}})
    assert html.index("Dazu") < html.index("Ab 8 Uhr"), "без якоря — как раньше: полоса, блоки"
    assert detail_parts.cart_flow({"page_blocks": {"cart": [TEXT]}}) == []


def test_lift_keeps_the_anchor_only_with_a_block_above():
    cfg: dict = {}
    out = detail_parts.lift(cfg, "cart", [{"key": "upsell", "enabled": True}, TEXT])
    assert out == [TEXT] and "cart_show_upsell" not in cfg
    out = detail_parts.lift(cfg, "cart", [TEXT, {"key": "upsell", "enabled": False}])
    assert out == [TEXT, {"key": "upsell"}] and cfg["cart_show_upsell"] is False


def test_upsell_settings_live_on_its_row_not_on_the_page_row():
    from apps.core import site_schema

    b = Browser(_tenant())
    assert site_schema.row_settings("cart", "upsell") == ("cart_upsell",)
    html = b.get("?seite=cart&block=upsell")
    assert 'data-schema-setting-box="cart_upsell"' in html
    page = b.get("?seite=cart&block=__page")
    assert 'data-schema-setting-box="cart_upsell"' not in page


def test_review_hidden_strip_with_a_block_above_keeps_the_block_and_no_strip():
    cfg = {"cart_show_upsell": False, "page_blocks": {"cart": [TEXT, {"key": "upsell"}]}}
    flow = detail_parts.cart_flow(cfg)
    assert {"section": "upsell"} not in flow and flow[0]["part"] == "ids:t-cart"
    html = _cart_html(cfg)
    assert "Ab 8 Uhr" in html and "Dazu" not in html


def test_review_empty_cart_draws_own_blocks_once():
    from apps.orders import public_views

    cfg = {"page_blocks": {"cart": [TEXT, {"key": "upsell"}]}}
    html = public_views.cart_view(_req("/warenkorb/", cfg)).content.decode()
    assert html.count("Ab 8 Uhr") == 1
