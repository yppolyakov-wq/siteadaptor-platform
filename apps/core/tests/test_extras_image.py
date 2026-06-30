"""A5: фото доп-услуги (Extra.image) — модель + кабинет-загрузка + показ на витрине."""

import io
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import RequestFactory
from PIL import Image

from apps.core import views
from apps.core.models import Extra
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _png() -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 100, 50)).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile("pic.png", buf.read(), content_type="image/png")


def _req(data):
    request = RequestFactory().post("/dashboard/extras/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build()
    return request


def test_extra_image_url_property():
    assert Extra(image={"url": "/m/x.png"}).image_url == "/m/x.png"
    assert Extra(image={}).image_url == ""
    assert Extra(image="bad").image_url == ""  # не-dict безопасно


def test_cabinet_add_extra_with_photo():
    resp = views.extras_view(
        _req({"action": "add", "label": "Frühstück", "price": "12", "image": _png()})
    )
    assert resp.status_code == 302
    assert Extra.objects.get(label="Frühstück").image_url  # фото сохранено


def test_cabinet_set_image_on_existing_extra():
    extra = Extra.objects.create(label="Parkplatz", price_cents=500)
    views.extras_view(_req({"action": "set_image", "extra": str(extra.pk), "image": _png()}))
    extra.refresh_from_db()
    assert extra.image_url


def test_cabinet_add_without_photo_ok():
    resp = views.extras_view(_req({"action": "add", "label": "Späte Abreise", "price": "0"}))
    assert resp.status_code == 302
    assert Extra.objects.get(label="Späte Abreise").image_url == ""  # без фото — как раньше


def test_extras_partial_renders_thumbnail():
    extra = Extra(label="Frühstück", price_cents=1200, image={"url": "/media/extras/x.png"})
    html = Template("{% include 'storefront/_extras.html' %}").render(Context({"extras": [extra]}))
    assert "/media/extras/x.png" in html and "Frühstück" in html
