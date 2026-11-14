"""FB-22: слайды баннера — ссылка из списка целей, оформление, даты показа; опасные
ссылки не проходят; старые слайды без новых ключей — прежний вид."""

from datetime import timedelta

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.utils import timezone

from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _norm(*slides):
    return siteconfig.normalize({"heroes": list(slides)})["heroes"]


def test_old_slides_keep_their_shape_and_unsafe_urls_are_cut():
    old = _norm({"title": "Hallo", "button_url": "/sortiment/"})[0]
    assert set(old) == {"image", "title", "text", "button_label", "button_url"}
    bad = _norm({"title": "X", "button_url": "javascript:alert(1)"})[0]
    assert bad["button_url"] == ""


def test_style_link_and_dates_are_validated():
    h = _norm(
        {
            "title": "Sale",
            "link": "page:contact",
            "align": "left",
            "overlay": "light",
            "tone": "dark",
            "starts": "2026-11-01",
            "ends": "kaputt",
            "click_all": True,
        },
        {"title": "Y", "link": "evil:x", "align": "diagonal"},
    )
    assert h[0]["link"] == "page:contact" and h[0]["align"] == "left"
    assert h[0]["overlay"] == "light" and h[0]["tone"] == "dark" and h[0]["click_all"] is True
    assert h[0]["starts"] == "2026-11-01" and "ends" not in h[0]
    assert "link" not in h[1] and "align" not in h[1]


def _slides(heroes, tenant):
    req = RequestFactory().get("/")
    req.tenant = tenant
    tpl = Template(
        "{% load siteui %}{% hero_slides heroes as s %}{% for h in s %}{{ h.title }}={{ h.href }};{% endfor %}"
    )
    return tpl.render(Context({"heroes": heroes, "request": req}))


def test_only_active_slides_and_link_resolves_like_the_menu():
    today = timezone.localdate()
    heroes = _norm(
        {"title": "Jetzt", "link": "page:home"},
        {"title": "Spaeter", "starts": (today + timedelta(days=3)).isoformat()},
        {"title": "Vorbei", "ends": (today - timedelta(days=1)).isoformat()},
        {"title": "Eigen", "button_url": "https://example.org"},
    )
    out = _slides(heroes, TenantFactory.build())
    assert out == "Jetzt=/;Eigen=https://example.org;"


def test_slider_markup_uses_style_and_whole_image_link():
    tpl = open("templates/storefront/sections/_hero.html", encoding="utf-8").read()
    # FB-29.2 (осознанная переписка): тег получает и выбор баннеров из библиотеки
    assert "{% hero_slides site.heroes site.hero_banners as slides %}" in tpl
    assert "{% elif slides %}" in tpl
    assert "h.click_all and h.href" in tpl and "h.overlay == 'light'" in tpl
