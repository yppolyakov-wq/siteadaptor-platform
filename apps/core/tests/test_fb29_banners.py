"""FB-29.2 S1: библиотека баннеров — модель и логика (витрина ещё читает прежние слайды)."""

import datetime

import pytest
from django.utils import timezone

from apps.core import banners, media_registry
from apps.core.models import Banner
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _banner(**kwargs):
    fields = {"title": "Herbsttee", "image": {"url": "/media/banner/a.jpg", "path": "banner/a.jpg"}}
    fields.update(kwargs)
    return banners.create(fields)


def test_fields_go_through_the_same_cleaning_as_hero_slides():
    b = _banner(
        text="x" * 900,
        button_label="Zum Tee",
        button_url="javascript:alert(1)",
        link="product:abc",
        align="left",
        overlay="<script>",
        tone="dark",
        click_all=True,
    )
    b.refresh_from_db()
    assert len(b.text) == 400
    assert b.button_url == "", "небезопасная схема отбрасывается"
    assert b.link == "product:abc" and b.align == "left" and b.tone == "dark"
    assert b.overlay == "", "мусор в оформлении не хранится"
    assert b.click_all is True


def test_unknown_link_type_is_dropped():
    assert _banner(link="evil:1").link == ""


def test_empty_banner_is_refused():
    with pytest.raises(ValueError):
        banners.create({"title": "", "text": "", "image": {}})


def test_slide_has_the_shape_the_storefront_already_renders():
    b = _banner(text="Neu", link="category:tee", starts=datetime.date(2026, 1, 1))
    slide = banners.to_slide(b)
    cleaned = siteconfig.normalize_heroes([slide])
    assert len(cleaned) == 1
    for key, value in cleaned[0].items():
        assert slide[key] == value, key
    assert slide["image"] == "/media/banner/a.jpg" and slide["starts"] == "2026-01-01"


def test_resolve_keeps_the_owners_order_and_skips_inactive():
    today = timezone.localdate()
    a = _banner(title="A")
    b = _banner(title="B")
    past = _banner(title="Vorbei", ends=today - datetime.timedelta(days=1))
    future = _banner(title="Später", starts=today + datetime.timedelta(days=1))
    off = _banner(title="Aus", is_active=False)
    pick = [str(x.pk) for x in (b, past, a, future, off)]
    assert [s["title"] for s in banners.resolve(pick)] == ["B", "A"]


def test_resolve_survives_a_deleted_banner_and_rubbish():
    a = _banner(title="A")
    gone = _banner(title="Weg")
    pick = [str(gone.pk), "not-a-uuid", str(a.pk), str(a.pk)]
    gone.delete()
    assert [s["title"] for s in banners.resolve(pick)] == ["A"]


def test_resolve_falls_back_to_legacy_slides_when_nothing_is_picked():
    legacy = [{"image": "/x.jpg", "title": "Alt"}]
    assert banners.resolve([], legacy=legacy) == legacy
    assert banners.resolve(None, legacy=legacy) == legacy


def test_translation_overlays_the_base_text():
    b = _banner(title="Herbsttee")
    b.title_i18n = {"ru": "Осенний чай"}
    b.save()
    assert banners.to_slide(b, locale="ru")["title"] == "Осенний чай"
    assert banners.to_slide(b, locale="tr")["title"] == "Herbsttee"


def test_media_library_sees_banner_photos():
    _banner()
    assert "banner/a.jpg" in media_registry.used_paths()


def test_legacy_key_is_unique_only_when_set():
    _banner(title="A")
    _banner(title="B")  # два пустых ключа — можно
    banners.create({"title": "C"}, legacy_key="heroes:0")
    assert Banner.objects.filter(legacy_key="").count() == 2
    with pytest.raises(Exception):  # noqa: B017, PT011 — нарушение уникальности
        banners.create({"title": "D"}, legacy_key="heroes:0")


# ───────── ревью database-reviewer ─────────


def test_form_cannot_set_order_or_migration_key():
    b = banners.create({"title": "A", "sort_order": 99, "legacy_key": "heroes:7"})
    assert b.sort_order == 0 and b.legacy_key == ""
    with pytest.raises(ValueError):
        banners.create({"title": "B"}, legacy_key="x" * 81)


def test_broken_date_is_an_error_not_always_on():
    with pytest.raises(ValueError):
        banners.create({"title": "A", "starts": "2026-13-45"})
    assert banners.create({"title": "B", "starts": ""}).starts is None


def test_partial_update_does_not_switch_a_banner_back_on():
    b = _banner(is_active=False)
    banners.update(b, {"title": "Neu", "image": b.image})
    b.refresh_from_db()
    assert b.is_active is False and b.title == "Neu"


def test_changed_base_text_drops_its_stale_translation():
    b = _banner(title="Herbsttee", text="Frisch")
    b.title_i18n, b.text_i18n = {"ru": "Осенний чай"}, {"ru": "Свежий"}
    b.save()
    banners.update(b, {"title": "Wintertee", "text": "Frisch", "image": b.image})
    b.refresh_from_db()
    assert b.title_i18n == {} and b.text_i18n == {"ru": "Свежий"}


def test_pick_is_capped():
    import uuid

    pick = [str(uuid.uuid4()) for _ in range(banners.MAX_SLIDES + 5)]
    assert len(banners.clean_pick(pick)) == banners.MAX_SLIDES
