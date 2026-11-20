"""FB-33 M2b-2b: свои вопросы FAQ у объекта (услуга, товар, номер, событие, тур).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3» (M2b-2b), решения владельца
(2026-11-20): свои вопросы — у всех пяти видов; лимиты по виду (12/200/1000 у услуги, товара
и номера, 30/200/2000 у события и тура); FAQPage — одна на страницу и только из блока
`faq_ref` с `data.source == "object"`; старые разделы «faq» услуги и события — как были.

Где лежат вопросы (`KINDS`): у услуги, товара и номера — поля `faq` / `faq_i18n`
(переводы `{язык: [{q?, a?}]}` по позиции); у события и тура — `details["faq"]` и
`details_i18n[язык]["faq"]` (прочие ключи `details` писатель не трогает).

ЕДИНСТВЕННЫЙ писатель своих вопросов — `put` (формы услуги, товара, номера, события и тура,
окно блока «Seitenaufbau» при «Speichern»); исключения — демо-киты (замок
`test_fb33_m2b2b_object_faq::test_one_writer_of_object_faq`). Переводы едут за вопросом тем же
разбором, что у общего FAQ (`faq_content.mapping` / `remap_overlay`): по индексу источника,
правка немецкого снимает перевод именно этого поля.

Модели — только ленивым импортом (`apps.core` не импортирует приложения при загрузке).
"""

from __future__ import annotations

import copy
import logging
from typing import NamedTuple

from django.utils.translation import gettext_lazy as _

from apps.core import faq_content

logger = logging.getLogger(__name__)

FIELDS = faq_content.FIELDS


class Kind(NamedTuple):
    key: str
    model: str  # «app_label.Модель» — ленивый `apps.get_model`
    details: bool  # вопросы в `details["faq"]` (событие, тур), иначе поле `faq`
    max_items: int
    max_q: int
    max_a: int
    ctx: str  # имя объекта в контексте детальной страницы витрины
    shared_host: str  # общий хост детали (`detail_parts.OBJECT_SHARED`)
    own_hint: object  # «eigene Liste dieser …» (макет M0-12)
    each_hint: object  # на общем хосте: «Jede … zeigt ihre eigenen Fragen»
    edit_url: str  # форма объекта в кабинете


KINDS: dict[str, Kind] = {
    "service": Kind(
        "service",
        "booking.Service",
        False,
        12,
        200,
        1000,
        "service",
        "service_detail",
        _("eigene Liste dieser Leistung"),
        _("Jede Leistung zeigt ihre eigenen Fragen."),
        "booking:service-edit",
    ),
    "product": Kind(
        "product",
        "catalog.Product",
        False,
        12,
        200,
        1000,
        "product",
        "product_detail",
        _("eigene Liste dieses Produkts"),
        _("Jedes Produkt zeigt seine eigenen Fragen."),
        "catalog:product-edit",
    ),
    "stay": Kind(
        "stay",
        "stays.StayUnit",
        False,
        12,
        200,
        1000,
        "unit",
        "stay_detail",
        _("eigene Liste dieser Unterkunft"),
        _("Jede Unterkunft zeigt ihre eigenen Fragen."),
        "stays:unit-edit",
    ),
    "event": Kind(
        "event",
        "events.Event",
        True,
        30,
        2000,  # ревью M2b-2b: как хранилось раньше (вопрос события до 2000 знаков)
        2000,
        "event",
        "event_detail",
        _("eigene Liste dieser Veranstaltung"),
        _("Jede Veranstaltung zeigt ihre eigenen Fragen."),
        "events:edit",
    ),
    "tour": Kind(
        "tour",
        "events.Tour",
        True,
        30,
        2000,  # ревью M2b-2b: как хранилось раньше (вопрос события до 2000 знаков)
        2000,
        "tour",
        "event_detail",
        _("eigene Liste dieser Tour"),
        _("Jede Tour zeigt ihre eigenen Fragen."),
        "events:tour-edit",
    ),
}
#: значение `data.source` блока `faq_ref`: свои вопросы объекта страницы (нет ключа — общие)
SOURCE_OBJECT = "object"
#: превью черновика «Seitenaufbau»: {hex объекта: {"items", "i18n"}} — служебный ключ конфига
#: превью (как `object_structure.DRAFT_KEY`; `normalize` его не хранит, на сайт не попадает)
DRAFT_KEY = "_object_faq"


def model(kind: str):
    from django.apps import apps

    return apps.get_model(KINDS[kind].model)


def kind_of(obj) -> str:
    """Вид объекта по его модели ("" — не объект со своими вопросами)."""
    for key in KINDS:
        try:
            if isinstance(obj, model(key)):
                return key
        except LookupError:
            continue
    return ""


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_with_positions(raw) -> tuple[list[dict], list[int]]:
    out, positions = [], []
    for pos, item in enumerate(raw if isinstance(raw, (list, tuple)) else ()):
        if isinstance(item, dict):
            q, a = _s(item.get("q")), _s(item.get("a"))
        elif isinstance(item, str):
            q, _sep, a = item.partition("|")
            q, a = q.strip(), a.strip()
        else:
            continue
        if q:
            out.append({"q": q, "a": a})
            positions.append(pos)
    return out, positions


