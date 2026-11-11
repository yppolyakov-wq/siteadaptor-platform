"""M21.11: ширина фото шагом 5 % и кадрирование (новый файл на сервере)."""

import io
import json

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from apps.core import content_page_views as views
from apps.core import page_images, richtext
from apps.core.tests.test_m21_10_text_pages_hub import _req

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_width_classes_step_5_and_exclusive():
    out = richtext.sanitize_page(
        '<figure class="sf-img-sm sf-w-45"><img src="/media/p/a.png" alt=""></figure>'
    )
    assert 'class="sf-w-45"' in out
    assert "sf-w-47" not in richtext.sanitize_page(
        '<figure class="sf-w-47"><img src="/media/p/a.png" alt=""></figure>'
    )
    assert 'sf-w-5"' not in richtext.sanitize_page(
        '<figure class="sf-w-5"><img src="/media/p/a.png" alt=""></figure>'
    )
    assert 'class="sf-w-100"' in richtext.sanitize_page(
        '<figure class="sf-w-100"><img src="/media/p/a.png" alt=""></figure>'
    )


def _image(w=400, h=200):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 50, 50)).save(buf, "PNG")
    name = default_storage.save("pages/test-crop.png", ContentFile(buf.getvalue()))
    return "/media/" + name


def test_crop_makes_a_new_smaller_file(settings):
    settings.MEDIA_URL = "/media/"
    src = _image()
    url = page_images.crop_page_image(src, ["0.25", "0", "0.5", "1"])
    assert url != src and url.startswith("/media/pages/")
    with default_storage.open(url[len("/media/") :]) as fh:
        assert Image.open(fh).size == (200, 200)
    assert default_storage.exists(src[len("/media/") :])  # оригинал не тронут


@pytest.mark.parametrize(
    "src",
    [
        "https://evil.example/a.png",
        "/media/../etc/passwd",
        "/media/a%2f..%2fb.png",
        "/other/a.png",
        "",
    ],
)
def test_crop_rejects_foreign_sources(settings, src):
    settings.MEDIA_URL = "/media/"
    with pytest.raises(page_images.CropError):
        page_images.crop_page_image(src, ["0", "0", "0.5", "0.5"])


@pytest.mark.parametrize(
    "box", [["0", "0", "0", "0.5"], ["-1", "0", "0.5", "0.5"], ["x", "0", "1", "1"], [None] * 4]
)
def test_crop_rejects_bad_box(settings, box):
    settings.MEDIA_URL = "/media/"
    with pytest.raises(page_images.CropError):
        page_images.crop_page_image(_image(), box)


def test_crop_view_needs_seiten_edit_and_post(settings):
    from django.core.exceptions import PermissionDenied

    from apps.core.models import Membership
    from apps.core.tests.test_m21_10_text_pages_hub import _user

    settings.MEDIA_URL = "/media/"
    src = _image()
    staff = _user(Membership.ROLE_STAFF)
    try:
        resp = views.page_image_crop(_req("/x/", "post", {"src": src}, user=staff))
        assert resp.status_code == 403
    except PermissionDenied:
        pass
    resp = views.page_image_crop(
        _req("/x/", "post", {"src": src, "x": "0", "y": "0", "w": "0.5", "h": "0.5"})
    )
    assert resp.status_code == 200 and json.loads(resp.content)["url"].startswith("/media/pages/")
