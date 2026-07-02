"""UC1-1 (U-C): единый реестр секций по типу страницы — фасад
`page_types`/`page_section_keys`/`page_section_labels`/`page_sections`
над SECTIONS (home) и apps.core.detail_sections (детальные)."""

from apps.core import detail_sections
from apps.tenants import siteconfig
from apps.tenants.tests.golden_configs import DETAIL_PAGES, RICH_HOME


def test_page_types_cover_home_details_listing_info_legal():
    assert siteconfig.page_types() == (
        "home",
        "product_detail",
        "event_detail",
        "service_detail",
        "stay_detail",
        "listing",
        "info",
        "legal",
    )


def test_static_page_types_fixed_order_config_ignored():
    """UC1-2: listing/info/legal — фиксированный порядок реестра; конфиг пока
    не управляет ими (управление — UC2-3/UC3-2)."""
    assert siteconfig.page_sections({}, "listing") == [
        "header",
        "facets",
        "toolbar",
        "grid",
        "pagination",
        "empty",
        "after",
    ]
    assert siteconfig.page_sections({"listing": {"hidden": ["grid"]}}, "listing") == list(
        siteconfig.page_section_keys("listing")
    )
    assert siteconfig.page_sections({}, "legal") == ["impressum", "datenschutz", "widerruf"]
    assert siteconfig.page_sections({}, "info") == ["about"]


def test_keys_match_underlying_registries():
    assert siteconfig.page_section_keys("home") == tuple(k for k, _l, _e in siteconfig.SECTIONS)
    assert siteconfig.page_section_keys("event_detail") == siteconfig.EVENT_DETAIL_SECTION_KEYS
    assert siteconfig.page_section_keys("product_detail") == siteconfig.PRODUCT_DETAIL_SECTION_KEYS
    assert siteconfig.page_section_keys("service_detail") == detail_sections.section_keys("booking")
    assert siteconfig.page_section_keys("stay_detail") == detail_sections.section_keys("stays")
    assert siteconfig.page_section_keys("nope") == ()  # fail-safe


def test_every_key_has_label_on_every_page_type():
    for pt in siteconfig.page_types():
        labels = siteconfig.page_section_labels(pt)
        for key in siteconfig.page_section_keys(pt):
            assert labels.get(key), (pt, key)
    assert siteconfig.page_section_labels("nope") == {}


def test_home_page_sections_default_config_matches_defaults():
    expected = [k for k, _l, enabled in siteconfig.SECTIONS if enabled]
    assert siteconfig.page_sections({}, "home") == expected
    assert siteconfig.page_sections(None, "home") == expected  # мусор-safe


def test_home_page_sections_respects_order_toggle_and_cblocks():
    keys = siteconfig.page_sections(RICH_HOME, "home")
    # порядок конфига: products → C-блоки (text/image_text; выключенный button
    # отсутствует) → hero → faq; выключенные фикс-секции не попадают.
    assert keys[:5] == ["products", "text", "image_text", "hero", "faq"]
    assert "button" not in keys  # C-блок с enabled=False скрыт
    assert "about" not in keys  # фикс-секция по дефолту выключена


def test_detail_page_sections_apply_order_and_hidden():
    keys = siteconfig.page_sections(DETAIL_PAGES, "event_detail")
    assert keys[:3] == ["program", "for_whom", "faq"]  # сохранённый порядок
    assert "testimonials" not in keys  # скрыта конфигом
    assert set(keys) < set(siteconfig.EVENT_DETAIL_SECTION_KEYS) | set(keys)
    assert siteconfig.page_sections(DETAIL_PAGES, "product_detail") == [
        k for k in siteconfig.PRODUCT_DETAIL_SECTION_KEYS if k != "related"
    ]
    assert "team" not in siteconfig.page_sections(DETAIL_PAGES, "service_detail")
    assert "similar" not in siteconfig.page_sections(DETAIL_PAGES, "stay_detail")


def test_unknown_page_type_is_empty_list():
    assert siteconfig.page_sections({"sections": []}, "nope") == []