def clean_items(raw) -> list[dict]:
    """Сохранённые вопросы → [{q, a}] (пустой вопрос — вопроса нет; строка «Frage | Antwort»
    старых данных события — по ПЕРВОМУ «|»). Сохранённое не режется."""
    return _clean_with_positions(raw)[0]


def _raw(obj, kind: str):
    if KINDS[kind].details:
        details = getattr(obj, "details", None)
        return (details if isinstance(details, dict) else {}).get("faq")
    return getattr(obj, "faq", None)


def items(obj, kind: str) -> list[dict]:
    """Сохранённые свои вопросы объекта [{q, a}]."""
    return clean_items(_raw(obj, kind))


def overlays(obj, kind: str) -> dict:
    """Переводы своих вопросов {язык: [{q?, a?}]} по позициям `items` (ревью M2b-2b: сырые
    записи без вопроса `items` отбрасывает — переводы выравниваются по сырым позициям, иначе
    съехали бы на соседний вопрос)."""
    if KINDS[kind].details:
        raw = getattr(obj, "details_i18n", None)
        raw = raw if isinstance(raw, dict) else {}
        stored = {
            loc: node["faq"]
            for loc, node in raw.items()
            if isinstance(node, dict) and isinstance(node.get("faq"), list)
        }
    else:
        raw = getattr(obj, "faq_i18n", None)
        raw = raw if isinstance(raw, dict) else {}
        stored = {k: v for k, v in raw.items() if isinstance(v, list)}
    _rows, positions = _clean_with_positions(_raw(obj, kind))
    if positions == list(range(len(positions))):
        return stored  # сырые записи без пропусков — позиции совпадают
    return {loc: [tr[p] if p < len(tr) else {} for p in positions] for loc, tr in stored.items()}


def fingerprint(obj_or_items, kind: str = "") -> str:
    """Отпечаток списка своих вопросов (объект + вид или готовый список)."""
    rows = items(obj_or_items, kind) if kind else obj_or_items
    return faq_content.fingerprint(rows)


def limit_note(kind: str) -> str:
    k = KINDS[kind]
    return _("Zu lange Fragen oder Antworten wurden gekürzt (höchstens %(q)s / %(a)s Zeichen).") % {
        "q": k.max_q,
        "a": k.max_a,
    }


def full_note(kind: str) -> str:
    return _("Höchstens %(n)s Fragen — weitere wurden nicht übernommen.") % {
        "n": KINDS[kind].max_items
    }


def clean_input(rows, kind: str, notes: list | None = None) -> tuple[list[dict], list]:
    """Ввод владельца → ([{q, a}], src) с лимитами вида (режутся с сообщением). `rows` —
    [{q, a, src}] (src — индекс источника или None)."""
    k = KINDS[kind]
    out, src, cut, over = [], [], False, False
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        q, a = _s(row.get("q")), _s(row.get("a"))
        if not q:
            continue
        if len(out) >= k.max_items:
            over = True
            break
        if len(q) > k.max_q or len(a) > k.max_a:
            cut = True
            q, a = q[: k.max_q], a[: k.max_a]
        out.append({"q": q, "a": a})
        s = row.get("src")
        src.append(s if isinstance(s, int) and not isinstance(s, bool) and s >= 0 else None)
    if notes is not None:
        if cut:
            notes.append(limit_note(kind))
        if over:
            notes.append(full_note(kind))
    return out, src


def remapped(old: list[dict], old_overlays: dict, new: list[dict], src=None, by_text=False):
    """Переводы после правки `old` → `new`: {язык: список} (пустые языки — без ключа)."""
    mapping = faq_content.mapping(old, new, src, by_text)
    out = {}
    for loc, tr in (old_overlays or {}).items():
        moved = faq_content.remap_overlay(old, new, mapping, tr)
        if moved:
            out[loc] = moved
    return out


