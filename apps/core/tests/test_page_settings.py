"""STU-19a: one service for page settings (schema + targeted write + preview).

Locks:
* the schema is derived from the Studio registry — no second list of settings;
* every setting the cabinet offers has a value spec (allowed values + labels);
* a write touches ONE key and keeps every other key (W0/W6 class);
* garbage and unavailable templates are refused, the config stays unchanged;
* the cabinet validator agrees with the Studio scope validator (STU-15 class);
* the preview override never writes anything.
"""

import pytest

from apps.catalog.models import Category
from apps.core import page_settings, studio_pages, studio_scope
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return TenantFactory(business_type="bakery")


def _codes(type_schema):
    return {s.code for s in type_schema.settings}


def test_schema_agrees_with_registry(tenant):
    """Every supported type shows exactly the registry's settings minus the
    Studio-only block order (and minus settings that do not apply here)."""
    for ts in page_settings.schema(tenant):
        expected = {
            s.code
            for s in studio_pages.settings_for(ts.code)
            if not page_settings.is_studio_only(s) and page_settings.applies(tenant, s)
        }
        assert _codes(ts) == expected, ts.code


def test_block_order_stays_in_studio(tenant):
    codes = set().union(*(_codes(ts) for ts in page_settings.schema(tenant)))
    assert "product_detail_sections" not in codes
    assert not any(c.endswith("_sections") for c in codes)


def test_every_supported_setting_has_a_spec():
    for type_code in page_settings.SUPPORTED_TYPES:
        for s in page_settings.cabinet_settings(type_code):
            assert page_settings.choices(s), s.code


def test_object_scoped_values_agree_with_studio_scope():
    """Two validators for one setting must not drift (STU-15 precedent). The Studio
    also ACCEPTS legacy codes that are no longer offered (reading is wider than
    offering, LAY Р-2), so the cabinet's offer must be a subset of it."""
    for type_code in page_settings.SUPPORTED_TYPES:
        for s in page_settings.cabinet_settings(type_code):
            if not s.has_object_scope:
                continue
            cabinet = {c.value for c in page_settings.choices(s)} - {""}
            assert cabinet <= set(studio_scope._valid_values(s)), s.code


def test_regale_unavailable_without_subcategories_then_available(tenant):
    def regale(ts_code):
        ts = next(t for t in page_settings.schema(tenant, (ts_code,)))
        row = next(r for r in ts.settings if r.code.endswith("page_style"))
        return next(c for c in row.choices if c.value == "regale")

    choice = regale("category")
    assert not choice.available and choice.reason

    parent = Category.objects.create(name={"de": "Brot"}, slug="brot", is_active=True)
    Category.objects.create(name={"de": "Roggen"}, slug="roggen", parent=parent, is_active=True)
    assert regale("category").available


@pytest.mark.parametrize(
    "code,value,path,stored",
    [
        ("catalog_page_style", "magazin", ("catalog_page_style",), "magazin"),
        ("category_page_style", "kopfbild", ("site_defaults", "category_page_style"), "kopfbild"),
        ("product_card_form", "lookbook", ("site_defaults", "card_style"), "lookbook"),
        ("catalog_sort", "price_asc", ("catalog_sort",), "price_asc"),
        ("product_detail_layout", "tabs", ("product_detail", "layout"), "tabs"),
        ("catalog_filters", "0", ("catalog_show_filters",), False),
        ("catalog_layout", "cols5", ("catalog_layout", "preset"), "cols5"),
        ("catalog_layout", "preisliste", ("catalog_layout", "preset"), "preisliste"),
        ("product_related", "cols2", ("detail_related_layout", "preset"), "cols2"),
    ],
)
def test_write_round_trip(tenant, code, value, path, stored):
    page_settings.write(tenant, code, value)
    tenant.refresh_from_db()
    node = tenant.site_config
    for part in path:
        node = node[part]
    assert node == stored


def test_write_keeps_every_other_key(tenant):
    """W6: a single write must not drop foreign keys (Studio, SEO, board, …)."""
    tenant.site_config = {
        "seo": {"title": "X"},
        "board": {"labels": {"new": "Neu"}},
        "page_blocks": {"info": [{"id": "a"}]},
        "promo_groups": {"Brot": "prospekt"},
        "site_defaults": {"card_radius": 12, "category_page_style": "magazin"},
        "catalog_layout": {"preset": "cols4", "rows": 2, "scroll": True},
        "_draft": {"hero_title": "draft"},
    }
    tenant.save(update_fields=["site_config"])
    page_settings.write(tenant, "product_card_form", "deal")
    page_settings.write(tenant, "catalog_layout", "cols3")
    tenant.refresh_from_db()
    cfg = tenant.site_config
    assert cfg["seo"] == {"title": "X"}
    assert cfg["board"] == {"labels": {"new": "Neu"}}
    assert cfg["page_blocks"] == {"info": [{"id": "a"}]}
    assert cfg["promo_groups"] == {"Brot": "prospekt"}
    assert cfg["_draft"] == {"hero_title": "draft"}
    assert cfg["site_defaults"]["card_radius"] == 12
    assert cfg["site_defaults"]["category_page_style"] == "magazin"
    assert cfg["site_defaults"]["card_style"] == "deal"
    # the grid output type survives a preset change
    assert cfg["catalog_layout"]["preset"] == "cols3"
    assert cfg["catalog_layout"]["rows"] == 2 and cfg["catalog_layout"]["scroll"] is True


