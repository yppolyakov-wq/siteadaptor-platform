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
from apps.core import page_settings, studio_pages
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
        ("promo_page_style", "erfunden"),
        ("services_sort", "erfunden"),
        ("tours_layout", "preisliste"),  # extra preset of the catalog only
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
    monkeypatch.setattr(
        type(tenant), "is_module_active", lambda self, key: key in ("orders", "catalog")
    )
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


def test_cabinet_owned_is_exactly_the_moved_axes():
    """19e-1: listing templates + detail layouts. The set grows axis by axis (19e-2,
    19e-3, 19f), always in the same commit that removes the Studio control."""
    from apps.core import compositions

    assert page_settings.CABINET_OWNED == frozenset(
        {f"{s}_page_style" for s in compositions.LISTING_SURFACES}
        | {
            "product_detail_layout",
            "service_detail_layout",
            "stay_detail_layout",
            "event_detail_layout",
            # 19e-2
            "catalog_page_style",
            "category_page_style",
            "promo_page_style",
            "promo_group_style",
            "promo_detail_style",
            # 19e-3
            "home_hero",
            # 19f-3: card forms
            "product_card_form",
            "promo_card_form",
            # 19f-2: the twelve page grids
            "catalog_layout",
            "product_related",
            "service_layout",
            "stay_layout",
            "events_layout",
            "promo_index_layout",
            "combos_layout",
            "tours_layout",
            "lookbook_layout",
            "reviews_page_layout",
            "wishlist_layout",
            "blog_index_layout",
        }
    )


def test_empty_bool_value_is_not_off(tenant):
    """Review: a lost form field must not switch a setting off."""
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "catalog_filters", "")


def test_every_setting_can_resave_its_current_value(tenant):
    """Saving what is already shown must never fail (a stuck setting otherwise)."""
    for ts in page_settings.schema(tenant):
        for s in ts.settings:
            value = ("1" if s.value else "0") if s.kind == "bool" else s.value
            page_settings.write(tenant, s.code, value)


def test_apply_override_refuses_unknown_codes():
    with pytest.raises(page_settings.PageSettingError):
        page_settings.apply_override({}, "nope", "x")
    with pytest.raises(page_settings.PageSettingError):
        page_settings.apply_override({}, "product_detail_sections", "x")


# ── STU-19d: every page type ─────────────────────────────────────────────────────


@pytest.fixture
def all_modules(monkeypatch, tenant):
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: True)
    return tenant


def test_every_type_has_a_module_entry():
    """A new page type must say which module it belongs to (or None)."""
    assert set(page_settings.TYPE_MODULES) == set(page_settings.SUPPORTED_TYPES)


def test_types_of_inactive_modules_are_not_offered(tenant, monkeypatch):
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: key == "catalog")
    codes = {ts.code for ts in page_settings.schema(tenant)}
    assert "catalog" in codes and "text" in codes
    assert not codes & {"services", "stays", "events", "promos", "blog"}
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "services_sort", "price_asc")


def test_every_offered_value_round_trips(all_modules):
    """Writing any offered value, then reading it back, gives that value — for all
    settings of all types (the storage paths of 19d are many and different)."""
    gate = {k: set() for k in page_settings.composition_gate({})}
    for ts in page_settings.schema(all_modules):
        for st in ts.settings:
            setting = studio_pages.SETTINGS[st.code]
            for choice in page_settings.choices(setting, gate):
                stored = choice.value == "1" if st.kind == page_settings.KIND_BOOL else choice.value
                cfg = page_settings.apply_override({"keep": 1}, st.code, stored)
                assert cfg["keep"] == 1, st.code
                value, _set = page_settings.current_value(cfg, setting)
                if st.kind == page_settings.KIND_BOOL:
                    assert value is (choice.value == "1"), st.code
                elif choice.value == "" and st.code == "home_hero":
                    pass
                else:
                    assert value == choice.value, (st.code, choice.value, value)


def test_optional_layout_standard_removes_the_key(all_modules):
    page_settings.write(all_modules, "tours_layout", "cols3")
    assert all_modules.site_config["tours_layout"]["preset"] == "cols3"
    page_settings.write(all_modules, "tours_layout", "")
    assert "tours_layout" not in all_modules.site_config


def test_promo_grid_retires_the_legacy_switch(all_modules):
    all_modules.site_config = {"promo_layout": "slider"}
    all_modules.save(update_fields=["site_config"])
    page_settings.write(all_modules, "promo_index_layout", "cols4")
    assert "promo_layout" not in all_modules.site_config


def test_promo_grid_standard_keeps_the_legacy_ribbon(all_modules):
    """ "Standard" means "as it is now" — the legacy ribbon must survive it."""
    all_modules.site_config = {"promo_layout": "slider"}
    all_modules.save(update_fields=["site_config"])
    page_settings.write(all_modules, "promo_index_layout", "")
    assert all_modules.site_config["promo_layout"] == "slider"


def test_types_the_storefront_hides_are_not_offered(all_modules):
    codes = set(page_settings.active_types(all_modules))
    assert "finder" not in codes  # Finder is an option, off by default
    all_modules.site_config = {"profile": "aktionen"}
    codes = set(page_settings.active_types(all_modules))
    assert not codes & {"catalog", "category", "product", "cart", "combos"}
    assert "promos" in codes


def test_listing_template_is_presence_minimal(all_modules, monkeypatch):
    monkeypatch.setattr(page_settings, "composition_gate", lambda cfg=None: {"services": set()})
    page_settings.write(all_modules, "services_page_style", "kompakt")
    assert all_modules.site_config["page_styles"] == {"services": "kompakt"}
    page_settings.write(all_modules, "services_page_style", "")
    assert "page_styles" not in all_modules.site_config


def test_detail_layout_and_upsell_are_targeted(all_modules):
    all_modules.site_config = {"service_detail": {"hidden": ["faq"]}, "x": 1}
    all_modules.save(update_fields=["site_config"])
    page_settings.write(all_modules, "service_detail_layout", "tabs")
    page_settings.write(all_modules, "cart_upsell", "0")
    cfg = all_modules.site_config
    assert cfg["service_detail"] == {"hidden": ["faq"], "layout": "tabs"}
    assert cfg["cart_show_upsell"] is False and cfg["x"] == 1


def test_storefront_reader_applies_cabinet_preview_only_for_members(tenant, monkeypatch):
    """STU-19d: every storefront view reads `raw_config` — the `?tpl=` override for a
    signed-in member, the saved config for anyone else."""
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: True)
    tenant.site_config = {"x": 1}
    tenant.save(update_fields=["site_config"])
    req = RequestFactory().get("/termin/", {"preview": "1", "tpl": "services_sort:price_asc"})
    req.tenant, req.session = tenant, {}
    req.user = AnonymousUser()
    assert page_settings.raw_config(req) == {"x": 1}
    monkeypatch.setattr(page_settings, "_may_preview", lambda request: True)
    req2 = RequestFactory().get("/termin/", {"preview": "1", "tpl": "services_sort:price_asc"})
    req2.tenant, req2.session = tenant, {}
    assert page_settings.raw_config(req2) == {"x": 1, "services_sort": "price_asc"}
