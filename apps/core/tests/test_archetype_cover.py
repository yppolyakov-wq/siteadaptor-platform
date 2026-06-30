"""H2-6: обложка архетипа над лендингом — описание (intro) + hero + СЛАЙДЕР из gallery.
Слайдер = CSS snap-scroll (без JS-состояния), рендерится поверх любого лендинга (_base.html)."""

from django.template.loader import render_to_string


def test_cover_renders_gallery_as_swipe_slider():
    out = render_to_string(
        "storefront/_archetype_cover.html",
        {
            "archetype_cover": {
                "intro": "Unsere Retreats",
                "hero_image": "/hero.svg",
                "gallery": [{"url": "/a.svg"}, {"url": "/b.svg"}, {"url": "/c.svg"}],
            }
        },
    )
    assert "data-cover-slider" in out  # слайдер-контейнер
    assert "snap-x snap-mandatory" in out  # CSS snap-scroll
    assert "Unsere Retreats" in out  # описание
    assert "/a.svg" in out and "/c.svg" in out  # картинки слайдера


def test_cover_without_gallery_has_no_slider():
    out = render_to_string(
        "storefront/_archetype_cover.html",
        {"archetype_cover": {"intro": "Nur Text", "hero_image": "", "gallery": []}},
    )
    assert "data-cover-slider" not in out
    assert "Nur Text" in out


def test_cover_empty_renders_nothing_meaningful():
    out = render_to_string("storefront/_archetype_cover.html", {"archetype_cover": {}})
    assert "data-cover-slider" not in out
    assert "<img" not in out
