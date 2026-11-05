"""Фото номера: сохранение пачкой с отчётом об ошибках (AIS-W W4-2).

Раньше ошибка любого файла молча пропускалась (`except Exception: continue`): владелец видел
«готово», а фото не было — и номер оставался без онлайн-брони (readiness `zimmer.room`)."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

MAX_PER_UPLOAD = 8
MAX_PER_UNIT = 24


def add_unit_photos(unit, uploaded) -> tuple[int, list[str]]:
    """Сохранить фото номера. Первое — обложка, если фото ещё нет.

    Возвращает (сохранено, [причина по каждому несохранённому файлу])."""
    from apps.catalog.images import save_product_image

    if not uploaded:
        return 0, []
    images = list(unit.images or [])
    failed: list[str] = []
    files = list(uploaded)
    if len(files) > MAX_PER_UPLOAD:
        failed.append(_("Höchstens %(n)s Fotos auf einmal.") % {"n": MAX_PER_UPLOAD})
        files = files[:MAX_PER_UPLOAD]
    saved = 0
    for f in files:
        if len(images) >= MAX_PER_UNIT:
            failed.append(_("Höchstens %(n)s Fotos je Zimmer.") % {"n": MAX_PER_UNIT})
            break
        try:
            ref = save_product_image(
                f, is_primary=not images, sort_order=len(images), folder="stays"
            )
        except ValidationError as exc:
            failed.append(f"{getattr(f, 'name', '')}: {' '.join(exc.messages)}")
            continue
        except Exception:
            logger.exception("unit photo upload failed (unit=%s)", unit.pk)
            failed.append(
                _("%(name)s: Foto konnte nicht gespeichert werden.")
                % {"name": getattr(f, "name", "")}
            )
            continue
        images.append(ref)
        saved += 1
    if saved:
        unit.images = images
        unit.save(update_fields=["images", "updated_at"])
    return saved, failed
