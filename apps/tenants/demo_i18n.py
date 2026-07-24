"""DL-2/DL-3: централизованный DE→{локаль} словарь демо-контента + пост-сид перевод.

Демо-витрины многоязычны (DL-1: ``DemoKit.enabled_locales``). Немецкий контент —
источник (плоские поля / база оверлея), остальные локали накладываются оверлеем.
Чтобы не править 14 больших определений китов и не выравнивать вручную позиционные
списки, держим ПО ОДНОМУ словарю на локаль (``demo_i18n_<loc>.json`` = {de: перевод})
+ два генерик-прохода, вызываемых из ``apply_kit``:

  * :func:`overlay_config` — строит ``cfg["i18n"][loc]`` из немецких значений
    site_config (hero/about/section_titles/cta/faq/testimonials/process/heroes/
    trust/archetypes) для каждой локали, зеркаля структуру базы (позиционный merge
    ``localize``).
  * :func:`translate_tenant_content` — заполняет ``*_i18n[loc]`` у Product/Category
    (full-JSON) и Service/StayUnit/Combo/Event/Collection (flat+overlay).

Идемпотентно: уже заданный перевод локали (ручной оверлей кита ``pranasy`` или
двуязычные позиции) НЕ перезаписывается. Словари — данные, грузятся лениво (нужны
только при сидинге демо, не в рантайме витрины).
"""

from __future__ import annotations

import json
import os

# Целевые локали демо-перевода (кроме базовой de). Каждой соответствует файл
# ``demo_i18n_<loc>.json`` рядом с этим модулем. Порядок = порядок пилюль свитчера
# (после de) для новых демо-китов.
DEMO_LOCALES = ("en", "ru", "uk", "tr")

_DIR = os.path.dirname(__file__)
_MAPS: dict[str, dict[str, str]] = {}


