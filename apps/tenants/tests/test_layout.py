"""M20R-1: универсальный layout-движок секций (пресеты + override + purge-safe грид).

Чистая логика `siteconfig`: normalize_layout, grid_class_string, section_layout,
и привязка layout к секциям-сеткам в normalize() (с back-compat).
"""

from apps.tenants import siteconfig

# --- normalize_layout ---------------------------------------------------------


def test_layout_from_preset_default():
    lay = siteconfig.normalize_layout(None, {"preset": "cols3"})
    assert lay == {
        "preset": "cols3",
        "width": "contained",
        "cols": 3,
        "mobile": 2,
        "tablet": 0,
        "gap": "md",
    }


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


def test_section_limit_default_override_and_clamp():
    # M20U-7: число элементов секции-превью.
    assert siteconfig.section_limit({"sections": []}, "products") == 8  # дефолт
    assert siteconfig.section_limit({"sections": []}, "events") == 6
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True, "limit": 3}]})
    assert siteconfig.section_limit(cfg, "products") == 3
    # мусор/выход за границы → клампится к дефолту/максимуму
    assert siteconfig.section_limit({"sections": [{"key": "events", "limit": "x"}]}, "events") == 6
    assert (
        siteconfig.section_limit({"sections": [{"key": "products", "limit": 999}]}, "products")
        == 24
    )


def test_normalize_attaches_limit_only_to_preview_sections():
    cfg = siteconfig.normalize({})
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    team = next(s for s in cfg["sections"] if s["key"] == "team")
    assert products["limit"] == 8  # дефолт
    assert "limit" not in team  # не секция-превью


def test_product_source_default_override_and_normalize():
    # M20U-7: источник товаров секции products.
    assert siteconfig.product_source({"sections": []}) == "featured_first"  # дефолт
    cfg = siteconfig.normalize({"sections": [{"key": "products", "source": "newest"}]})
    assert siteconfig.product_source(cfg) == "newest"
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["source"] == "newest"
    # мусорный источник → дефолт; не-products секции source не несут
    bad = siteconfig.normalize({"sections": [{"key": "products", "source": "zzz"}]})
    assert siteconfig.product_source(bad) == "featured_first"
    events = next(s for s in bad["sections"] if s["key"] == "events")
    assert "source" not in events


def test_catalog_layout_default_and_override():
    # M20U-7 (per-page): раскладка страницы каталога.
    assert siteconfig.normalize({})["catalog_layout"]["cols"] == 3  # дефолт = прежняя сетка
    cfg = siteconfig.normalize({"catalog_layout": {"preset": "cols4"}})
    assert cfg["catalog_layout"]["cols"] == 4 and cfg["catalog_layout"]["preset"] == "cols4"


def test_stay_index_layout_default_and_override():
    # M20U-7 (per-page): раскладка сетки номеров.
    cfg = siteconfig.normalize({})
    assert cfg["stay_index_layout"]["cols"] == 3 and cfg["stay_index_layout"]["mobile"] == 1
    cfg2 = siteconfig.normalize({"stay_index_layout": {"preset": "cols4"}})
    assert cfg2["stay_index_layout"]["cols"] == 4


def test_detail_related_layout_default_and_override():
    # M20U-7 (per-page): раскладка «похожих товаров» на детальной.
    assert siteconfig.normalize({})["detail_related_layout"]["cols"] == 4  # дефолт
    cfg = siteconfig.normalize({"detail_related_layout": {"preset": "cols3"}})
    assert cfg["detail_related_layout"]["cols"] == 3


def test_events_index_layout_default_list_and_override():
    # M20U-7 (per-page): раскладка индекса событий; дефолт — список.
    assert siteconfig.normalize({})["events_index_layout"]["preset"] == "list"
    cfg = siteconfig.normalize({"events_index_layout": {"preset": "cols2"}})
    assert (
        cfg["events_index_layout"]["preset"] == "cols2" and cfg["events_index_layout"]["cols"] == 2
    )