def put(
    obj,
    kind: str,
    new_items,
    src=None,
    base_fp: str | None = None,
    per_locale: dict | None = None,
    tenant=None,
) -> list[str]:
    """ЕДИНСТВЕННЫЙ писатель своих вопросов объекта (без `save`): база и переводы.

    `src[j]` — индекс вопроса j в СОХРАНЁННОМ списке (None — новый); `base_fp` — отпечаток
    списка, от которого считаны индексы: не совпал (или `src` нет) — переводы по тексту
    вопроса. `per_locale` — переводы, введённые в форме объекта явно ({язык: список}, по
    новым позициям; языки вне формы не трогаются) — тогда сопоставления нет. Возвращает
    изменённые поля модели (для `update_fields`)."""
    k = KINDS[kind]
    old = items(obj, kind)
    new = clean_items(new_items)
    by_text = base_fp is not None and base_fp != faq_content.fingerprint(old)
    if by_text:
        from django.db import connection

        logger.warning(
            "object_faq: questions changed meanwhile — translations matched by text "
            "(%s, %s %s, saved %s, written %s)",
            getattr(connection, "schema_name", ""),
            kind,
            getattr(obj, "pk", ""),
            len(old),
            len(new),
        )
    changed: list[str] = []
    if per_locale is not None and k.details:
        _put_base(obj, kind, new, changed)
        if _put_details_overlays(obj, per_locale, tenant):
            changed.append("details_i18n")
        return changed
    if per_locale is not None:
        _put_base(obj, kind, new, changed)
        from apps.core.i18n_input import apply_seq_overlay

        if apply_seq_overlay(obj, "faq_i18n", per_locale, tenant):
            changed.append("faq_i18n")
        return changed
    moved = remapped(old, overlays(obj, kind), new, src, by_text)
    _put_base(obj, kind, new, changed)
    if k.details:
        raw = getattr(obj, "details_i18n", None)
        before = raw if isinstance(raw, dict) else {}
        after = copy.deepcopy(before)
        for loc in list(after):
            node = after[loc]
            if not isinstance(node, dict) or "faq" not in node:
                continue
            if loc in moved:
                node["faq"] = moved[loc]
            else:
                node.pop("faq")
        if after != before:
            obj.details_i18n = after
            changed.append("details_i18n")
        return changed
    raw = getattr(obj, "faq_i18n", None)
    before = raw if isinstance(raw, dict) else {}
    after = {loc: v for loc, v in before.items() if not isinstance(v, list)}
    after.update(moved)
    if after != before:
        obj.faq_i18n = after
        changed.append("faq_i18n")
    return changed


def _put_details_overlays(obj, per_locale: dict, tenant) -> bool:
    """Явные переводы формы события/тура → `details_i18n[язык]["faq"]` (языки вне формы — как
    были; пустой список снимает ключ). Прочие ключи перевода `details` — как были."""
    from apps.core.i18n_input import extra_locales

    raw = getattr(obj, "details_i18n", None)
    before = raw if isinstance(raw, dict) else {}
    after = copy.deepcopy(before)
    for loc in extra_locales(tenant):
        if loc not in per_locale:
            continue
        node = dict(after.get(loc)) if isinstance(after.get(loc), dict) else {}
        if per_locale[loc]:
            node["faq"] = per_locale[loc]
        else:
            node.pop("faq", None)
        if node:
            after[loc] = node
        else:
            after.pop(loc, None)
    if after == before:
        return False
    obj.details_i18n = after
    return True


def _put_base(obj, kind: str, new: list[dict], changed: list[str]) -> None:
    if KINDS[kind].details:
        details = dict(obj.details) if isinstance(obj.details, dict) else {}
        if details.get("faq") != new:
            details["faq"] = new  # прочие ключи `details` — как были
            obj.details = details
            changed.append("details")
        return
    if obj.faq != new:
        obj.faq = new
        changed.append("faq")


# ───────────── формы объекта в кабинете (услуга, товар, номер) ─────────────


def form_rows(obj, kind: str, locales) -> list[dict]:
    """Строки редактора формы объекта: существующие пары + одна пустая (слоты дорастают
    после Save, без JS) — с полями переводов по языкам бизнеса."""
    base = items(obj, kind) if obj is not None else []
    overlay = overlays(obj, kind) if obj is not None else {}
    rows = []
    for i, item in enumerate(base + [{"q": "", "a": ""}]):
        tr = []
        for loc in locales:
            seq = overlay.get(loc)
            src = seq[i] if isinstance(seq, list) and i < len(seq) else {}
            src = src if isinstance(src, dict) else {}
            tr.append(
                {
                    "locale": loc,
                    "q_name": f"faq_q_{i}_{loc}",
                    "a_name": f"faq_a_{i}_{loc}",
                    "q": src.get("q", ""),
                    "a": src.get("a", ""),
                }
            )
        rows.append(
            {
                "q_name": f"faq_q_{i}",
                "a_name": f"faq_a_{i}",
                "q": item.get("q", ""),
                "a": item.get("a", ""),
                "i18n": tr,
            }
        )
    return rows


