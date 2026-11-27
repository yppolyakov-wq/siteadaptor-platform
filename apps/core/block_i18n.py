"""FB-33 M3-5c: переводы текстов блока в окне «Seitenaufbau» — единственный писатель.

План — scratchpad `m35c-plan.md` (planner, 2026-11-21), решения владельца 2026-11-21:
1) правка немецкого текста СНИМАЕТ перевод этого поля (сообщение со списком языков; перевод,
   введённый в той же форме, остаётся; до «Speichern» откатывают «Abbrechen»/«Verwerfen»);
2) основной язык бизнеса не de — немецкое поле подписано «Deutsch (Ausgangstext)», язык бизнеса —
   первой кнопкой и выбран по умолчанию (стопка 16 T1b: одно правило `i18n_input.window_langs`,
   как у «Felder»);
3) у нового вопроса FAQ поля перевода — после «Speichern» (ключ — индекс источника `src`),
   перевод подписи плашки — только при своей немецкой подписи.

Что переводится (ключ поля в черновике → где лежит перевод):
- C-блок «Text», «Foto + Text», «Button», «Bild»: `title`/`body`/`label`/`caption` →
  `i18n[<язык>]["sections"|"page_blocks"][<хост>][<позиция блока>]["data"][<поле>]`;
- «Seitentitel»: `title`/`intro` → `i18n[<язык>]["page_titles"][<хост>]`, у каталога —
  `i18n[<язык>]["catalog_title"|"catalog_intro"]` (`page_title.tr_path`, стопка 15 M5e-2b);
- «Was passiert jetzt»: `text` → `i18n[<язык>]["confirmation_next"]`;
- плашки «Schnellzugriff»: `label.<ключ>` → `…["data"]["labels"][<ключ>]`;
- общие вопросы FAQ: `faq.<src>.q|a` → `i18n[<язык>]["faq"]` (пишет `faq_content.put(explicit=)`);
- свои вопросы объекта: `ofaq.<src>.q|a` → объект (`object_faq.put(explicit=)` под блокировкой);
- пункты полосы доверия (стопка 16 T1a): `usp.<src>.label|text` → `i18n[<язык>]["usp_bar"]
  [<позиция пункта>]`; `src` — место пункта в сохранённом списке, едет с пунктом при ↑/↓/✕
  (`usp_items`); ключ пункта — не его немецкий `label` (сам переводимый текст), поле формы — по
  позиции показа (`before`), как номер вопроса FAQ;
- пункты секций главной (стопка 16 T6): шаг `title`/`text`, команда `role`, отзыв `text`
  (`home_texts.TR_ITEM_FIELDS`, имена не переводятся): `item.<src>.<поле>` →
  `i18n[<язык>][<секция>][<позиция пункта>]` — тот же позиционный оверлей, что у Студии; `src` —
  место пункта в сохранённом списке, пункт окна узнаётся по ключу (`home_texts.item_src`, правило
  D9); поле формы — по позиции показа (снимок `htx_of`); при правке пунктов переводы окна кладёт
  писатель текстов (`home_texts.put(window_tr=)`, `explicit_items`), без неё — `apply`;
- SEO страницы (стопка 16 T1b, ★ текстовой страницы `siteconfig.is_seo_page_host`): поля
  `seo_title`/`seo_description` (имена `page_window.SEO_FIELDS`, не `title` — тот у
  «Seitentitel») → `i18n[<язык>]["seo"]["pages"][<хост>]["title"|"description"]`
  (`content_pages.seo_tr_path`); немецкое — черновик `seo` окна, его пишет `put_page_seo`.

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
    # FB-33 стопка 15 M5e-1b (A12): строки «Zahlen» — текстом «Wert | Bezeichnung» (`stats_rows`)
    "stats": ("rows",),
}
_TITLE_FIELDS = ("title", "intro")
_NEXT_FIELD = "text"
#: имя поля перевода формы «fields»/плашек: f_tr_<поле>_<язык> (в `fields` — без «f_»)
_FIELD_RE = re.compile(r"tr_([A-Za-z0-9_]+?)_([a-z]{2})")
_FAQ_RE = re.compile(r"faq_(\d{1,3})_([qa])_([a-z]{2})")
#: стопка 16 T1a: поле перевода пункта полосы доверия (без «f_tr_» и языка): usp_<позиция>_<поле>
_USP_RE = re.compile(r"usp_(\d{1,2})_(label|text)")
#: ревью T1a D1: немецкое поле строки формы USP (`usp_<i>_label`) — число строк формы
_USP_SLOT_RE = re.compile(r"usp_(\d{1,2})_label")
_USP_FIELDS = ("label", "text")
#: потолки ввода пункта — те же, что у немецких полей окна (`site_schema._update_usp`)
USP_CAPS = {"label": 120, "text": 200}
#: пространства id блоков языков окна (`_bw_langs.html` с `ns`): якорь кнопки языка после POST
USP_NS = "usp"
#: стопка 16 T1b: блок языков формы SEO ★-строки текстовой страницы
SEO_NS = "seo"
#: стопка 16 T6: блок языков «Texte» секций со списком пунктов (шаги, команда, отзывы)
HTX_NS = {key: f"htx-{key}" for key in ("process", "team", "testimonials")}
LANG_NAMESPACES = (USP_NS, SEO_NS, *HTX_NS.values())
#: стопка 16 T1b: поле окна (`page_window.SEO_FIELDS`) → поле записи SEO (`seo_tr_path`)
_SEO_TR = {"seo_title": "title", "seo_description": "description"}
#: стопка 16 T6: поле пункта секции главной в форме окна (без «f_»): htx_<секция>_<позиция>_<поле>
_ITEM_RE = re.compile(r"htx_(process|team|testimonials)_(\d{1,2})_([a-z]+)")


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
    if site_schema.page_ref(ref) == site_schema.PAGE_REF:
        # FB-33 M5b-2: после слияния переводы заголовка — в окне ★-строки страницы; отпечаток
        # тот же, что у прежнего `__title` (открытые до деплоя черновики — без конфликта)
        # стопка 15 M5e-2b (A4): и шапка каталога (`page_title.has_head`)
        if page_title.has_head(host):
            return ("title",)
        # стопка 16 T1b: у ★ текстовой страницы — её SEO (хосты со своим заголовком другие,
        # `test_seo_and_head_hosts_disjoint`: у ★ одна форма с переводами)
        return ("seo",) if _seo_host(host) else ()
    if ref == site_schema.NEXT_REF:
        return ("next",) if host == confirmation_page.HOST else ()
    row = _row(page, ref)
    if not isinstance(row, dict):
        return ()
    out = []
    if _is_usp(page, row):
        out.append("usp")  # стопка 16 T1a: пункты полосы доверия
    if row.get("id") and _type(row) in TEXT_FIELDS:
        out.append("block")
    if page.get("home") and _home_texts().has_texte(row):
        out.append("htx")  # FB-33 стопка 15 M5e-1b: тексты секции главной (без списков)
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


def _seo_host(host: str) -> bool:
    from apps.tenants import siteconfig

    return siteconfig.is_seo_page_host(host)


def _seo_german(config: dict, page: dict) -> dict:
    """Немецкое SEO окна: черновика (`seo`), иначе сохранённое (черновик до SEO в окне)."""
    from apps.core import page_window
    from apps.tenants import siteconfig

    if isinstance(page.get(page_window.SEO_KEY), dict):
        return siteconfig.clean_seo_page(page[page_window.SEO_KEY])
    return page_window.saved_seo(config, str(page.get("host") or ""))


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
            out[field] = _rows_text(data.get(field)) if field == "rows" else _s(data.get(field))
    if "htx" in found:
        out.update(_htx_texts(config, page, row["key"]))
        out.update(_item_texts(config, page, row["key"]))
    if "title" in found:
        entry = page.get("title") or {}
        for field in _TITLE_FIELDS:
            out[field] = _s(entry.get(field))
    if "next" in found:
        out[_NEXT_FIELD] = _s(page.get("next"))
    if "seo" in found:
        entry = _seo_german(config, page)
        for name, field in _SEO_TR.items():
            out[name] = entry.get(field, "")
    if "tiles" in found:
        for key, text in (hero_tiles.clean_data(row.get("data") or {}).get("labels") or {}).items():
            out[f"label.{key}"] = text
    if "usp" in found:
        items, src = usp_items(row.get("data"), config)
        for item, s in zip(items, src, strict=False):
            if isinstance(s, int):
                for field in _USP_FIELDS:
                    out[f"usp.{s}.{field}"] = _s(item.get(field))
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
                    text = _rows_text(data.get(field)) if field == "rows" else _s(data.get(field))
                    if text:
                        mine[field] = text
            if "tiles" in found and isinstance(data.get("labels"), dict):
                for key, text in data["labels"].items():
                    if _s(text):
                        mine[f"label.{key}"] = _s(text)
        if "title" in found:
            for field in _TITLE_FIELDS:
                text = _at(node, _page_title().tr_path(host, field))
                if text:
                    mine[field] = text
        if "htx" in found:
            key = (_row(page, ref) or {}).get("key")
            for name in _htx_texts(config, page, key):
                text = _at(node, _home_texts().tr_path(key, name))
                if text:
                    mine[name] = text
            fields = _home_texts().TR_ITEM_FIELDS.get(key, ())
            rows = node.get(key) if fields else None
            for j, entry in enumerate(rows if isinstance(rows, list) else ()):
                for field in fields:
                    if isinstance(entry, dict) and _s(entry.get(field)):
                        mine[f"item.{j}.{field}"] = _s(entry[field])
        if "usp" in found and isinstance(node.get("usp_bar"), list):
            for s, entry in enumerate(node["usp_bar"]):
                for field in _USP_FIELDS:
                    if isinstance(entry, dict) and _s(entry.get(field)):
                        mine[f"usp.{s}.{field}"] = _s(entry[field])
        if "seo" in found:
            for name, field in _SEO_TR.items():
                text = _at(node, _content_pages().seo_tr_path(host, field))
                if text:
                    mine[name] = text
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
    if isinstance(mine, dict) and isinstance(mine.get(key), str):
        return mine[key]
    value = (saved.get(loc) or {}).get(key, "")
    return value if isinstance(value, str) else ""


def _object_fp(obj, kind: str) -> str:
    """Отпечаток своих вопросов объекта: немецкий список и переводы (ключ — индекс источника)."""
    from apps.core import object_faq

    if obj is None:
        return ""
    return fingerprint({"items": object_faq.items(obj, kind), "tr": object_faq.overlays(obj, kind)})


def bases(config: dict, page: dict, ref: str, obj=None) -> dict:
    """Отпечатки окна на первой правке (ревью H2): `all` — переводы и немецкие списки вопросов
    (переводы вопросов ключуются индексом источника — изменённый в другом месте список сдвинул
    бы их на чужой вопрос), `faq` — общий немецкий список, `obj` — свои вопросы объекта (`obj` —
    заблокированный объект при «Speichern»)."""
    from apps.core import faq_content
    from apps.core import object_faq as _ofaq

    found = set(kinds(page, ref))
    if "ofaq" in found and _ofaq.is_ref_row(page, _row(page, ref)):
        found.add("faq")
    faq = faq_content.fingerprint(faq_content.base_items(config)) if "faq" in found else ""
    ofp = ""
    if "ofaq" in found:
        okind, found_obj = _object(str(page.get("host") or ""))
        ofp = _object_fp(obj if obj is not None else found_obj, okind)
    tr = saved_for(config, page, ref)
    keys = _item_keys(config, page, ref) if "htx" in found else None
    if keys is None:
        return {"all": fingerprint({"tr": tr, "faq": faq, "obj": ofp}), "faq": faq, "obj": ofp}
    # стопка 16 T6 (ревью D1): ключи пунктов — в отпечатке (Студия переставила шаги без
    # переводов — тоже конфликт) и в черновике (`_put_item` узнаёт свой пункт после «Trotzdem»)
    return {
        "all": fingerprint({"tr": tr, "faq": faq, "obj": ofp, "items": keys}),
        "faq": faq,
        "obj": ofp,
        "keys": keys,
    }


def _base_part(value, part: str) -> str:
    return value.get(part, "") if isinstance(value, dict) else ""


# ───────────── правка в черновике ─────────────


def _caps(page: dict, ref: str, key: str) -> int:
    from apps.core import confirmation_page, faq_content, hero_tiles, object_faq, page_title
    from apps.tenants import siteconfig

    if key.startswith("label."):
        return hero_tiles.LABEL_MAX
    if key in _SEO_TR:  # стопка 16 T1b: 70/200, как немецкие поля (`clean_seo_page`)
        return (
            siteconfig.SEO_PAGE_TITLE_MAX
            if key == "seo_title"
            else siteconfig.SEO_PAGE_DESCRIPTION_MAX
        )
    if key.startswith("usp."):
        return USP_CAPS.get(key.rsplit(".", 1)[-1], 200)
    if key.startswith("item."):  # стопка 16 T6: те же потолки, что у немецких полей пункта
        ht = _home_texts()
        return ht.TEXT_MAX if key.endswith(".text") else ht.TITLE_MAX
    if key.startswith(("faq.", "ofaq.")):
        kind, _s_, field = key.split(".")
        if kind == "ofaq":
            okind = _object(str(page.get("host") or ""))[0]
            k = object_faq.KINDS.get(okind)
            if k is not None:
                return k.max_q if field == "q" else k.max_a
        return faq_content.MAX_Q if field == "q" else faq_content.MAX_A
    found = kinds(page, ref)
    if "htx" in found:
        spec = _home_texts()._spec((_row(page, ref) or {}).get("key") or "", key)
        if spec is not None:
            return spec[3]
    if "title" in found:
        return page_title.TITLE_MAX if key == "title" else page_title.INTRO_MAX
    if "next" in found:
        return confirmation_page.NEXT_MAX
    if key == "rows":
        return _ROWS_MAX
    return siteconfig.CBLOCK_INPUT_CAPS.get(_type(_row(page, ref)), {}).get(key, 200)


def _clean(key: str, value, cap: int) -> tuple[str, bool]:
    text = value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else ""
    # стопка 16 T1b: SEO — пробелы схлопнуты, как у немецкого (`clean_seo_page`)
    text = " ".join(text.split()) if key.startswith("label.") or key in _SEO_TR else text.strip()
    if key.startswith("item."):
        # стопка 16 T6: пункт Студии — строка «A | B»: перевод одной строкой и без «|», как
        # немецкое поле пункта (`home_texts._item_text`)
        text = _home_texts()._item_text(text)
    if len(text) <= cap:
        return text, False
    # стопка 16 T1b: обрезанное SEO — без пробела в хвосте (как `clean_seo_page` при чтении)
    return (text[:cap].rstrip() if key in _SEO_TR else text[:cap]), True


def _posted(page: dict, ref: str, fields, post, before_src: dict, lost: list | None = None) -> dict:
    """Присланные переводы: {(язык, ключ): текст}. Поля формы — только своих ключей и языков
    платформы; номер вопроса FAQ — позиция в окне ДО правки (`before_src`)."""
    allowed_locs = set(_locales())
    out: dict = {}
    usp_src = item_src = None
    for name, value in (fields or {}).items():
        match = _FIELD_RE.fullmatch(str(name))
        if not match or match.group(2) not in allowed_locs:
            continue
        field, loc = match.groups()
        usp = _USP_RE.fullmatch(field)
        if usp:
            # стопка 16 T1a: позиция пункта в окне при показе → его место в сохранённом списке
            if usp_src is None:
                usp_src = usp_slot_src(
                    before_src.get("usp_items") or [], before_src.get("usp") or [], fields
                )
            src, i = usp_src, int(usp.group(1))
            s = src[i] if i < len(src) else None
            if isinstance(s, int):
                out[(loc, f"usp.{s}.{usp.group(2)}")] = value
            continue
        item = _ITEM_RE.fullmatch(field)
        if item:
            # стопка 16 T6: позиция пункта в окне при показе → его место в сохранённом списке
            section, i, part = item.group(1), int(item.group(2)), item.group(3)
            if section != before_src.get("htx_key"):
                continue
            if item_src is None:
                item_src = item_slot_src(before_src, fields)
            s = item_src[i] if i < len(item_src) else None
            if isinstance(s, int) and part in _home_texts().TR_ITEM_FIELDS.get(section, ()):
                out[(loc, f"item.{s}.{part}")] = value
            elif lost is not None and _s(value):
                lost.append(field)  # ревью D3: пункт не узнан (устаревшая вкладка) — не молча
            continue
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
    if "usp" in kinds(draft, ref):
        items, usp_src = usp_items((_row(draft, ref) or {}).get("data"), config)
        src["usp"], src["usp_items"] = usp_src, items
    key = (_row(draft, ref) or {}).get("key")
    if "htx" in kinds(draft, ref) and key in _home_texts().TR_ITEM_FIELDS:
        items, item_src = _home_texts().window_items(config, key, draft)
        src["htx"], src["htx_items"], src["htx_key"] = item_src, items, key
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
    lost: list = []
    posted = _posted(old_draft, ref, fields, post, prior.get("src") or {}, lost)
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
        capped = capped or cut or (key == "rows" and _rows_cut(text))
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
    if lost:
        logger.warning("block_i18n: %s item translations of a stale form skipped", len(lost))
    if notes is not None:
        if lost:
            notes.append(window_skipped_note())
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
        base[ref] = bases(config, draft, ref)
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
        bases(config, draft, ref)["all"] != _base_part(value, "all")
        for ref, value in base.items()
        if ref in draft["btr"] and kinds(draft, ref)  # блока на странице нет — переводить нечего
    )


def drop(draft: dict, ref: str) -> None:
    """Блок удалили из черновика — его переводов (и отпечатка) больше нет (ревью H1)."""
    btr = {r: v for r, v in (draft.get("btr") or {}).items() if r != ref}
    base = {r: v for r, v in (draft.get("btr_base") or {}).items() if r != ref}
    if btr:
        draft["btr"], draft["btr_base"] = btr, base
    else:
        for key in DRAFT_KEYS:
            draft.pop(key, None)


def faq_moved(config: dict, draft: dict) -> bool:
    """Общий немецкий список вопросов изменили с первой правки перевода (запись поверх — force)."""
    from apps.core import faq_content

    now = faq_content.fingerprint(faq_content.base_items(config))
    return any(
        _base_part(v, "faq") not in ("", now) for v in (draft.get("btr_base") or {}).values()
    )


def obj_moved(draft: dict, locked, kind: str) -> bool:
    """Свои вопросы объекта (под блокировкой) изменили с первой правки перевода (ревью H2)."""
    now = _object_fp(locked, kind)
    return any(
        _base_part(v, "obj") not in ("", now) for v in (draft.get("btr_base") or {}).values()
    )


def window_skipped_note() -> str:
    from django.utils.translation import gettext

    return gettext("Übersetzungen aus dem Fenster wurden nicht übernommen.")


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
                    _set_path(config, loc, _page_title().tr_path(host, key), text)
                elif "next" in found and key == _NEXT_FIELD:
                    _set_path(config, loc, ("confirmation_next",), text)
                elif "seo" in found and key in _SEO_TR:
                    # стопка 16 T1b: после `page_window.commit` (немецкое и снятие перевода
                    # изменённого поля) — перевод, введённый в той же форме, остаётся
                    if text and not _seo_room(config, loc, host):
                        logger.warning("block_i18n: seo translation hosts full — skipped")
                        continue
                    _set_path(config, loc, _content_pages().seo_tr_path(host, _SEO_TR[key]), text)
                elif "htx" in found and home and key.startswith("item."):
                    _put_item(config, draft, ref, loc, key, text)
                elif "htx" in found and home:
                    row = _row(draft, ref) or {}
                    if _htx_allowed(config, draft, row.get("key") or "", key):
                        _set_path(config, loc, _home_texts().tr_path(row["key"], key), text)
                    else:
                        logger.debug("block_i18n: %s %s — not a window text, skipped", ref, key)
                elif "usp" in found and home and key.startswith("usp."):
                    _put_usp(config, draft, ref, loc, key, text)
                elif at is None:
                    # блока на странице больше нет — переводить нечего
                    logger.debug("block_i18n: block %s is gone — translation skipped", ref)
                    continue
                elif "block" in found and key in TEXT_FIELDS.get(_type(at[1]), ()):
                    value = _rows_list(text) if key == "rows" else text
                    _set_path(config, loc, (*_block_path(home, host, at[0]), key), value)
                elif "tiles" in found and key.startswith("label."):
                    tile = key[6:]
                    own = hero_tiles.clean_data(at[1].get("data") or {}).get("labels") or {}
                    if tile in own or not text:  # перевод — только у своей немецкой подписи
                        _set_path(
                            config, loc, (*_block_path(home, host, at[0]), "labels", tile), text
                        )


def _seo_room(config: dict, loc: str, host: str) -> bool:
    """Потолок хостов перевода SEO — `_MAX_SEO_PAGES` (больше читатель `page_seo` считает
    оверлей битым и показывает немецкое)."""
    from apps.tenants import siteconfig

    root = config.get("i18n") if isinstance(config.get("i18n"), dict) else {}
    seo = root.get(loc, {}).get("seo") if isinstance(root.get(loc), dict) else None
    pages = seo.get("pages") if isinstance(seo, dict) else None
    if not isinstance(pages, dict):
        return True
    return host in pages or len(pages) < siteconfig._MAX_SEO_PAGES


def _block_path(home: bool, host: str, idx: int) -> tuple:
    return ("sections", idx, "data") if home else ("page_blocks", host, idx, "data")


# ───────────── стопка 16 T1a: пункты полосы доверия ─────────────


def _is_usp(page: dict, row) -> bool:
    from apps.core import site_schema

    return bool(page.get("home")) and site_schema._is_usp_row(row)


def _valid_src(src, n: int) -> bool:
    if not isinstance(src, list) or len(src) != n:
        return False
    ints = [s for s in src if s is not None]
    return all(type(s) is int and s >= 0 for s in ints) and len(set(ints)) == len(ints)


def usp_items(data, config: dict | None = None) -> tuple[list, list]:
    """Пункты строки USP черновика и место каждого в сохранённом списке (`None` — новый пункт).
    Без `src` (не правили или черновик до T1a) — пункты на своих местах."""
    from apps.tenants import siteconfig

    data = data if isinstance(data, dict) else {}
    items = siteconfig.clean_usp(
        data["items"] if "items" in data else (config or {}).get("usp_bar")
    )
    src = data.get("src")
    return items, list(src) if _valid_src(src, len(items)) else list(range(len(items)))


def usp_fp(items) -> str:
    return fingerprint({"usp": items or []})


def usp_slot_src(items: list, src: list, fields) -> list:
    """Место в сохранённом списке для каждой строки формы USP (`usp_<i>_…`). Форма несёт
    снимок пунктов при показе (`usp_of`); не совпал с черновиком (пункты тем временем правили
    в другой вкладке) — строка узнаёт свой пункт по ключу (немецкий `label`, правило D9
    `siteconfig._match_items`), не узнала — новый пункт (ревью T1a D1). Без снимка (запрос в
    обход формы, форма до правки) — по номеру строки, как прежде."""
    from apps.tenants import siteconfig

    of = str((fields or {}).get("usp_of", ""))
    if not of or of == usp_fp(items):
        return src
    n = 1 + max(
        (int(m.group(1)) for m in map(_USP_SLOT_RE.fullmatch, map(str, fields or ())) if m),
        default=-1,
    )
    labels = [
        siteconfig._item_identity(
            {"label": _clean("usp", fields.get(f"usp_{i}_label"), 120)[0]}, "label"
        )
        if f"usp_{i}_label" in fields
        else ""
        for i in range(n)
    ]
    found = siteconfig._match_items(
        labels, [[siteconfig._item_identity(it, "label")] for it in items]
    )
    return [src[j] if isinstance(j, int) and j < len(src) else None for j in found]


def usp_data(data: dict, cur_items: list, items: list, src: list) -> dict:
    """Данные строки USP после правки окна: `src` и отпечаток списка, на который он указывает
    (`src_of`), — только когда пункты не совпадают с ним как есть (черновик «как сохранено»
    остаётся без лишних ключей: отпечаток и «чистый» черновик прежние)."""
    of = data.get("src_of") if "src" in data and isinstance(data.get("src_of"), str) else ""
    of = of or usp_fp(cur_items)
    if src == list(range(len(items))) and usp_fp(items) == of:
        return {"items": items}
    return {"items": items, "src": src, "src_of": of}


def realign_usp(config: dict, data: dict, new: list) -> None:
    """Подъём USP (`site_schema.lift_hero_choice`, до замены `usp_bar`): переводы пунктов —
    за своим пунктом (`src`), удалённый уносит свои, у нового их нет; перевод поля, чей
    немецкий текст изменился, снимается (`home_texts.drop_changed`). `src` указывает не на
    этот список (его тем временем изменили, «Trotzdem speichern»; черновик до T1a) — пункты
    узнаются по ключу правилом D9 (`siteconfig._match_items`)."""
    from apps.core import home_texts
    from apps.tenants import siteconfig

    overlay = config.get("i18n")
    if not isinstance(overlay, dict) or not overlay:
        return
    old = siteconfig.clean_usp(config.get("usp_bar"))
    items, src = usp_items(data)
    has_src = _valid_src(data.get("src"), len(items)) and len(items) == len(new)
    if has_src and data.get("src_of") == usp_fp(old):
        pass
    elif not has_src and usp_fp(new) == usp_fp(old):
        return  # пункты как сохранено — переводам двигаться некуда
    else:
        src = siteconfig._match_items(
            [siteconfig._item_identity(it, "label") for it in new],
            [[siteconfig._item_identity(it, "label")] for it in old],
            by_place=True,
        )

    def full(item):
        return {f: _s(item.get(f)) for f in _USP_FIELDS} if isinstance(item, dict) else None

    for node in overlay.values():
        if not isinstance(node, dict) or not isinstance(node.get("usp_bar"), list):
            continue
        tr = node["usp_bar"]
        node["usp_bar"] = [
            copy.deepcopy(tr[s])
            if isinstance(s, int) and s < len(tr) and isinstance(tr[s], dict)
            else {}
            for s in src
        ]
    aligned = [full(old[s]) if isinstance(s, int) and s < len(old) else None for s in src]
    home_texts.drop_changed(
        config, "usp_bar", [full(it) for it in old], [full(it) for it in new], aligned=aligned
    )
    for loc in list(overlay):
        node = overlay[loc]
        if not isinstance(node, dict) or not isinstance(node.get("usp_bar"), list):
            continue
        rows = node["usp_bar"]
        while rows and rows[-1] in ({}, None):
            rows.pop()
        if not rows:
            node.pop("usp_bar")


def _put_usp(config: dict, draft: dict, ref: str, loc: str, key: str, text: str) -> None:
    """Перевод пункта из окна — на место пункта в записанном списке (после подъёма USP)."""
    _kind, s, field = (key.split(".") + ["", ""])[:3]
    if not s.isdigit() or field not in _USP_FIELDS:
        return
    _items, src = usp_items((_row(draft, ref) or {}).get("data"), config)
    if int(s) not in src:
        logger.debug("block_i18n: usp item %s is gone — translation skipped", s)
        return
    j = src.index(int(s))
    if j < len(config.get("usp_bar") or []):
        _set_path(config, loc, ("usp_bar", j, field), text)


def put_shown(config: dict, draft: dict) -> None:
    """Показ черновика (`aufbau_draft.overlay`): переводы на копии конфига превью; вопросы FAQ
    без правки самих вопросов — тем же писателем, что «Speichern»."""
    from apps.core import faq_content

    apply(config, draft, bool(draft.get("home")), str(draft.get("host") or ""))
    tr = explicit(draft, "faq")
    if tr and "faq" not in draft and not faq_moved(config, draft):
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


def _empty_text(key: str, german_text: str) -> tuple[str, bool]:
    """Что покажет сайт без перевода и служебная ли это строка интерфейса (`empty_ui`: без
    `lang` бизнеса, a11y №10) — немецкий текст бизнеса служебным не бывает."""
    from django.utils.translation import gettext

    if german_text:
        return german_text, False
    if key in _SEO_TR:  # стопка 16 T1b: пустое немецкое SEO — «Leer = automatisch»
        return gettext("automatisch"), True
    if key in _TITLE_FIELDS or key == _NEXT_FIELD:
        return gettext("Standardtext der Seite"), True
    return "—", False


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
    from django.utils.translation import get_language

    from apps.core import aufbau_draft, i18n_input

    allowed = set(_locales())
    # стопка 16 T1b (T2/T5): одно правило языков окна с «Felder» — порядок, выбранный язык,
    # «Deutsch (Ausgangstext)» и «Ihre Seite zeigt zuerst …»
    rule = i18n_input.window_langs(
        [loc for loc in locales or () if loc in allowed], default_locale, wanted
    )
    locs = rule["locs"]
    if not locs:
        return
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
    lang = rule["lang"]
    names = dict(settings.LANGUAGES)
    base = settings.LANGUAGE_CODE[:2]
    ui = (get_language() or base)[:2]
    saved = saved_for(saved_config, page, ref)
    texts = german(saved_config, page, ref)

    def inputs(key: str, name, ident: str, area: bool = False, hint: str = HINT_ID) -> list[dict]:
        cap = _caps(page, ref, key)
        empty, empty_ui = _empty_text(key, texts.get(key, ""))
        return [
            {
                "loc": loc,
                "label": names.get(loc, loc),
                "name": name(loc),
                "id": f"{ident}-{loc}",
                "value": shown(saved, page, ref, loc, key),
                "shown": loc == lang,
                "empty": empty,
                # служебная строка — на языке кабинета, текст бизнеса — немецкий (a11y №10)
                "empty_ui": empty_ui,
                "empty_lang": ui if empty_ui else base,
                "area": area,
                "limit": cap if cap <= 2000 else "",
                "hint": hint,
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
    htx = selected.get("home_texts") or {}
    for f in [
        *(htx.get("fields") or ()),
        *(x for g in htx.get("groups") or () for x in g["fields"]),
    ]:
        name = f.get("name", "")
        if name in texts and not part.startswith("fields"):
            f["translations"] = inputs(
                name,
                lambda loc, n=name: f"f_tr_{n}_{loc}",
                f"schema-f-{name}",
                area=f.get("kind") == "text",
            )
            part = "hometext"
    if "htx" in found and not part.startswith("fields"):
        part = _decorate_items(htx, saved_config, page, texts, saved, inputs, base) or part
    faq = selected.get("faq_items") or {}
    scope = "ofaq" if faq.get("scope") == "object" else "faq"
    if (
        not part  # ревью A5: кнопки языка — в одной форме окна
        and faq.get("items")
        and scope in found
        and faq.get("scope") in (None, "shared", "object")
    ):
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
    tiles = (selected.get("tiles") or {}) if not part else {}  # ревью A5: одна форма окна
    for r in tiles.get("rows") or ():
        key = f"label.{r['key']}"
        if key in texts:  # только своя немецкая подпись (решение владельца 3)
            r["translations"] = inputs(
                key, lambda loc, k=r["key"]: f"f_tr_label_{k}_{loc}", f"bw-tile-{r['key']}"
            )
            part = "tiles"
    usp = (selected.get("usp") or {}) if not part else {}  # ревью A5: одна форма окна
    if "usp" in found and usp.get("items"):
        # стопка 16 T1a: поле перевода — по позиции пункта в окне, ключ — его место в
        # сохранённом списке; у нового пункта полей нет (после «Speichern»)
        _items, src = usp_items((_row(page, ref) or {}).get("data"), saved_config)
        for i, it in enumerate(usp["items"]):
            s = src[i] if i < len(src) else None
            if not isinstance(s, int):
                continue
            for field in _USP_FIELDS:
                key = f"usp.{s}.{field}"
                if field == "text" and not (
                    texts.get(key) or any(key in v for v in saved.values())
                ):
                    continue  # без немецкого текста переводить нечего
                it[f"tr_{field}"] = inputs(
                    key,
                    lambda loc, i=i, fl=field: f"f_tr_usp_{i}_{fl}_{loc}",
                    f"bw-usp-{i}-{field}",
                    hint=f"{USP_NS}-lang-hint",
                )
                for t in it[f"tr_{field}"]:
                    t["of"] = f"f_usp_{i}_{field}"  # источник текста для «Übersetzen» (T3)
            part = "usp"
    seo = (selected.get("seo") or {}) if not part else {}  # ревью A5: одна форма окна
    if "seo" in found and seo:
        # стопка 16 T1b: переводы SEO ★ текстовой страницы — и при пустом немецком (решение
        # владельца: тогда «Ohne Übersetzung: automatisch»)
        for name in _SEO_TR:
            field = name.removeprefix("seo_")
            seo[f"tr_{field}"] = inputs(
                name,
                lambda loc, n=name: f"f_tr_{n}_{loc}",
                f"bw-seo-{field}",
                area=field == "description",
                hint=f"{SEO_NS}-lang-hint",
            )
            for t in seo[f"tr_{field}"]:
                t["of"] = (
                    f"f_{name}"  # имя немецкого поля — источник «Übersetzen» (T3; ревью T3b LOW)
                )
                t["max_id"] = f"{t['id']}-max"
                t["hint"] = f"{t['hint']} {t['max_id']}"  # «Höchstens N Zeichen.» (артборд)
        part = "seo"
    if not part:
        return
    selected["field_langs"] = {
        "part": part,
        "lang": lang,
        "locales": [
            {"code": loc, "label": names.get(loc, loc), "shown": loc == lang} for loc in locs
        ],
        "title_id": TITLE_ID,
        "hint_id": HINT_ID,
        "base_note": rule["base_note"],
        "first_note": rule["first_note"],
    }
    item_ns = HTX_NS.get(htx.get("key")) if part == "hometext" else None
    if part in ("usp", "seo") or item_ns:
        # стопка 16 T1a/T1b (a11y №4): блок языков формы USP и SEO — своё пространство id
        # (T6: и «Texte» секций с пунктами — `htx-<секция>`)
        ns = item_ns or (USP_NS if part == "usp" else SEO_NS)
        selected["field_langs"].update(
            ns=ns, title_id=f"{ns}-lang-title", hint_id=f"{ns}-lang-hint"
        )


def _decorate_items(htx: dict, saved_config: dict, page: dict, texts, saved, inputs, base):
    """Стопка 16 T6: поля перевода пунктов «Texte» (шаги, команда, отзывы) — по позиции пункта
    в окне, ключ — его место в сохранённом списке; у нового пункта полей нет (после
    «Speichern»), имя — «Name wird nicht übersetzt.». Возвращает "hometext" или ""."""
    ht = _home_texts()
    key = htx.get("key")
    fields = ht.TR_ITEM_FIELDS.get(key)
    if not fields:
        return ""
    win, src = ht.window_items(saved_config, key, page)
    keyfield = ht._ITEM_KEY[key]
    hint = f"{HTX_NS[key]}-lang-hint"
    names, groups = [], []
    for g in htx.get("groups") or ():
        i = g.get("i")
        s = src[i] if isinstance(i, int) and i < len(src) else None
        if not isinstance(s, int):
            continue  # новый пункт: переводы — после «Speichern» (решение владельца 4)
        groups.append((g, _s(win[i].get(keyfield))))
        for f in g["fields"]:
            field = f["name"].rsplit("_", 1)[-1]
            k = f"item.{s}.{field}"
            if field not in fields:
                if field == keyfield:
                    names.append(f)
                continue
            if field != keyfield and not (texts.get(k) or any(k in v for v in saved.values())):
                continue  # без немецкого текста переводить нечего
            f["translations"] = inputs(
                k,
                lambda loc, n=f["name"]: f"f_tr_{n}_{loc}",
                f["id"],
                area=f.get("kind") == "text",
                hint=hint,
            )
            for t in f["translations"]:
                t["of"] = f"f_{f['name']}"  # источник текста для «Übersetzen» (T3)
            f["tr_short"] = True  # подпись «Titel – Übersetzung (…)», пункт назван в legend
    if not any(f.get("translations") for g, _q in groups for f in g["fields"]):
        return ""
    htx["of"] = items_fp(win, src)
    for g, quote in groups:
        g["quote"], g["quote_lang"] = quote, base
    from django.utils.translation import gettext

    for f in names:
        f["not_tr"] = gettext("Name wird nicht übersetzt.")
        f["described"] = " ".join(x for x in (f.get("described"), f"{f['id']}-nt") if x)
    return "hometext"


#: id заголовка и подсказки кнопок языка окна (одна такая форма на окно; у «Felder» — свои)
TITLE_ID = "bwtr-lang-title"
HINT_ID = "bwtr-lang-hint"


# ───────────── FB-33 стопка 15 M5e-1b: тексты секций главной и строки «Zahlen» ─────────────
#: потолок текста строк «Zahlen» в поле перевода (12 строк по «Wert | Bezeichnung»)
_ROWS_MAX = 1000


def _home_texts():
    from apps.core import home_texts

    return home_texts


def _htx_texts(config: dict, page: dict, key) -> dict:
    """Немецкие тексты секции главной, перевод которых правится в окне (черновик или
    сохранённое; списки — нет: их пункты переводятся в Студии)."""
    ht = _home_texts()
    if key not in ht.FIELDS:
        return {}
    current = ht.state(
        config, key, page, ht.arch_keys_of(ht.pending(page, key) or {}) or _tenant_keys(config, key)
    )
    return {n: v for n, v in current.items() if ht.translatable(key, n)}


def _tenant_keys(config: dict, key: str) -> list[str]:
    if key != "archetypes":
        return []
    arch = config.get("archetypes") if isinstance(config.get("archetypes"), dict) else {}
    return sorted(arch, key=str)


def _at(node, path: tuple) -> str:
    for step in path:
        node = node.get(step) if isinstance(node, dict) else None
    return _s(node)


def _page_title():
    from apps.core import page_title

    return page_title


def _content_pages():
    from apps.core import content_pages

    return content_pages


def _rows_text(value) -> str:
    """Строки «Zahlen» → текст поля «Wert | Bezeichnung» (как у Студии)."""
    from apps.tenants import siteconfig

    if isinstance(value, str):
        return value.strip()
    return siteconfig.stats_to_text(value if isinstance(value, list) else [])


def _rows_list(text: str):
    """Текст «Wert | Bezeichnung» → строки перевода [{value, label}] ("" — снять перевод)."""
    if not text:
        return ""
    rows = []
    for line in text.splitlines():
        value, _sep, label = line.partition("|")
        if value.strip():
            rows.append({"value": value.strip(), "label": label.strip()})
    return rows or ""


def _rows_cut(text: str) -> bool:
    """Перевод строк «Zahlen» длиннее потолков нормализации (значение 12, подпись 40, пар —
    `siteconfig._MAX_STAT_ITEMS`) — её обрежут: заметка, не молча (ревью M5e-1b D)."""
    from apps.core import site_schema
    from apps.tenants import siteconfig

    rows = _rows_list(text) or []
    return site_schema.stats_capped(text) or len(rows) > siteconfig._MAX_STAT_ITEMS


def _htx_allowed(config: dict, draft: dict, section: str, key: str) -> bool:
    """Перевод поля секции главной: только переводимое поле окна, у тизера — только ключ
    архетипа, который есть (в сохранённом или в правке черновика)."""
    ht = _home_texts()
    if not ht.translatable(section, key):
        return False
    if section != "archetypes":
        return True
    arch = config.get("archetypes") if isinstance(config.get("archetypes"), dict) else {}
    known = set(arch) | set(ht.arch_keys_of(ht.pending(draft, "archetypes") or {}))
    return any(key == f"{p}{k}" for p in ("arch_label_", "arch_blurb_") for k in known)


# ───────────── стопка 16 T6: пункты секций главной (шаги, команда, отзывы) ─────────────


def _item_texts(config: dict, page: dict, key) -> dict:
    """Немецкие тексты пунктов окна, перевод которых правится в окне: {item.<src>.<поле>}."""
    ht = _home_texts()
    fields = ht.TR_ITEM_FIELDS.get(key)
    if not fields:
        return {}
    out = {}
    win, src = ht.window_items(config, key, page)
    for item, s in zip(win, src, strict=False):
        if isinstance(s, int):
            for field in fields:
                out[f"item.{s}.{field}"] = _s(item.get(field))
    return out


def items_fp(items, src) -> str:
    """Снимок пунктов окна при показе (`htx_of` формы)."""
    return fingerprint({"items": items or [], "src": src or []})


def item_slot_src(before_src: dict, fields) -> list:
    """Место в сохранённом списке для каждой позиции пункта формы «Texte». Снимок формы
    (`htx_of`) совпал с окном до правки — позиции те же; нет — пункты тем временем правили в
    другой вкладке: позиция узнаёт свой пункт по присланному немецкому ключу (правило D9
    `siteconfig._match_items`), не узнала — без перевода. Без снимка — по позиции, как прежде."""
    from apps.tenants import siteconfig

    items, src = before_src.get("htx_items") or [], before_src.get("htx") or []
    key = before_src.get("htx_key") or ""
    of = str((fields or {}).get("htx_of", ""))
    if not of or of == items_fp(items, src) or key not in _home_texts().TR_ITEM_FIELDS:
        return src
    keyfield = _home_texts()._ITEM_KEY[key]
    slot = re.compile(rf"htx_{key}_(\d{{1,2}})_{keyfield}")
    n = 1 + max((int(m.group(1)) for m in map(slot.fullmatch, map(str, fields)) if m), default=-1)
    posted = [
        siteconfig._item_identity(
            {keyfield: _home_texts()._item_text(fields.get(f"htx_{key}_{i}_{keyfield}"))},
            keyfield,
        )
        for i in range(n)
    ]
    found = siteconfig._match_items(
        posted, [[siteconfig._item_identity(it, keyfield)] for it in items]
    )
    return [src[j] if isinstance(j, int) and j < len(src) else None for j in found]


def explicit_items(draft: dict, section: str) -> dict:
    """Переводы пунктов секции из черновика ({язык: {src: {поле: текст}}}, "" — снять) — для
    писателя текстов `home_texts.put(window_tr=)`, когда пункты секции правили в окне."""
    out: dict = {}
    btr = draft.get("btr") if isinstance(draft.get("btr"), dict) else {}
    allowed = set(_locales())
    for ref, per_loc in btr.items():
        row = _row(draft, ref)
        if not isinstance(row, dict) or row.get("id") or row.get("key") != section:
            continue
        for loc, entries in (per_loc or {}).items():
            if loc not in allowed or not isinstance(entries, dict):
                continue
            for key, text in entries.items():
                parts = str(key).split(".")
                if len(parts) != 3 or parts[0] != "item" or not parts[1].isdigit():
                    continue
                if isinstance(text, str):
                    out.setdefault(loc, {}).setdefault(int(parts[1]), {})[parts[2]] = text
    return out


def put_items(config: dict, section: str, src: list, tr: dict) -> None:
    """Переводы пунктов из окна — на место пункта в записанном списке (`src` — место каждого
    нового пункта в прежнем списке, `home_texts.item_src`); ушедший пункт — без записи."""
    fields = _home_texts().TR_ITEM_FIELDS.get(section, ())
    for loc, by_src in sorted((tr or {}).items()):
        for s, entry in sorted(by_src.items()):
            if s not in src:
                logger.debug("block_i18n: %s item %s is gone — translation skipped", section, s)
                continue
            j = src.index(s)
            for field, text in sorted(entry.items()):
                if field in fields and isinstance(text, str):
                    _set_path(config, loc, (section, j, field), text)


def _put_item(config: dict, draft: dict, ref: str, loc: str, key: str, text: str) -> None:
    """Перевод пункта, когда сами пункты секции в окне не правили: места те же, что в
    сохранённом списке (правили — пишет `home_texts.put(window_tr=)` после выравнивания)."""
    ht = _home_texts()
    section = (_row(draft, ref) or {}).get("key") or ""
    if section in ht.clean_htx(draft):
        return
    _kind, s, field = (key.split(".") + ["", ""])[:3]
    if not s.isdigit() or field not in ht.TR_ITEM_FIELDS.get(section, ()):
        return
    rows = config.get(section)
    j = _item_now(config, draft, ref, section, int(s))
    if j is None:
        logger.warning("block_i18n: %s item %s is gone — translation skipped", section, s)
    elif isinstance(rows, list) and j < len(rows):
        _set_path(config, loc, (section, j, field), text)


def _item_keys(config: dict, page: dict, ref: str):
    """Ключи сохранённых пунктов секции окна (`None` — у строки пунктов нет)."""
    from apps.tenants import siteconfig

    ht = _home_texts()
    section = (_row(page, ref) or {}).get("key")
    if section not in ht.TR_ITEM_FIELDS:
        return None
    rows = config.get(section) if isinstance(config.get(section), list) else []
    return [siteconfig._item_identity(r, ht._ITEM_KEY[section]) for r in rows]


def _item_now(config: dict, draft: dict, ref: str, section: str, s: int):
    """Ревью D1: место пункта `s` (место при первой правке перевода) в списке `config` сейчас —
    по ключу пункта из черновика (k-й дубль ↔ k-й); ключей нет (черновик до правки) — `s`."""
    base = (
        (draft.get("btr_base") or {}).get(ref) if isinstance(draft.get("btr_base"), dict) else None
    )
    keys = base.get("keys") if isinstance(base, dict) else None
    now = _item_keys(config, draft, ref)
    if not isinstance(keys, list) or now is None or keys == now:
        return s
    if s >= len(keys):
        return None
    occurrence = keys[:s].count(keys[s])
    places = [j for j, k in enumerate(now) if k == keys[s]]
    return places[occurrence] if occurrence < len(places) else None
