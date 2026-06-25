"""Спринт A.3 (T-B): полоса доверия usp_bar — нормализация + парс + рендер."""

from django.template.loader import render_to_string

from apps.tenants import siteconfig

# --- нормализация / парсинг ---------------------------------------------------


def test_clean_usp_validates_icon_and_drops_empty_label():
    out = siteconfig.clean_usp(
        [
            {"icon": "shipping", "label": "Versand ab 4,90 €"},
            {"icon": "unknown-token", "label": "Fallback"},  # неизвестная иконка → check
            {"icon": "payment", "label": ""},  # пустой label → пропуск
            "garbage",  # не dict → пропуск
        ]
    )
    assert out == [
        {"icon": "shipping", "label": "Versand ab 4,90 €"},
        {"icon": "check", "label": "Fallback"},
    ]


def test_clean_usp_caps():
    raw = [{"icon": "check", "label": f"U{i}"} for i in range(10)]
    assert len(siteconfig.clean_usp(raw)) == siteconfig._MAX_USP


def test_text_to_usp_roundtrip():
    items = [{"icon": "returns", "label": "14 Tage Widerruf"}]
    text = siteconfig.usp_to_text(items)
    assert text == "returns | 14 Tage Widerruf"
    assert siteconfig.text_to_usp(text) == items


def test_text_to_usp_unknown_icon_falls_back():
    assert siteconfig.text_to_usp("foo | Bar") == [{"icon": "check", "label": "Bar"}]


def test_usp_icon_fallback():
    assert siteconfig.usp_icon("shipping") == "🚚"
    assert siteconfig.usp_icon("nope") == "✓"


def test_normalize_includes_usp_bar():
    cfg = siteconfig.normalize({"usp_bar": [{"icon": "bio", "label": "Bio"}]})
    assert cfg["usp_bar"] == [{"icon": "bio", "label": "Bio"}]


def test_parse_content_sections_reads_usp():
    data = {"usp_text": "secure | SSL-verschlüsselt"}
    frag = siteconfig.parse_content_sections(data.get)
    assert frag["usp_bar"] == [{"icon": "secure", "label": "SSL-verschlüsselt"}]


def test_usp_bar_in_registry_disabled_by_default():
    default = {s["key"]: s["enabled"] for s in siteconfig.default_sections()}
    assert default["usp_bar"] is False


# --- рендер партиала ----------------------------------------------------------


def test_usp_bar_renders_items():
    html = render_to_string(
        "storefront/sections/_usp_bar.html",
        {"site": {"usp_bar": [{"icon": "shipping", "label": "Versand ab 4,90 €"}]}},
    )
    assert "Versand ab 4,90 €" in html
    assert "🚚" in html


def test_usp_bar_empty_renders_nothing():
    html = render_to_string("storefront/sections/_usp_bar.html", {"site": {"usp_bar": []}})
    assert html.strip() == ""
