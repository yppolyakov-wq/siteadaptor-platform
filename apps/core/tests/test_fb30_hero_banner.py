"""FB-30.1: баннер, выбранный для главной, ведёт заголовок, текст, кнопку и фото
приветственного баннера В ЛЮБОМ его виде (раньше — только в слайдере, остальные виды
показывали старые поля главной: название магазина и кнопку главного раздела)."""

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import banners
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

STYLES = ["plain", "accent", "split", "fullscreen", "bento"]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _banner(**kw):
    raw = {
        "title": "Die wunderbare Welt des Tees",
        "text": "Über 200 Sorten",
        "button_label": "Lass mich verzaubern",
        "button_url": "/sortiment/",
        "image": {"url": "/media/hero/tee.jpg"},
    }
    return banners.create({**raw, **kw})


def _hero(style, pick=(), **site):
    tenant = _tenant()
    raw = {**site, "hero_banners": {"pick": [str(p) for p in pick]}}
    if style != "plain":
        raw["hero_style"] = style
    cfg = siteconfig.normalize(raw)
    request = RequestFactory().get("/")
    request.tenant = tenant
    primary = {"landing": "storefront-products", "label": "Sortiment", "module": "catalog"}
    ctx = {"site": cfg, "request": request, "primary_item": primary}
    return render_to_string("storefront/sections/_hero.html", ctx)


@pytest.mark.parametrize("style", STYLES)
def test_single_picked_banner_drives_text_button_and_photo(style):
    b = _banner()
    html = _hero(style, [b.pk], hero_title="Alter Titel", hero_text="Alter Text")
    assert "Die wunderbare Welt des Tees" in html and "Über 200 Sorten" in html
    assert "Lass mich verzaubern" in html and 'href="/sortiment/"' in html
    assert "Alter Titel" not in html and "Alter Text" not in html
    assert ">Sortiment<" not in html, "кнопка главного раздела не подменяет кнопку баннера"
    if style != "bento":
        assert "/media/hero/tee.jpg" in html


@pytest.mark.parametrize("style,marker", [("split", "data-hero-split"), ("bento", "data-hero-bento"),
                                          ("fullscreen", "data-hero-fullscreen")])  # fmt: skip
def test_single_picked_banner_keeps_the_chosen_style(style, marker):
    html = _hero(style, [_banner().pk])
    assert marker in html and "data-hero-slider" not in html


def test_two_picked_banners_stay_a_slider():
    a, b = _banner(), _banner(title="Winter")
    html = _hero("split", [a.pk, b.pk])
    assert "data-hero-slider" in html and html.count("data-hero-slide") >= 2


@pytest.mark.parametrize("style", STYLES)
def test_button_without_a_link_keeps_its_label_and_leads_to_the_main_section(style):
    b = _banner(button_url="")
    html = _hero(style, [b.pk])
    assert "Lass mich verzaubern" in html and ">Sortiment<" not in html
    assert 'href="/sortiment/"' in html


def test_banner_text_is_not_marked_as_the_old_inline_field():
    """Правка на странице ушла бы в старое поле, которого на сайте не видно."""
    html = _hero("split", [_banner().pk])
    assert 'data-edit="hero_title"' not in html and 'data-edit="hero_text"' not in html


def test_picked_but_inactive_banner_does_not_borrow_the_old_slide_photo():
    b = _banner(is_active=False)
    old = [{"title": "Alt", "image": "/media/hero/alt.jpg"}]
    html = _hero("split", [b.pk], hero_title="Mein Laden", heroes=old)
    assert "Mein Laden" in html and "/media/hero/alt.jpg" not in html
    assert "Die wunderbare Welt" not in html


def test_without_a_pick_nothing_changes():
    html = _hero("split", [], hero_title="Mein Laden", hero_text="Wie immer")
    assert "Mein Laden" in html and "Wie immer" in html and ">Sortiment<" in html
    assert 'data-edit="hero_title"' in html


# --- ревью (django-reviewer) ---


@pytest.mark.parametrize("style", ["plain", "accent"])
def test_expired_old_slides_do_not_turn_the_plain_hero_into_a_photo_banner(style):
    """Без выбора всё как раньше: фото прежнего слайда вне срока не делает из простого
    баннера фото-баннер (его берут только «текст + фото» и «во весь экран»)."""
    old = [{"title": "Alt", "image": "/media/hero/alt.jpg", "ends": "2020-01-01"}]
    html = _hero(style, [], hero_title="Mein Laden", heroes=old)
    assert "/media/hero/alt.jpg" not in html and "Mein Laden" in html
    assert "/media/hero/alt.jpg" in _hero("split", [], hero_title="Mein Laden", heroes=old)


def test_banner_photo_is_not_offered_as_the_old_studio_media_slot():
    html = _hero("split", [_banner().pk])
    assert 'data-sf-media-slot="hero"' not in html
    assert 'data-sf-media-slot="hero"' in _hero("split", [], hero_image="/media/hero/x.jpg")


def test_bento_with_a_bare_banner_does_not_borrow_the_old_text():
    b = _banner(title="", text="")
    html = _hero("bento", [b.pk], hero_title="Alter Titel", hero_text="Alter Text")
    assert "Alter Titel" not in html and "Alter Text" not in html


def test_banner_link_without_a_label_does_not_relabel_the_main_button():
    """У баннера ссылка без подписи: кнопка главного раздела ведёт в главный раздел."""
    b = _banner(button_label="", button_url="/ueber-uns/")
    html = _hero("split", [b.pk])
    cta = html[html.index("data-hero-cta") - 400 : html.index("data-hero-cta")]
    assert 'href="/sortiment/"' in cta and "/ueber-uns/" not in cta


def test_hero_lead_states():
    from apps.tenants.templatetags.siteui import hero_lead

    slide = {"title": "T", "text": "X", "image": "/a.jpg", "button_label": "B", "href": "/z/"}
    picked = {"hero_banners": {"pick": ["1"]}, "hero_title": "Alt", "heroes": [{"image": "/o.jpg"}]}
    lead = hero_lead(picked, [slide])
    assert lead["from_banner"] and lead["title"] == "T" and lead["own_image"] == "/a.jpg"
    lead = hero_lead(picked, [])
    assert not lead["from_banner"] and lead["title"] == "Alt" and lead["image"] == ""
    lead = hero_lead({"heroes": [{"image": "/o.jpg"}]}, [])
    assert lead["image"] == "/o.jpg" and lead["own_image"] == ""
    assert hero_lead(None, None)["title"] == ""
