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

from apps.core import i18n_json

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
    # Аудит 2026-08-06 (стенд): переводы полосы преимуществ и ролей команды
    # ЛЕЖАЛИ в словарях, но не доезжали до витрины — ключей не было в обходе
    # (тот же класс, что с акциями в HF-волне). В конфиге полоса называется
    # `usp_bar` (у кита поле `usp`) — ключ берём КОНФИГА, иначе обход промахнётся.
    # Имена людей не переводим: их в словарях нет, `t()` вернёт None и строка
    # останется как есть.
    "usp_bar",
    "team",
    # Аудит переводов демо 2026-08-13: ещё два ключа с немецким текстом, которые
    # обход пропускал. `anfrage` — виды мероприятия формы заявки (AF-1); ПОКАЗ
    # локализуется, а value <option> остаётся немецким (тег `anfrage_event_choices`
    # в siteui) — иначе POST не прошёл бы валидацию по базовому списку.
    # `before_after` — подписи кейсов «Vorher/Nachher» (ключи фото — URL, в словаре
    # их нет, `t()` вернёт None и они останутся как есть).
    "anfrage",
    "before_after",
)

# Аудит 2026-08-13: C-блоки (UC6/GK-15) живут внутри `sections` (главная) и
# `page_blocks` (прочие страницы). Гонять по ним общий `_tr_node` нельзя: там
# лежат служебные токены (ключ блока, стиль, выравнивание), и совпадение такого
# токена со словарной записью молча сломало бы структуру. Поэтому обходим ТОЛЬКО
# поля данных, которые санитайзер `_clean_cblock_data` объявляет текстовыми.
_CBLOCK_TEXT_FIELDS = ("title", "body", "caption", "label", "button_label")
# Списки внутри данных блока: ключ → переводимые поля элемента. `value` у stats
# обычно число («200+»), но бывает и текстом («seit 2012») — берём его тоже:
# перевод подставляется ТОЛЬКО при точном совпадении со словарной записью,
# поэтому числа остаются числами. URL/иконки не трогаем.
_CBLOCK_LIST_FIELDS = {"rows": ("label", "value"), "items": ("title", "text", "label")}


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


def _tr_cblock_data(data, locale: str):
    """Оверлей ДАННЫХ одного C-блока: только текстовые поля (см. `_CBLOCK_TEXT_FIELDS`
    и `_CBLOCK_LIST_FIELDS`). ``None`` — переводить нечего."""
    if not isinstance(data, dict):
        return None
    out = {}
    for field in _CBLOCK_TEXT_FIELDS:
        tr = t(data.get(field), locale) if isinstance(data.get(field), str) else None
        if tr:
            out[field] = tr
    for field, item_keys in _CBLOCK_LIST_FIELDS.items():
        rows = data.get(field)
        if not isinstance(rows, list):
            continue
        tr_rows, any_tr = [], False
        for row in rows:
            row_ov = {}
            if isinstance(row, dict):
                for key in item_keys:
                    tr = t(row.get(key), locale) if isinstance(row.get(key), str) else None
                    if tr:
                        row_ov[key] = tr
            tr_rows.append(row_ov)  # {} = no-op merge, индекс строки цел
            any_tr = any_tr or bool(row_ov)
        if any_tr:
            out[field] = tr_rows
    return out or None


def _tr_blocks(rows, locale: str):
    """Оверлей СПИСКА блоков/секций: позиционный, у каждого — только `data`."""
    if not isinstance(rows, list):
        return None
    out, any_tr = [], False
    for row in rows:
        row_ov = {}
        if isinstance(row, dict):
            data_ov = _tr_cblock_data(row.get("data"), locale)
            if data_ov:
                row_ov["data"] = data_ov
        out.append(row_ov)
        any_tr = any_tr or bool(row_ov)
    return out if any_tr else None


def _tr_page_blocks(page_blocks, locale: str):
    """Оверлей `page_blocks` ({хост: [блок, …]}) — теми же правилами, что секции."""
    if not isinstance(page_blocks, dict):
        return None
    out = {}
    for host, rows in page_blocks.items():
        blocks_ov = _tr_blocks(rows, locale)
        if blocks_ov:
            out[host] = blocks_ov
    return out or None