def test_event_detail_order_default_and_overrides():
    # M20U-4: порядок/видимость тематических секций детальной события.
    full = list(siteconfig.EVENT_DETAIL_SECTION_KEYS)
    assert siteconfig.event_detail_order({}) == full  # дефолт — порядок реестра
    # переупорядочивание: заданные ключи вперёд, остальные — в дефолтном порядке
    cfg = siteconfig.normalize({"event_detail": {"order": ["faq", "idea"], "hidden": ["price"]}})
    order = siteconfig.event_detail_order(cfg)
    assert order[0] == "faq" and order[1] == "idea"
    assert "price" not in order  # скрыта
    assert set(order) == set(full) - {"price"}
    # мусор в order/hidden отбрасывается
    bad = siteconfig.normalize({"event_detail": {"order": ["zzz"], "hidden": ["nope"]}})
    assert siteconfig.event_detail_order(bad) == full


def test_section_show_all_default_and_override():
    # M20U-7: видимость ссылки «View all».
    assert siteconfig.section_show_all({"sections": []}, "products") is True  # дефолт
    cfg = siteconfig.normalize({"sections": [{"key": "products", "show_all": False}]})
    assert siteconfig.section_show_all(cfg, "products") is False
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["show_all"] is False
    # без флага → True; не-viewall секция флаг не несёт
    fresh = siteconfig.normalize({})
    assert next(s for s in fresh["sections"] if s["key"] == "products")["show_all"] is True
    assert "show_all" not in next(s for s in fresh["sections"] if s["key"] == "team")


def test_section_title_default_override_and_cleanup():
    # M20U-7: кастомный заголовок секции.
    assert siteconfig.section_title({"sections": []}, "events") == ""  # дефолт → пусто
    cfg = siteconfig.normalize(
        {"section_titles": {"events": "Unsere Retreats", "hero": "x", "ghost": "y"}}
    )
    # известный title-ключ сохранён; не-title и неизвестные ключи отброшены
    assert cfg["section_titles"] == {"events": "Unsere Retreats"}
    assert siteconfig.section_title(cfg, "events") == "Unsere Retreats"


# --- SE-2d: глобальные дефолты стиля карточек + наследование ------------------


def test_site_defaults_empty_is_zero():
    # legacy: нет site_defaults → нули/false/"" (= текущее поведение, без регрессии)
    empty = {"card_radius": 0, "card_shadow": False, "card_bg": "", "card_padding": 0}
    assert siteconfig.normalize_site_defaults(None) == empty
    assert siteconfig.normalize(None)["site_defaults"] == empty


def test_site_defaults_valid_and_clamped():
    sd = siteconfig.normalize_site_defaults({"card_radius": 12, "card_shadow": True})
    assert sd["card_radius"] == 12 and sd["card_shadow"] is True
    # кламп 0..24 + мусор → 0
    assert siteconfig.normalize_site_defaults({"card_radius": 999})["card_radius"] == 24
    assert siteconfig.normalize_site_defaults({"card_radius": "x"})["card_radius"] == 0


def test_normalize_keeps_site_defaults():
    cfg = siteconfig.normalize({"site_defaults": {"card_radius": 8, "card_shadow": True}})
    assert cfg["site_defaults"]["card_radius"] == 8 and cfg["site_defaults"]["card_shadow"] is True


def test_effective_card_visual_inherits_global():
    # нет секционного override → берётся глобальный дефолт «весь сайт»
    cfg = siteconfig.normalize({"site_defaults": {"card_radius": 10, "card_shadow": True}})
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["radius"] == 10 and v["shadow"] is True


def test_effective_card_visual_section_override_beats_global():
    # секционный radius побеждает глобальный дефолт
    cfg = siteconfig.normalize(
        {
            "site_defaults": {"card_radius": 10, "card_shadow": True},
            "sections": [{"key": "products", "enabled": True, "visual": {"radius": 4}}],
        }
    )
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["radius"] == 4 and v["shadow"] is False


def test_effective_card_visual_section_shadow_is_override():
    # секционная тень (без radius) тоже считается override → глобальный не подмешивается
    cfg = siteconfig.normalize(
        {
            "site_defaults": {"card_radius": 10, "card_shadow": False},
            "sections": [{"key": "events", "enabled": True, "visual": {"shadow": True}}],
        }
    )
    v = siteconfig.effective_card_visual(cfg, "events")
    assert v["radius"] == 0 and v["shadow"] is True


def test_effective_card_visual_legacy_empty():
    # ни глобального, ни секционного → нули (без регрессии)
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True}]})
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["radius"] == 0 and v["shadow"] is False


# --- SE-3d: фон/отступы карточек (visual.background/padding + site_defaults) ---