def from_form(
    post, locales, kind: str, notes: list | None = None, keep: int = 0
) -> tuple[list[dict], dict] | None:
    """Пары `faq_q_<i>`/`faq_a_<i>` (+ `_<язык>`) формы объекта → (база, {язык: список}).
    Без сентинела `faq_present` — None (компактная строка списка не стирает вопросы, W0).

    База и переводы разбираются ОДНИМ проходом: пара без вопроса отбрасывается (очистка
    вопроса = удаление), и вместе с ней — её перевод (иначе переводы ниже съехали бы).
    Лимиты вида — на вводе, с сообщением в `notes` (ревью M2b-2b); `keep` — сколько вопросов
    уже сохранено: сохранённые сверх лимита (данные до среза) без явного удаления не теряются."""
    if not _s(post.get("faq_present", "")):
        return None
    k = KINDS[kind]
    cap = max(k.max_items, keep)
    base, per_locale = [], {loc: [] for loc in locales}
    cut = over = False
    i = 0
    while True:
        q, a = post.get(f"faq_q_{i}"), post.get(f"faq_a_{i}")
        if q is None and a is None:
            break
        q, a = _s(q), _s(a)
        if q and len(base) >= cap:
            over = True
        elif q:
            cut = cut or len(q) > k.max_q or len(a) > k.max_a
            base.append({"q": q[: k.max_q], "a": a[: k.max_a]})
            for loc in locales:
                tq = _s(post.get(f"faq_q_{i}_{loc}"))[: k.max_q]
                ta = _s(post.get(f"faq_a_{i}_{loc}"))[: k.max_a]
                per_locale[loc].append({f: v for f, v in (("q", tq), ("a", ta)) if v})
        i += 1
    for loc in locales:  # хвост пустых переводов не несёт информации
        while per_locale[loc] and not per_locale[loc][-1]:
            per_locale[loc].pop()
    if notes is not None:
        if cut:
            notes.append(limit_note(kind))
        if over:
            notes.append(full_note(kind))
    return base, per_locale


def lock_fresh(obj, kind: str) -> None:
    """Перед полной записью объекта формой (`ModelForm.save` пишет все столбцы) — свежие свои
    вопросы под блокировкой строки (ревью M2b-2b: иначе форма, открытая до чужой правки,
    вернула бы старые вопросы). Звать внутри `transaction.atomic`; нового объекта — нет."""
    if getattr(getattr(obj, "_state", None), "adding", True) or obj.pk is None:
        return
    locked = type(obj).objects.select_for_update().filter(pk=obj.pk).first()
    if locked is not None:
        _sync(obj, locked, kind)


def _sync(obj, fresh, kind: str) -> None:
    """Свои вопросы (база и переводы) объекта `obj` — как у `fresh` (прочее не трогается)."""
    if KINDS[kind].details:
        details = dict(obj.details) if isinstance(obj.details, dict) else {}
        fresh_details = fresh.details if isinstance(fresh.details, dict) else {}
        if "faq" in fresh_details:
            details["faq"] = fresh_details["faq"]
        else:
            details.pop("faq", None)
        obj.details = details
        obj.details_i18n = copy.deepcopy(fresh.details_i18n)
        return
    obj.faq = copy.deepcopy(fresh.faq)
    obj.faq_i18n = copy.deepcopy(fresh.faq_i18n)


def save_from_form(obj, kind: str, post, tenant=None, notes: list | None = None) -> list[str]:
    """Форма объекта в кабинете → свои вопросы (по сентинелу `faq_present`, W0): под
    блокировкой строки и со сверкой отпечатка `faq_base` формы (ревью M2b-2b: форма и окно,
    два сотрудника). Не совпал — вопросы не пишутся, сообщение в `notes`; прочие поля формы —
    дело вызывающего. Записывает сам (`update_fields`); `obj` получает записанное."""
    from django.db import transaction

    from apps.core.i18n_input import extra_locales

    if not _s(post.get("faq_present", "")) or obj.pk is None:
        return []
    with transaction.atomic():
        locked = type(obj).objects.select_for_update().filter(pk=obj.pk).first()
        if locked is None:
            return []
        base = post.get("faq_base")
        if base is not None and base != fingerprint(locked, kind):
            if notes is not None:
                notes.append(form_changed_note())
            _sync(obj, locked, kind)
            return []
        parsed = from_form(post, extra_locales(tenant), kind, notes, keep=len(items(locked, kind)))
        fields = put(locked, kind, parsed[0], per_locale=parsed[1], tenant=tenant)
        if fields:
            if any(f.name == "updated_at" for f in locked._meta.concrete_fields):
                fields.append("updated_at")
            locked.save(update_fields=fields)
        _sync(obj, locked, kind)
    return fields


def form_ctx(obj, kind: str, tenant) -> dict:
    """Контекст общего редактора формы объекта (`tenant/_object_faq_fields.html`)."""
    from apps.core.i18n_input import extra_locales

    return {
        "faq_rows": form_rows(obj, kind, extra_locales(tenant)),
        "faq_base": fingerprint(obj, kind) if obj is not None else "",
    }


def form_changed_note() -> str:
    return _(
        "Die Fragen wurden inzwischen woanders geändert – Ihre Änderungen an den Fragen wurden "
        "nicht gespeichert. Bitte die Seite neu laden und noch einmal eintragen."
    )


# ───────────── витрина ─────────────