def overlay_config(cfg: dict, locales) -> None:
    """Добавить/дополнить ``cfg["i18n"][loc]`` сгенерированным оверлеем site_config
    для каждой локали из ``locales``. Изменяет ``cfg`` на месте. Существующий ручной
    оверлей (pranasy) имеет приоритет — генерённый лишь заполняет пробелы."""
    if not isinstance(cfg, dict):
        return
    source = {k: cfg.get(k) for k in _TRANSLATABLE_CONFIG_KEYS if k in cfg}
    i18n = dict(cfg.get("i18n") or {})
    # C-блоки оверлеятся ПОЗИЦИОННО (`_deep_overlay` мерджит списки по индексу), а
    # витрина рендерит НОРМАЛИЗОВАННЫЙ конфиг: `normalize_sections` дедупит фикс-секции,
    # дописывает недостающие в конец и режет длинные строки. Поэтому индексы и значения
    # для словаря берём из нормализованной формы — иначе перевод сел бы не на тот блок.
    from . import siteconfig

    norm_sections = siteconfig.normalize_sections(cfg.get("sections"))
    norm_pages = siteconfig.normalize_page_blocks(cfg.get("page_blocks"))
    for loc in locales:
        generated = _tr_node(source, loc) or {}
        blocks_ov = _tr_blocks(norm_sections, loc)
        if blocks_ov:
            generated["sections"] = blocks_ov
        pages_ov = _tr_page_blocks(norm_pages, loc)
        if pages_ov:
            generated["page_blocks"] = pages_ov
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


def _fill_seq_overlay(obj, base_list, overlay_field, locales, keys=None) -> bool:
    """Списочный overlay (`Service.attributes`/`faq`): перевод ЭЛЕМЕНТОВ базового
    списка с выравниванием по индексу. `base_list` — уже нормализованный список
    (тот же, что уходит в рендер), иначе строки разъедутся; `keys` — переводимые
    ключи для списка словарей (FAQ: q/a), None — список строк."""
    if not base_list:
        return False
    ov = getattr(obj, overlay_field, None)
    ov = dict(ov) if isinstance(ov, dict) else {}
    changed = False
    for loc in locales:
        if ov.get(loc):
            continue  # перевод локали уже есть — идемпотентность
        items = []
        got = False
        for item in base_list:
            if keys is None:
                tr = t(item, loc) if isinstance(item, str) else ""
                items.append(tr)
                got = got or bool(tr)
                continue
            row = {}
            for k in keys:
                tr = t(str(item.get(k, "") or ""), loc) if isinstance(item, dict) else ""
                if tr:
                    row[k] = tr
                    got = True
            items.append(row)
        if got:
            ov[loc] = items
            changed = True
    if changed:
        setattr(obj, overlay_field, ov)
    return changed


def _base_landing(event) -> dict:
    """Нормализованный ретрит-лендинг БЕЗ перевода — база для оверлея (I18N-12)."""
    from apps.events import details as details_mod

    return details_mod.normalize(event.details)


