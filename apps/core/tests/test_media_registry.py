"""CM-4: реестр MediaAsset поверх FileRef — хук загрузки, backfill,
alt write-back, удаление незанятых, кабинет «Medien»."""

import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image as PILImage

from apps.catalog.images import delete_stored_image, save_product_image
from apps.core import media_registry
from apps.core.models import MediaAsset

pytestmark = pytest.mark.django_db


def _png(name="p.png"):
    buf = BytesIO()
    PILImage.new("RGB", (40, 40), "#abc").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_save_image_registers_asset_and_delete_removes(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    ref = save_product_image(_png(), folder="products")
    asset = MediaAsset.objects.get(path=ref["path"])
    assert asset.folder == "products" and asset.mime_type == "image/png" and asset.size > 0
    delete_stored_image(ref)
    assert not MediaAsset.objects.filter(path=ref["path"]).exists()


def test_backfill_covers_gallery_single_shim_and_siteconfig(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.booking.models import Service
    from apps.catalog.models import Product
    from apps.events.models import BlogPost
    from apps.tenants.tests.factories import TenantFactory

    Product.objects.create(
        name={"de": "Brot"},
        base_price="3.00",
        images=[{"id": "a", "url": "/m/a.jpg", "path": "products/a.jpg"}],
    )
    BlogPost.objects.create(
        title="P", slug="p", cover={"id": "b", "url": "/m/b.jpg", "path": "blog/b.jpg"}
    )
    Service.objects.create(name="S", image={"id": "c", "url": "/m/c.jpg", "path": "services/c.jpg"})
    tenant = TenantFactory.build(
        site_config={"gallery": [{"id": "d", "url": "/m/d.jpg", "path": "gallery/d.jpg"}]}
    )
    created = media_registry.backfill(tenant)
    assert created == 4
    assert set(MediaAsset.objects.values_list("path", flat=True)) == {
        "products/a.jpg",
        "blog/b.jpg",
        "services/c.jpg",
        "gallery/d.jpg",
    }
    assert media_registry.backfill(tenant) == 0  # идемпотентно


def test_write_back_alt_updates_fileref_copies():
    from apps.catalog.models import Product

    p = Product.objects.create(
        name={"de": "Brot"},
        base_price="3.00",
        images=[{"id": "a", "url": "/m/a.jpg", "path": "products/a.jpg", "alt": {"de": ""}}],
    )
    n = media_registry.write_back_alt("products/a.jpg", {"de": "Frisches Brot"})
    assert n == 1
    p.refresh_from_db()
    assert p.images[0]["alt"]["de"] == "Frisches Brot"


def test_delete_unused_refuses_when_used(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.catalog.models import Product

    ref = save_product_image(_png(), folder="products")
    Product.objects.create(name={"de": "Brot"}, base_price="3.00", images=[ref])
    asset = MediaAsset.objects.get(path=ref["path"])
    assert media_registry.delete_unused(asset) is False  # занят — отказ
    Product.objects.all().delete()
    asset.refresh_from_db()
    assert media_registry.delete_unused(asset) is True
    assert not MediaAsset.objects.filter(path=ref["path"]).exists()


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/medien/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = SimpleNamespace(schema_name="public", site_config={})
    return request


def test_media_library_view_lists_and_saves_alt(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import media_library

    asset = MediaAsset.objects.create(path="products/x.jpg", url="/m/x.jpg", folder="products")
    body = media_library(_req()).content.decode()
    assert "/m/x.jpg" in body and "unused" in body

    resp = media_library(_req("post", {"action": "alt", "pk": str(asset.pk), "alt_de": "Torte"}))
    assert resp.status_code == 302
    asset.refresh_from_db()
    assert asset.alt["de"] == "Torte"
