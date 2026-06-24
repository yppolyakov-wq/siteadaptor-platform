"""M20R-1: универсальный layout-движок секций (пресеты + override + purge-safe грид).

Чистая логика `siteconfig`: normalize_layout, grid_class_string, section_layout,
и привязка layout к секциям-сеткам в normalize() (с back-compat).
"""

from apps.tenants import siteconfig

# --- normalize_layout ---------------------------------------------------------


def test_layout_from_preset_default():
    lay = siteconfig.normalize_layout(None, {"preset": "cols3"})
    assert lay == {"preset": "cols3", "width": "contained", "cols": 3, "mobile": 2, "gap": "md"}


def test_layout_default_mobile_override():
    # дефолт секции может переопределить mobile поверх пресета
    lay = siteconfig.normalize_layout(None, {"preset": "cols3", "mobile": 1})
    assert lay["cols"] == 3 and lay["mobile"] == 1


def test_layout_user_override_beats_preset():
    lay = siteconfig.normalize_layout({"preset": "cols2", "cols": 5, "mobile": 1, "width": "full"})
    assert lay["preset"] == "cols2" and lay["cols"] == 5 and lay["mobile"] == 1
    assert lay["width"] == "full"


def test_layout_clamps_and_sanitizes_garbage():
    lay = siteconfig.normalize_layout(
        {"preset": "nonsense", "cols": 99, "mobile": 7, "gap": "huge", "width": "weird"},
        {"preset": "cols4"},
    )
    assert lay["preset"] == "cols4"  # неизвестный пресет → дефолт
    assert lay["cols"] == 5 and lay["mobile"] == 2  # клампы
    assert lay["gap"] == "md" and lay["width"] == "contained"


# --- grid_class_string (purge-safe) ------------------------------------------


def test_grid_class_string_cols4():
    s = siteconfig.grid_class_string({"preset": "cols4"})
    assert s == "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 md:gap-6"


def test_grid_class_string_list():
    s = siteconfig.grid_class_string({"preset": "list"})
    assert s == "grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-1 gap-4 md:gap-6"


def test_grid_class_string_stay_rooms_default_matches_legacy_tablet():
    # cols3 + mobile1 → планшет 2 (как в старом шаблоне grid-cols-1 sm:2 lg:3)
    s = siteconfig.grid_class_string({"preset": "cols3", "mobile": 1, "cols": 3, "gap": "md"})
    assert s == "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6"


def test_grid_class_string_gallery_tight_gap():
    s = siteconfig.grid_class_string({"preset": "gallery"})
    assert "gap-3" in s and "lg:grid-cols-4" in s


# --- normalize() привязка layout к секциям ----------------------------------


def test_normalize_attaches_layout_to_grid_sections_only():
    cfg = siteconfig.normalize({})
    by_key = {s["key"]: s for s in cfg["sections"]}
    # секция-сетка несёт layout
    assert "layout" in by_key["products"]
    assert by_key["products"]["layout"]["cols"] == 4
    # не-сетка (hero/about) — без layout
    assert "layout" not in by_key["hero"]
    assert "layout" not in by_key["about"]


def test_normalize_preserves_user_layout():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "layout": {"preset": "cols2"}}]}
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["layout"]["cols"] == 2 and products["layout"]["preset"] == "cols2"


def test_normalize_backcompat_old_config_without_layout():
    # старый конфиг без layout → секция получает дефолтную раскладку (без падения)
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True}]})
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["layout"]["cols"] == 4  # дефолт products


def test_section_layout_lookup_and_fallback():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "layout": {"preset": "cols2"}}]}
    )
    assert siteconfig.section_layout(cfg, "products")["cols"] == 2
    # секция без записи → дефолт по ключу
    assert siteconfig.section_layout({"sections": []}, "team")["cols"] == 4
