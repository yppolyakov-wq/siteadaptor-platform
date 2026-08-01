"""Overlay-переводы для СПИСОЧНЫХ полей (план i18n-owner-content-2026-08-01).

`I18nMixin.get_overlay` покрывает скалярные поля («база в плоском поле,
переводы в `*_i18n[locale]`»). Часть витринного контента — списки: атрибуты
услуги (`list[str]`) и её FAQ (`list[{q,a}]`). Здесь та же семантика, но
поэлементно.

Инварианты (важны, потому что список владельца — источник правды):

* **База задаёт длину.** Лишние элементы оверлея игнорируются: перевод не
  может «дорисовать» пункт, которого владелец не писал.
* **Пустой перевод = фолбэк на базу** (как у скаляров), поэтому частичный
  перевод списка безопасен.
* **Выравнивание по индексу НОРМАЛИЗОВАННОГО базового списка** — того самого,
  что уходит в рендер (мусор из сырого поля уже выброшен). Засев переводов
  обязан идти по нему же, иначе строки разъедутся.
"""

from django.conf import settings
from django.utils.translation import get_language


def _resolved_locale(locale: str | None) -> str:
    return locale or get_language() or settings.LANGUAGE_CODE


def overlay_seq(base: list, overlay, locale: str | None = None, *, keys=None) -> list:
    """Наложить переводы `overlay[locale]` на нормализованный список `base`.

    `keys=None` — список строк; `keys=("q", "a")` — список словарей, где
    переводятся указанные ключи (остальные берутся из базы без изменений).
    Любой мусор в оверлее (не список / не тот тип элемента) молча даёт базу —
    перевод не должен ломать витрину.
    """
    if not isinstance(base, list):
        return []
    if _resolved_locale(locale) == settings.LANGUAGE_CODE:
        return list(base)
    items = overlay.get(_resolved_locale(locale)) if isinstance(overlay, dict) else None
    if not isinstance(items, (list, tuple)):
        return list(base)

    out = []
    for i, item in enumerate(base):
        tr = items[i] if i < len(items) else None
        if keys is None:
            out.append(tr.strip() if isinstance(tr, str) and tr.strip() else item)
            continue
        merged = dict(item) if isinstance(item, dict) else item
        if isinstance(merged, dict) and isinstance(tr, dict):
            for k in keys:
                v = tr.get(k)
                if isinstance(v, str) and v.strip():
                    merged[k] = v.strip()
        out.append(merged)
    return out
