"""FB-27 R4a: настройки типа страницы пачкой и по черновику (сервис `page_settings`)."""

import pytest

from apps.core import page_settings
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _state(tenant, type_code, code, config=None):
    (ts,) = page_settings.schema(tenant, (type_code,), config=config)
    return next(s for s in ts.settings if s.code == code)


def test_schema_describes_a_given_config_not_the_saved_one():
    tenant = _tenant()
    draft = page_settings.apply_override(tenant.site_config or {}, "catalog_sort", "price_asc")
    assert _state(tenant, "catalog", "catalog_sort", config=draft).value == "price_asc"
    assert _state(tenant, "catalog", "catalog_sort").value != "price_asc"  # сохранённое прежнее


def test_write_many_equals_a_sequence_of_single_writes():
    one, many = _tenant(), _tenant()
    pending = {
        "catalog_sort": {"v": "price_asc", "o": None},
        "catalog_filters": {"v": "0", "o": None},
        "catalog_layout": {"v": "cols4", "o": {"rows": "2"}},
    }
    for code, entry in pending.items():
        page_settings.write(one, code, entry["v"], entry["o"])
    page_settings.write_many(many, pending)
    a = siteconfig.normalize(Tenant.objects.get(pk=one.pk).site_config)
    b = siteconfig.normalize(Tenant.objects.get(pk=many.pk).site_config)
    assert a == b and b["catalog_sort"] == "price_asc"


def test_one_bad_value_writes_nothing():
    tenant = _tenant()
    before = Tenant.objects.get(pk=tenant.pk).site_config
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write_many(
            tenant,
            {"catalog_sort": {"v": "price_asc", "o": None}, "catalog_layout": {"v": "<x>"}},
        )
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_output_axis_is_refused_for_a_plain_setting():
    tenant = _tenant()
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write_many(tenant, {"catalog_sort": {"v": "price_asc", "o": {"rows": "2"}}})


# ───────────── R4b: настройки типа в черновике «Seitenaufbau» ─────────────

