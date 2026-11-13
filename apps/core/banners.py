"""FB-29.2: библиотека баннеров — единственный писатель и читатель модели `Banner`.

Баннер несёт те же поля, что слайд прежнего `site_config["heroes"]`, и чистится тем же
нормализатором (`siteconfig.normalize_heroes`): безопасные схемы ссылок, цели из списка
целей меню, оформление из реестра. Место показа хранит выбор — список UUID; `resolve`
превращает его в слайды той же формы, что уже рисует витрина.
"""

from __future__ import annotations

import datetime
import uuid

from django.utils import timezone

#: Поля слайда, которые баннер хранит строками как есть.
_TEXT_FIELDS = ("title", "text", "button_label", "button_url", "link")
_STYLE_FIELDS = ("align", "overlay", "tone")
_I18N_FIELDS = (
    ("title", "title_i18n"),
    ("text", "text_i18n"),
    ("button_label", "button_label_i18n"),
)


def _day(value):
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def clean_fields(raw: dict) -> dict:
    """Сырые поля формы/переноса → значения модели. Та же санитизация, что у слайда
    баннера главной; пустой баннер (ни фото, ни заголовка, ни текста) — ValueError."""
    from apps.tenants import siteconfig

    raw = raw if isinstance(raw, dict) else {}
    image = raw.get("image") if isinstance(raw.get("image"), dict) else {}
    url = str(image.get("url") or "") if image else str(raw.get("image") or "")
    starts, ends = _day(raw.get("starts")), _day(raw.get("ends"))
    slide = {
        **{k: raw.get(k) for k in (*_TEXT_FIELDS, *_STYLE_FIELDS)},
        "image": url,
        "click_all": bool(raw.get("click_all")),
    }
    cleaned = siteconfig.normalize_heroes([slide])
    if not cleaned:
        raise ValueError("empty banner")
    slide = cleaned[0]
    ref = {"url": slide["image"]} if slide["image"] else {}
    if ref and image.get("path"):
        ref["path"] = str(image["path"])
    if ref and image.get("alt"):
        ref["alt"] = str(image["alt"])[:300]
    out = {k: slide.get(k, "") for k in (*_TEXT_FIELDS, *_STYLE_FIELDS)}
    out.update(
        image=ref,
        click_all=bool(slide.get("click_all")),
        starts=starts,
        ends=ends,
        is_active=raw.get("is_active") is not False,
    )
    if "sort_order" in raw:
        out["sort_order"] = max(0, int(raw.get("sort_order") or 0))
    if raw.get("legacy_key"):
        out["legacy_key"] = str(raw["legacy_key"])[:80]
    return out


def create(raw: dict):
    from apps.core.models import Banner

    return Banner.objects.create(**clean_fields(raw))


def update(banner, raw: dict):
    for field, value in clean_fields(raw).items():
        setattr(banner, field, value)
    banner.save()
    return banner


def to_slide(banner, locale: str | None = None) -> dict:
    """Запись → слайд той формы, что рисует витрина (`normalize_heroes`), с переводом."""
    slide = {
        "image": (banner.image or {}).get("url", ""),
        "button_url": banner.button_url,
    }
    for base, overlay in _I18N_FIELDS:
        slide[base] = banner.get_overlay(base, overlay, locale)
    if banner.link:
        slide["link"] = banner.link
    for key in _STYLE_FIELDS:
        if getattr(banner, key):
            slide[key] = getattr(banner, key)
    if banner.starts:
        slide["starts"] = banner.starts.isoformat()
    if banner.ends:
        slide["ends"] = banner.ends.isoformat()
    if banner.click_all:
        slide["click_all"] = True
    if (banner.image or {}).get("alt"):
        slide["alt"] = banner.image["alt"]
    slide["id"] = str(banner.pk)
    return slide


def clean_pick(pick) -> list[str]:
    """Выбор места показа → UUID-строки без мусора и повторов, в порядке владельца."""
    out: list[str] = []
    for value in pick if isinstance(pick, (list, tuple)) else []:
        try:
            key = str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            continue
        if key not in out:
            out.append(key)
    return out


def resolve(pick, legacy=None, locale: str | None = None) -> list[dict]:
    """Слайды места показа. Есть выбор — записи, активные СЕГОДНЯ, в порядке выбора
    (удалённая или выключенная запись просто выпадает). Выбора нет — прежние слайды
    `legacy` как есть (их фильтрует и дополняет ссылкой тег витрины)."""
    from apps.core.models import Banner

    keys = clean_pick(pick)
    if not keys:
        return list(legacy or [])
    today = timezone.localdate()
    found = {str(b.pk): b for b in Banner.objects.filter(pk__in=keys, is_active=True)}
    out = []
    for key in keys:
        banner = found.get(key)
        if banner is None:
            continue
        if banner.starts and banner.starts > today:
            continue
        if banner.ends and banner.ends < today:
            continue
        out.append(to_slide(banner, locale))
    return out
