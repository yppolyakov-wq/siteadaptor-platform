"""SEC-G14 (аудит 2026-11-01): фото заявки сохраняется без EXIF (GPS клиента)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.images import strip_metadata


def _jpeg_with_gps():
    img = Image.new("RGB", (20, 10), "red")
    exif = Image.Exif()
    exif[0x8825] = {2: (51.0, 10.0, 0.0), 4: (7.0, 5.0, 0.0)}  # GPSInfo
    exif[0x0110] = "Pixel 9"  # Model
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return SimpleUploadedFile("x.jpg", buf.getvalue(), content_type="image/jpeg")


def test_strip_metadata_removes_gps_and_keeps_pixels():
    up = _jpeg_with_gps()
    assert Image.open(io.BytesIO(up.read())).getexif()  # фикстура действительно с EXIF
    clean = strip_metadata(up, "JPEG")
    out = Image.open(io.BytesIO(clean.read()))
    assert not out.getexif()
    assert out.size == (20, 10)


@pytest.mark.django_db
def test_job_photo_is_saved_without_exif(monkeypatch):
    from apps.jobs import services

    saved = []
    monkeypatch.setattr(
        "apps.jobs.models.JobPhoto.objects.create",
        lambda **kw: saved.append(kw["image"].read()),
    )
    assert services.add_job_photos(object(), [_jpeg_with_gps()]) == 1
    assert not Image.open(io.BytesIO(saved[0])).getexif()
