"""Overlay-переводы для ВЛОЖЕННОГО JSON (аудит переводов демо 2026-08-13).

`I18nMixin.get_overlay` покрывает скаляры, `core.i18n_seq` — плоские списки.
Остался третий вид контента: свободная JSON-структура, где текст лежит на разной
глубине — ретрит-лендинг (`Event.details`: скаляры + списки строк + списки
словарей). Здесь та же семантика «база + оверлей», но рекурсивно.

Инварианты (те же, что у `i18n_seq`, и по той же причине — база принадлежит
владельцу, перевод её не переписывает):

* **База задаёт форму.** Оверлей может заменить только те листья, которые в базе
  есть: лишние ключи и элементы игнорируются, перевод не «дорисовывает» блок.
* **Пустой перевод = фолбэк на базу** (частичный перевод безопасен).
* **Списки мерджатся ПОЗИЦИОННО** — как `siteconfig._deep_overlay`. Значит,
  засевать перевод надо по НОРМАЛИЗОВАННОЙ структуре (той, что уходит в рендер),
  иначе строки разъедутся; в демо это `Event.landing`.
* **Не-строковые листья не трогаем** (числа, ссылки на фото): переводится ТОЛЬКО
  показной текст, ключи и URL остаются базовыми.
"""

from django.conf import settings
from django.utils.translation import get_language


def _resolved_locale(locale: str | None) -> str:
    return locale or get_language() or settings.LANGUAGE_CODE


# Ключи, которые НИКОГДА не переводятся, даже если содержат строку: это адреса
# картинок и служебные значения (в базе они рядом с текстом — напр. hosts.photo).
SKIP_KEYS = frozenset({"photo", "image", "url", "src", "href", "icon", "id", "key", "rating"})


def _merge(base, ov):
    if isinstance(base, dict):
        if not isinstance(ov, dict):
            return base
        return {k: (base[k] if k in SKIP_KEYS else _merge(base[k], ov.get(k))) for k in base}
    if isinstance(base, list):
        if not isinstance(ov, (list, tuple)):
            return base
        return [_merge(item, ov[i] if i < len(ov) else None) for i, item in enumerate(base)]
    if isinstance(base, str):
        return ov.strip() if isinstance(ov, str) and ov.strip() else base
    return base


def overlay_json(base, overlay, locale: str | None = None):
    """Наложить `overlay[locale]` на нормализованную структуру `base`.

    Базовая локаль (или отсутствие перевода) → база без изменений.
    """
    if _resolved_locale(locale) == settings.LANGUAGE_CODE:
        return base
    ov = overlay.get(_resolved_locale(locale)) if isinstance(overlay, dict) else None
    if ov is None:
        return base
    return _merge(base, ov)


def collect_strings(node, out=None) -> list[str]:
    """Все переводимые строки структуры (для засева словарей и замера покрытия)."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for key, val in node.items():
            if key not in SKIP_KEYS:
                collect_strings(val, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            collect_strings(item, out)
    elif isinstance(node, str) and node.strip():
        out.append(node.strip())
    return out


def build_overlay(base, translate) -> dict | None:
    """Построить оверлей той же формы: `translate(строка)` → перевод либо None.

    ``None`` — если не переведено ничего (оверлей не заводим). Непереведённые
    листья остаются пустыми строками → рендер возьмёт базу (см. `_merge`).
    """
    got = False

    def walk(node):
        nonlocal got
        if isinstance(node, dict):
            return {k: ("" if k in SKIP_KEYS else walk(v)) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [walk(item) for item in node]
        if isinstance(node, str):
            tr = translate(node.strip()) if node.strip() else None
            if tr:
                got = True
                return tr
            return ""
        return ""

    result = walk(base)
    return result if got else None
