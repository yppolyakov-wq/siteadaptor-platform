"""Фидбэк владельца (2026-10-21): после «Veröffentlichen» в Mini App форма возвращалась в
начало, писала «Zu viele Versuche» и «Allowed formats», фото пропадали.

Причины: кадр камеры iPhone Pillow называет MPO (JPEG с доп. кадром) и отклонял его;
каждая повторная попытка сжигала лимит 5 в час; общая ошибка открывала шаг 1; форма с
файлами при повторе теряла уже сохранённые фото.
"""

import io
from pathlib import Path
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from PIL import Image

from apps.catalog import images
from apps.tenants import quickstart_views
from apps.tenants.models import Tenant
from apps.tenants.tests.test_quick_start import _drop, _post, _post_data


@pytest.fixture(autouse=True)
def _private_ratelimit(monkeypatch):
    """Счётчик лимита — свой на тест (общий Redis копит попытки соседей по IP)."""
    import uuid

    from django.core.cache.backends.locmem import LocMemCache

    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-qs-photos-{uuid.uuid4()}", {}))


TPL = Path(__file__).resolve().parents[3] / "templates" / "tenants" / "quick_start.html"


def _mpo(name="iphone.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(
        buf, format="MPO", save_all=True, append_images=[Image.new("RGB", (32, 32), "blue")]
    )
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def _gif():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="GIF")
    return SimpleUploadedFile("a.gif", buf.getvalue(), content_type="image/gif")


def test_iphone_mpo_photo_is_accepted_as_jpeg():
    assert images.validate_image(_mpo()) == "JPEG"


@pytest.mark.django_db
def test_wrong_photo_format_does_not_burn_rate_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(quickstart_views.ratelimit, "hit", lambda *a, **k: calls.append(a) or False)
    resp = quickstart_views.quick_start(_post({**_post_data(), "photo": _gif()}))
    assert resp.status_code == 200 and b"JPEG, PNG, WEBP" in resp.content
    assert calls == []


@pytest.mark.django_db
def test_saved_photos_survive_a_failed_submit_and_are_reused():
    with mock.patch("apps.tenants.quickstart_views.start_quick_provisioning") as start:
        start.side_effect = IntegrityError
        resp = quickstart_views.quick_start(_post({**_post_data(), "photo": _mpo()}))
    html = resp.content.decode()
    assert 'name="photos_kept"' in html and "data-source-photo" in html
    signed = html.split('name="photos_kept" value="', 1)[1].split('"', 1)[0]
    real = quickstart_views.start_quick_provisioning
    with (
        mock.patch("apps.tenants.tasks.provision_quick.delay"),
        mock.patch.object(quickstart_views, "start_quick_provisioning", wraps=real) as start,
    ):
        quickstart_views.quick_start(_post({**_post_data(), "photos_kept": signed}))
    tenants = Tenant.objects.filter(slug="baeckerei-mueller-soehne")
    try:
        assert tenants.exists()
        promo = start.call_args.kwargs["promo"]
        assert promo["images"] and promo["images"][0]["path"].startswith("promotions/")
    finally:
        for t in tenants:
            _drop(t)


@pytest.mark.django_db
def test_terminal_telegram_refusal_deletes_saved_photos(monkeypatch):
    monkeypatch.setattr(quickstart_views, "_telegram_gate", lambda *a: False)
    dropped = []
    monkeypatch.setattr(quickstart_views, "_drop_photos", lambda refs: dropped.extend(refs or []))
    resp = quickstart_views.quick_start(_post({**_post_data(), "photo": _mpo()}))
    assert resp.status_code == 200 and len(dropped) == 1
    assert b'name="photos_kept"' not in resp.content


@pytest.mark.django_db
def test_forged_kept_photos_are_ignored():
    req = _post({**_post_data(), "photos_kept": "promotions/x.jpg"})
    assert quickstart_views._kept_photos(req) == []


def test_general_error_opens_the_submit_step_not_the_first():
    src = TPL.read_text()
    assert "general ? last : 1" in src
