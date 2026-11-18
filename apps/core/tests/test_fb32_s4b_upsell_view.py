"""FB-32 S4b: вид «Passt dazu» корзины — как у «Ähnliche» (Automatisch · Raster · Slider,
Spalten, Höchstens 4/8/12); настройка живёт на строке «Passt gut dazu» в «Seitenaufbau».
Без выбора владельца корзина рисует прежние 4 карточки сеткой (golden байт-в-байт)."""

import pytest

from apps.core import site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.core.tests.test_fb32_s4_cart_rows import _cart_html
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _more(n):
    from apps.catalog.tests.factories import ProductFactory

    for i in range(n):
        ProductFactory(name={"de": f"Extra {i}"})


def test_without_a_choice_the_old_four_cards_grid():
    assert "cart_upsell_layout" not in siteconfig.normalize({})
    html = _cart_html({})
    assert "data-upsell-grid" not in html and "data-upsell-strip" not in html
    assert 'class="grid grid-cols-2 lg:grid-cols-4 gap-4"' in html


def test_raster_twelve_shows_more_cards_and_auto_strips():
    _more(8)
    html = _cart_html({"cart_upsell_layout": {"preset": "cols3", "raster": True, "max": 12}})
    assert "data-upsell-grid" in html and "data-upsell-strip" not in html
    assert html.count("Extra ") >= 8
    html = _cart_html({"cart_upsell_layout": {"preset": "cols4"}})
    assert "data-upsell-strip" in html, "Automatisch: больше ряда — лента"


def test_setting_lives_on_the_upsell_row_and_saves():
    b = Browser(_tenant())
    assert "cart_upsell_layout" in site_schema.row_settings("cart", "upsell")
    html = b.get("?seite=cart&block=upsell")
    assert "data-schema-related-view" in html and 'name="out_max"' in html
    b.post(
        seite="cart", ref="upsell", op="setting", setting="cart_upsell_layout",
        value="cols3", out_mode="raster", out_max="12",
    )  # fmt: skip
    b.post(seite="cart", op="save")
    lay = _cfg(b.tenant)["cart_upsell_layout"]
    assert lay["cols"] == 3 and lay["raster"] is True and lay["max"] == 12


def test_review_any_schema_save_does_not_switch_the_cart_view():
    b = Browser(_tenant())
    b.post(seite="cart", op="add", type="text")
    b.post(seite="cart", op="save")
    assert "cart_upsell_layout" not in (b.tenant.__class__.objects.get(pk=b.tenant.pk).site_config)


def test_review_owner_can_go_back_to_the_old_four_cards():
    b = Browser(_tenant())
    b.post(
        seite="cart", ref="upsell", op="setting", setting="cart_upsell_layout",
        value="cols3", out_mode="raster", out_max="12",
    )  # fmt: skip
    b.post(seite="cart", op="save")
    assert "cart_upsell_layout" in _cfg(b.tenant)
    html = b.get("?seite=cart&block=upsell")
    assert "data-schema-related-standard" in html
    b.post(seite="cart", ref="upsell", op="setting", setting="cart_upsell_layout", value="")
    b.post(seite="cart", op="save")
    assert "cart_upsell_layout" not in _cfg(b.tenant)