def _fill_json_overlay(obj, base, overlay_field: str, locales) -> bool:
    """Оверлей вложенного JSON (`core.i18n_json`): та же форма, переведены листья."""
    if not base:
        return False
    ov = getattr(obj, overlay_field, None)
    ov = dict(ov) if isinstance(ov, dict) else {}
    changed = False
    for loc in locales:
        if ov.get(loc):
            continue  # идемпотентность: перевод локали уже есть
        built = i18n_json.build_overlay(base, lambda s, loc=loc: t(s, loc))
        if built:
            ov[loc] = built
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
    from apps.catalog.models import (
        Category,
        Combo,
        ModifierGroup,
        ModifierOption,
        Product,
        ProductVariant,
    )
    from apps.events.models import BlogPost, Event, Teacher
    from apps.stays.models import RatePlan, StaySettings, StayUnit

    for prod in Product.objects.all():
        changed = _fill_full(prod, "name", locales) | _fill_full(prod, "description", locales)
        if changed:
            prod.save(update_fields=["name", "description"])
        # I18N-10: характеристики товара — overlay-поля (Herkunft/Zutaten с Ф2,
        # Material/Pflegehinweise с M1 Boutique). Витрина их показывает, но обход
        # их не заполнял → на не-немецкой витрине они оставались немецкими.
        char_changed = [
            f
            for f in ("origin", "ingredients", "material", "care")
            if _fill_overlay(prod, f, f"{f}_i18n", locales)
        ]
        if char_changed:
            prod.save(update_fields=[f"{f}_i18n" for f in char_changed])

    for cat in Category.objects.all():
        cat_fields = ["name"] if _fill_full(cat, "name", locales) else []
        # Аудит 2026-08-13: описание направления (DS-7a) — единственный текст
        # лендинга `/bereich/<slug>/`; поле полноценно i18n, но обход его не брал.
        if _fill_full(cat, "description", locales):
            cat_fields.append("description")
        # I18N-10: Größentabelle («Größe | Brust») — показная таблица.
        if _fill_overlay(cat, "size_table", "size_table_i18n", locales):
            cat_fields.append("size_table_i18n")
        if cat_fields:
            cat.save(update_fields=cat_fields)

    # I18N-10: метки вариантов и модификаторов («Klein», «Teig», «Pommes»).
    # Плоские поля — ключи учёта (склад/заказ/импорт), переводим только показ.
    for var in ProductVariant.objects.all():
        var_fields = [
            f"{f}_i18n"
            for f in ("label", "size", "color")
            if _fill_overlay(var, f, f"{f}_i18n", locales)
        ]
        if var_fields:
            var.save(update_fields=var_fields)

    for grp in ModifierGroup.objects.all():
        if _fill_overlay(grp, "name", "name_i18n", locales):
            grp.save(update_fields=["name_i18n"])

    for opt in ModifierOption.objects.all():
        if _fill_overlay(opt, "label", "label_i18n", locales):
            opt.save(update_fields=["label_i18n"])

    for svc in Service.objects.all():
        changed = _fill_overlay(svc, "name", "name_i18n", locales) | _fill_overlay(
            svc, "description", "description_i18n", locales
        )
        # Богатая карточка услуги (UA4-3): пункты «Details» и FAQ — списки, поэтому
        # переводятся поэлементно (иначе на не-немецкой витрине оставались немецкими).
        changed |= _fill_seq_overlay(svc, svc.attributes_list, "attributes_i18n", locales)
        changed |= _fill_seq_overlay(svc, svc.faq_list, "faq_i18n", locales, keys=("q", "a"))
        if changed:
            svc.save(
                update_fields=[
                    "name_i18n",
                    "description_i18n",
                    "attributes_i18n",
                    "faq_i18n",
                ]
            )

    # Фидбэк владельца 2026-07-31: акции демо оставались немецкими на любой
    # локали — их просто не было в этом обходе. Поля те же full-JSON, что у товара.
    from apps.promotions.models import Promotion

    for promo in Promotion.objects.all():
        changed = _fill_full(promo, "title", locales) | _fill_full(promo, "description", locales)
        # Метка группы («Wochenangebote», «Räumung») — заголовок секции на /aktionen/;
        # ключ фасета остаётся плоским, переводится только показ.
        changed |= _fill_overlay(promo, "group", "group_i18n", locales)
        if changed:
            promo.save(update_fields=["title", "description", "group_i18n"])

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
        # I18N-12: ретрит-лендинг (вложенный JSON), программа и анкета. Оверлей
        # строится по НОРМАЛИЗОВАННОЙ форме (`ev.landing` без перевода = база),
        # иначе позиционный merge разъедется.
        changed |= _fill_json_overlay(ev, _base_landing(ev), "details_i18n", locales)
        changed |= _fill_seq_overlay(ev, list(ev.program or []), "program_i18n", locales)
        changed |= _fill_seq_overlay(ev, list(ev.questions or []), "questions_i18n", locales)
        if changed:
            ev.save(
                update_fields=[
                    "title_i18n",
                    "description_i18n",
                    "details_i18n",
                    "program_i18n",
                    "questions_i18n",
                ]
            )

    for teacher in Teacher.objects.all():
        fields = [
            f"{f}_i18n" for f in ("title", "bio") if _fill_overlay(teacher, f, f"{f}_i18n", locales)
        ]
        if fields:
            teacher.save(update_fields=fields)

    for post in BlogPost.objects.all():
        fields = [
            f"{f}_i18n"
            for f in ("title", "excerpt", "body")
            if _fill_overlay(post, f, f"{f}_i18n", locales)
        ]
        if fields:
            post.save(update_fields=fields)

    for rp in RatePlan.objects.all():
        changed = _fill_overlay(rp, "name", "name_i18n", locales) | _fill_overlay(
            rp, "description", "description_i18n", locales
        )
        if changed:
            rp.save(update_fields=["name_i18n", "description_i18n"])

    # Hausordnung (StaySettings — синглтон): перевод свободного текста.
    settings_obj = StaySettings.objects.first()
    if settings_obj and _fill_overlay(settings_obj, "house_rules", "house_rules_i18n", locales):
        settings_obj.save(update_fields=["house_rules_i18n"])

    _translate_side_models(locales)

    # Показные тексты САМОГО бизнеса (часы работы строкой, заметка о зоне выезда):
    # поля живут на Tenant (SHARED), поэтому идут не общим циклом моделей, а здесь.
    tenant_fields = [
        f"{f}_i18n"
        for f in ("opening_hours", "service_area_note")
        if _fill_overlay(tenant, f, f"{f}_i18n", locales)
    ]
    if tenant_fields:
        tenant.save(update_fields=tenant_fields)

    # Collection — TENANT-апп, но может быть отключён в тест-настройках; мягкий импорт.
    try:
        from apps.collections.models import Collection
    except ImportError:
        return
    for coll in Collection.objects.all():
        if _fill_overlay(coll, "name", "name_i18n", locales):
            coll.save(update_fields=["name_i18n"])


