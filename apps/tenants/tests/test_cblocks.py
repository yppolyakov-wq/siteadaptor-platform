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
