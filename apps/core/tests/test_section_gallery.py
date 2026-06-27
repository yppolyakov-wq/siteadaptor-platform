"""S3b: галерея фото на раздел — загрузка/удаление + рендер в обложке."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _png(name="x.png"):
    buf = BytesIO()
    Image.new("RGB", (12, 12), "green").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _post(data, tenant):
    req = RequestFactory().post("/dashboard/site/sections/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _gallery(tenant, key="catalog"):
    return siteconfig.normalize(tenant.site_config)["archetypes"].get(key, {}).get("gallery", [])


def test_cover_gallery_upload_then_delete():
    tenant = TenantFactory(schema_name="public", slug="cg", name="CG")
    views.sections_view(
        _post({"action": "upload_cover_gallery", "archetype": "catalog", "images": _png()}, tenant)
    )
    gal = _gallery(tenant)
    assert len(gal) == 1 and gal[0]["url"]
    image_id = gal[0]["id"]

    views.sections_view(
        _post(
            {"action": "delete_cover_image", "archetype": "catalog", "image_id": image_id}, tenant
        )
    )
    assert _gallery(tenant) == []


def _hero(tenant, key="catalog"):
    return siteconfig.normalize(tenant.site_config)["archetypes"].get(key, {}).get("hero_image", "")


def test_cover_hero_upload_sets_banner():
    """Загрузка баннера раздела файлом → archetypes[key].hero_image = URL (не только ссылка)."""
    tenant = TenantFactory(schema_name="public", slug="ch", name="CH")
    views.sections_view(
        _post({"action": "upload_cover_hero", "archetype": "catalog", "image": _png()}, tenant)
    )
    url = _hero(tenant)
    assert url and url.startswith(("/", "http"))


def test_cover_hero_upload_rejects_unknown_archetype():
    tenant = TenantFactory(schema_name="public", slug="ch2", name="CH2")
    views.sections_view(
        _post({"action": "upload_cover_hero", "archetype": "bogus", "image": _png()}, tenant)
    )
    assert _hero(tenant, "bogus") == ""


def test_upload_rejects_unknown_archetype():
    tenant = TenantFactory(schema_name="public", slug="cg2", name="CG2")
    views.sections_view(
        _post({"action": "upload_cover_gallery", "archetype": "bogus", "images": _png()}, tenant)
    )
    assert _gallery(tenant, "bogus") == []  # неизвестный ключ — ничего не сохранили


def test_normalize_sanitizes_cover_gallery():
    cfg = siteconfig.normalize(
        {
            "archetypes": {
                "catalog": {"gallery": [{"url": "/m/a.png", "id": "1"}, {"id": "no"}, "x"]}
            }
        }
    )
    assert cfg["archetypes"]["catalog"]["gallery"] == [{"url": "/m/a.png", "id": "1"}]
