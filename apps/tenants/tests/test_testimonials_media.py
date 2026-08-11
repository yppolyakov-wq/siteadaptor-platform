"""GK-6: testimonials — рейтинг (stars 1..5) + фото + аватар-ряд в trust.

Общий _clean_pairs не расширялся (faq/process целы); extras presence-minimal —
golden (rich_home с парами name/text) байт-в-байт."""

from django.template.loader import render_to_string

from apps.tenants import siteconfig
from apps.tenants.templatetags.siteui import stars_filter


def test_clean_testimonials_extras_presence_minimal():
    out = siteconfig.clean_testimonials(
        [
            {"name": "Anna", "text": "Toll!"},
            {"name": "Ben", "text": "Super", "stars": "5", "photo": " https://x.de/a.jpg "},
            {"name": "Cid", "text": "Ok", "stars": "9"},  # вне 1..5 → без ключа
            {"name": "", "text": "ohne Name"},  # пропуск
        ]
    )
    assert out[0] == {"name": "Anna", "text": "Toll!"}  # пары байт-в-байт (golden)
    assert out[1] == {"name": "Ben", "text": "Super", "stars": 5, "photo": "https://x.de/a.jpg"}
    assert out[2] == {"name": "Cid", "text": "Ok"}
    assert len(out) == 3


def test_testimonials_text_round_trip():
    text = "Anna | Toll!\nBen | Super | 5\nCid | Mit Foto | 4 | https://x.de/c.jpg"
    items = siteconfig.text_to_testimonials(text)
    assert items == [
        {"name": "Anna", "text": "Toll!"},
        {"name": "Ben", "text": "Super", "stars": 5},
        {"name": "Cid", "text": "Mit Foto", "stars": 4, "photo": "https://x.de/c.jpg"},
    ]
    assert siteconfig.testimonials_to_text(items) == text


def test_stars_filter():
    assert stars_filter(4) == "★★★★☆"
    assert stars_filter("5") == "★★★★★"
    assert stars_filter(0) == "" and stars_filter("junk") == ""


def test_testimonials_render_stars_and_photo_all_styles():
    site = {
        "testimonials": [
            {"name": "Ben", "text": "Super", "stars": 5, "photo": "https://x.de/a.jpg"}
        ]
    }
    for style in ("", "quotes", "list", "accent", "single"):
        html = render_to_string(
            "storefront/sections/_testimonials.html",
            {"site": site, "section_row": {"key": "testimonials", "style": style}},
        )
        assert "★★★★★" in html, style
        assert 'src="https://x.de/a.jpg"' in html, style


def test_testimonials_without_extras_render_plain():
    html = render_to_string(
        "storefront/sections/_testimonials.html",
        {"site": {"testimonials": [{"name": "Anna", "text": "Toll!"}]}},
    )
    assert "★" not in html and "<img" not in html


def test_trust_avatar_row_photos_and_initials():
    html = render_to_string(
        "storefront/sections/_trust.html",
        {
            "site": {
                "trust": {"since": "2012", "marks": []},
                "testimonials": [
                    {"name": "Ben", "text": "x", "photo": "https://x.de/a.jpg"},
                    {"name": "anna", "text": "y"},
                ],
            },
            "section_row": {"key": "trust", "style": ""},
        },
    )
    assert "-space-x-2" in html
    assert 'src="https://x.de/a.jpg"' in html
    assert ">A</span>" in html  # инициал-фолбэк, upper


def test_trust_without_testimonials_has_no_avatar_row():
    html = render_to_string(
        "storefront/sections/_trust.html",
        {
            "site": {"trust": {"since": "2012", "marks": []}, "testimonials": []},
            "section_row": {"key": "trust", "style": ""},
        },
    )
    assert "-space-x-2" not in html
