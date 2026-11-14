"""FB-29, последние пункты остатка: тур как место баннера, файл удалённого баннера,
перетаскивание пальцем."""

import pathlib

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

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