def localized(obj, kind: str, locale: str | None = None, config=None) -> list[dict]:
    """Свои вопросы объекта на языке витрины (перевод поэлементно, иначе база). В превью
    черновика «Seitenaufbau» — его вопросы (`DRAFT_KEY` в конфиге превью)."""
    from apps.core.i18n_seq import overlay_seq

    cap = KINDS[kind].max_items  # ревью M2b-2b: на витрине и в FAQPage — не больше лимита вида
    entry = _draft_entry(config, obj)
    if entry is not None:
        return overlay_seq(entry["items"], entry["i18n"], locale, keys=FIELDS)[:cap]
    return overlay_seq(items(obj, kind), overlays(obj, kind), locale, keys=FIELDS)[:cap]


def _draft_entry(config, obj):
    drafts = config.get(DRAFT_KEY) if isinstance(config, dict) else None
    hexed = getattr(getattr(obj, "pk", None), "hex", "")
    entry = drafts.get(hexed) if isinstance(drafts, dict) and hexed else None
    if isinstance(entry, dict) and isinstance(entry.get("items"), list):
        return {"items": entry["items"], "i18n": entry.get("i18n") or {}}
    return None


def object_in_context(context, host: str):
    """(вид, объект) страницы, на которой рисуется блок хоста `host`, либо ("", None).
    Хост объекта (`<kind>:<hex>`) — его объект из контекста страницы (чужой hex — нет);
    общий хост детали — объект страницы (у `event_detail` — тур, иначе событие)."""
    from apps.core import detail_parts

    own = detail_parts.object_kind(host)
    shared = detail_parts.shared_host(host or "")
    candidates = [own] if own else [k for k, v in KINDS.items() if v.shared_host == shared]
    for kind in sorted(candidates, key=lambda k: k != "tour"):
        if kind not in KINDS:
            continue
        obj = context.get(KINDS[kind].ctx) if hasattr(context, "get") else None
        if obj is None or not getattr(obj, "pk", None) or kind_of(obj) != kind:
            continue
        if own and host != f"{kind}:{obj.pk.hex}":
            continue
        return kind, obj
    return "", None


def is_object_source(data) -> bool:
    return isinstance(data, dict) and data.get("source") == SOURCE_OBJECT


#: запрос: FAQPage своих вопросов уже выведена (одна на страницу — решение владельца)
_LD_FLAG = "_object_faq_ld"


def shown_for_context(context, host: str, raw=None) -> list[dict]:
    """Свои вопросы, которые блок `faq_ref(source=object)` покажет на странице `host`
    ([] — объекта нет или вопросов нет)."""
    from django.utils.translation import get_language

    kind, obj = object_in_context(context, host)
    if obj is None:
        return []
    if raw is None:
        raw = context.get("pb_raw") if hasattr(context, "get") else None
    return localized(obj, kind, get_language(), raw)


def render_block(context, row: dict, request) -> str:
    """HTML блока FAQ со своими вопросами объекта (`section_row` — вид блока)."""
    from django.template.loader import render_to_string

    faq = shown_for_context(context, context.get("pb_page_key") or "")
    ld = bool(faq) and request is not None and not getattr(request, _LD_FLAG, False)
    if ld:
        try:
            setattr(request, _LD_FLAG, True)
        except AttributeError:
            ld = False
    flat = context.flatten() if hasattr(context, "flatten") else dict(context)
    return render_to_string(
        "storefront/sections/_faq_own.html",
        {**flat, "section_row": row, "own_faq": faq, "own_ld": ld},
        request=request,
    )


def drop_empty(blocks: list, context, page_key: str, raw=None) -> list:
    """Блоки `faq_ref(source=object)` без своих вопросов на сайте не рисуются (фильтр ДО
    `group_block_rows` — ни обёртки, ни места в ряду). Прочие блоки — как есть."""
    out = []
    for b in blocks:
        if b.get("key") == "faq_ref" and is_object_source(b.get("data")):
            if not shown_for_context(context, page_key, raw):
                continue
        out.append(b)
    return out


# ───────────── окно блока «Seitenaufbau» (вкладка «Texte») ─────────────
# Решения владельца (2026-11-20): окно блока `faq_ref` на детальной выбирает источник
# («Fragen nur für <объект>» / «Allgemeine FAQ»); окно старого раздела «faq» услуги и события
# открывает ТОТ ЖЕ редактор своих вопросов (одно место правки). Править свои вопросы можно на
# хосте объекта (`<kind>:<hex>`); на общем хосте детали — подсказка и ссылки на формы.
# Черновик держит состояние правки (`ofaq` = {items, src, obj}) и отпечаток сохранённых
# вопросов объекта на первой правке (`ofaq_base`) — вне `_saved_state` (строка `SIDE_PARTS`).
DRAFT_KEYS = ("ofaq", "ofaq_base")
#: сколько ссылок на формы объектов показывает подсказка общего хоста
LINKS_MAX = 8


def _host_kind(host: str) -> str:
    """Вид своих вопросов страницы: хост объекта — его вид; общий хост детали — вид(ы) его
    объектов (у `event_detail` — событие; тур тоже на нём, ссылки — на оба)."""
    from apps.core import detail_parts

    own = detail_parts.object_kind(host)
    if own:
        return own
    return next((k for k, v in KINDS.items() if v.shared_host == host), "")