def test_visual_bg_padding_clamped_and_validated():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "products",
                    "enabled": True,
                    "visual": {"background": "#ABCDEF", "padding": 999},
                }
            ]
        }
    )
    v = siteconfig.section_visual(cfg, "products")
    assert v["background"] == "#ABCDEF" and v["padding"] == 32  # padding клампится 0..32


def test_visual_bg_invalid_dropped():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "visual": {"background": "red"}}]}
    )
    assert siteconfig.section_visual(cfg, "products")["background"] == ""  # не #rrggbb → ""


def test_site_defaults_bg_padding():
    sd = siteconfig.normalize_site_defaults({"card_bg": "#112233", "card_padding": 12})
    assert sd == {"card_radius": 0, "card_shadow": False, "card_bg": "#112233", "card_padding": 12}


def test_effective_card_visual_inherits_global_bg_padding():
    cfg = siteconfig.normalize({"site_defaults": {"card_bg": "#f0f0f0", "card_padding": 16}})
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["background"] == "#f0f0f0" and v["padding"] == 16


def test_effective_card_visual_section_bg_is_override():
    # секционный фон (без radius/shadow) считается override → глобальный НЕ подмешивается
    cfg = siteconfig.normalize(
        {
            "site_defaults": {"card_bg": "#000000", "card_padding": 20},
            "sections": [{"key": "products", "enabled": True, "visual": {"background": "#ffffff"}}],
        }
    )
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["background"] == "#ffffff" and v["padding"] == 0  # секционный, не глобальный


def test_effective_card_visual_legacy_empty_bg_padding():
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True}]})
    v = siteconfig.effective_card_visual(cfg, "products")
    assert v["background"] == "" and v["padding"] == 0  # без регрессии


# --- SE-3b: глобальная типографика (начертание заголовков + межстрочный) -------


def test_typography_empty_default():
    assert siteconfig.normalize_typography(None) == {"weight_head": 0, "line_height": 0.0}
    assert siteconfig.normalize(None)["typography"] == {"weight_head": 0, "line_height": 0.0}


def test_typography_valid_and_invalid():
    t = siteconfig.normalize_typography({"weight_head": 700, "line_height": 1.6})
    assert t == {"weight_head": 700, "line_height": 1.6}
    # вес вне набора → 0; line_height вне 1.0..2.0 → 0.0
    assert siteconfig.normalize_typography({"weight_head": 450})["weight_head"] == 0
    assert siteconfig.normalize_typography({"line_height": 3.0})["line_height"] == 0.0
    assert siteconfig.normalize_typography({"line_height": "x"})["line_height"] == 0.0


def test_normalize_keeps_typography():
    cfg = siteconfig.normalize({"typography": {"weight_head": 600, "line_height": 1.8}})
    assert cfg["typography"] == {"weight_head": 600, "line_height": 1.8}


# --- SE-3a: микрошаблоны «Quick styles» --------------------------------------


def test_micro_templates_registry_valid():
    mts = siteconfig.micro_templates()
    assert len(mts) >= 4
    for mt in mts:
        assert mt["key"] and mt["label"]
        assert mt["preset"] in siteconfig.LAYOUT_PRESETS  # purge-safe: только известные пресеты
        assert 0 <= mt["radius"] <= 24 and 0 <= mt["padding"] <= 32
        assert isinstance(mt["shadow"], bool)


# --- SE-3c: пер-девайс число колонок (tablet) --------------------------------


def test_layout_tablet_default_zero_auto():
    # legacy без tablet → 0 (= авто, прежний планшетный вывод)
    lay = siteconfig.normalize_layout(None, {"preset": "cols4"})
    assert lay["tablet"] == 0


def test_layout_tablet_explicit_and_clamped():
    assert siteconfig.normalize_layout({"preset": "cols4", "tablet": 3})["tablet"] == 3
    assert (
        siteconfig.normalize_layout({"preset": "cols4", "tablet": 99})["tablet"] == 4
    )  # кламп 0..4
    assert siteconfig.normalize_layout({"preset": "cols4", "tablet": "x"})["tablet"] == 0  # мусор


def test_grid_class_string_explicit_tablet_wins():
    # tablet=4 → sm:grid-cols-4 (явный планшет побеждает авто-вывод)
    s = siteconfig.grid_class_string({"preset": "cols4", "tablet": 4})
    assert "sm:grid-cols-4" in s and "lg:grid-cols-4" in s