def _translate_side_models(locales) -> None:
    """I18N-12: остальной демо-контент, у которого до аудита 2026-08-13 не было
    i18n-полей вовсе — мастера/ресурсы, абонементы, Extras, лояльность, ваучеры,
    шаги набора, отзывы, заявки-сметы кабинета.

    Отзывы и заявки — записи КЛИЕНТОВ: их «перевод» допустим только потому, что
    заполняет его демо-сидер по своему же словарю. У живого тенанта оверлей
    остаётся пустым, и витрина показывает подлинный текст гостя.
    """
    from apps.booking.models import PassPlan, Resource
    from apps.catalog.models import ComboGroup
    from apps.core.models import Extra
    from apps.jobs.models import Job, JobLine
    from apps.loyalty.models import LoyaltyProgram, Voucher
    from apps.reviews.models import Review

    simple = (
        (Resource, ("name", "title", "bio")),
        (PassPlan, ("label",)),
        (Extra, ("label",)),
        (ComboGroup, ("label",)),
        (Voucher, ("label",)),
        (Review, ("comment",)),
        (Job, ("title", "description")),
        (JobLine, ("text",)),
    )
    for model, fields in simple:
        for obj in model.objects.all():
            touched = [f"{f}_i18n" for f in fields if _fill_overlay(obj, f, f"{f}_i18n", locales)]
            if touched:
                obj.save(update_fields=touched)

    for prog in LoyaltyProgram.objects.all():
        touched = [
            f"{f}_i18n"
            for f in ("label", "reward_label")
            if _fill_overlay(prog, f, f"{f}_i18n", locales)
        ]
        if touched:
            prog.save(update_fields=touched)

    # Портальные отзывы о бизнесе живут в SHARED-таблице, поэтому фильтруем по
    # схеме тенанта (стенд поймал: без этого прохода оверлей оставался пустым и
    # секция отзывов демо была немецкой на любой локали).
    from django.db import connection

    from apps.aggregator.models import BusinessReview

    for review in BusinessReview.objects.filter(tenant_schema=connection.schema_name):
        if _fill_overlay(review, "comment", "comment_i18n", locales):
            review.save(update_fields=["comment_i18n"])
