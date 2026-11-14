"""FB-29, последние пункты остатка: тур как место баннера, файл удалённого баннера,
перетаскивание пальцем."""

import pathlib

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import RequestFactory

from apps.core import banners
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_tour_is_a_banner_place():
    from apps.events.models import Tour

    tour = Tour.objects.create(title="Rheinsteig", slug="rheinsteig", is_published=True)
    key = banners.place_key("tour", tour)
    assert key == f"tour:{tour.pk}" and banners.place_exists(key)
    assert banners.page_place_key({"tour": tour}) == key
    src = pathlib.Path("templates/storefront/tour_detail.html").read_text()
    assert '{% place_banners "tour" tour %}' in src


def test_deleting_a_banner_removes_its_own_file(django_capture_on_commit_callbacks):
    name = default_storage.save("hero/fb29-delete-me.jpg", ContentFile(b"x"))
    tenant = TenantFactory()
    b = banners.create({"title": "Weg", "image": {"url": f"/media/{name}", "path": name}})
    with django_capture_on_commit_callbacks(execute=True):
        banners.delete(tenant, b)
    assert not default_storage.exists(name)


def test_a_shared_file_and_foreign_paths_stay(django_capture_on_commit_callbacks):
    name = default_storage.save("hero/fb29-shared.jpg", ContentFile(b"x"))
    tenant = TenantFactory()
    a = banners.create({"title": "A", "image": {"url": f"/media/{name}", "path": name}})
    banners.create({"title": "B", "image": {"url": f"/media/{name}", "path": name}})
    with django_capture_on_commit_callbacks(execute=True):
        banners.delete(tenant, a)
    assert default_storage.exists(name), "файлом пользуется другой баннер"
    default_storage.delete(name)
    other = default_storage.save("pages/fb29-foreign.jpg", ContentFile(b"x"))
    banners._drop_file(other)
    assert default_storage.exists(other), "чужая папка не трогается"
    default_storage.delete(other)


def test_rows_can_be_dragged_by_finger():
    js = pathlib.Path("static/js/aufbau.js").read_text()
    assert "pointerdown" in js and "elementFromPoint" in js and "touchAction" in js
    assert 'e.pointerType === "mouse"' in js, "мышь идёт прежним путём drag/drop"


def test_list_in_a_narrow_section_gets_only_the_columns_that_fit():
    from apps.tenants import siteconfig

    def layout(width):
        row = {"key": "products", "enabled": True, "layout": {"preset": "cols4"}}
        if width:
            row["width"] = width
        cfg = siteconfig.normalize({"sections": [row]})
        return siteconfig.section_layout(cfg, "products")

    full = layout("")
    assert full["cols"] == 4, "обычная секция — как задано"
    assert layout("w12")["cols"] == 2 and layout("w13")["cols"] == 1 and layout("w23")["cols"] == 3
    two = siteconfig.normalize(
        {
            "sections": [
                {"key": "products", "enabled": True, "width": "w12", "layout": {"preset": "cols2"}}
            ]
        }
    )
    assert siteconfig.section_layout(two, "products")["cols"] == 2


def test_file_still_used_by_the_site_settings_stays(django_capture_on_commit_callbacks):
    """Перенесённый баннер делит файл с прежней копией слайда (она оставлена для отката)."""
    name = default_storage.save("hero/fb29-legacy.jpg", ContentFile(b"x"))
    tenant = TenantFactory(site_config={"heroes": [{"image": f"/media/{name}", "title": "Alt"}]})
    b = banners.create({"title": "Alt", "image": {"url": f"/media/{name}", "path": name}})
    with django_capture_on_commit_callbacks(execute=True):
        banners.delete(tenant, b)
    assert default_storage.exists(name)
    default_storage.delete(name)


def test_narrow_section_fetches_full_rows_of_the_capped_columns():
    from apps.tenants import siteconfig

    row = {
        "key": "products",
        "enabled": True,
        "width": "w12",
        "layout": {"preset": "cols4", "rows": 2},
    }
    cfg = siteconfig.normalize({"sections": [row]})
    assert siteconfig.section_limit(cfg, "products") == 4, "2 колонки × 2 ряда, а не 4 × 2"


def test_file_used_by_a_text_page_stays(django_capture_on_commit_callbacks, monkeypatch):
    from apps.core import media_registry

    name = default_storage.save("hero/fb29-page.jpg", ContentFile(b"x"))
    monkeypatch.setattr(media_registry, "used_paths", lambda tenant=None: {name})
    banners._drop_file(name, TenantFactory.build())
    assert default_storage.exists(name)
    default_storage.delete(name)


