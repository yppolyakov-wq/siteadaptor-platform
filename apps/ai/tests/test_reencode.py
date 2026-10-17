"""Д1-0: копия фото для провайдера без EXIF/GPS, выпрямлена и уменьшена."""

import io

import pytest
from PIL import Image

from apps.ai import images
from apps.ai.errors import AIConfigError


def _jpeg_with_gps(size=(3000, 2000), orientation=6):
    img = Image.new("RGB", size, (200, 50, 50))
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation: повернуть на 90°
    exif[0x010F] = "Kamera mit Standort"  # любой тег EXIF (у реальных фото тут и GPS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_reencode_strips_exif_and_gps_and_bounds_size():
    out = images.reencode(_jpeg_with_gps())
    assert images.sniff(out) == "image/jpeg"
    with Image.open(io.BytesIO(out)) as img:
        assert max(img.size) <= 1568
        assert not img.getexif()  # ни ориентации, ни GPS
        assert img.size[1] > img.size[0]  # выпрямлено по EXIF (портрет)


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_reencode_accepts_png_and_webp(fmt):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 30), (0, 0, 0, 0)).save(buf, format=fmt)
    out = images.reencode(buf.getvalue())
    assert images.sniff(out) == "image/jpeg"


def test_reencode_rejects_non_image():
    with pytest.raises(AIConfigError):
        images.reencode(b"%PDF-1.4 not an image")
    with pytest.raises(AIConfigError):
        images.reencode(b"\xff\xd8\xff" + b"garbage" * 10)  # сигнатура есть, тело битое


def test_huge_pixel_count_rejected_before_decode(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, format="PNG")
    with pytest.raises(AIConfigError):
        images.reencode(buf.getvalue())


def test_broken_png_is_config_error_not_500():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, format="PNG")
    data = buf.getvalue()
    with pytest.raises(AIConfigError):
        images.reencode(data[:40] + b"\x00" * 20 + data[60:])


def test_transparent_background_becomes_white():
    buf = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(buf, format="PNG")
    out = images.reencode(buf.getvalue())
    with Image.open(io.BytesIO(out)) as img:
        assert img.getpixel((5, 5))[0] > 240
