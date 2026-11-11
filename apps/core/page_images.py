"""M21.11: кадрирование картинки страницы (редактор «Seiten»).

Обрезаем файл на сервере: новая картинка сохраняется рядом (папка ``pages``), старая
не трогается — её могут использовать другие страницы. Стилей в тексте нет: санитайзер
пропускает только адрес картинки, поэтому обрезка = новый файл.
"""

from __future__ import annotations

import io

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import gettext as _

#: Минимальная доля стороны рамки (2 %) — иначе вышла бы картинка в пару пикселей.
MIN_SIDE = 0.02
#: Потолок пикселей для обрезки (память воркера): фото с телефона — до ~50 Мпикс.
MAX_CROP_PIXELS = 40_000_000


class CropError(ValueError):
    """Ошибка кадрирования — текст для владельца."""


def _media_path(src: str) -> str:
    media = (getattr(settings, "MEDIA_URL", "") or "/media/").strip()
    lowered = (src or "").lower()
    if (
        not src
        or media in ("", "/")
        or not src.startswith(media)
        or any(ch in src for ch in "\\ \t\r\n?#")
        or "%" in lowered
        or "/../" in src
        or src.endswith("/..")
    ):
        raise CropError(_("Dieses Bild kann nicht zugeschnitten werden."))
    path = src[len(media) :]
    # Ревью безопасности: медиа общее для всех бизнесов — обрезаем только из публичных
    # папок (те же, что раздаёт витрина), а не из закрытых (документы, импорт).
    from apps.core.media_views import PUBLIC_PREFIXES

    if path.startswith("/") or path.split("/", 1)[0] not in PUBLIC_PREFIXES or "/" not in path:
        raise CropError(_("Dieses Bild kann nicht zugeschnitten werden."))
    return path


def _box(values) -> tuple[float, float, float, float]:
    try:
        x, y, w, h = (float(v) for v in values)
    except (TypeError, ValueError):
        raise CropError(_("Ungültiger Bildausschnitt.")) from None
    if not all(0 <= v <= 1 for v in (x, y, w, h)) or w < MIN_SIDE or h < MIN_SIDE:
        raise CropError(_("Ungültiger Bildausschnitt."))
    return x, y, min(w, 1 - x), min(h, 1 - y)


def crop_page_image(src: str, values) -> str:
    """Обрезать картинку ``src`` по доле (x, y, w, h) от 0 до 1 → адрес нового файла."""
    from PIL import Image, ImageOps

    from apps.catalog.images import _MIME, MAX_STRIP_PIXELS, save_product_image

    path = _media_path(src)
    x, y, w, h = _box(values)
    try:
        if not default_storage.exists(path):
            raise CropError(_("Dieses Bild kann nicht zugeschnitten werden."))
        with default_storage.open(path, "rb") as fh, Image.open(fh, formats=list(_MIME)) as img:
            fmt = img.format
            if img.size[0] * img.size[1] > min(MAX_STRIP_PIXELS, MAX_CROP_PIXELS):
                raise CropError(_("Das Bild ist zu groß zum Zuschneiden."))
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            left, top = round(x * width), round(y * height)
            right = min(width, max(left + 1, round((x + w) * width)))
            bottom = min(height, max(top + 1, round((y + h) * height)))
            out_img = img.crop((left, top, right, bottom))
            if fmt == "JPEG" and out_img.mode not in ("RGB", "L"):
                out_img = out_img.convert("RGB")
            buf = io.BytesIO()
            params = {"quality": 90} if fmt in ("JPEG", "WEBP") else {}
            out_img.save(buf, format=fmt, **params)
    except CropError:
        raise
    except Exception as exc:  # noqa: BLE001 — битый/чужой файл: честный отказ
        raise CropError(_("Dieses Bild kann nicht zugeschnitten werden.")) from exc
    try:
        ref = save_product_image(ContentFile(buf.getvalue(), name="crop"), folder="pages")
    except ValidationError as exc:
        raise CropError(" ".join(exc.messages)) from exc
    return ref["url"]