from apps.core import aufbau_draft  # noqa: E402
from apps.core.tests.test_fb27_r2_draft import Browser  # noqa: E402


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _saved(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def test_setting_waits_in_the_draft_until_saved(_urlconf):
    b = Browser(_tenant())
    b.post(seite="catalog", op="setting", setting="catalog_sort", value="price_asc")
    assert _saved(b.tenant)["catalog_sort"] != "price_asc"
    assert "data-schema-draft" in b.get("?seite=catalog")
    b.post(seite="catalog", op="save")
    assert _saved(b.tenant)["catalog_sort"] == "price_asc"
    assert "data-schema-draft" not in b.get("?seite=catalog")


def test_setting_back_to_the_saved_value_leaves_no_draft(_urlconf):
    b = Browser(_tenant())
    old = _saved(b.tenant)["catalog_sort"]
    b.post(seite="catalog", op="setting", setting="catalog_sort", value="price_asc")
    b.post(seite="catalog", op="setting", setting="catalog_sort", value=old)
    assert "data-schema-draft" not in b.get("?seite=catalog")


def test_setting_of_another_page_type_is_refused(_urlconf):
    b = Browser(_tenant())
    _resp, msgs = b.post(seite="text", op="setting", setting="catalog_sort", value="price_asc")
    assert msgs and "nicht möglich" in msgs[0]
    assert "data-schema-draft" not in b.get("?seite=text")


def test_garbage_value_is_refused_and_nothing_is_drafted(_urlconf):
    b = Browser(_tenant())
    _resp, msgs = b.post(seite="catalog", op="setting", setting="catalog_sort", value="<x>")
    assert msgs and "nicht möglich" in msgs[0]
    assert "data-schema-draft" not in b.get("?seite=catalog")


def test_grid_output_axis_needs_its_sentinel(_urlconf):
    """Без `out_mode` ряды и лента остаются как были (W0)."""
    b = Browser(_tenant())
    page_settings.write(b.tenant, "catalog_layout", "cols4", {"rows": "2"})
    b.post(seite="catalog", op="setting", setting="catalog_layout", value="cols3")
    b.post(seite="catalog", op="save")
    layout = _saved(b.tenant)["catalog_layout"]
    assert layout["preset"] == "cols3" and layout.get("rows") == 2
    b.post(
        seite="catalog", op="setting", setting="catalog_layout", value="cols3",
        out_mode="slider", out_rows="",
    )  # fmt: skip
    b.post(seite="catalog", op="save")
    layout = _saved(b.tenant)["catalog_layout"]
    assert layout.get("scroll") is True and "rows" not in layout


def test_draft_setting_is_visible_in_the_overlay_preview(_urlconf):
    b = Browser(_tenant())
    b.post(seite="catalog", op="setting", setting="catalog_sort", value="price_asc")
    req = b._request("get")
    draft = aufbau_draft.get(req, "catalog")
    shown = aufbau_draft.overlay(_saved(b.tenant), draft)
    assert shown["catalog_sort"] == "price_asc"


def test_shared_key_changed_elsewhere_is_a_conflict(_urlconf):
    b = Browser(_tenant())
    b.post(seite="catalog", op="setting", setting="product_card_form", value="deal")
    page_settings.write(b.tenant, "product_card_form", "regal")  # другая страница/вкладка
    _resp, msgs = b.post(seite="catalog", op="save")
    assert any("inzwischen" in m for m in msgs)
    assert _saved(b.tenant)["site_defaults"]["card_style"] == "regal"


def test_old_draft_without_settings_still_works(_urlconf):
    """Черновик, начатый до R4 (нет `settings`/`kbase`), не падает и сохраняется."""
    b = Browser(_tenant())
    from apps.core import site_schema as ss

    req = b._request("post")
    aufbau_draft.op(req, b.tenant, "text", "add", block_type="text")
    draft = dict(req.session[aufbau_draft.SESSION_KEY]["text"])
    assert "settings" not in draft and "kbase" not in draft
    assert aufbau_draft.info(req, _saved(b.tenant), "text")["conflict"] is False
    b.post(seite="text", op="save")
    assert ss.blocks_for(_saved(b.tenant), "text")


# ───────────── R4c: панель настроек типа в «Seitenaufbau» ─────────────

from apps.core import site_schema  # noqa: E402

_ALL_TYPES = [key for key, _label in Tenant.BUSINESS_TYPES]


@pytest.mark.parametrize("business_type", _ALL_TYPES)
def test_every_page_setting_is_reachable_from_seitenaufbau(business_type):
    """Главный замок R4: «Seitenvorlagen» сносится, поэтому КАЖДАЯ настройка каждого
    активного типа страниц обязана правиться с какой-то строки «Seitenaufbau»."""
    tenant = TenantFactory(
        business_type=business_type,
        disabled_modules=list(default_disabled_for(business_type)),
    )
    wanted = {s.code for ts in page_settings.schema(tenant) for s in ts.settings}
    cfg = siteconfig.normalize(tenant.site_config)
    rows = [r for _label, items in site_schema.type_groups(tenant, cfg) for r in items]
    reachable = set()
    for row in rows:
        reachable.update(site_schema.setting_codes(tenant, row.code))
    assert wanted and wanted <= reachable, sorted(wanted - reachable)


def test_main_list_panel_carries_the_page_settings(_urlconf):
    b = Browser(_tenant())
    cfg = siteconfig.normalize(b.tenant.site_config)
    main = next(x for x in site_schema.blocks_for(cfg, "catalog") if x["main"])
    html = b.get(f"?seite=catalog&block={main['ref']}")
    assert "data-schema-settings" in html
    for code in ("catalog_sort", "catalog_layout", "product_card_form"):
        assert f'data-schema-setting="{code}"' in html
    assert 'name="out_mode"' in html  # ось вывода сетки — в той же форме


def test_page_without_a_main_list_gets_a_settings_row(_urlconf):
    b = Browser(_tenant())
    html = b.get("?seite=text")
    assert 'data-schema-block="__page"' in html and "data-schema-settings" not in html
    html = b.get("?seite=text&block=__page")
    assert 'data-schema-setting="text_width"' in html and "gilt für alle Seiten" in html


def test_category_settings_live_on_the_catalog_row(_urlconf):
    b = Browser(_tenant())
    assert "category_page_style" in site_schema.setting_codes(b.tenant, "catalog")


def test_panel_shows_the_draft_value_not_the_saved_one(_urlconf):
    b = Browser(_tenant())
    cfg = siteconfig.normalize(b.tenant.site_config)
    main = next(x for x in site_schema.blocks_for(cfg, "catalog") if x["main"])
    b.post(seite="catalog", op="setting", ref=main["ref"], setting="catalog_filters", value="0")
    html = b.get(f"?seite=catalog&block={main['ref']}")
    form = html[html.index('data-schema-setting="catalog_filters"') :]
    form = form[: form.index("</form>")]
    assert 'value="0" checked' in form
