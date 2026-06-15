"""M20 ⑤b: фото-галерея витрины — загрузка/удаление + санитайз normalize."""

from io import BytesIO

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


def _png(name="x.png"):
    buf = BytesIO()
    Image.new("RGB", (12, 12), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_normalize_sanitizes_gallery():
    cfg = siteconfig.normalize(
        {"gallery": [{"url": "/m/a.png", "id": "1"}, {"id": "no-url"}, "junk"]}
    )
    assert cfg["gallery"] == [{"url": "/m/a.png", "id": "1"}]


def test_upload_then_delete_gallery_image():
    request = RequestFactory().post("/dashboard/site/", {"action": "upload_gallery"})
    request.FILES["images"] = _png()
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory(schema_name="public", slug="x", name="X")

    views._upload_gallery_images(request)
    gallery = siteconfig.normalize(request.tenant.site_config)["gallery"]
    assert len(gallery) == 1
    assert gallery[0]["url"]
    image_id = gallery[0]["id"]

    views._delete_gallery_image(request, image_id)
    assert siteconfig.normalize(request.tenant.site_config)["gallery"] == []


def test_gallery_section_registered_default_off():
    cfg = siteconfig.normalize({})
    off = {s["key"]: s["enabled"] for s in cfg["sections"]}
    assert off["gallery"] is False
