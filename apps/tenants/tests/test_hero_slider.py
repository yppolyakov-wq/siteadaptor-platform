"""M20U-2: слайдер главных баннеров (heroes[]) — нормализация + рендер секции hero."""

from django.template.loader import render_to_string

from apps.tenants import siteconfig

# --- normalize_heroes ---------------------------------------------------------


def test_normalize_heroes_parses_and_drops_empty():
    out = siteconfig.normalize_heroes(
        [
            {
                "image": "https://x/1.jpg",
                "title": "A",
                "text": "t",
                "button_label": "Go",
                "button_url": "/x",
            },
            {"title": "", "text": "", "image": ""},  # пустой → отброшен
            "garbage",  # не dict → пропуск
            {"title": "B"},  # только заголовок — валиден
        ]
    )
    assert len(out) == 2
    assert out[0] == {
        "image": "https://x/1.jpg",
        "title": "A",
        "text": "t",
        "button_label": "Go",
        "button_url": "/x",
    }
    assert out[1]["title"] == "B" and out[1]["image"] == ""


def test_normalize_heroes_caps():
    raw = [{"title": f"H{i}"} for i in range(10)]
    assert len(siteconfig.normalize_heroes(raw)) == siteconfig._MAX_HEROES


def test_normalize_includes_heroes_key():
    cfg = siteconfig.normalize({"heroes": [{"title": "Welcome"}]})
    assert cfg["heroes"] == [
        {"image": "", "title": "Welcome", "text": "", "button_label": "", "button_url": ""}
    ]


def test_normalize_heroes_backcompat_empty():
    cfg = siteconfig.normalize({})  # старый конфиг без heroes
    assert cfg["heroes"] == []


# --- рендер секции hero -------------------------------------------------------


def _req():
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(name="Pranasy")
    return request


def test_hero_section_renders_slider_for_multiple_banners():
    site = {
        "heroes": [
            {
                "image": "https://x/1.jpg",
                "title": "Eins",
                "text": "",
                "button_label": "",
                "button_url": "",
            },
            {
                "image": "https://x/2.jpg",
                "title": "Zwei",
                "text": "",
                "button_label": "Buch",
                "button_url": "/p",
            },
        ]
    }
    html = render_to_string("storefront/sections/_hero.html", {"site": site, "request": _req()})
    assert "data-hero-slider" in html
    assert "data-hero-dot" in html  # точки навигации (>1 слайда)
    # оба баннера присутствуют (две картинки слайдов)
    assert "https://x/1.jpg" in html and "https://x/2.jpg" in html and "Buch" in html


def test_hero_section_falls_back_to_single_when_no_heroes():
    # без heroes, но с hero_image → старый одиночный баннер (без слайдера)
    site = {"heroes": [], "hero_image": "https://x/bg.jpg", "hero_title": "Hallo", "hero_text": ""}
    html = render_to_string("storefront/sections/_hero.html", {"site": site, "request": _req()})
    assert "data-hero-slider" not in html
    assert "https://x/bg.jpg" in html and "Hallo" in html
