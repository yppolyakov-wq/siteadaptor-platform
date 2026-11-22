"""FB-31 P2 (стратегия блоков): общие для всего сайта настройки — форма карточек товаров и
акций, ширина текста, цены и метки в меню — правятся на экране «Design» («Für alle
Seiten»). Панель «Seitenaufbau» их только показывает строкой «wie Design: X · ändern →»;
поправки «только здесь» у блоков и объектов остаются."""

import pytest

from apps.core import design_page, page_settings, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_stu12_design_screen import _html, _post
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type="online_shop", **kw):
    return TenantFactory(
        business_type=business_type,
        disabled_modules=list(default_disabled_for(business_type)),
        **kw,
    )


def test_no_page_row_edits_a_design_setting():
    tenant = _tenant()
    cfg = siteconfig.normalize(tenant.site_config)
    for _label, rows in site_schema.type_groups(tenant, cfg):
        for row in rows:
            codes = set(site_schema.setting_codes(tenant, row.code))
            assert not codes & set(page_settings.DESIGN_SETTINGS), row.code


def test_page_row_refuses_a_design_setting_op():
    b = Browser(_tenant())
    _resp, _msgs = b.post(seite="catalog", op="setting", setting="product_card_form", value="deal")
    b.tenant.refresh_from_db()
    assert "card_style" not in (b.tenant.site_config.get("site_defaults") or {})


def test_design_screen_saves_the_shared_settings_at_once():
    tenant = _tenant()
    body = _html(tenant, ("karten",))
    assert 'data-design-form="defaults"' in body
    for code in ("product_card_form", "text_width"):
        assert f'data-design-default="{code}"' in body
    cfg = _post(
        tenant,
        {"action": "design_defaults", "dd_product_card_form": "deal", "dd_text_width": "wide"},
    )
    assert cfg["site_defaults"]["card_style"] == "deal"
    assert cfg["site_defaults"]["text_width"] == "wide"


def test_field_missing_from_the_post_keeps_its_value():
    tenant = _tenant()
    page_settings.write(tenant, "text_width", "wide")
    cfg = _post(tenant, {"action": "design_defaults", "dd_product_card_form": "deal"})
    assert cfg["site_defaults"]["text_width"] == "wide"


def test_invalid_value_writes_nothing():
    tenant = _tenant()
    cfg = _post(
        tenant,
        {"action": "design_defaults", "dd_product_card_form": "deal", "dd_text_width": "nope"},
    )
    assert "card_style" not in cfg["site_defaults"], "всё или ничего"


def test_menu_prices_only_without_orders_and_labels_only_for_food():
    shop = _tenant()
    codes = {s.code for s in page_settings.design_schema(shop)}
    assert "catalog_menu_prices" not in codes, "PAngV: при заказах цены не прячем"
    assert "catalog_menu_labels" not in codes
    cafe = _tenant("cafe", enabled_modules=["catalog"])
    cafe_codes = {s.code for s in page_settings.design_schema(cafe)}
    assert "catalog_menu_labels" in cafe_codes


def test_panel_shows_the_design_value_with_a_link():
    b = Browser(_tenant())
    page_settings.write(b.tenant, "product_card_form", "deal")
    cfg = siteconfig.normalize(b.tenant.site_config)
    assert cfg is not None
    # FB-33 M5b-2 W1: настройки типа и строки «Design» — у ★-строки страницы (не у ★)
    html = b.get(f"?seite=catalog&block={site_schema.page_row_ref(b.tenant, 'catalog')}")
    row = html.split('data-schema-design-row="product_card_form"', 1)[1].split("</p>", 1)[0]
    assert "wie Design" in row and "?tab=karten#dd-product_card_form" in row


def test_studio_summary_links_to_design():
    tenant = _tenant()
    found = page_settings.summaries(tenant, ["product_card_form", "catalog_sort"])
    assert found["product_card_form"]["url"].endswith("?tab=karten#dd-product_card_form")
    assert "/aufbau/" in found["catalog_sort"]["url"]


def test_both_card_forms_have_distinct_labels_on_design():
    tenant = _tenant(enabled_modules=["catalog", "promotions"])
    labels = [str(s.label) for s in design_page._design_defaults(tenant)]
    assert len(labels) == len(set(labels))


def test_review_bool_setting_shows_its_value_not_true():
    cafe = _tenant("cafe", enabled_modules=["catalog"])
    page_settings.write(cafe, "catalog_menu_labels", "1")
    found = page_settings.summaries(cafe, ["catalog_menu_labels"])
    assert str(found["catalog_menu_labels"]["value"]) not in {"True", "False", "Standard"}


def test_review_old_draft_does_not_write_a_design_setting():
    from apps.core import aufbau_draft

    draft = {"settings": {"product_card_form": {"v": "deal"}, "catalog_sort": {"v": "newest"}}}
    assert set(aufbau_draft._settings(draft)) == {"catalog_sort"}