def test_grid_class_string_tablet_zero_keeps_legacy():
    # tablet=0 (или нет) → прежний авто-вывод (без регрессии)
    auto = siteconfig.grid_class_string({"preset": "cols4"})
    explicit_zero = siteconfig.grid_class_string({"preset": "cols4", "tablet": 0})
    assert auto == explicit_zero == "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 md:gap-6"


# --- SE-4a: блок-шаблоны (многоразовые C-блоки) ------------------------------


def test_block_templates_normalize_and_sanitize():
    cfg = siteconfig.normalize(
        {
            "block_templates": {
                "t1": {
                    "key": "text",
                    "label": "  Hallo  ",
                    "data": {"title": "T", "body": "B", "junk": "x"},
                },
                "t2": {"key": "bogus", "label": "x", "data": {}},  # неизвестный тип → отброшен
            }
        }
    )
    bt = cfg["block_templates"]
    assert "t2" not in bt
    assert bt["t1"]["label"] == "Hallo"  # _s трим
    assert bt["t1"]["data"] == {"title": "T", "body": "B"}  # junk отброшен по типу


def test_block_templates_empty_default():
    assert siteconfig.normalize(None)["block_templates"] == {}


# --- SE-3c-mid: скрыть секцию на устройстве ---------------------------------------


def test_hidden_on_default_empty_for_sections():
    cfg = siteconfig.normalize({})
    for s in cfg["sections"]:
        assert s["hidden_on"] == []  # дефолт = видна везде (без регрессии)


def test_hidden_on_sanitized_and_ordered():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "products", "enabled": True, "hidden_on": ["desktop", "bogus", "mobile"]},
            ]
        }
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    # мусор отброшен, порядок канонический (mobile, tablet, desktop)
    assert products["hidden_on"] == ["mobile", "desktop"]


def test_hidden_on_non_list_falls_back_to_empty():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "hidden_on": "mobile"}]}
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["hidden_on"] == []


def test_hidden_on_on_cblock():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "text", "id": "x1", "data": {"title": "T"}, "hidden_on": ["mobile"]}]}
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "x1")
    assert block["hidden_on"] == ["mobile"]


# --- SE-3e: ширина контейнера секции (contained/full) ----------------------------


def test_section_width_default_contained():
    cfg = siteconfig.normalize({})
    for s in cfg["sections"]:
        assert s["width"] == "contained"  # дефолт = в общем контейнере (без регрессии)


def test_section_width_full_preserved_and_garbage_dropped():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "products", "enabled": True, "width": "full"},
                {"key": "hero", "enabled": True, "width": "weird"},
            ]
        }
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    hero = next(s for s in cfg["sections"] if s["key"] == "hero")
    assert products["width"] == "full"  # валидное значение сохранено
    assert hero["width"] == "contained"  # мусор → дефолт


def test_section_width_on_cblock():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "text", "id": "x9", "data": {"title": "T"}, "width": "full"}]}
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "x9")
    assert block["width"] == "full"  # ширина действует и на C-блоки


# --- H1.5: пер-секционный шрифт ---------------------------------------------------


def test_section_font_default_empty():
    cfg = siteconfig.normalize({})
    for s in cfg["sections"]:
        assert s["font"] == ""  # дефолт = наследовать глобальный (без регрессии)


def test_section_font_valid_and_garbage():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "products", "enabled": True, "font": "serif"},
                {"key": "about", "enabled": True, "font": "nonsense"},
            ]
        }
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    about = next(s for s in cfg["sections"] if s["key"] == "about")
    assert products["font"] == "serif"  # валидный ключ FONTS сохранён
    assert about["font"] == ""  # мусор → наследовать


def test_section_font_on_cblock():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "text", "id": "fz", "data": {"title": "T"}, "font": "rounded"}]}
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "fz")
    assert block["font"] == "rounded"


def test_section_font_vars_tag():
    from apps.tenants.templatetags.siteui import section_font_vars

    assert section_font_vars("") == ""  # наследует — пусто
    assert section_font_vars("bogus") == ""
    out = section_font_vars("serif")
    assert "--font-body:" in out and "--font-head:" in out


# --- SE-4b: шаблоны страниц (page_templates) --------------------------------------


def test_page_templates_empty_default():
    assert siteconfig.normalize(None)["page_templates"] == {}


