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
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        # SyntaxError/ValueError: Pillow на битых чанках (напр. «broken PNG file»)
        # — отдаём чистый 400, а не 500 (важно для замены фото на канве редактора).
        raise ValidationError(_("Not a valid image file.")) from exc
    finally:
        uploaded.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError(_("Allowed formats: JPEG, PNG, WEBP."))
    return fmt


def save_product_image(uploaded, *, is_primary=False, sort_order=0, folder="products") -> dict:
    """Валидирует, сохраняет в storage и возвращает FileRef-dict."""
    fmt = validate_image(uploaded)
    name = f"{folder}/{uuid.uuid4().hex}.{_EXT[fmt]}"
    saved_name = default_storage.save(name, uploaded)
    ref = {
        "id": uuid.uuid4().hex,
        "url": default_storage.url(saved_name),
        "path": saved_name,  # для удаления из storage
        "alt": {"de": "", "en": ""},
        "mime_type": _MIME[fmt],
        "size": uploaded.size,
        "is_primary": is_primary,
        "sort_order": sort_order,
    }
    _register_asset(ref, folder)
    return ref


def _register_asset(ref: dict, folder: str) -> None:
    """CM-4: запись в реестр MediaAsset — строго fail-safe (реестр вторичен
    к файлу; ошибка индекса не должна ронять загрузку)."""
    try:
        from apps.core.models import MediaAsset

        MediaAsset.objects.get_or_create(
            path=ref["path"],
            defaults={
                "url": ref["url"],
                "folder": folder,
                "mime_type": ref["mime_type"],
                "size": ref["size"],
            },
        )
    except Exception:  # noqa: BLE001 — индекс не критичен для загрузки
        pass


def delete_stored_image(file_ref: dict) -> None:
    """Удаляет файл из storage (best-effort) + запись реестра (CM-4)."""
    path = file_ref.get("path")
    if path and default_storage.exists(path):
        default_storage.delete(path)
    if path:
        try:
            from apps.core.models import MediaAsset

            MediaAsset.objects.filter(path=path).delete()
        except Exception:  # noqa: BLE001
            pass


# --- Пер-слайд управление галереей на канве (id-keyed) ---------------------------
# Товар/Событие/Номер: images — список FileRef со стабильным `id`. Операции ниже
# работают по id, поэтому редактор может заменить/удалить КОНКРЕТНЫЙ слайд, добавить
# фото и держать корректное «главное» (is_primary) без формы в кабинете.


def gallery_replace(images, image_id, uploaded, *, folder="products") -> list:
    """Заменить фото новым файлом В МЕСТЕ (новый FileRef наследует is_primary/sort_order
    старого, старый файл удаляется из storage):
      • `image_id` задан и найден → меняем именно этот слайд (📷 на миниатюре);
      • `image_id` пуст → меняем ГЛАВНОЕ фото (📷 на карточке; для одиночного фото —
        честная замена без дубля-миниатюры);
      • галерея пуста → добавить как главное; id задан, но не найден (устаревший) →
        добавить как новое (чтобы не потерять загруженный файл)."""
    images = list(images or [])
    new = save_product_image(uploaded, folder=folder)
    target = None
    if image_id:
        target = next((i for i, img in enumerate(images) if img.get("id") == image_id), None)
    elif images:
        target = next((i for i, img in enumerate(images) if img.get("is_primary")), 0)
    if target is None:
        new["is_primary"] = not images
        new["sort_order"] = len(images)
        images.append(new)
        return images
    old = images[target]
    new["is_primary"] = old.get("is_primary", target == 0)
    new["sort_order"] = old.get("sort_order", target)
    delete_stored_image(old)  # не плодить осиротевшие файлы
    images[target] = new
    return images


def gallery_add(images, uploaded, *, folder="products") -> list:
    """Добавить фото в конец галереи (главное только если галерея была пуста)."""
    images = list(images or [])
    new = save_product_image(uploaded, is_primary=not images, sort_order=len(images), folder=folder)
    images.append(new)
    return images


def gallery_remove(images, image_id) -> list:
    """Удалить фото по id (файл — из storage); если убрали главное — назначить главным
    первое оставшееся, чтобы галерея не осталась без primary."""
    images = list(images or [])
    kept = []
    for img in images:
        if img.get("id") == image_id:
            delete_stored_image(img)
            continue
        kept.append(img)
    if kept and not any(i.get("is_primary") for i in kept):
        kept[0]["is_primary"] = True
    return kept


def apply_gallery_op(images, *, op, image_id, uploaded, folder) -> list:
    """Диспетчер пер-слайд операций галереи для эндпоинтов товара/события/номера.
    op ∈ {replace, add, remove}. ValueError — неизвестный op / нет файла для replace|add.
    ValidationError (из save_product_image) — пробрасывается вызывающему (битый файл)."""
    if op == "remove":
        return gallery_remove(images, image_id)
    if op in ("add", "replace"):
        if not uploaded:
            raise ValueError("image required")
        if op == "add":
            return gallery_add(images, uploaded, folder=folder)
        return gallery_replace(images, image_id, uploaded, folder=folder)
    raise ValueError(f"unknown gallery op: {op}")
