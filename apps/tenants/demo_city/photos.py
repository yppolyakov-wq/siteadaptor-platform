"""DCC: статус фото-ключа для замков («свой кадр | плейсхолдер | чужой кадр»)."""

from __future__ import annotations

from apps.tenants import demo_images


def photo_status(keyword: str) -> str:
    """own — есть файл ровно с этим слагом; placeholder — файла нет (SVG);
    borrowed — резолвер отдал бы ЧУЖОЙ кадр (префиксная группа / псевдоним / lock)."""
    slug = demo_images._kw_slug(keyword)
    found = demo_images.photo_static_name(keyword)
    if found is None:
        return "placeholder"
    stem = found.rsplit(".", 1)[0]
    if stem == slug or stem in {demo_images._kw_slug(t) for t in keyword.split(",")}:
        return "own"
    return "borrowed"