def test_page_templates_normalize_label_and_sections():
    cfg = siteconfig.normalize(
        {
            "page_templates": {
                "p1": {
                    "label": "  Klassisch  ",
                    "sections": [
                        {"key": "hero", "enabled": True},
                        {"key": "products", "enabled": True},
                    ],
                }
            }
        }
    )
    pt = cfg["page_templates"]["p1"]
    assert pt["label"] == "Klassisch"  # трим
    # секции прогнаны через normalize_sections → фикс-секции дописаны, hero/products есть
    by_key = {s["key"]: s for s in pt["sections"]}
    assert by_key["hero"]["enabled"] is True
    assert by_key["products"]["enabled"] is True
    assert "contact" in by_key  # недостающие фикс-секции дописаны


def test_page_templates_drops_non_dict_and_caps():
    raw = {f"p{i}": {"label": f"T{i}", "sections": []} for i in range(25)}
    raw["bad"] = "not-a-dict"
    cfg = siteconfig.normalize({"page_templates": raw})
    assert len(cfg["page_templates"]) <= siteconfig._MAX_PAGE_TEMPLATES


def test_page_template_sections_sanitized():
    # неизвестный ключ секции в снимке выкидывается normalize_sections
    cfg = siteconfig.normalize(
        {"page_templates": {"p1": {"label": "X", "sections": [{"key": "totally-bogus"}]}}}
    )
    keys = {s["key"] for s in cfg["page_templates"]["p1"]["sections"]}
    assert "totally-bogus" not in keys


def test_normalize_sections_helper_idempotent():
    # рефактор: normalize_sections — module-level, прогон дважды стабилен
    once = siteconfig.normalize_sections([{"key": "products", "enabled": True}])
    twice = siteconfig.normalize_sections(once)
    assert [s["key"] for s in once] == [s["key"] for s in twice]


# --- SE-5b: история версий (history) ----------------------------------------------


def test_history_empty_default():
    assert siteconfig.normalize(None)["history"] == []


def test_normalize_history_sanitizes_and_caps():
    raw = [{"ts": f"t{i}", "config": {"hero_title": str(i)}} for i in range(12)]
    raw.append("not-a-dict")
    raw.append({"ts": "x", "config": "not-a-dict"})  # config не dict → выкинут
    cfg = siteconfig.normalize({"history": raw})
    assert len(cfg["history"]) == siteconfig._MAX_HISTORY  # кап 8
    assert cfg["history"][0] == {"ts": "t0", "config": {"hero_title": "0"}}


def test_normalize_history_strips_nested_history():
    # анти-рекурсия: снимок не должен тащить вложенный history
    cfg = siteconfig.normalize(
        {"history": [{"ts": "t", "config": {"hero_title": "A", "history": [{"x": 1}]}}]}
    )
    assert "history" not in cfg["history"][0]["config"]


def test_push_history_prepends_snapshot():
    prev = {"hero_title": "Old", "history": [{"ts": "z", "config": {}}]}
    out = siteconfig.push_history(prev, [], "2026-06-28T10:00")
    assert out[0]["ts"] == "2026-06-28T10:00"
    assert out[0]["config"]["hero_title"] == "Old"
    assert "history" not in out[0]["config"]  # вложенный history снят


def test_push_history_empty_prev_is_noop():
    # первая публикация (пустой prev) → история без новой записи
    assert siteconfig.push_history({}, [{"ts": "a", "config": {"x": "1"}}], "t") == [
        {"ts": "a", "config": {"x": "1"}}
    ]


def test_push_history_caps_to_max():
    existing = [{"ts": f"e{i}", "config": {"n": str(i)}} for i in range(8)]
    out = siteconfig.push_history({"hero_title": "New"}, existing, "now")
    assert len(out) == siteconfig._MAX_HISTORY
    assert out[0]["config"]["hero_title"] == "New"  # новейшая первая


def test_push_history_strips_draft_keys():
    # SE-5b-2: автосейв-черновик `_draft`/`_draft_ts` не должен попадать в снимок истории
    prev = {"hero_title": "Pub", "_draft": {"hero_title": "WIP"}, "_draft_ts": "t"}
    out = siteconfig.push_history(prev, [], "now")
    assert out[0]["config"] == {"hero_title": "Pub"}  # только опубликованное


def test_normalize_drops_draft_keys_from_served_config():
    # SE-5b-2: `_draft`/`_draft_ts` — служебные, не попадают в нормализованную выдачу
    cfg = siteconfig.normalize({"hero_title": "X", "_draft": {"y": 1}, "_draft_ts": "t"})
    assert "_draft" not in cfg and "_draft_ts" not in cfg