def test_empty_value_removes_the_key(tenant):
    page_settings.write(tenant, "catalog_page_style", "magazin")
    page_settings.write(tenant, "catalog_page_style", "")
    tenant.refresh_from_db()
    assert "catalog_page_style" not in tenant.site_config


@pytest.mark.parametrize(
    "code,value",
    [
        ("catalog_page_style", "erfunden"),
        ("catalog_layout", "cols99"),
        ("product_related", "preisliste"),  # extra preset of the catalog only
        ("catalog_filters", "vielleicht"),
        ("product_detail_sections", "x"),  # Studio-only
        ("promo_page_style", "magazin"),  # not offered in the cabinet yet
        ("nope", "x"),
    ],
)
def test_garbage_is_refused_and_nothing_changes(tenant, code, value):
    tenant.site_config = {"catalog_page_style": "kompakt"}
    tenant.save(update_fields=["site_config"])
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, code, value)
    tenant.refresh_from_db()
    assert tenant.site_config == {"catalog_page_style": "kompakt"}


def test_unavailable_template_cannot_be_chosen(tenant):
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "category_page_style", "regale")


def test_menu_prices_only_for_browse_only_storefront(tenant, monkeypatch):
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: key == "orders")
    codes = _codes(page_settings.schema(tenant, ("catalog",))[0])
    assert "catalog_menu_prices" not in codes
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "catalog_menu_prices", "0")


def test_preview_config_is_in_memory_only(tenant):
    tenant.site_config = {"catalog_page_style": "kompakt"}
    tenant.save(update_fields=["site_config"])
    cfg = page_settings.preview_config(tenant, tenant.site_config, "catalog_page_style:magazin")
    assert cfg["catalog_page_style"] == "magazin"
    tenant.refresh_from_db()
    assert tenant.site_config == {"catalog_page_style": "kompakt"}


@pytest.mark.parametrize("tpl", ["", "catalog_page_style", "catalog_page_style:erfunden", "x:y"])
def test_preview_config_ignores_garbage(tenant, tpl):
    assert page_settings.preview_config(tenant, {}, tpl) is None


def test_legacy_current_value_can_be_kept(tenant):
    """A code removed from the offer (e.g. category "preisliste") still renders;
    saving the same value again must not fail."""
    tenant.site_config = {"site_defaults": {"category_page_style": "preisliste"}}
    tenant.save(update_fields=["site_config"])
    assert page_settings.write(tenant, "category_page_style", "preisliste") == "preisliste"


def test_write_bumps_storefront_cache_on_commit(tenant, django_capture_on_commit_callbacks):
    from apps.core import pagecache

    before = pagecache._sf_version(tenant.schema_name)
    with django_capture_on_commit_callbacks(execute=True):
        page_settings.write(tenant, "catalog_sort", "price_desc")
    assert pagecache._sf_version(tenant.schema_name) == before + 1


def test_protect_owned_keeps_stored_value(tenant):
    """Locks a/b: an owned setting cannot be changed by a stale Studio payload."""
    tenant.site_config = {
        "catalog_page_style": "magazin",
        "site_defaults": {"card_style": "deal", "card_radius": 4},
        "catalog_layout": {"preset": "cols5"},
    }
    tenant.save(update_fields=["site_config"])
    stale = {
        "catalog_page_style": "kompakt",
        "site_defaults": {"card_style": "", "card_radius": 9},
        "catalog_layout": {"preset": "list"},
        "hero_title": "neu",
    }
    owned = {"catalog_page_style", "product_card_form", "catalog_layout"}
    out = page_settings.protect_owned(tenant, stale, owned)
    assert out["catalog_page_style"] == "magazin"
    assert out["site_defaults"]["card_style"] == "deal"
    assert out["site_defaults"]["card_radius"] == 9, "non-owned keys follow the Studio"
    assert out["catalog_layout"] == {"preset": "cols5"}
    assert out["hero_title"] == "neu"


def test_protect_owned_removes_key_absent_in_store(tenant):
    tenant.site_config = {}
    tenant.save(update_fields=["site_config"])
    out = page_settings.protect_owned(
        tenant, {"catalog_page_style": "kompakt"}, {"catalog_page_style"}
    )
    assert "catalog_page_style" not in out


def test_nothing_is_cabinet_owned_yet():
    """19a ships the mechanism only; the set grows with 19e/19f (Studio control removed
    in the same commit)."""
    assert page_settings.CABINET_OWNED == frozenset()


def test_empty_bool_value_is_not_off(tenant):
    """Review: a lost form field must not switch a setting off."""
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "catalog_filters", "")


def test_every_setting_can_resave_its_current_value(tenant):
    """Saving what is already shown must never fail (a stuck setting otherwise)."""
    for type_code in page_settings.SUPPORTED_TYPES:
        for s in page_settings.schema(tenant, (type_code,))[0].settings:
            value = ("1" if s.value else "0") if s.kind == "bool" else s.value
            page_settings.write(tenant, s.code, value)


def test_apply_override_refuses_unknown_codes():
    with pytest.raises(page_settings.PageSettingError):
        page_settings.apply_override({}, "nope", "x")
    with pytest.raises(page_settings.PageSettingError):
        page_settings.apply_override({}, "product_detail_sections", "x")
