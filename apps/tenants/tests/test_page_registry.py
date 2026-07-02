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
