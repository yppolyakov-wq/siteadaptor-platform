"""FB-21: формат фото по местам витрины (`site_defaults.media_places`)."""

import pathlib

import pytest
from django.conf import settings

from apps.core import media_places
from apps.tenants import siteconfig

TEMPLATES = pathlib.Path(settings.BASE_DIR) / "templates" / "storefront"


def test_presence_minimal_and_junk_dropped():
    assert "media_places" not in siteconfig.normalize({})["site_defaults"]
    junk = {"product": {"ratio": "9-9", "fit": "stretch"}, "evil": {"ratio": "1-1"}, "promo": "x"}
    sd = siteconfig.normalize({"site_defaults": {"media_places": junk}})["site_defaults"]
    assert "media_places" not in sd
    ok = {"product": {"ratio": "4-3", "fit": "contain"}, "tour": {"ratio": "round"}}
    sd = siteconfig.normalize({"site_defaults": {"media_places": ok}})["site_defaults"]
    assert sd["media_places"] == ok


def test_css_only_from_registry():
    assert media_places.css({}) == ""
    out = media_places.css({"product": {"ratio": "16-9", "fit": "contain"}})
    assert 'data-sf-place="product"' in out
    assert "aspect-ratio:16 / 9" in out and "object-fit:contain" in out
    # мусор в конфиге не превращается в CSS
    assert media_places.css({"product": {"ratio": "1/1;}body{display:none"}}) == ""
    # боковое фото горизонтальных форм не трогаем
    assert ':not([data-sf-media-box="side"])' in out


def test_from_post_reads_form():
    post = {"mp_promo_ratio": "3-4", "mp_promo_fit": "contain", "mp_product_ratio": ""}
    assert media_places.from_post(post) == {"promo": {"ratio": "3-4", "fit": "contain"}}


@pytest.mark.parametrize(
    "path,place",
    [
        ("cards/_photo.html", "product"),
        ("cards/_promo_photo.html", "promo"),
        ("_product_card.html", "product"),
        ("_promo_card.html", "promo"),
        ("_sellable_card.html", "sellable"),
        ("_category_tile.html", "category"),
        ("_combo_card.html", "combo"),
        ("_tour_card.html", "tour"),
    ],
)
def test_every_media_box_is_marked_with_its_place(path, place):
    text = (TEMPLATES / path).read_text()
    boxes = text.count("data-sf-media-box")
    assert boxes and text.count(f'data-sf-place="{place}"') == boxes


def test_every_marked_box_in_storefront_names_a_known_place():
    for f in TEMPLATES.rglob("*.html"):
        if f.name == "_base.html":
            continue
        text = f.read_text()
        assert text.count("data-sf-media-box") == text.count("data-sf-place="), f
        for code in media_places.PLACES:
            text = text.replace(f'data-sf-place="{code}"', "")
        assert "data-sf-place=" not in text, f


@pytest.mark.django_db
def test_design_page_shows_and_saves_places():
    from apps.core.tests.test_stu12_design_screen import _html, _post
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(slug="fb21", name="Fb21")
    body = _html(tenant)
    for code in media_places.PLACES:
        assert f'name="mp_{code}_ratio"' in body and f'name="mp_{code}_fit"' in body
    cfg = _post(
        tenant,
        {
            "action": "design_settings",
            "sd_cards_present": "1",
            "mp_category_ratio": "round",
            "mp_combo_fit": "contain",
        },
    )
    places = cfg["site_defaults"]["media_places"]
    assert places == {"category": {"ratio": "round"}, "combo": {"fit": "contain"}}
    # без блока карточек в POST настройка не стирается
    cfg = _post(tenant, {"action": "design_settings", "font": "serif"})
    assert cfg["site_defaults"]["media_places"] == places