def has_section(host: str) -> bool:
    """Есть ли у страницы старый раздел «faq» (услуга, событие, тур)."""
    from apps.core import detail_parts

    return "faq" in detail_parts.section_keys(host or "")


def _detail(host: str) -> bool:
    from apps.core import faq_views

    return faq_views.is_detail_host(host)


def is_ref_row(draft: dict, item) -> bool:
    """Строка блока `faq_ref` на детальной (там у окна есть выбор источника)."""
    from apps.tenants import siteconfig

    if not isinstance(item, dict) or not item.get("id"):
        return False
    key = item.get("key") or ""
    return (siteconfig.cblock_type(key) or key) == "faq_ref" and _detail(draft.get("host") or "")


def is_row(draft: dict, item) -> bool:
    """Строка, в окне которой правятся СВОИ вопросы объекта: блок `faq_ref(source=object)`
    на детальной и старый раздел «faq» услуги/события (строка без id)."""
    if not isinstance(item, dict):
        return False
    host = str(draft.get("host") or "")
    if item.get("key") == "faq" and not item.get("id"):
        return not draft.get("home") and has_section(host)
    return is_ref_row(draft, item) and is_object_source(item.get("data"))


def is_window_edit(request, draft: dict, ref: str, op_name: str) -> bool:
    """Форма вопросов окна на детальной (сентинел `faq_present`) — правка этого модуля:
    свои вопросы, выбор источника и (у источника «Allgemeine FAQ») общие вопросы."""
    from apps.core import aufbau_draft

    post = getattr(request, "POST", None) or {}
    if op_name not in ("update", "faq_update") or post.get("faq_present") != "1":
        return False
    row = aufbau_draft._row(draft, ref)
    return is_row(draft, row) or is_ref_row(draft, row)


def _object(host: str):
    from apps.core import detail_parts

    kind = detail_parts.object_kind(host)
    return kind, (detail_parts.object_for_host(host) if kind else None)


def state(obj, kind: str, draft: dict | None = None) -> tuple[list[dict], list]:
    """Текущее состояние правки своих вопросов: черновика (если в нём есть) или сохранённое."""
    pending = (draft or {}).get("ofaq")
    if isinstance(pending, dict) and isinstance(pending.get("items"), list):
        return copy.deepcopy(pending["items"]), list(pending.get("src") or ())
    saved = items(obj, kind)
    return saved, list(range(len(saved)))


def _allowed(user, kind: str) -> bool:
    from apps.core import aufbau_draft, view_perms

    return user is None or view_perms.allowed(user, aufbau_draft.OBJECT_EDIT_VIEWS[kind], "POST")


def window_op(request, config: dict, draft: dict, ref: str, notes: list | None) -> str:
    """Правка окна FAQ на детальной: сначала тексты текущего источника (свои вопросы — в
    `draft["ofaq"]`, общие — прежним `_faq_op`), затем выбор источника (`faq_source`)."""
    from apps.core import aufbau_draft, site_schema

    post = request.POST
    row = aufbau_draft._row(draft, ref)
    host = str(draft.get("host") or "")
    own = is_row(draft, row)
    if not own:
        aufbau_draft._faq_op(config, draft, ref, post, notes, request)
    elif _object(host)[0]:
        _ofaq_op(request, draft, host, post, notes)
    wanted = post.get("faq_source")
    if is_ref_row(draft, row) and wanted in ("object", "shared") and (wanted == "object") != own:
        data = dict(row.get("data") or {})
        if wanted == "object":
            data["source"] = SOURCE_OBJECT
        else:
            data.pop("source", None)
        row["data"] = data
        if (
            wanted == "shared"
            and "ofaq" in draft
            and not any(is_row(draft, it) for it in draft.get("items") or ())
        ):
            # ревью M2b-2b: свои вопросы больше нигде на странице не показаны — их правка
            # снимается сразу и честным текстом (а не «блок удалён» при «Speichern»)
            for key in DRAFT_KEYS:
                draft.pop(key, None)
            if notes is not None:
                notes.append(switched_note())
    if ref and row is None:
        raise site_schema.SchemaError("block")
    return ref


def _ofaq_op(request, draft: dict, host: str, post, notes: list | None) -> None:
    from apps.core import site_schema

    kind, obj = _object(host)
    if obj is None:
        if notes is not None:
            notes.append(gone_note())
        return
    if not _allowed(getattr(request, "user", None), kind):
        raise site_schema.SchemaError("ofaq_rights")
    cur, src = state(obj, kind, draft)
    saved = items(obj, kind)
    stale = post.get("faq_rev") != faq_content.revision(cur, src)
    if "ofaq" not in draft and post.get("faq_base") not in (None, faq_content.fingerprint(saved)):
        stale = True
    if stale:
        if notes is not None:
            notes.append(faq_content.stale_note())
        return
    info: dict = {}
    new_items, new_src = faq_content.apply_ops(
        cur, src, post, notes, info, clean=lambda rows, n: clean_input(rows, kind, n)
    )
    _remember_focus(request, post, info, len(new_items))
    if new_items == saved and new_src == list(range(len(saved))):
        for key in DRAFT_KEYS:  # вернули как сохранено — правки нет
            draft.pop(key, None)
    else:
        draft["ofaq"] = {"items": new_items, "src": new_src, "obj": obj.pk.hex}
        draft.setdefault("ofaq_base", faq_content.fingerprint(saved))


