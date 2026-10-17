"""Проверка картинок до отправки: тип по сигнатуре (не по имени/заголовку), размер, число."""

from __future__ import annotations

from .errors import AIConfigError
from .providers.base import Image

MAX_BYTES = 5 * 1024 * 1024
MAX_COUNT = 4
MAX_TOTAL_BYTES = 10 * 1024 * 1024  # base64 ×4/3 и повторы умножают трафик
MAX_PIXELS = 40_000_000  # reencode: больше — не фото с телефона, а бомба по памяти


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def prepare(images) -> tuple[Image, ...]:
    images = list(images or ())
    if len(images) > MAX_COUNT:
        raise AIConfigError("too many images")
    out = []
    total = 0
    for data in images:
        data = bytes(data)
        total += len(data)
        if len(data) > MAX_BYTES or total > MAX_TOTAL_BYTES:
            raise AIConfigError("image too large")
        mime = sniff(data)
        if mime is None:
            raise AIConfigError("unsupported image type")
        out.append(Image(mime=mime, data=data))
    return tuple(out)


def reencode(data: bytes, *, max_side: int = 1568, quality: int = 85) -> bytes:
    """Копия фото для провайдера: выпрямлена по EXIF, уменьшена, без EXIF/GPS/ICC.

    Т-8.10a: геолокация магазина или дома владельца не уходит наружу, трафик меньше.
    Не картинка / бомба по пикселям → AIConfigError (спокойная ошибка у потребителя)."""
    import io

    from PIL import Image as PILImage
    from PIL import ImageOps, UnidentifiedImageError

    if sniff(bytes(data[:16])) is None:
        raise AIConfigError("unsupported image type")
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            # Размер — из заголовка, ДО декодирования: маленький файл с огромной картинкой
            # иначе съел бы память веб-воркера (Pillow сам бросает лишь выше ~178 MP).
            width, height = img.size
            if width * height > MAX_PIXELS:
                raise AIConfigError("image too large")
            if img.format == "JPEG":
                img.draft("RGB", (max_side, max_side))  # JPEG декодируется уже уменьшенным
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                # Прозрачный фон → белый, а не чёрный (так фото товара узнаётся лучше).
                img = img.convert("RGBA")
                canvas = PILImage.new("RGB", img.size, (255, 255, 255))
                canvas.paste(img, mask=img.split()[-1])
                img = canvas
            img = img.convert("RGB")
            img.thumbnail((max_side, max_side))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
    except AIConfigError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,  # Pillow: «broken PNG file»
        ValueError,
        MemoryError,
        PILImage.DecompressionBombError,
    ) as exc:
        raise AIConfigError("unsupported image type") from exc
    return out.getvalue()
