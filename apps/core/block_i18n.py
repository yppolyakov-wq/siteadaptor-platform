"""FB-33 M3-5c: переводы текстов блока в окне «Seitenaufbau» — единственный писатель.

План — scratchpad `m35c-plan.md` (planner, 2026-11-21), решения владельца 2026-11-21:
1) правка немецкого текста СНИМАЕТ перевод этого поля (сообщение со списком языков; перевод,
   введённый в той же форме, остаётся; до «Speichern» откатывают «Abbrechen»/«Verwerfen»);
2) основной язык бизнеса не de — немецкое поле подписано «Deutsch (Grundtext)», язык бизнеса —
   первой кнопкой и выбран по умолчанию;
3) у нового вопроса FAQ поля перевода — после «Speichern» (ключ — индекс источника `src`),
   перевод подписи плашки — только при своей немецкой подписи.

Что переводится (ключ поля в черновике → где лежит перевод):
- C-блок «Text», «Foto + Text», «Button», «Bild»: `title`/`body`/`label`/`caption` →
  `i18n[<язык>]["sections"|"page_blocks"][<хост>][<позиция блока>]["data"][<поле>]`;
- «Seitentitel»: `title`/`intro` → `i18n[<язык>]["page_titles"][<хост>]`;
- «Was passiert jetzt»: `text` → `i18n[<язык>]["confirmation_next"]`;
- плашки «Schnellzugriff»: `label.<ключ>` → `…["data"]["labels"][<ключ>]`;
- общие вопросы FAQ: `faq.<src>.q|a` → `i18n[<язык>]["faq"]` (пишет `faq_content.put(explicit=)`);
- свои вопросы объекта: `ofaq.<src>.q|a` → объект (`object_faq.put(explicit=)` под блокировкой).

Черновик: `draft["btr"] = {ref: {язык: {ключ: текст}}}` ("" — снять перевод) и
`draft["btr_base"] = {ref: отпечаток сохранённых переводов на первой правке}` — вне
`_saved_state` (строка `SIDE_PARTS`); «Speichern» при изменённых тем временем переводах —
`SchemaError("btr_conflict")`, «Trotzdem speichern» (force) пишет поверх.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re

logger = logging.getLogger(__name__)

DRAFT_KEYS = ("btr", "btr_base")
#: тексты C-блоков, перевод которых правится в окне (поля `site_schema.PANEL_FIELDS`)
TEXT_FIELDS = {
    "text": ("title", "body"),
    "image_text": ("title", "body"),
    "button": ("label",),
    "image": ("caption",),
}
_TITLE_FIELDS = ("title", "intro")
_NEXT_FIELD = "text"
#: имя поля перевода формы «fields»/плашек: f_tr_<поле>_<язык> (в `fields` — без «f_»)
_FIELD_RE = re.compile(r"tr_([A-Za-z0-9_]+?)_([a-z]{2})")
_FAQ_RE = re.compile(r"faq_(\d{1,3})_([qa])_([a-z]{2})")


def _locales() -> list[str]:
    from apps.tenants import siteconfig

    return sorted(siteconfig.overlay_locales())


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _type(row) -> str:
    from apps.tenants import siteconfig

    key = (row or {}).get("key") or ""
    return siteconfig.cblock_type(key) or key


def _row(page: dict, ref: str):
    from apps.core import aufbau_draft

    return aufbau_draft._row(page, ref)


def kinds(page: dict, ref: str) -> tuple[str, ...]:
    """Что переводится в окне строки `ref` страницы `page` (черновик или сохранённое в его
    форме: {home, host, items, title, next})."""
    from apps.core import aufbau_draft, confirmation_page, object_faq, page_title, site_schema

    host = str(page.get("host") or "")
    if ref == site_schema.TITLE_REF:
        return ("title",) if host in page_title.HEAD_HOSTS else ()
    if ref == site_schema.NEXT_REF:
        return ("next",) if host == confirmation_page.HOST else ()
    row = _row(page, ref)
    if not isinstance(row, dict):
        return ()
    out = []
    if row.get("id") and _type(row) in TEXT_FIELDS:
        out.append("block")
    if row.get("id") and _type(row) == "quick_links":
        out.append("tiles")
    if aufbau_draft._is_faq_row(page, row):
        out.append("faq")
    if (object_faq.is_row(page, row) or object_faq.is_ref_row(page, row)) and _object(host)[1]:
        out.append("ofaq")
    return tuple(out)


def _object(host: str):
    from apps.core import object_faq

    return object_faq._object(host)


# ───────────── немецкие тексты и сохранённые переводы ─────────────


def _faq_state(config: dict, page: dict, kind: str):
    from apps.core import faq_content, object_faq

    if kind == "faq":
        return faq_content.state(config, page)
    okind, obj = _object(str(page.get("host") or ""))
    if obj is None:
        return [], []
    return object_faq.state(obj, okind, page)


def german(config: dict, page: dict, ref: str) -> dict:
    """Немецкие тексты окна строки: {ключ поля: текст}. `config` — сохранённый (вопросы
    черновика FAQ — из `page`)."""
    from apps.core import hero_tiles

    out: dict = {}
    found = kinds(page, ref)
    row = _row(page, ref) or {}
    if "block" in found:
        data = row.get("data") or {}
        for field in TEXT_FIELDS[_type(row)]:
            out[field] = _s(data.get(field))
    if "title" in found:
        entry = page.get("title") or {}
        for field in _TITLE_FIELDS:
            out[field] = _s(entry.get(field))
    if "next" in found:
        out[_NEXT_FIELD] = _s(page.get("next"))
    if "tiles" in found:
        for key, text in (hero_tiles.clean_data(row.get("data") or {}).get("labels") or {}).items():
            out[f"label.{key}"] = text
    for kind in ("faq", "ofaq"):
        if kind in found:
            items, src = _faq_state(config, page, kind)
            for item, s in zip(items, src, strict=False):
                if isinstance(s, int):
                    out[f"{kind}.{s}.q"] = _s(item.get("q"))
                    out[f"{kind}.{s}.a"] = _s(item.get("a"))
    return out


def _rows_of(config: dict, home: bool, host: str) -> list:
    """Строки страницы в нормализованном виде — позиции те же, что у оверлея на витрине."""
    from apps.tenants import siteconfig

    if home:
        return siteconfig.normalize_sections(config.get("sections") or [])
    pages = siteconfig.normalize_page_blocks(config.get("page_blocks") or {})
    return pages.get(host) or []


def index_of(config: dict, home: bool, host: str, ref: str):
    """Позиция C-блока `ref` в списке страницы `config` (None — блока там нет)."""
    if not ref:
        return None
    for i, row in enumerate(_rows_of(config, home, host)):
        if isinstance(row, dict) and row.get("id") == ref:
            return i
    return None


def _ov_rows(node: dict, home: bool, host: str):
    if not isinstance(node, dict):
        return None
    if home:
        rows = node.get("sections")
    else:
        pages = node.get("page_blocks")
        rows = pages.get(host) if isinstance(pages, dict) else None
    return rows if isinstance(rows, list) else None


def saved_for(config: dict, page: dict, ref: str) -> dict:
    """Сохранённые переводы окна строки: {язык: {ключ: текст}} (только непустые)."""
    from apps.core import object_faq as _ofaq

    home, host = bool(page.get("home")), str(page.get("host") or "")
    found = set(kinds(page, ref))
    if "ofaq" in found and _ofaq.is_ref_row(page, _row(page, ref)):
        found.add("faq")  # источник блока переключается в окне — отпечаток от него не зависит
    overlay = config.get("i18n") if isinstance(config.get("i18n"), dict) else {}
    out: dict = {}
    idx = index_of(config, home, host, ref) if {"block", "tiles"} & found else None
    okind, obj = _object(host) if "ofaq" in found else ("", None)
    obj_tr = _ofaq.overlays(obj, okind) if obj is not None else {}
    for loc in _locales():
        node = overlay.get(loc) if isinstance(overlay.get(loc), dict) else {}
        mine: dict = {}
        if idx is not None:
            rows = _ov_rows(node, home, host) or []
            entry = rows[idx] if idx < len(rows) and isinstance(rows[idx], dict) else {}
            data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
            if "block" in found:
                for field in TEXT_FIELDS[_type(_row(page, ref))]:
                    if _s(data.get(field)):
                        mine[field] = _s(data[field])
            if "tiles" in found and isinstance(data.get("labels"), dict):
                for key, text in data["labels"].items():
                    if _s(text):
                        mine[f"label.{key}"] = _s(text)
        if "title" in found:
            titles = node.get("page_titles") if isinstance(node.get("page_titles"), dict) else {}
            entry = titles.get(host) if isinstance(titles.get(host), dict) else {}
            for field in _TITLE_FIELDS:
                if _s(entry.get(field)):
                    mine[field] = _s(entry[field])
        if "next" in found and _s(node.get("confirmation_next")):
            mine[_NEXT_FIELD] = _s(node["confirmation_next"])
        lists = {"faq": node.get("faq"), "ofaq": obj_tr.get(loc)}
        for kind in ("faq", "ofaq"):
            if kind not in found or not isinstance(lists[kind], list):
                continue
            for s, entry in enumerate(lists[kind]):
                for field in ("q", "a"):
                    if isinstance(entry, dict) and _s(entry.get(field)):
                        mine[f"{kind}.{s}.{field}"] = _s(entry[field])
        if mine:
            out[loc] = mine
    return out


def fingerprint(saved: dict) -> str:
    raw = json.dumps(saved or {}, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def _pending(draft: dict, ref: str) -> dict:
    pending = (draft.get("btr") or {}).get(ref) if isinstance(draft.get("btr"), dict) else None
    return pending if isinstance(pending, dict) else {}


def shown(saved: dict, draft: dict, ref: str, loc: str, key: str) -> str:
    """Перевод, который сейчас видит владелец: черновика, иначе сохранённый."""
    mine = _pending(draft, ref).get(loc)
    if isinstance(mine, dict) and key in mine:
        return mine[key]
    return (saved.get(loc) or {}).get(key, "")


# ───────────── правка в черновике ─────────────


def _caps(page: dict, ref: str, key: str) -> int:
    from apps.core import confirmation_page, faq_content, hero_tiles, object_faq, page_title
    from apps.tenants import siteconfig

    if key.startswith("label."):
        return hero_tiles.LABEL_MAX
    if key.startswith(("faq.", "ofaq.")):
        kind, _s_, field = key.split(".")
        if kind == "ofaq":
            okind = _object(str(page.get("host") or ""))[0]
            k = object_faq.KINDS.get(okind)
            if k is not None:
                return k.max_q if field == "q" else k.max_a
        return faq_content.MAX_Q if field == "q" else faq_content.MAX_A
    found = kinds(page, ref)
    if "title" in found:
        return page_title.TITLE_MAX if key == "title" else page_title.INTRO_MAX
    if "next" in found:
        return confirmation_page.NEXT_MAX
    return siteconfig.CBLOCK_INPUT_CAPS.get(_type(_row(page, ref)), {}).get(key, 200)


def _clean(key: str, value, cap: int) -> tuple[str, bool]:
    text = value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else ""
    text = " ".join(text.split()) if key.startswith("label.") else text.strip()
    return (text[:cap], True) if len(text) > cap else (text, False)


def _posted(page: dict, ref: str, fields, post, before_src: dict) -> dict:
    """Присланные переводы: {(язык, ключ): текст}. Поля формы — только своих ключей и языков
    платформы; номер вопроса FAQ — позиция в окне ДО правки (`before_src`)."""
    allowed_locs = set(_locales())
    out: dict = {}
    for name, value in (fields or {}).items():
        match = _FIELD_RE.fullmatch(str(name))
        if not match or match.group(2) not in allowed_locs:
            continue
        field, loc = match.groups()
        key = f"label.{field[6:]}" if field.startswith("label_") else field
        out[(loc, key)] = value
    scope = "ofaq" if (post or {}).get("faq_scope") == "object" else "faq"
    for name in post or {}:
        match = _FAQ_RE.fullmatch(str(name))
        if not match or match.group(3) not in allowed_locs:
            continue
        i, field, loc = int(match.group(1)), match.group(2), match.group(3)
        src = before_src.get(scope) or []
        s = src[i] if i < len(src) else None
        if isinstance(s, int):
            out[(loc, f"{scope}.{s}.{field}")] = post.get(name)
    return out


def before(config: dict, draft: dict, ref: str) -> dict:
    """Состояние до правки, нужное `take`: немецкие тексты и источники вопросов окна."""
    src = {}
    for kind in ("faq", "ofaq"):
        if kind in kinds(draft, ref):
            src[kind] = list(_faq_state(config, draft, kind)[1])
    return {"german": german(config, draft, ref), "src": src, "draft": copy.deepcopy(draft)}


def take(
    request, config: dict, draft: dict, ref: str, prior: dict, fields, notes: list | None
) -> None:
    """Правка окна → переводы черновика. Присланный перевод, отличный от показанного, — в
    `draft["btr"]` (равный сохранённому — записи нет). Немецкий текст поля изменился — перевод
    этого поля у всех языков снимается ("" в черновике), кроме введённого в той же форме;
    снятые языки — сообщением. Свои вопросы объекта — только с правом на объект."""
    from apps.core import object_faq, site_schema
    from apps.tenants import siteconfig

    post = getattr(request, "POST", None) or {}
    old_draft = prior.get("draft") or draft
    saved = _merged(saved_for(config, old_draft, ref), saved_for(config, draft, ref))
    posted = _posted(old_draft, ref, fields, post, prior.get("src") or {})
    now = german(config, draft, ref)
    was = prior.get("german") or {}
    valid = set(now) | set(was)
    btr = copy.deepcopy(draft.get("btr")) if isinstance(draft.get("btr"), dict) else {}
    mine = btr.setdefault(ref, {})
    typed, capped = set(), False
    for (loc, key), value in posted.items():
        if key not in valid:
            continue
        text, cut = _clean(key, value, _caps(old_draft, ref, key))
        capped = capped or cut
        if text == shown(saved, old_draft, ref, loc, key):
            continue
        if key.startswith("ofaq."):
            okind = _object(str(draft.get("host") or ""))[0]
            if not object_faq._allowed(getattr(request, "user", None), okind):
                raise site_schema.SchemaError("ofaq_rights")
        typed.add((loc, key))
        _set(mine, saved, loc, key, text)
    removed = []
    for key in sorted(set(was) & set(now)):
        if was[key] == now[key]:
            continue
        for loc in _locales():
            if (loc, key) in typed or not shown(saved, old_draft, ref, loc, key):
                continue
            _set(mine, saved, loc, key, "")
            if loc not in removed:
                removed.append(loc)
    if mine:
        btr[ref] = mine
    else:
        btr.pop(ref, None)
    _store(draft, btr, config, ref)
    if notes is not None:
        if capped:
            notes.append(siteconfig.cap_note())
        if removed:
            notes.append(dropped_note(removed))


def _merged(first: dict, second: dict) -> dict:
    out = copy.deepcopy(first)
    for loc, entries in second.items():
        out.setdefault(loc, {}).update(entries)
    return out


def _set(mine: dict, saved: dict, loc: str, key: str, text: str) -> None:
    entry = dict(mine.get(loc) or {})
    if text == (saved.get(loc) or {}).get(key, ""):
        entry.pop(key, None)
    else:
        entry[key] = text
    if entry:
        mine[loc] = entry
    else:
        mine.pop(loc, None)


def _store(draft: dict, btr: dict, config: dict, ref: str) -> None:
    base = dict(draft.get("btr_base") or {}) if isinstance(draft.get("btr_base"), dict) else {}
    if ref in btr and ref not in base:
        base[ref] = fingerprint(saved_for(config, draft, ref))
    base = {r: v for r, v in base.items() if r in btr}
    if btr:
        draft["btr"] = btr
        draft["btr_base"] = base
    else:
        for key in DRAFT_KEYS:
            draft.pop(key, None)


def count(draft: dict) -> int:
    """Изменений для счётчика черновика: по одному на окно с переводами."""
    btr = draft.get("btr")
    return len(btr) if isinstance(btr, dict) else 0


def conflict(config: dict, draft: dict) -> bool:
    """Переводы, которые держит черновик, успели изменить в другом месте (Студия, канва)."""
    base = draft.get("btr_base")
    if not isinstance(draft.get("btr"), dict) or not isinstance(base, dict):
        return False
    return any(
        fingerprint(saved_for(config, draft, ref)) != value
        for ref, value in base.items()
        if ref in draft["btr"]
    )


def conflict_note() -> str:
    from django.utils.translation import gettext

    return gettext("Die Übersetzungen dieses Blocks wurden inzwischen an anderer Stelle geändert.")


def dropped_note(locs) -> str:
    """Сообщение (role=status) о снятых переводах — список языков на их названиях."""
    from django.conf import settings
    from django.utils.translation import gettext

    names = dict(settings.LANGUAGES)
    return gettext("Übersetzung entfernt, weil der deutsche Text geändert wurde: %(names)s") % {
        "names": ", ".join(names.get(loc, loc) for loc in locs)
    }


# ───────────── «Abbrechen» окна ─────────────


def snapshot(proto: dict, source: dict, ref: str) -> None:
    """Прообраз переводов окна `ref` (только своего блока) — для «Abbrechen»."""
    btr = source.get("btr") if isinstance(source.get("btr"), dict) else {}
    base = source.get("btr_base") if isinstance(source.get("btr_base"), dict) else {}
    proto["btr_ref"] = {
        "tr": copy.deepcopy(btr[ref]) if ref in btr else None,
        "base": base.get(ref),
    }


def revert(draft: dict, ref: str, proto: dict) -> None:
    entry = proto.get("btr_ref")
    if not isinstance(entry, dict):
        return
    btr = dict(draft.get("btr") or {}) if isinstance(draft.get("btr"), dict) else {}
    base = dict(draft.get("btr_base") or {}) if isinstance(draft.get("btr_base"), dict) else {}
    if isinstance(entry.get("tr"), dict):
        btr[ref] = copy.deepcopy(entry["tr"])
        base[ref] = entry.get("base")
    else:
        btr.pop(ref, None)
        base.pop(ref, None)
    if btr:
        draft["btr"], draft["btr_base"] = btr, base
    else:
        for key in DRAFT_KEYS:
            draft.pop(key, None)


# ───────────── запись: показ черновика и «Speichern» ─────────────


def _set_path(config: dict, loc: str, path: tuple, text: str) -> None:
    from apps.tenants import siteconfig

    if text:
        siteconfig.set_overlay_value(config, loc, path, text)
        return
    root = config.get("i18n")
    node = root.get(loc) if isinstance(root, dict) else None
    trail = []
    for key in path[:-1]:
        trail.append((node, key))
        if isinstance(node, dict):
            node = node.get(key)
        elif isinstance(node, list) and isinstance(key, int) and key < len(node):
            node = node[key]
        else:
            return
    if isinstance(node, dict):
        node.pop(path[-1], None)
    for parent, key in reversed(trail):
        child = parent[key] if isinstance(parent, list) else parent.get(key)
        if child in ({}, []):
            if isinstance(parent, dict):
                parent.pop(key, None)
            elif key == len(parent) - 1:
                parent.pop()
        if isinstance(parent, list):
            while parent and parent[-1] in ({}, None):
                parent.pop()
    if isinstance(root, dict) and root.get(loc) == {}:
        root.pop(loc)


def explicit(draft: dict, kind: str) -> dict:
    """Переводы вопросов черновика ({язык: {src: {q|a: текст}}}) — для `faq_content.put` /
    `object_faq.put` (`kind` — «faq» или «ofaq»; "" — снять перевод поля)."""
    out: dict = {}
    btr = draft.get("btr") if isinstance(draft.get("btr"), dict) else {}
    for per_loc in btr.values():
        for loc, entries in (per_loc or {}).items():
            for key, text in (entries or {}).items():
                parts = str(key).split(".")
                if len(parts) != 3 or parts[0] != kind or not parts[1].isdigit():
                    continue
                out.setdefault(loc, {}).setdefault(int(parts[1]), {})[parts[2]] = text
    return out


def apply(config: dict, draft: dict, home: bool, host: str) -> None:
    """Переводы блоков, «Seitentitel», «Was passiert jetzt» и подписей плашек черновика —
    в `config` (показ — копия превью, «Speichern» — заблокированная строка). Позиции блоков —
    по их месту в `config` (блоки уже на своих местах). Вопросы FAQ — `explicit`."""
    from apps.core import hero_tiles

    btr = draft.get("btr") if isinstance(draft.get("btr"), dict) else {}
    rows = _rows_of(config, home, host) if btr else []
    by_id = {r.get("id"): (i, r) for i, r in enumerate(rows) if isinstance(r, dict) and r.get("id")}
    for ref, per_loc in btr.items():
        found = kinds(draft, ref)
        at = by_id.get(ref)
        for loc, entries in sorted((per_loc or {}).items()):
            if loc not in _locales():
                continue
            for key, text in sorted((entries or {}).items()):
                if not isinstance(text, str):
                    continue
                if "title" in found and key in _TITLE_FIELDS:
                    _set_path(config, loc, ("page_titles", host, key), text)
                elif "next" in found and key == _NEXT_FIELD:
                    _set_path(config, loc, ("confirmation_next",), text)
                elif at is None:
                    continue  # блока на странице больше нет — переводить нечего
                elif "block" in found and key in TEXT_FIELDS.get(_type(at[1]), ()):
                    _set_path(config, loc, (*_block_path(home, host, at[0]), key), text)
                elif "tiles" in found and key.startswith("label."):
                    tile = key[6:]
                    own = hero_tiles.clean_data(at[1].get("data") or {}).get("labels") or {}
                    if tile in own or not text:  # перевод — только у своей немецкой подписи
                        _set_path(
                            config, loc, (*_block_path(home, host, at[0]), "labels", tile), text
                        )


def _block_path(home: bool, host: str, idx: int) -> tuple:
    return ("sections", idx, "data") if home else ("page_blocks", host, idx, "data")


def put_shown(config: dict, draft: dict) -> None:
    """Показ черновика (`aufbau_draft.overlay`): переводы на копии конфига превью; вопросы FAQ
    без правки самих вопросов — тем же писателем, что «Speichern»."""
    from apps.core import faq_content

    apply(config, draft, bool(draft.get("home")), str(draft.get("host") or ""))
    tr = explicit(draft, "faq")
    if tr and "faq" not in draft:
        items = faq_content.base_items(config)
        faq_content.put(config, items, list(range(len(items))), explicit=tr)


def check(config: dict, draft: dict, force: bool) -> None:
    """«Speichern» (в транзакции `aufbau_draft.commit`, ДО записи блоков): переводы тем
    временем изменили в другом месте — отказ; с `force` — запись поверх (в лог). Пишет
    `apply` после `store_items`; вопросы — у своих писателей (`explicit`)."""
    from apps.core import site_schema

    if not conflict(config, draft):
        return
    if not force:
        raise site_schema.SchemaError("btr_conflict")
    from django.db import connection

    logger.warning(
        "block_i18n: translations changed meanwhile — written over (%s, %s)",
        getattr(connection, "schema_name", ""),
        draft.get("host") or "home",
    )


# ───────────── окно: модель полей перевода ─────────────


def _empty_text(key: str, german_text: str):
    from django.utils.translation import gettext

    if german_text:
        return german_text
    if key in _TITLE_FIELDS or key == _NEXT_FIELD:
        return gettext("Standardtext der Seite")
    return "—"


def decorate(
    selected: dict | None,
    saved_config: dict,
    draft: dict | None,
    config: dict,
    home: bool,
    host: str,
    locales,
    wanted: str = "",
    default_locale: str = "",
) -> None:
    """Поля перевода выбранной строки (у бизнеса с одним языком и у строк без переводимых
    текстов — ничего, окно байт-в-байт прежнее). Языки — кнопками (`_bw_langs.html`), группы
    всех языков в DOM, имя (`name`) — только у полей выбранного языка."""
    if not selected:
        return
    from django.conf import settings
    from django.utils.translation import gettext

    from apps.core import aufbau_draft

    allowed = set(_locales())
    locs = [loc for loc in locales or () if loc in allowed]
    if not locs:
        return
    if default_locale in locs:
        locs = [default_locale, *[loc for loc in locs if loc != default_locale]]
    ref = selected.get("ref") or ""
    page = draft
    if not page:
        page = {
            **aufbau_draft._saved_state(saved_config, home, host),
            "home": home,
            "host": host,
        }
    found = kinds(page, ref)
    if not found:
        return
    lang = wanted if wanted in locs else locs[0]
    names = dict(settings.LANGUAGES)
    base = settings.LANGUAGE_CODE[:2]
    saved = saved_for(saved_config, page, ref)
    texts = german(saved_config, page, ref)

    def inputs(key: str, name, ident: str, area: bool = False) -> list[dict]:
        cap = _caps(page, ref, key)
        return [
            {
                "loc": loc,
                "label": names.get(loc, loc),
                "name": name(loc),
                "id": f"{ident}-{loc}",
                "value": shown(saved, page, ref, loc, key),
                "shown": loc == lang,
                "empty": _empty_text(key, texts.get(key, "")),
                "empty_lang": base,
                "area": area,
                "limit": cap if cap <= 2000 else "",
                "hint": HINT_ID,
            }
            for loc in locs
        ]

    part = ""
    for f in selected.get("fields") or ():
        name = f.get("name", "")
        if name in texts and not name.startswith(("label.", "faq.", "ofaq.")):
            f["translations"] = inputs(
                name,
                lambda loc, n=name: f"f_tr_{n}_{loc}",
                f"schema-f-{name}",
                area=f.get("kind") == "area",
            )
            part = "fields"
    faq = selected.get("faq_items") or {}
    scope = "ofaq" if faq.get("scope") == "object" else "faq"
    if faq.get("items") and scope in found and faq.get("scope") in (None, "shared", "object"):
        _items, src = _faq_state(saved_config, page, scope)
        for it in faq["items"]:
            i = it["i"]
            s = src[i] if i < len(src) else None
            if not isinstance(s, int):
                continue  # новый вопрос: переводы — после «Speichern» (решение владельца 3)
            for field in ("q", "a"):
                it[f"tr_{field}"] = inputs(
                    f"{scope}.{s}.{field}",
                    lambda loc, i=i, fl=field: f"faq_{i}_{fl}_{loc}",
                    f"bw-faq-{i}-{field}",
                    area=field == "a",
                )
                part = "faq"
    tiles = selected.get("tiles") or {}
    for r in tiles.get("rows") or ():
        key = f"label.{r['key']}"
        if key in texts:  # только своя немецкая подпись (решение владельца 3)
            r["translations"] = inputs(
                key, lambda loc, k=r["key"]: f"f_tr_label_{k}_{loc}", f"bw-tile-{r['key']}"
            )
            part = "tiles"
    if not part:
        return
    first = default_locale if default_locale in locs and default_locale != base else ""
    selected["field_langs"] = {
        "part": part,
        "lang": lang,
        "locales": [
            {"code": loc, "label": names.get(loc, loc), "shown": loc == lang} for loc in locs
        ],
        "title_id": TITLE_ID,
        "hint_id": HINT_ID,
        "base_note": gettext("Deutsch (Grundtext)") if first else "",
        "first_note": (
            gettext("Ihre Seite zeigt zuerst %(lang)s.") % {"lang": names.get(first, first)}
            if first
            else ""
        ),
    }


#: id заголовка и подсказки кнопок языка окна (одна такая форма на окно; у «Felder» — свои)
TITLE_ID = "bwtr-lang-title"
HINT_ID = "bwtr-lang-hint"