def _remember_focus(request, post, info: dict, count: int) -> None:
    """Куда вернуть фокус после кнопки вопроса (сессия `FAQ_OPENED`, один раз): ↑↓ — сдвинутый
    вопрос, «Entfernen» — вставший на его место (иначе предыдущий; нет — список, -1), новый
    вопрос — последний. Якорь адреса строит `window_parts.faq_anchor` по этому номеру."""
    from apps.core import aufbau_draft

    session = getattr(request, "session", None)
    if session is None:
        return
    opened = info.get("opened")
    removed = str(post.get("faq_remove") or "")
    if opened is None and removed.isdigit():
        opened = min(int(removed), count - 1) if count else -1
    elif opened is None and post.get("faq_add") is not None and _s(post.get("faq_new_q")):
        opened = count - 1
    if opened is not None:
        session[aufbau_draft.FAQ_OPENED] = opened


def put_shown(config: dict, draft: dict) -> None:
    """Вопросы черновика — для превью: служебный ключ `DRAFT_KEY` конфига превью (переводы
    тем же разбором, что при «Speichern»; сохранённое успели изменить — по тексту)."""
    kind, obj = _object(str(draft.get("host") or ""))
    pending = draft.get("ofaq") or {}
    if obj is None or pending.get("obj") not in (None, obj.pk.hex):
        return
    old = items(obj, kind)
    new = clean_items(pending.get("items"))
    by_text = draft.get("ofaq_base") != faq_content.fingerprint(old)
    drafts = dict(config.get(DRAFT_KEY) or {})
    drafts[obj.pk.hex] = {
        "items": new,
        "i18n": remapped(old, overlays(obj, kind), new, pending.get("src"), by_text),
    }
    config[DRAFT_KEY] = drafts


def snapshot(proto: dict, source: dict, item) -> None:
    """«Abbrechen» окна: свои вопросы (и общие — у блока на детальной: в окне меняют
    источник) — как при открытии окна."""
    if not (is_row(source, item) or is_ref_row(source, item)):
        return
    from apps.core import aufbau_draft

    proto["ofaq"] = {k: copy.deepcopy(source[k]) for k in DRAFT_KEYS if k in source}
    if "faq" not in proto and is_ref_row(source, item):
        proto["faq"] = {k: copy.deepcopy(source[k]) for k in aufbau_draft.FAQ_KEYS if k in source}


def commit(locked, kind: str, draft: dict | None, user, notes: list | None, force: bool):
    """«Speichern»: свои вопросы черновика — в объект, заблокированный `_lock_object`
    (одна блокировка с разделами объекта). Возвращает изменённые поля модели."""
    from apps.core import site_schema

    if not draft or not isinstance(draft.get("ofaq"), dict):
        return []
    pending = draft["ofaq"]
    if pending.get("obj") not in (None, locked.pk.hex):
        logger.warning("object_faq: draft of another object ignored (%s)", kind)
        return []
    if not any(is_row(draft, it) for it in draft.get("items") or ()):
        # блок своих вопросов из черновика убрали — правку «в тени» не публикуем
        if notes is not None:
            notes.append(dropped_note())
        return []
    if not _allowed(user, kind):
        raise site_schema.SchemaError("ofaq_rights")
    moved = draft.get("ofaq_base") != fingerprint(locked, kind)
    if moved and not force:
        raise site_schema.SchemaError("ofaq_conflict")
    fields = put(
        locked, kind, pending.get("items") or [], pending.get("src"), draft.get("ofaq_base")
    )
    if moved and notes is not None:
        notes.append(forced_note())
    return fields


def add_default(new: dict, host: str) -> None:
    """Новый блок `faq_ref` на детальной — со своими вопросами объекта (решение владельца)."""
    if _detail(host):
        new["data"] = {**(new.get("data") or {}), "source": SOURCE_OBJECT}


def switched_note() -> str:
    return _(
        "Der Block zeigt jetzt die allgemeinen FAQ – die Änderungen an den eigenen Fragen "
        "wurden verworfen."
    )


def gone_note() -> str:
    return _("Dieses Angebot gibt es nicht mehr – die Fragen wurden nicht übernommen.")


def dropped_note() -> str:
    return _(
        "Die Änderungen an den eigenen Fragen wurden nicht gespeichert, weil der FAQ-Block "
        "entfernt wurde."
    )


