"""Спринт D.2: C-блоки (повторяемые «кубики») — нормализация + рендер."""

from django.template import Context
from django.test import RequestFactory

from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui

# --- нормализация -----------------------------------------------------------------


def test_normalize_keeps_multiple_cblocks_with_ids_and_data():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "hero", "enabled": True},
                {"key": "text", "id": "a1", "enabled": True, "data": {"title": "T", "body": "B"}},
                {"key": "text", "id": "a2", "enabled": True, "data": {"title": "Zwei"}},
                {"key": "button", "data": {"label": "Los", "url": "/x"}},  # id сгенерится
            ]
        }
    )
    blocks = [s for s in cfg["sections"] if s["key"] in siteconfig.REPEATABLE_BLOCKS]
    assert len(blocks) == 3  # два text + button, НЕ дедуплены по key
    assert blocks[0]["id"] == "a1" and blocks[0]["data"]["body"] == "B"
    assert blocks[2]["id"]  # автогенерируемый id непустой
    assert blocks[2]["data"] == {"label": "Los", "url": "/x"}


def test_cblock_data_sanitized_per_type():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "image_text", "data": {"url": "/i.jpg", "side": "bogus"}}]}
    )
    block = next(s for s in cfg["sections"] if s["key"] == "image_text")
    assert block["data"]["side"] == "left"  # мусорный side → дефолт
    assert block["data"]["url"] == "/i.jpg"


def test_cblocks_capped():
    raw = [{"key": "spacer"} for _ in range(50)]
    cfg = siteconfig.normalize({"sections": raw})
    blocks = [s for s in cfg["sections"] if s["key"] == "spacer"]
    assert len(blocks) == siteconfig._MAX_CBLOCKS


def test_unknown_section_key_still_dropped():
    cfg = siteconfig.normalize({"sections": [{"key": "totally-unknown"}]})
    keys = {s["key"] for s in cfg["sections"]}
    assert "totally-unknown" not in keys


# --- рендер ------------------------------------------------------------------------


def _render(block):
    ctx = Context({"request": RequestFactory().get("/")})
    return siteui.render_block(ctx, block)


def test_render_text_block():
    html = _render({"key": "text", "id": "x", "data": {"title": "Hallo", "body": "Welt"}})
    assert "Hallo" in html and "Welt" in html


def test_render_button_block():
    html = _render({"key": "button", "id": "x", "data": {"label": "Buchen", "url": "/t/"}})
    assert "Buchen" in html and 'href="/t/"' in html


def test_render_image_text_side_order():
    html = _render(
        {"key": "image_text", "id": "x", "data": {"url": "/i.jpg", "title": "A", "side": "right"}}
    )
    assert "md:order-2" in html and "/i.jpg" in html


def test_render_empty_text_block_is_blank():
    assert _render({"key": "text", "id": "x", "data": {}}).strip() == ""


# --- UC6-2: стиль текста блока (align/size/color, палитра темы) --------------------


def test_text_style_keeps_only_valid_non_default_values():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {
                    "key": "text",
                    "id": "s1",
                    "data": {
                        "title": "T",
                        "align": "center",
                        "size": "xl",
                        "color": "accent",
                    },
                },
                {
                    "key": "text",
                    "id": "s2",
                    # дефолты/мусор → ключей стиля НЕТ (старые конфиги байт-в-байт)
                    "data": {"title": "U", "align": "left", "size": "#f00", "color": "red"},
                },
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["data"]["align"] == "center"
    assert b1["data"]["size"] == "xl"
    assert b1["data"]["color"] == "accent"
    assert "align" not in b2["data"] and "size" not in b2["data"] and "color" not in b2["data"]


def test_image_text_style_flows_through():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "image_text", "data": {"title": "T", "align": "right", "color": "muted"}}
            ]
        }
    )
    block = next(s for s in cfg["sections"] if s["key"] == "image_text")
    assert block["data"]["align"] == "right" and block["data"]["color"] == "muted"


def test_render_text_block_applies_style_classes():
    html = _render(
        {
            "key": "text",
            "enabled": True,
            "data": {"title": "T", "body": "B", "align": "center", "size": "xl", "color": "accent"},
        }
    )
    assert "text-center" in html
    assert "md:text-4xl" in html
    assert "var(--accent)" in html


# --- UC6-3: ширина блока (w23/w12) + положение --------------------------------------


def test_cblock_width_w23_w12_and_pos():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "text", "id": "w1", "data": {"title": "T"}, "width": "w23", "pos": "right"},
                {"key": "text", "id": "w2", "data": {"title": "U"}, "width": "w12"},
                {"key": "text", "id": "w3", "data": {"title": "V"}, "width": "bogus", "pos": "up"},
            ]
        }
    )
    b1, b2, b3 = (s for s in cfg["sections"] if s["key"] == "text")
    assert b1["width"] == "w23" and b1["pos"] == "right"
    assert b2["width"] == "w12" and "pos" not in b2  # центр = без ключа
    assert b3["width"] == "contained" and "pos" not in b3  # мусор → дефолты


def test_section_width_not_extended_to_w23():
    """Секции остаются на contained/full — w23 только у C-блоков."""
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True, "width": "w23"}]})
    sec = next(s for s in cfg["sections"] if s["key"] == "products")
    assert sec["width"] == "contained"


# --- UC6-4: скругление фото + 📷 на канве -------------------------------------------


def test_image_rounded_validated_and_rendered():
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "image", "id": "r1", "data": {"url": "/i.jpg", "rounded": "3xl"}},
                {"key": "image", "id": "r2", "data": {"url": "/i.jpg", "rounded": "bogus"}},
            ]
        }
    )
    b1, b2 = (s for s in cfg["sections"] if s["key"] == "image")
    assert b1["data"]["rounded"] == "3xl"
    assert "rounded" not in b2["data"]  # мусор → дефолт (без ключа)
    html = _render({"key": "image", "id": "r1", "data": {"url": "/i.jpg", "rounded": "3xl"}})
    assert "rounded-3xl" in html and "rounded-2xl" not in html


def test_image_block_photo_button_only_in_preview():
    ctx = Context({"request": RequestFactory().get("/"), "is_preview": True})
    html = siteui.render_block(ctx, {"key": "image", "id": "px", "data": {"url": "/i.jpg"}})
    assert 'data-edit-model="cblock"' in html and 'data-edit-pk="px"' in html
    # публичная витрина (не превью) — кнопки нет
    html_pub = _render({"key": "image", "id": "px", "data": {"url": "/i.jpg"}})
    assert "data-photo-edit" not in html_pub
