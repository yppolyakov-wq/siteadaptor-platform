"""FB-29 R2: «Wo zeigen» — ещё номера и события (туры); у страницы акции свои блоки, поэтому
блок-место можно поставить и там. Правки ревью R1: предел до проверки, черновики акций."""

import pathlib

import pytest

from apps.core import banners, site_schema
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def test_stays_and_events_are_places_too():
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name="Doppelzimmer")
    key = banners.place_key("stay", unit)
    assert key == f"stay:{unit.pk}" and banners.place_exists(key)
    assert "event" in banners.SHOW_ON_TYPES
    assert banners.page_place_key({"unit": unit}) == key


def test_detail_pages_of_rooms_events_and_promotions_carry_the_banners():
    for name, call in (
        ("stay_detail.html", '{% place_banners "stay" unit %}'),
        ("event_detail.html", '{% place_banners "event" event %}'),
        ("promotion_detail.html", '{% page_blocks "promo_detail" %}'),
    ):
        assert call in pathlib.Path("templates/storefront", name).read_text(), name


def test_promotion_page_has_its_own_blocks_and_can_host_a_place_block():
    assert siteconfig.is_page_block_host("promo_detail")
    for host in ("promo_detail", "stay_detail", "event_detail", "product_detail"):
        assert site_schema.place_capable(host), host
    assert not site_schema.place_capable("info")
    place = {"key": "banner", "id": "b1", "enabled": True, "data": {"from_page": True}}
    cfg = siteconfig.normalize({"page_blocks": {"promo_detail": [place]}})
    assert banners.place_block_present(cfg, ["promo_detail"])


def test_draft_promotions_are_not_offered():
    from apps.promotions.models import Promotion
    from apps.promotions.tests.factories import PromotionFactory

    live = PromotionFactory(status="active")
    draft = PromotionFactory(status="draft")
    assert banners.place_exists(f"promotion:{live.pk}")
    assert not banners.place_exists(f"promotion:{draft.pk}")
    assert Promotion.objects.count() == 2


def test_posted_places_are_capped_before_the_lookup(monkeypatch):
    seen = {}

    def spy(values):
        seen["n"] = len(list(values))
        return {}

    monkeypatch.setattr(banners, "place_labels", spy)
    b = banners.create({"title": "x", "image": {"url": "/media/hero/a.jpg"}})
    banners.set_show_on(b, keep=[], add=[f"product:{i}" for i in range(900)])
    assert seen["n"] <= banners.SHOW_ON_MAX


def test_label_never_breaks_on_odd_objects():
    class Odd:
        def name_localized(self, needed):  # вызывается без аргумента — TypeError
            return needed

        name = {"de": "Ding"}

    assert banners._place_label(Odd()) == "Ding"


def test_promotion_row_has_a_preview_of_a_real_promotion(settings):
    """Ревью R2: без образца владелец не видел бы блоки страницы акции в превью."""
    from apps.core import studio_pages
    from apps.promotions.tests.factories import PromotionFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    promo = PromotionFactory(status="active")
    pt = next(p for p in studio_pages.PAGE_TYPES if p.code == "promo")
    assert str(promo.pk) in site_schema._preview_url(pt)