def test_page_inspector_hide_only_and_orderable():
    """UC1-3: generic-инспектор деталей — hide-only без order, event с order
    и сохранённым порядком; паритет с прежней ручной сборкой home_builder_view."""
    rows = siteconfig.page_inspector(DETAIL_PAGES, "product_detail")
    assert [r["key"] for r in rows] == list(siteconfig.PRODUCT_DETAIL_SECTION_KEYS)
    by_key = {r["key"]: r for r in rows}
    assert by_key["related"]["visible"] is False  # скрыта конфигом
    assert "order" not in rows[0]  # hide-only — без order

    ev = siteconfig.page_inspector(DETAIL_PAGES, "event_detail")
    assert [r["key"] for r in ev[:3]] == ["program", "for_whom", "faq"]  # сохранённый порядок
    assert [r["order"] for r in ev] == list(range(1, len(ev) + 1))  # 1-based
    assert {r["key"]: r["visible"] for r in ev}["testimonials"] is False
    assert len(ev) == len(siteconfig.EVENT_DETAIL_SECTION_KEYS)  # скрытые остаются в списке

    assert siteconfig.page_inspector({}, "home") == []  # home — свой формат, не здесь
    assert siteconfig.page_inspector({}, "listing") == []  # fail-safe


def test_page_section_icons_home_only_for_now():
    icons = siteconfig.page_section_icons("home")
    for key in siteconfig.page_section_keys("home"):
        assert icons.get(key), key  # у каждой home-секции есть иконка
    assert siteconfig.page_section_icons("event_detail") == {}


# --- UC2-1 (слайс A): page-scoped draft-модуль -----------------------------------


def test_page_config_keys_registry_consistent_with_apply_groups():
    """Реестр PAGE_CONFIG_KEYS и группы apply_page_payload — одно множество
    ключей (замок от расхождения декларации и применения)."""
    from_registry = {k for keys in siteconfig.PAGE_CONFIG_KEYS.values() for k in keys}
    from_apply = (
        set(siteconfig._PAGE_DETAIL_KEYS)
        | set(siteconfig._PAGE_LAYOUT_KEYS)
        | set(siteconfig._PAGE_BOOL_KEYS)
        | {"catalog_sort"}
    )
    assert from_registry == from_apply


def test_apply_page_payload_semantics_match_legacy_branches():
    """Семантика 1:1 с прежними ветками site_preview_draft: детали — dict как
    есть; раскладки — только валидный preset; флаги — строгий bool; сорт — реестр."""
    cfg = {}
    siteconfig.apply_page_payload(
        cfg,
        {
            "event_detail": {"order": ["faq"], "hidden": []},
            "product_detail": "мусор",  # не dict → игнор
            "catalog_layout": {"preset": "cols3"},
            "stay_index_layout": {"preset": "нет-такого"},  # невалид → игнор
            "service_index_layout": {"preset": "list"},
            "catalog_show_filters": True,
            "catalog_subcats_first": "on",  # не bool → игнор
            "cart_show_upsell": False,
            "catalog_sort": "price_asc",
        },
    )
    assert cfg["event_detail"] == {"order": ["faq"], "hidden": []}
    assert "product_detail" not in cfg
    assert cfg["catalog_layout"] == {"preset": "cols3"}
    assert "stay_index_layout" not in cfg
    assert cfg["service_index_layout"] == {"preset": "list"}
    assert cfg["catalog_show_filters"] is True
    assert "catalog_subcats_first" not in cfg
    assert cfg["cart_show_upsell"] is False
    assert cfg["catalog_sort"] == "price_asc"
    # пустой payload ничего не пишет (частичный драфт не трёт)
    cfg2 = {"catalog_sort": "newest"}
    siteconfig.apply_page_payload(cfg2, {})
    assert cfg2 == {"catalog_sort": "newest"}


def test_page_config_slices_normalized_config():
    cfg = {
        "event_detail": {"order": ["program"], "hidden": ["testimonials"]},
        "catalog_layout": {"preset": "cols2"},
        "catalog_sort": "price_desc",
    }
    ev = siteconfig.page_config(cfg, "event_detail")
    assert set(ev) == {"event_detail"} and "testimonials" in ev["event_detail"]["hidden"]
    listing = siteconfig.page_config(cfg, "listing")
    assert listing["catalog_layout"]["preset"] == "cols2"  # normalize материализует cols/mobile
    assert listing["catalog_sort"] == "price_desc"
    # service_index_layout не материализован → его нет в срезе
    assert "service_index_layout" not in listing
    assert siteconfig.page_config(cfg, "nope") == {}  # fail-safe
