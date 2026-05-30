"""Сохранение картинок товара в FileRef-envelope (доп. 2.2).

Формат элемента Product.images:
  {"id","url","alt":{de,en},"mime_type","size","is_primary","sort_order"}
"""

import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.utils.translation import gettext as _
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def validate_image(uploaded) -> str:
    """Проверяет размер и реальный формат (через Pillow). Возвращает формат."""
    if uploaded.size > MAX_IMAGE_BYTES:
        raise ValidationError(_("Image too large (max 5 MB)."))
    try:
        img = Image.open(uploaded)
        img.verify()  # проверка целостности
        fmt = img.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(_("Not a valid image file.")) from exc
    finally:
        uploaded.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError(_("Allowed formats: JPEG, PNG, WEBP."))
    return fmt


def save_product_image(uploaded, *, is_primary=False, sort_order=0) -> dict:
    """Валидирует, сохраняет в storage и возвращает FileRef-dict."""
    fmt = validate_image(uploaded)
    name = f"products/{uuid.uuid4().hex}.{_EXT[fmt]}"
    saved_name = default_storage.save(name, uploaded)
    return {
        "id": uuid.uuid4().hex,
        "url": default_storage.url(saved_name),
        "path": saved_name,  # для удаления из storage
        "alt": {"de": "", "en": ""},
        "mime_type": _MIME[fmt],
        "size": uploaded.size,
        "is_primary": is_primary,
        "sort_order": sort_order,
    }


def delete_stored_image(file_ref: dict) -> None:
    """Удаляет файл из storage (best-effort)."""
    path = file_ref.get("path")
    if path and default_storage.exists(path):
        default_storage.delete(path)