def test_storage_failure_does_not_break_the_delete(monkeypatch):
    from apps.core import media_registry

    def boom(tenant=None):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(media_registry, "used_paths", boom)
    banners._drop_file("hero/x.jpg", None)  # не бросает


# --- R7 ---


def test_place_block_on_the_tour_page_silences_the_default_place():
    from django.template import Context, Template
    from django.test import RequestFactory

    from apps.events.models import Tour

    tour = Tour.objects.create(title="Rheinsteig", slug="rheinsteig-r7", is_published=True)
    b = banners.create({"title": "Tourbanner", "image": {"url": "/media/hero/a.jpg"}})
    banners.set_show_on(b, keep=[], add=[f"tour:{tour.pk}"])
    place = {"key": "banner", "id": "b1", "enabled": True, "data": {"from_page": True}}
    tpl = Template('{% load siteui %}{% place_banners "tour" tour %}')

    def render(blocks):
        request = RequestFactory().get("/")
        request.tenant = TenantFactory.build(site_config={"page_blocks": {"event_detail": blocks}})
        return tpl.render(Context({"request": request, "tour": tour}))

    assert "Tourbanner" in render([])
    assert render([place]).strip() == ""


def test_own_list_block_in_a_narrow_width_gets_the_columns_that_fit():
    from apps.tenants.templatetags import siteui

    assert siteui._narrow_list_data({"cols": 4}, "w12", 4) == {"cols": 2}
    assert siteui._narrow_list_data({}, "w13", 4) == {"cols": 1}
    assert siteui._narrow_list_data({"cols": 2}, "w12", 2) == {"cols": 2}, "помещается — не трогаем"
    assert siteui._narrow_list_data({"cols": 4}, "full", 4) == {"cols": 4}
    assert siteui._narrow_list_data({"cols": 4}, "", 4) == {"cols": 4}


def test_narrow_width_reaches_the_list_block_through_the_row(monkeypatch):
    """Проводка: ширина берётся из строки блока `b` в контексте, лента не трогается."""
    from apps.core import list_blocks
    from apps.tenants.templatetags import siteui

    seen = {}
    monkeypatch.setattr(list_blocks, "source_active", lambda tenant, data: True)
    monkeypatch.setattr(
        list_blocks, "resolve_for", lambda request, cfg, data: seen.setdefault("data", data)
    )

    def cols(width, scroll=False):
        seen.clear()
        monkeypatch.setattr(
            list_blocks,
            "effective_view",
            lambda cfg, data: {"layout": {"cols": 4, "scroll": scroll}},
        )
        request = RequestFactory().get("/")
        request.tenant = TenantFactory.build()
        ctx = {"request": request, "site": {"sections": []}, "b": {"width": width}}
        siteui.list_block(ctx, {"cols": 4})
        return seen["data"]["cols"]

    assert cols("w12") == 2
    assert cols("w13") == 1
    assert cols("full") == 4
    assert cols("w12", scroll=True) == 4, "лента листается — колонки не режем"


# --- T5 ---


def test_grid_blocks_in_a_narrow_width_stack_their_columns():
    """Блоки-сетки (цифры, фото+текст) в узкой ширине не делят её ещё раз на колонки."""
    from django.template import Context, Template

    stats = {"rows": [{"value": "7", "label": "Jahre"}, {"value": "3", "label": "Läden"}] * 2}
    tpl = Template('{% load siteui %}{% page_blocks "info" %}')

    def render(width):
        blocks = [
            {"key": "stats", "id": "s1", "enabled": True, "width": width, "data": stats},
            {
                "key": "image_text",
                "id": "i1",
                "enabled": True,
                "width": width,
                "data": {"title": "Über uns T5", "text": "Text"},
            },
        ]
        request = RequestFactory().get("/")
        request.tenant = TenantFactory.build(site_config={"page_blocks": {"info": blocks}})
        return tpl.render(Context({"request": request}))

    wide = render("contained")
    assert "sm:grid-cols-4" in wide and "md:grid-cols-2" in wide
    third = render("w13")
    assert "Über uns T5" in third
    # на телефоне блок во всю ширину — прежние колонки; узкая колонка — с планшета
    assert "sm:grid-cols-4 md:grid-cols-1" in third
    assert third.count("md:grid-cols-2") == 0
    half = render("w12")
    assert "sm:grid-cols-4 md:grid-cols-2" in half and half.count("md:grid-cols-2") == 1
    assert "md:grid-cols-1" not in wide and wide.count("md:grid-cols-2") == 1


def test_reset_hint_mentions_the_position_of_own_blocks():
    src = pathlib.Path("templates/tenant/_object_structure.html").read_text()
    assert "ps.blocks_first" in src.split('id="ps-reset-help"', 1)[1].split("</span>", 1)[0]
