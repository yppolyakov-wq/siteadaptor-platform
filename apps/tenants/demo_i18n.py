"""DL-2: централизованный DE→EN словарь демо-контента + пост-сид перевод.

Демо-витрины двуязычны (DL-1: ``DemoKit.enabled_locales=["de","en"]`` → в шапке
переключатель языка). Немецкий контент — источник (плоские поля / база оверлея),
английский накладывается оверлеем. Чтобы не править 14 больших определений китов
и не выравнивать вручную позиционные списки, держим ОДИН словарь ``EN[de]=en`` +
два генерик-прохода, вызываемых из ``apply_kit``:

  * :func:`overlay_config_en` — строит ``cfg["i18n"]["en"]`` из немецких значений
    site_config (hero/about/section_titles/cta/faq/testimonials/process/heroes/
    trust/archetypes), зеркаля структуру базы (позиционный merge ``localize``).
  * :func:`translate_tenant_content` — заполняет ``*_i18n["en"]`` у Product/Category
    (full-JSON) и Service/StayUnit/Combo/Event/Collection (flat+overlay), где перевод
    есть в словаре.

Идемпотентно: уже заданный ``en`` (напр. ручной оверлей кита ``pranasy`` или
двуязычные позиции) НЕ перезаписывается. Словарь — данные (``demo_i18n_en.json``),
грузится лениво (нужен только при сидинге демо, не в рантайме витрины).
"""

from __future__ import annotations

import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "demo_i18n_en.json")
_EN: dict[str, str] | None = None


def _map() -> dict[str, str]:
    global _EN
    if _EN is None:
        try:
            with open(_DATA_PATH, encoding="utf-8") as fh:
                _EN = json.load(fh)
        except (OSError, ValueError):
            _EN = {}
    return _EN


def t(de: str) -> str | None:
    """EN-перевод немецкой строки (``None``, если перевода нет)."""
    if not isinstance(de, str):
        return None
    return _map().get(de.strip())


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


def _tr_node(node):
    """Рекурсивно построить EN-оверлей узла (та же форма, только переведённые
    листья). ``None`` — если ничего не переведено (узел не оверлеится).

    Для СПИСКОВ индексы сохраняются (``localize._deep_overlay`` мерджит позиционно):
    непереведённая строка остаётся немецкой (no-op), непереведённый dict → ``{}``.
    """
    if isinstance(node, str):
        return t(node)
    if isinstance(node, dict):
        out = {}
        for key, val in node.items():
            res = _tr_node(val)
            if res is not None:
                out[key] = res
        return out or None
    if isinstance(node, list):
        out = []
        any_tr = False
        for item in node:
            if isinstance(item, str):
                en = t(item)
                if en is not None:
                    any_tr = True
                out.append(en if en is not None else item)
            elif isinstance(item, dict):
                res = _tr_node(item)
                if res is not None:
                    any_tr = True
                    out.append(res)
                else:
                    out.append({})  # пустой оверлей = no-op merge, индекс цел
            elif isinstance(item, list):
                res = _tr_node(item)
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


def overlay_config_en(cfg: dict) -> None:
    """Добавить/дополнить ``cfg["i18n"]["en"]`` сгенерированным EN-оверлеем
    site_config. Изменяет ``cfg`` на месте. Существующий ручной оверлей (pranasy)
    имеет приоритет — генерённый лишь заполняет пробелы."""
    if not isinstance(cfg, dict):
        return
    source = {k: cfg.get(k) for k in _TRANSLATABLE_CONFIG_KEYS if k in cfg}
    generated = _tr_node(source) or {}
    i18n = dict(cfg.get("i18n") or {})
    existing_en = i18n.get("en") if isinstance(i18n.get("en"), dict) else {}
    merged = _deep_merge_prefer_b(generated, existing_en)
    if merged:
        i18n["en"] = merged
        cfg["i18n"] = i18n


# --- модельный контент -----------------------------------------------------


def _fill_full(obj, field: str) -> bool:
    """Full-JSON поле (Product/Category ``name``/``description`` = ``{de,en}``):
    добавить ``en``, если его нет и перевод найден."""
    val = getattr(obj, field, None)
    if isinstance(val, dict):
        de = val.get("de")
        if de and not val.get("en"):
            en = t(de)
            if en:
                val["en"] = en
                return True
    return False


def _fill_overlay(obj, base_field: str, overlay_field: str) -> bool:
    """Flat+overlay (Service/StayUnit/Combo/Event/Collection): база — плоское
    поле (de), перевод — в ``*_i18n["en"]``. Добавить ``en``, если его нет."""
    de = getattr(obj, base_field, "") or ""
    ov = getattr(obj, overlay_field, None)
    ov = dict(ov) if isinstance(ov, dict) else {}
    if de and not ov.get("en"):
        en = t(de)
        if en:
            ov["en"] = en
            setattr(obj, overlay_field, ov)
            return True
    return False


def translate_tenant_content(tenant) -> None:
    """Проставить EN-переводы на весь демо-контент тенанта (вызывать В СХЕМЕ
    тенанта, после сидинга). Идемпотентно: существующий ``en`` не трогаем.

    Тенант демо свежий/пересоздаётся сидером → безопасно обходить все объекты.
    """
    from apps.booking.models import Service
    from apps.catalog.models import Category, Combo, Product
    from apps.events.models import Event
    from apps.stays.models import StayUnit

    for prod in Product.objects.all():
        changed = _fill_full(prod, "name") | _fill_full(prod, "description")
        if changed:
            prod.save(update_fields=["name", "description"])

    for cat in Category.objects.all():
        if _fill_full(cat, "name"):
            cat.save(update_fields=["name"])

    for svc in Service.objects.all():
        changed = _fill_overlay(svc, "name", "name_i18n") | _fill_overlay(
            svc, "description", "description_i18n"
        )
        if changed:
            svc.save(update_fields=["name_i18n", "description_i18n"])

    for unit in StayUnit.objects.all():
        changed = _fill_overlay(unit, "name", "name_i18n") | _fill_overlay(
            unit, "description", "description_i18n"
        )
        if changed:
            unit.save(update_fields=["name_i18n", "description_i18n"])

    for combo in Combo.objects.all():
        changed = _fill_overlay(combo, "name", "name_i18n") | _fill_overlay(
            combo, "description", "description_i18n"
        )
        if changed:
            combo.save(update_fields=["name_i18n", "description_i18n"])

    for ev in Event.objects.all():
        changed = _fill_overlay(ev, "title", "title_i18n") | _fill_overlay(
            ev, "description", "description_i18n"
        )
        if changed:
            ev.save(update_fields=["title_i18n", "description_i18n"])

    # Collection — TENANT-апп, но может быть отключён в тест-настройках; мягкий импорт.
    try:
        from apps.collections.models import Collection
    except ImportError:
        return
    for coll in Collection.objects.all():
        if _fill_overlay(coll, "name", "name_i18n"):
            coll.save(update_fields=["name_i18n"])