def forced_note() -> str:
    return _(
        "Die eigenen Fragen wurden inzwischen geändert – Ihre Fassung ist gespeichert, "
        "Übersetzungen wurden nach dem Fragetext zugeordnet."
    )


def error_note(code: str) -> str:
    """Сообщение отказа «Seitenaufbau» по коду `SchemaError`."""
    if code == "ofaq_rights":
        return _("Die eigenen Fragen darf nur ändern, wer auch das Angebot selbst bearbeiten darf.")
    return _("Die eigenen Fragen dieses Angebots wurden inzwischen an anderer Stelle geändert.")


def display_name(obj) -> str:
    for attr in ("title", "name"):
        value = getattr(obj, attr, None)
        if isinstance(value, dict):
            getter = getattr(obj, "get_i18n", None)
            value = getter(attr) if callable(getter) else next(iter(value.values()), "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(obj)


def _links(host: str, user=None) -> list[dict]:
    """На общем хосте детали — ссылки на формы объектов (свои вопросы правятся там). Виды,
    чьи формы пользователю закрыты, ссылок не дают (ревью M2b-2b, security LOW)."""
    from django.db import DatabaseError
    from django.urls import NoReverseMatch, reverse

    out = []
    for kind, k in KINDS.items():
        if k.shared_host != host or not _allowed(user, kind):
            continue
        try:
            qs = model(kind).objects.all()
            for obj in qs.order_by(*_order(kind))[:LINKS_MAX]:
                out.append(
                    {
                        "label": display_name(obj),
                        "url": reverse(k.edit_url, args=[obj.pk]),
                        "count": len(items(obj, kind)),
                    }
                )
        except (LookupError, NoReverseMatch, DatabaseError):
            # ревью M2b-2b: окно без ссылок лучше упавшего экрана — видно в логе
            logger.warning("object_faq: links of %s unavailable", kind, exc_info=True)
    return out[:LINKS_MAX]


def _order(kind: str) -> tuple[str, ...]:
    return {"event": ("-starts_at",), "tour": ("title",), "product": ("-created_at",)}.get(
        kind, ("name",)
    )


def panel(draft: dict, host: str, item, opened=None, saved_config=None, user=None) -> dict | None:
    """Модель части «Fragen» окна на детальной (None — не наша строка). `scope`:
    object — свои вопросы правятся здесь; each — общий хост: подсказка и ссылки; shared —
    общие вопросы (их модель дополняет `faq_content.panel` у вызывающего); noaccess —
    сотрудник без права на объект видит только «нет доступа» (ревью M2b-2b)."""
    own = is_row(draft, item)
    ref = is_ref_row(draft, item)
    if not own and not ref:
        return None
    kind, obj = _object(host)
    hk = _host_kind(host)
    out: dict = {"scope": "shared", "kind": hk}
    if own and obj is not None and not _allowed(user, kind):
        out.update({"scope": "noaccess", "hint": error_note("ofaq_rights")})
    elif own and obj is not None:
        cur, src = state(obj, kind, draft)
        k = KINDS[kind]
        out.update(faq_content.panel(cur, src, saved_config or {}, opened))
        out.update(
            {
                "scope": "object",
                "name": display_name(obj),
                "free": len(cur) < k.max_items,
                "max": k.max_items,
                "max_q": k.max_q,
                "max_a": k.max_a,
                "base": faq_content.fingerprint(items(obj, kind)),
            }
        )
    elif own:
        out.update(
            {
                "scope": "each",
                "hint": KINDS[hk].each_hint if hk else "",
                "links": _links(host, user),
            }
        )
    if ref and hk:
        out["sources"] = [
            {
                "value": "object",
                "label": (
                    _("Fragen nur für %(name)s") % {"name": display_name(obj)}
                    if obj is not None
                    else _("Eigene Fragen jeder Seite")
                ),
                "hint": KINDS[hk].own_hint,
                "checked": own,
            },
            {
                "value": "shared",
                "label": _("Allgemeine FAQ"),
                "hint": _("dieselben Fragen wie auf „FAQ“"),
                "checked": not own,
            },
        ]
    if own and has_section(host):
        out["double"] = _shown_twice(draft)
    if own and isinstance(item, dict) and item.get("key") == "faq" and not item.get("id"):
        # ревью M2b-2b: раздел «faq» скрыт — правка видна только после показа раздела
        out["hidden_section"] = _section_hidden(draft)
    return out


def _section_hidden(draft: dict) -> bool:
    return any(
        it.get("key") == "faq" and not it.get("id") and it.get("enabled", True) is False
        for it in draft.get("items") or ()
    )


def _shown_twice(draft: dict) -> bool:
    """Свои вопросы стоят на странице дважды: блок `faq_ref(source=object)` и раздел «faq»."""
    rows = [it for it in draft.get("items") or () if it.get("enabled", True) is not False]
    section = any(it.get("key") == "faq" and not it.get("id") for it in rows)
    block = any(is_ref_row(draft, it) and is_object_source(it.get("data")) for it in rows)
    return section and block