def _map(locale: str) -> dict[str, str]:
    if locale not in _MAPS:
        path = os.path.join(_DIR, f"demo_i18n_{locale}.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _MAPS[locale] = json.load(fh)
        except (OSError, ValueError):
            _MAPS[locale] = {}
    return _MAPS[locale]


def t(de: str, locale: str) -> str | None:
    """Перевод немецкой строки на локаль (``None``, если перевода нет)."""
    if not isinstance(de, str):
        return None
    return _map(locale).get(de.strip())


# --- site_config оверлей ---------------------------------------------------

# Ключи site_config, которые можно локализовать (зеркалятся в i18n-оверлей).
_TRANSLATABLE_CONFIG_KEYS = (
    "hero_title",
    "hero_text",
    "about_title",
    "about_text",
    "section_titles",
    "section_intros",
    "cta",
    "faq",
    "testimonials",
    "process",
    "heroes",
    "trust",
    "archetypes",
)


def _tr_node(node, locale: str):
    """Рекурсивно построить оверлей узла на локаль (та же форма, только переведённые
    листья). ``None`` — если ничего не переведено (узел не оверлеится).

    Для СПИСКОВ индексы сохраняются (``localize._deep_overlay`` мерджит позиционно):
    непереведённая строка остаётся немецкой (no-op), непереведённый dict → ``{}``.
    """
    if isinstance(node, str):
        return t(node, locale)
    if isinstance(node, dict):
        out = {}
        for key, val in node.items():
            res = _tr_node(val, locale)
            if res is not None:
                out[key] = res
        return out or None
    if isinstance(node, list):
        out = []
        any_tr = False
        for item in node:
            if isinstance(item, str):
                tr = t(item, locale)
                if tr is not None:
                    any_tr = True
                out.append(tr if tr is not None else item)
            elif isinstance(item, dict):
                res = _tr_node(item, locale)
                if res is not None:
                    any_tr = True
                    out.append(res)
                else:
                    out.append({})  # пустой оверлей = no-op merge, индекс цел
            elif isinstance(item, list):
                res = _tr_node(item, locale)
                if res is not None:
                    any_tr = True
                    out.append(res)
                else:
                    out.append([])
            else:
                out.append(item)
        return out if any_tr else None
    return None


def _deep_merge_prefer_b(a: dict, b: dict) -> dict:
    """Слить ``a`` и ``b``, приоритет у ``b`` (ручной оверлей кита побеждает
    сгенерированный). Возвращает новый dict."""
    out = dict(a)
    for key, val in b.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_prefer_b(out[key], val)
        else:
            out[key] = val
    return out


def overlay_config(cfg: dict, locales) -> None:
    """Добавить/дополнить ``cfg["i18n"][loc]`` сгенерированным оверлеем site_config
    для каждой локали из ``locales``. Изменяет ``cfg`` на месте. Существующий ручной
    оверлей (pranasy) имеет приоритет — генерённый лишь заполняет пробелы."""
    if not isinstance(cfg, dict):
        return
    source = {k: cfg.get(k) for k in _TRANSLATABLE_CONFIG_KEYS if k in cfg}
    i18n = dict(cfg.get("i18n") or {})
    for loc in locales:
        generated = _tr_node(source, loc) or {}
        existing = i18n.get(loc) if isinstance(i18n.get(loc), dict) else {}
        merged = _deep_merge_prefer_b(generated, existing)
        if merged:
            i18n[loc] = merged
    if i18n:
        cfg["i18n"] = i18n


# --- модельный контент -----------------------------------------------------


def _fill_full(obj, field: str, locales) -> bool:
    """Full-JSON поле (Product/Category ``name``/``description`` = ``{de,en,…}``):
    добавить перевод локали, если его нет и перевод найден. Возвращает True, если
    хоть что-то добавлено."""
    val = getattr(obj, field, None)
    if not isinstance(val, dict):
        return False
    de = val.get("de")
    if not de:
        return False
    changed = False
    for loc in locales:
        if not val.get(loc):
            tr = t(de, loc)
            if tr:
                val[loc] = tr
                changed = True
    return changed


def _fill_overlay(obj, base_field: str, overlay_field: str, locales) -> bool:
    """Flat+overlay (Service/StayUnit/Combo/Event/Collection): база — плоское поле
    (de), переводы — в ``*_i18n[loc]``. Добавить недостающие локали."""
    de = getattr(obj, base_field, "") or ""
    if not de:
        return False
    ov = getattr(obj, overlay_field, None)
    ov = dict(ov) if isinstance(ov, dict) else {}
    changed = False
    for loc in locales:
        if not ov.get(loc):
            tr = t(de, loc)
            if tr:
                ov[loc] = tr
                changed = True
    if changed:
        setattr(obj, overlay_field, ov)
    return changed


def translate_tenant_content(tenant, locales) -> None:
    """Проставить переводы (для всех ``locales``) на весь демо-контент тенанта
    (вызывать В СХЕМЕ тенанта, после сидинга). Идемпотентно: существующий перевод
    локали не трогаем. Тенант демо свежий/пересоздаётся → безопасно обходить всё.
    """
    locales = [loc for loc in locales if loc != "de"]
    if not locales:
        return

    from apps.booking.models import Service
    from apps.catalog.models import Category, Combo, Product
    from apps.events.models import Event
    from apps.stays.models import StayUnit

    for prod in Product.objects.all():
        changed = _fill_full(prod, "name", locales) | _fill_full(prod, "description", locales)
        if changed:
            prod.save(update_fields=["name", "description"])

    for cat in Category.objects.all():
        if _fill_full(cat, "name", locales):
            cat.save(update_fields=["name"])

    for svc in Service.objects.all():
        changed = _fill_overlay(svc, "name", "name_i18n", locales) | _fill_overlay(
            svc, "description", "description_i18n", locales
        )
        if changed:
            svc.save(update_fields=["name_i18n", "description_i18n"])

    for unit in StayUnit.objects.all():
        changed = _fill_overlay(unit, "name", "name_i18n", locales) | _fill_overlay(
            unit, "description", "description_i18n", locales
        )
        if changed:
            unit.save(update_fields=["name_i18n", "description_i18n"])

    for combo in Combo.objects.all():
        changed = _fill_overlay(combo, "name", "name_i18n", locales) | _fill_overlay(
            combo, "description", "description_i18n", locales
        )
        if changed:
            combo.save(update_fields=["name_i18n", "description_i18n"])

    for ev in Event.objects.all():
        changed = _fill_overlay(ev, "title", "title_i18n", locales) | _fill_overlay(
            ev, "description", "description_i18n", locales
        )
        if changed:
            ev.save(update_fields=["title_i18n", "description_i18n"])

    # Collection — TENANT-апп, но может быть отключён в тест-настройках; мягкий импорт.
    try:
        from apps.collections.models import Collection
    except ImportError:
        return
    for coll in Collection.objects.all():
        if _fill_overlay(coll, "name", "name_i18n", locales):
            coll.save(update_fields=["name_i18n"])
