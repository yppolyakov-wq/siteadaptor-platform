"""FB-27 R2: черновик экрана «Seitenaufbau» — правки копятся и попадают на сайт
только по «Speichern».

Решение владельца (2026-11-11): черновик свой у каждого типа страницы, «Speichern» /
«Verwerfen», счётчик изменений. Хранение — сессия (план, вариант V1): `site_config`
не трогается, поэтому нет гонки с автосейвом Студии; цена — черновик не переживает
закрытие браузера и не переходит на другое устройство.

Черновик хранит блоки страницы целиком и отпечаток сохранённого состояния, с которого
начат (`base`). Если к моменту «Speichern» сохранённое изменилось в другом месте,
запись отклоняется (`DraftConflict`) — владелец решает: отбросить черновик или записать
поверх.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import secrets
import time

from django.db import transaction

from apps.core import site_schema

logger = logging.getLogger(__name__)

SESSION_KEY = "aufbau_draft"
#: Потолок числа черновиков в сессии (страниц с несохранёнными правками).
MAX_DRAFTS = 10


class DraftConflict(Exception):
    """Сохранённое состояние страницы изменилось с момента начала черновика."""


def _saved_state(config: dict, home: bool, host: str) -> dict:
    state = {"items": site_schema.load_items(config, home, host)}
    from apps.core import page_title

    if host in page_title.HEAD_HOSTS:
        # FB-33 M2d: «Seitentitel» — часть страницы в черновике (правка в другом месте —
        # конфликт, возврат к сохранённому — черновика нет)
        state["title"] = page_title.clean_one((config.get("page_titles") or {}).get(host))
    from apps.core import confirmation_page, detail_parts

    if host == confirmation_page.HOST:
        # FB-33 M2h-5: «Was passiert jetzt» — часть страницы в черновике (как «Seitentitel»)
        state["next"] = confirmation_page.clean_next(config.get(confirmation_page.NEXT_KEY))
    if detail_parts.object_kind(host):
        # R8: разделы объекта живут в нём самом — их правка в другом месте (вкладка
        # карточки, другая вкладка браузера) тоже конфликт черновика
        obj = detail_parts.object_for_host(host)
        state["override"] = getattr(obj, "page_override", None) or {}
    from apps.tenants import siteconfig

    if siteconfig.is_seo_page_host(host):
        # FB-33 M3-6: свой заголовок/описание для поисковиков — часть страницы в черновике
        # (правка на экране «Seiten» — конфликт; возврат к сохранённому — черновика нет)
        from apps.core import page_window

        state["seo"] = page_window.saved_seo(config, host)
    return state


def _has_section_rows(draft: dict) -> bool:
    from apps.core import detail_parts

    keys = set(detail_parts.section_keys(str(draft.get("host") or "")))
    return any(
        isinstance(r, dict) and r.get("key") in keys and not r.get("id")
        for r in draft.get("items") or []
    )


def _base_fingerprint(saved: dict, config: dict, draft: dict) -> str:
    """Отпечаток сохранённого состояния в форме черновика: черновик «Über uns», начатый до
    строк разделов (FB-32 S6a), считал отпечаток с карточкой контактов отдельным ключом — иначе
    чистый черновик выглядел бы конфликтом."""
    if draft.get("host") == "info" and "contact" in draft and not _has_section_rows(draft):
        saved = {**saved, "contact": config.get("about_contact") is not False}
    if "title" not in draft:
        # FB-33 M2d (ревью): черновик, начатый до «Seitentitel», — отпечаток без него
        saved = {k: v for k, v in saved.items() if k != "title"}
    if "next" not in draft:  # FB-33 M2h-5: то же у «Was passiert jetzt»
        saved = {k: v for k, v in saved.items() if k != "next"}
    if "seo" not in draft:  # FB-33 M3-6: черновик, начатый до SEO в окне, — без него
        saved = {k: v for k, v in saved.items() if k != "seo"}
    return _fingerprint(saved)


def _fingerprint(state: dict) -> str:
    raw = json.dumps(state, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def _keys_fingerprint(config: dict, codes) -> str:
    """Отпечаток сохранённых значений настроек типа (FB-27 R4). Многие ключи общие для
    нескольких страниц (форма карточки, ширина текста) — так видно, что значение успели
    изменить на другой странице."""
    from apps.core import page_settings

    return _fingerprint({c: page_settings.stored(config, c) for c in codes or ()})


def _settings(draft: dict) -> dict:
    from apps.core import page_settings

    pending = draft.get("settings")
    if not isinstance(pending, dict):
        return {}
    # FB-31 P2 (ревью): общие настройки правятся на «Design» — черновик, начатый до
    # переноса, их не пишет и не показывает (в панели их больше не отменить)
    return {k: v for k, v in pending.items() if k not in page_settings.DESIGN_SETTINGS}


def _apply_settings(config: dict, draft: dict) -> dict:
    """Настройки черновика поверх `config` (для показа и превью). Недопустимая запись
    пропускается: превью не должно падать из-за устаревшего черновика."""
    from apps.core import page_settings

    for code, entry in _settings(draft).items():
        try:
            config = page_settings.apply_override(
                config, code, (entry or {}).get("v"), (entry or {}).get("o")
            )
        except (page_settings.PageSettingError, AttributeError, KeyError, TypeError, ValueError):
            continue
    return config


def _all(request) -> dict:
    session = getattr(request, "session", None)
    drafts = session.get(SESSION_KEY) if session is not None else None
    return drafts if isinstance(drafts, dict) else {}


def _expired(draft: dict) -> bool:
    """«Пустой» черновик (только снимок окна, FB-33 M3-1b) старше суток — как его нет."""
    if not draft.get(IDLE_KEY):
        return False
    at = draft.get(IDLE_AT)
    return not isinstance(at, (int, float)) or time.time() - at > IDLE_TTL


def _raw(request, code: str) -> dict | None:
    draft = _all(request).get(code)
    if not isinstance(draft, dict) or not isinstance(draft.get("items"), list):
        return None
    return None if _expired(draft) else draft


def get(request, code: str) -> dict | None:
    """Черновик страницы. «Пустой» (правки вернули руками, а окно блока ещё открыто —
    в нём живёт только снимок для «Abbrechen», FB-33 M3-1b) — как его нет: экран, превью
    и список черновиков показывают сохранённое."""
    draft = _raw(request, code)
    return None if draft is None or draft.get(IDLE_KEY) else draft


def _put(request, code: str, draft: dict | None) -> None:
    drafts = dict(_all(request))
    if draft is None:
        drafts.pop(code, None)
    else:
        drafts.pop(code, None)  # свежий — в конец: при переполнении уходит самый старый
        drafts[code] = draft
        # FB-33 M3-1b: «пустые» (только снимок окна) — отдельный лимит и срок, места
        # настоящих черновиков они не занимают
        drafts = {c: d for c, d in drafts.items() if not (isinstance(d, dict) and _expired(d))}
        for idle, limit in ((False, MAX_DRAFTS), (True, MAX_IDLE)):
            mine = [c for c, d in drafts.items() if bool((d or {}).get(IDLE_KEY)) is idle]
            for c in mine[: max(len(mine) - limit, 0)]:
                drafts.pop(c)
    if drafts:
        request.session[SESSION_KEY] = drafts
    else:
        request.session.pop(SESSION_KEY, None)
    request.session.modified = True  # вложенный словарь: сессия видит правку явно


def dirty_codes(request) -> list[str]:
    """Коды страниц с несохранёнными правками (для пометок в списке страниц)."""
    return [code for code in _all(request) if get(request, code)]


def overlay(config: dict, draft: dict) -> dict:
    """Копия `config` с блоками черновика на месте сохранённых — для показа схемы и
    превью. Базу не читает: хост записан в самом черновике."""
    out = copy.deepcopy(config)
    home, host = bool(draft.get("home")), str(draft.get("host") or "")
    items = copy.deepcopy(draft.get("items") or [])
    if home:
        site_schema.lift_hero_choice(out, items)  # FB-29.2: выбор баннеров главной
        out["sections"] = items
    elif host:
        from apps.core import detail_parts

        if detail_parts.module_of(host):  # FB-31 P5: порядок/видимость разделов — на место
            items = detail_parts.lift(out, host, items)
        elif detail_parts.object_kind(host):
            # R8: разделы объекта — в служебный ключ превью (на сайт он не попадает)
            items, state = detail_parts.object_lift(out, host, items)
            if state is not None:
                from apps.core import object_structure

                obj = detail_parts.object_for_host(host)
                module = detail_parts.module_of(detail_parts.shared_host(host))
                drafts = dict(out.get(object_structure.DRAFT_KEY) or {})
                drafts[obj.pk.hex] = object_structure.schema_value(obj, module, state)
                out[object_structure.DRAFT_KEY] = drafts
        page_blocks = dict(out.get("page_blocks") or {})
        page_blocks[host] = items
        out["page_blocks"] = page_blocks
    if host == "info" and "contact" in draft and not _has_section_rows(draft):
        # FB-32 S6a: черновик, начатый до строк разделов, — карточка контактов как раньше
        if draft["contact"]:
            out.pop("about_contact", None)
        else:
            out["about_contact"] = False
    if "title" in draft:
        _put_title(out, host, draft["title"])
    if "next" in draft:
        _put_next(out, draft["next"])
    if "seo" in draft:  # FB-33 M3-6: SEO страницы из окна «Einstellungen der Seite»
        from apps.core import page_window

        page_window.put_shown(out, host, draft)
    if "form" in draft:
        out = _put_form(out, draft)
    if "faq" in draft:
        _put_faq_shown(out, draft)

    if "ofaq" in draft:  # FB-33 M2b-2b: свои вопросы объекта — в служебный ключ превью
        _object_faq().put_shown(out, draft)
    return _apply_settings(out, draft)


# ───────────── FB-33 M3-5b: вопросы FAQ в окне блока (вкладка «Texte») ─────────────
# Вопросы — общие для всех страниц (`site_config["faq"]`), пишет их `faq_content`. Черновик
# держит состояние правки (`faq` = {items, src}, src — индекс вопроса в сохранённом списке)
# и отпечаток сохранённого на первой правке (`faq_base`) — вне `_saved_state`: черновик другой
# страницы с нетронутым FAQ не конфликтует, когда вопросы правят в Студии. Состояние, равное
# сохранённому, черновик не держит (как `form`).
FAQ_KEYS = ("faq", "faq_base")
#: сессия: номер вопроса, который только что двигали (окно откроет его, один раз)
FAQ_OPENED = "aufbau_faq_opened"


def _is_faq_row(draft: dict, item) -> bool:
    """Строка, в окне которой правятся общие вопросы: секция главной и блок «FAQ» страниц
    (у детальных секция «faq» — свои вопросы объекта, не эти)."""
    from apps.tenants import siteconfig

    if not isinstance(item, dict):
        return False
    key = item.get("key") or ""
    if key == "faq" and not item.get("id"):
        return bool(draft.get("home"))
    # FB-33 M2b-2b: блок со своими вопросами объекта (`data.source == "object"`) — не общий FAQ
    data = item.get("data")
    if isinstance(data, dict) and data.get("source") == "object":
        return False
    return bool(item.get("id")) and (siteconfig.cblock_type(key) or key) == "faq_ref"


def _row(draft: dict, ref: str):
    return next((it for it in draft.get("items") or [] if _ident(it) == ref), None)


def is_faq_edit(request, draft: dict, ref: str, op_name: str) -> bool:
    """Форма вопросов окна (сентинел `faq_present`, без `panel_present`) — правка FAQ."""
    post = getattr(request, "POST", None) or {}
    return (
        op_name in ("update", "faq_update")
        and post.get("faq_present") == "1"
        and _is_faq_row(draft, _row(draft, ref))
    )


def _is_tiles_edit(draft: dict, ref: str, op_name: str, fields) -> bool:
    from apps.tenants import siteconfig

    item = _row(draft, ref)
    key = (item or {}).get("key") or ""
    return (
        op_name == "update"
        and isinstance(fields, dict)
        and fields.get("tiles_present") == "1"
        and bool((item or {}).get("id"))
        and (siteconfig.cblock_type(key) or key) == "quick_links"
    )


def _tiles_op(draft: dict, ref: str, fields: dict, notes: list | None = None) -> None:
    """Форма плашек окна → данные блока (`hero_tiles.update_data`); без изменений — блок не
    трогаем (канонизация не создаёт «правку»). Форма несёт отпечаток данных, с которых
    открыта (`tiles_rev`): не совпал (другая вкладка успела сменить набор) — отказ."""
    from apps.core import hero_tiles

    item = _row(draft, ref)
    old = hero_tiles.clean_data(item.get("data") or {})
    if fields.get("tiles_rev") != hero_tiles.revision(old):
        if notes is not None:
            notes.append(hero_tiles.stale_note())
        return
    new = hero_tiles.update_data(old, fields)
    if new != old:
        item["data"] = new


def faq_conflict(config: dict, draft: dict) -> bool:
    """Вопросы, которые держит черновик, успели изменить в другом месте (Студия, канва)."""
    from apps.core import faq_content

    if "faq" not in draft:
        return False
    return draft.get("faq_base") != faq_content.fingerprint(faq_content.base_items(config))


def _faq_op(config: dict, draft: dict, ref: str, post, notes: list | None, request=None) -> str:
    """Правка вопросов в черновике. Кнопки ↑↓/Entfernen несут отпечаток состояния (`faq_rev`):
    вторая вкладка браузера со старым номером — отказ с сообщением, ничего не меняется."""
    from apps.core import faq_content

    items, src = faq_content.state(config, draft)
    saved = faq_content.base_items(config)
    stale = post.get("faq_rev") != faq_content.revision(items, src)
    if "faq" not in draft and post.get("faq_base") not in (None, faq_content.fingerprint(saved)):
        stale = True
    if stale:
        if notes is not None:
            notes.append(faq_content.stale_note())
        return ref
    info: dict = {}
    new_items, new_src = faq_content.apply_ops(items, src, post, notes, info)
    session = getattr(request, "session", None)
    if session is not None and "opened" in info:
        # ревью a11y: после ↑↓ окно открывает сдвинутый вопрос и ставит на него фокус (раз)
        session[FAQ_OPENED] = info["opened"]
    if new_items == saved and new_src == list(range(len(saved))):
        for key in FAQ_KEYS:  # вернули как сохранено — правки нет
            draft.pop(key, None)
    else:
        draft["faq"] = {"items": new_items, "src": new_src}
        draft.setdefault("faq_base", faq_content.fingerprint(saved))
    return ref


def _put_faq_shown(config: dict, draft: dict) -> None:
    """Вопросы черновика — для показа и превью (переводы тем же писателем; сохранённое успели
    изменить — по тексту, без записи в лог на каждый показ)."""
    from apps.core import faq_content

    pending = draft.get("faq") or {}
    src = pending.get("src") if not faq_conflict(config, draft) else None
    faq_content.put(config, pending.get("items") or [], src)


# ───────────── FB-33 M2i-5: поля формы заявки (вкладка «Felder») ─────────────
# Черновик хранит состояние вкладки (`form`) и сохранённое на момент первой правки
# (`form_base`) — вне `_saved_state`/отпечатка: правка старой панели «Anfrage-Formular» между
# ними не конфликт, запись сливает трёхсторонне (`form_spec.merge`, ревью H2).
FORM_KEYS = ("form", "form_base")

# FB-33 стопка 3: части черновика ВНЕ `_saved_state`/отпечатка — одна таблица для `_settle`
# (черновик только с такой частью не «чистый») и `_revert` («Abbrechen» окна). Новый срез
# дописывает СВОЮ строку (между строками разных срезов — зазор, чтобы стопка собиралась
# без ручного слияния); снимок (`_snapshot`) у каждой части свой — там условие по строке.
SIDE_PARTS = (
    ("form", FORM_KEYS),  # FB-33 M2i-5 «Felder»
    ("faq", FAQ_KEYS),  # FB-33 M3-5b вопросы FAQ
    ("ofaq", ("ofaq", "ofaq_base")),  # FB-33 M2b-2b свои вопросы объекта (`object_faq`)
)


def form_state(config: dict, draft: dict, notes: list | None = None) -> dict:
    """Состояние вкладки черновика поверх СЕЙЧАС сохранённого `config` (трёхстороннее)."""
    from apps.core import form_spec

    saved = form_spec.edit_state(config, "anfrage")
    if "form" not in draft:
        return saved
    return form_spec.merge(draft.get("form_base", saved), draft["form"], saved, notes=notes)


def _put_form(config: dict, draft: dict) -> dict:
    """Поля формы черновика — для показа и превью тем же писателем `form_spec.put`, что и
    «Speichern» (на копии: при отказе — сохранённое, отметка `FORM_ERROR_KEY` для экрана)."""
    from apps.core import form_spec

    state = form_state(config, draft)
    out = copy.deepcopy(config)
    try:
        form_spec.put(out, "anfrage", state)
    except form_spec.FormSpecError:
        config[form_spec.FORM_ERROR_KEY] = True
        out = config
    out[form_spec.EDIT_KEY] = state  # панель — с временными id
    return out


def _put_title(config: dict, host: str, title) -> None:
    """FB-33 M2d: «Seitentitel» страницы `host` — в `page_titles` (пусто — ключа нет)."""
    from apps.core import page_title

    titles = dict(config.get("page_titles") or {})
    entry = page_title.clean_one(title)
    if entry:
        titles[host] = entry
    else:
        titles.pop(host, None)
    if titles:
        config["page_titles"] = titles
    else:
        config.pop("page_titles", None)


def _put_next(config: dict, text) -> None:
    """FB-33 M2h-5: «Was passiert jetzt» подтверждения (пусто — ключа нет)."""
    from apps.core import confirmation_page

    value = confirmation_page.clean_next(text)
    if value:
        config[confirmation_page.NEXT_KEY] = value
    else:
        config.pop(confirmation_page.NEXT_KEY, None)


#: поля вида строки/★, каждое изменение которых — правка черновика
_VIEW_FIELDS = ("style", "grid", "grouping", "focus")


def changes(saved: dict, draft: dict) -> int:
    """Число несохранённых изменений: добавлено + удалено + скрыто/показано +
    ширина + порядок (один раз) + карточка контактов."""

    def ident(item):
        return item.get("id") or item.get("key")

    old = {ident(i): i for i in saved["items"]}
    new = {ident(i): i for i in draft["items"]}
    common = [k for k in new if k in old]
    count = len(set(new) - set(old)) + len(set(old) - set(new))
    count += sum(
        1 for k in common if bool(old[k].get("enabled", True)) != bool(new[k].get("enabled", True))
    )
    # FB-27 R3: ширина и «с новой строки» — одно изменение на блок.
    count += sum(
        1
        for k in common
        if (old[k].get("width") or "contained", bool(old[k].get("newline")))
        != (new[k].get("width") or "contained", bool(new[k].get("newline")))
    )
    # FB-27 R3b: содержимое блока (текст, подпись, ссылка) — одно изменение на блок;
    # FB-33 M2e: смена вида (ключ блока при том же id) — тоже
    count += sum(
        1
        for k in common
        if (old[k].get("data") or {}) != (new[k].get("data") or {})
        or old[k].get("key") != new[k].get("key")
    )
    # FB-30.16 (ревью R4): вид блоков каталога (вид «Kategorien», вид/сетка ★)
    count += sum(
        1
        for k in common
        # FB-31 P3 (ревью R5): и абзацы ★ «Aktionen», и «Im Fokus»
        if tuple(old[k].get(f) for f in _VIEW_FIELDS) != tuple(new[k].get(f) for f in _VIEW_FIELDS)
    )
    if [k for k in old if k in new] != common:
        count += 1
    if (
        "contact" in draft
        and not _has_section_rows(draft)
        and bool(draft["contact"]) != bool(saved.get("contact", True))
    ):
        count += 1
    from apps.core import page_window

    count += page_window.changed(draft, saved)  # FB-33 M3-6

    # FB-33 M2d: «Seitentitel» — одно изменение
    if "title" in draft and draft["title"] != saved.get("title", {}):
        count += 1
    if "next" in draft and draft["next"] != saved.get("next", ""):
        count += 1  # FB-33 M2h-5
    # FB-33 M2i-5: вкладка «Felder» — одно изменение; «равно сохранённому» черновик не держит
    # (`site_schema.form_op` снимает ключи), поэтому сравнение с сохранённым не нужно
    if "form" in draft:
        count += 1
    if "faq" in draft:  # FB-33 M3-5b: вопросы FAQ — одно изменение
        count += 1

    if "ofaq" in draft:  # FB-33 M2b-2b: свои вопросы объекта — одно изменение
        count += 1
    # FB-27 R4: настройки типа страницы — по одному изменению на настройку.
    count += len(_settings(draft))
    return count


def info(request, config: dict, code: str) -> dict:
    """Состояние черновика страницы для экрана: {"count", "conflict"} (count=0 — чисто)."""
    draft = get(request, code)
    if not draft:
        return {"count": 0, "conflict": False}
    saved = _saved_state(config, bool(draft.get("home")), str(draft.get("host") or ""))
    return {
        "count": changes(saved, draft),
        "conflict": _base_fingerprint(saved, config, draft) != draft.get("base")
        or _keys_conflict(config, draft)
        or faq_conflict(config, draft),
    }


def _keys_conflict(config: dict, draft: dict) -> bool:
    """Значение настройки, которую держит черновик, успели изменить в другом месте."""
    if "kbase" not in draft:  # черновик без настроек (или начатый до R4)
        return False
    return _keys_fingerprint(config, draft.get("kcodes")) != draft["kbase"]


# ───────────── FB-33 M3-1b: окно блока — «Fertig» и «Abbrechen» ─────────────
#: снимки блоков на момент открытия окна: {ref: прообраз}; вне `_saved_state` (отпечаток,
#: счётчик и конфликт их не видят)
WINDOW_KEY = "window"
#: черновик без правок, который держится только ради снимка (см. `get`)
IDLE_KEY = "idle"
IDLE_AT = "idle_at"
#: «пустой» черновик живёт сутки и не занимает места настоящих (`MAX_DRAFTS`)
IDLE_TTL = 24 * 3600
MAX_IDLE = 10
#: снимков не больше трёх (по блоку; две вкладки браузера — два снимка)
WINDOW_MAX = 3
WINDOW_OPS = ("window_done",)
#: операции не из окна блока (перетаскивание в списке, добавление) — снимка не пишут
_NO_SNAPSHOT_OPS = frozenset({"add", "add_row", "adopt", "reset", "move", "delete", "revert"})
#: токен открытия окна (`wopen`): новый при каждом открытии, переживает действия окна
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
#: итог «Abbrechen»
CANCEL_DONE, CANCEL_NOTHING, CANCEL_CONFLICT = "done", "nothing", "conflict"


def new_token() -> str:
    return secrets.token_urlsafe(6)


def clean_token(value) -> str:
    return value if isinstance(value, str) and _TOKEN_RE.match(value) else ""


def _ident(item) -> str:
    return (item.get("id") or item.get("key") or "") if isinstance(item, dict) else ""


def _window_setting_codes(tenant, code: str, ref: str) -> list[str]:
    """Настройки, которые правятся в окне строки `ref`: свои у строки раздела, все
    настройки типа — у ★ и у строки-носителя (как их показывает окно)."""
    from apps.tenants import siteconfig

    own = site_schema.row_settings(code, ref)
    if own:
        return list(own)
    # FB-33 M3-6: и у строки «Einstellungen der Seite» (окно со вкладкой «Seite»)
    if ref in (siteconfig.MAIN_LIST_KEY, site_schema.settings_carrier(code), site_schema.PAGE_REF):
        try:
            return list(site_schema.setting_codes(tenant, code))
        except site_schema.SchemaError:
            # снимок без настроек: «Abbrechen» их не вернёт — видно в логе, не молча
            logger.warning("aufbau window: setting codes of %s/%s unavailable", code, ref)
            return []
    return []


def _record_codes(draft: dict, proto: dict, codes) -> None:
    """Прежнее значение настроек — до первой их правки в этом окне (и «на все списки»)."""
    pending = _settings(draft)
    have = proto.setdefault("codes", [])
    for c in codes or ():
        if c not in have:
            have.append(c)
            if c in pending:
                proto.setdefault("settings", {})[c] = copy.deepcopy(pending[c])


def _snapshot(tenant, code, host, draft, ref, token="", codes=(), source=None) -> None:
    """Прообраз блока `ref` в `draft` — на первой правке после открытия окна. Без токена
    открытия (`wopen`: правка не из окна — список «Blöcke», меню строки) снимка нет; другое
    открытие (другой токен) — снимок заново. `source` — состояние ДО правки: снимок
    записывают после успешной операции (ревью 2)."""
    from apps.core import confirmation_page

    if not token or not ref:
        return
    source = draft if source is None else source
    window = dict(draft.get(WINDOW_KEY) or {}) if isinstance(draft.get(WINDOW_KEY), dict) else {}
    old = window.get(ref)
    if isinstance(old, dict) and old.get("wopen") == token:
        _record_codes(source, old, codes)
        draft[WINDOW_KEY] = window
        return
    items = source.get("items") or []
    at = next((i for i, it in enumerate(items) if _ident(it) == ref), None)
    proto = {
        "item": copy.deepcopy(items[at]) if at is not None else None,
        "at": at,
        # место — по соседу сверху (индекс сдвигается, когда в другой вкладке правят выше)
        "after": _ident(items[at - 1]) if at else None,
        "base": source.get("base"),
        "wopen": token,
    }
    if ref == site_schema.TITLE_REF:
        proto["title"] = ["title" in source, copy.deepcopy(source.get("title"))]
    if host == confirmation_page.HOST and ref == site_schema.NEXT_REF:
        proto["next"] = ["next" in source, source.get("next")]
    if ref == site_schema.PAGE_REF:  # FB-33 M3-6: SEO страницы — в окне «Einstellungen»
        proto["seo"] = ["seo" in source, copy.deepcopy(source.get("seo"))]

    if host == site_schema.FORM_HOST and ref == site_schema.FORM_REF:
        proto["form"] = {k: copy.deepcopy(source[k]) for k in FORM_KEYS if k in source}
    if at is not None and _is_faq_row(source, items[at]):  # FB-33 M3-5b: вопросы FAQ
        proto["faq"] = {k: copy.deepcopy(source[k]) for k in FAQ_KEYS if k in source}

    _object_faq().snapshot(proto, source, items[at] if at is not None else None)  # M2b-2b
    _record_codes(source, proto, [*_window_setting_codes(tenant, code, ref), *codes])
    window.pop(ref, None)
    idents = {_ident(it) for it in draft.get("items") or []}
    # снимки блоков, которых больше нет, места не занимают
    window = {
        r: p
        for r, p in window.items()
        if isinstance(p, dict) and (p.get("item") is None or r in idents)
    }
    window[ref] = proto
    while len(window) > WINDOW_MAX:
        window.pop(next(iter(window)))
    draft[WINDOW_KEY] = window


def _drop_snapshot(draft: dict, ref: str) -> None:
    window = {k: v for k, v in (draft.get(WINDOW_KEY) or {}).items() if k != ref}
    if window:
        draft[WINDOW_KEY] = window
    else:
        draft.pop(WINDOW_KEY, None)


def _restore_key(draft: dict, key: str, entry) -> None:
    present, value = entry
    if present:
        draft[key] = value
    else:
        draft.pop(key, None)


def _place(items: list, proto: dict) -> int:
    """Куда вернуть строку: сразу после прежнего соседа сверху; его нет — прежний индекс."""
    after = proto.get("after")
    if "after" in proto and after is None:
        return 0
    if after:
        at = next((i for i, it in enumerate(items) if _ident(it) == after), None)
        if at is not None:
            return at + 1
    at = proto.get("at")
    return min(max(at if isinstance(at, int) else len(items), 0), len(items))


def _revert(draft: dict, ref: str, proto: dict) -> None:
    """«Abbrechen»: блок `ref` — как в снимке (строка на своём месте, тексты, настройки
    окна); прочие правки черновика (другие блоки, другие вкладки) не трогаются."""
    _drop_snapshot(draft, ref)
    items = [it for it in draft.get("items") or [] if _ident(it) != ref]
    if proto.get("item") is not None:
        items.insert(_place(items, proto), proto["item"])
    draft["items"] = items
    for key in ("title", "next", "seo"):  # FB-33 M3-6: SEO страницы
        if key in proto:
            _restore_key(draft, key, proto[key])
    for part, keys in SIDE_PARTS:
        # FB-33 M2i-5 «Felder», M3-5b вопросы FAQ — как при открытии окна
        if isinstance(proto.get(part), dict):
            for key in keys:
                if key in proto[part]:
                    draft[key] = copy.deepcopy(proto[part][key])
                else:
                    draft.pop(key, None)
    codes = proto.get("codes") or []
    if codes:
        pending = {k: v for k, v in _settings(draft).items() if k not in codes}
        pending.update(proto.get("settings") or {})
        if pending:
            draft["settings"] = pending
        else:
            for key in ("settings", "kbase", "kcodes"):
                draft.pop(key, None)


def _check_normalized(config: dict, draft: dict, home: bool, host: str) -> None:
    """После отката черновик проходит ту же нормализацию, что и витрина (ревью M3-1b): строки
    после нормализации нормализуются в то же самое (идемпотентно) — иначе в лог; черновик
    молча не правится."""
    from apps.tenants import siteconfig

    try:
        once = site_schema.load_items(siteconfig.normalize(overlay(config, draft)), home, host)
        again = site_schema.load_items(
            siteconfig.normalize(overlay(config, {**draft, "items": once})), home, host
        )
    except Exception:  # noqa: BLE001
        logger.warning("aufbau window: draft after revert does not normalize", exc_info=True)
        return
    if once != again:
        logger.warning("aufbau window: draft after revert differs after normalize (%s)", host)


def _working_draft(request, code: str, saved: dict, home: bool, host: str) -> tuple[dict, bool]:
    """Черновик для правки и был ли он. «Пустой» (только снимок) начинается заново с
    сохранённого — снимки окна остаются."""
    raw = _raw(request, code)
    if raw and not raw.get(IDLE_KEY):
        return raw, True
    draft = {**copy.deepcopy(saved), "base": _fingerprint(saved), "home": home, "host": host}
    if raw and raw.get(WINDOW_KEY):
        draft[WINDOW_KEY] = raw[WINDOW_KEY]
    return draft, raw is not None


def cancel(request, tenant, code: str, ref: str, token: str = "") -> str:
    """«Abbrechen» окна блока: `CANCEL_DONE` — блок как на момент открытия;
    `CANCEL_NOTHING` — откатывать нечего (снимка нет: окно без правок, другое открытие,
    «Speichern»/«Verwerfen» в другой вкладке, сессия истекла); `CANCEL_CONFLICT` — страницу
    тем временем сохранили в другом месте, черновик не трогаем."""
    from apps.tenants import siteconfig

    _pt, host, home = site_schema.resolve(tenant, code)
    if _raw(request, code) is None:
        return CANCEL_NOTHING
    config = siteconfig.normalize(tenant.site_config)
    saved = _saved_state(config, home, host)
    draft, _existed = _working_draft(request, code, saved, home, host)
    proto = (draft.get(WINDOW_KEY) or {}).get(ref)
    if not isinstance(proto, dict):
        return CANCEL_NOTHING
    token = clean_token(token)
    if not token or proto.get("wopen") != token:
        # снимок прежнего открытия: в этом окне правок не было — откатывать нечего
        _drop_snapshot(draft, ref)
        _settle(request, code, draft, saved, ref)
        return CANCEL_NOTHING
    if proto.get("base") != _base_fingerprint(saved, config, draft):
        return CANCEL_CONFLICT
    _revert(draft, ref, proto)
    _check_normalized(config, draft, home, host)
    _settle(request, code, draft, saved, ref)
    return CANCEL_DONE


def op(
    request,
    tenant,
    code: str,
    op_name: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
    token: str = "",
    notes: list | None = None,
) -> str:
    """Одна правка схемы — в черновик (база не меняется). SchemaError на недопустимом.
    `token` — токен открытия окна блока (`wopen`, FB-33 M3-1b); `notes` — сюда правка
    вкладки «Felder» кладёт сообщения владельцу (FB-33 M2i-5)."""
    from apps.tenants import siteconfig

    _pt, host, home = site_schema.resolve(tenant, code)
    config = siteconfig.normalize(tenant.site_config)
    saved = _saved_state(config, home, host)
    draft, existed = _working_draft(request, code, saved, home, host)
    if op_name in WINDOW_OPS:
        # FB-33 M3-1b: «Fertig» — снимок больше не нужен. Без черновика — писать нечего.
        if not existed:
            return ref
        _drop_snapshot(draft, ref)
        return _settle(request, code, draft, saved, ref)
    token = clean_token(token)
    window_ref = ref
    # снимок — ПОСЛЕ успешной правки, с состояния до неё (отказ SchemaError его не пишет)
    before = copy.deepcopy(draft) if token and op_name not in _NO_SNAPSHOT_OPS else None
    if (
        op_name in ("add", "add_row", "adopt")
        and host.startswith(siteconfig.CATEGORY_HOST_PREFIX)
        and siteconfig.category_hosts_full(config, host)
    ):
        raise site_schema.SchemaError("hosts")
    elif (
        op_name in ("add", "add_row")
        and siteconfig.is_object_host(host)
        and siteconfig.object_hosts_full(config, host)
        and not _room_after_purge(tenant, host)
    ):
        raise site_schema.SchemaError("objects")
    elif op_name in ("adopt", "reset"):
        # FB-27 R7: своя схема категории — взять блоки каталога или вернуться к ним.
        draft["items"] = site_schema.category_items(config, host, draft["items"], op_name)
        draft.pop(WINDOW_KEY, None)  # строки заменены целиком — их снимки больше не годятся
        ref = ""
    elif _m36_edit(host, ref, op_name, fields):
        # FB-33 M3-6: SEO страницы, вид категории, «Wo zeigen», закреплённые правовые строки
        ref = _m36_op(request, config, draft, code, host, saved, op_name, ref, fields, notes)
    elif ref == site_schema.TITLE_REF:
        # FB-33 M2d: «Seitentitel» — не строка `page_blocks`: тексты и вид — в черновике
        ref = site_schema.title_op(host, draft, op_name, fields)
    elif site_schema.is_next_edit(host, ref, op_name):
        # FB-33 M2h-5: текст «Was passiert jetzt» — в черновике, строка остаётся на месте
        ref = site_schema.next_op(host, draft, op_name, fields)
    elif site_schema.is_form_edit(host, ref, op_name):
        # FB-33 M2i-5: вкладка «Felder» — поля формы заявки в черновике, строка на месте
        ref = site_schema.form_op(tenant, config, draft, fields, notes)
    elif _is_tiles_edit(draft, ref, op_name, fields):
        # FB-33 M3-5b: плашки Schnellzugriff и набор — одной формой окна
        _tiles_op(draft, ref, fields, notes)

    elif _object_faq().is_window_edit(request, draft, ref, op_name):
        # FB-33 M2b-2b: FAQ на детальной — свои вопросы, выбор источника (общие — `_faq_op`)
        ref = _object_faq().window_op(request, config, draft, ref, notes)
    elif is_faq_edit(request, draft, ref, op_name):
        # FB-33 M3-5b: вопросы FAQ в окне блока — в черновике, строка на месте
        ref = _faq_op(config, draft, ref, request.POST, notes, request)
    else:
        ref = site_schema.mutate(
            draft["items"],
            code,
            op_name,
            ref,
            block_type,
            value,
            fields,
            config.get("block_templates"),
            notes,
        )
    if op_name == "delete":
        _drop_snapshot(draft, window_ref)  # блока больше нет — и снимка его
    elif before is not None:
        _snapshot(tenant, code, host, draft, window_ref, token, source=before)
    return _settle(request, code, draft, saved, ref)


def _m36_edit(host: str, ref: str, op_name: str, fields) -> bool:
    """FB-33 M3-6: правка окна, которую ведут `page_window`, `window_banner`, `legal_buttons`."""
    from apps.core import page_window

    return page_window.is_seo_edit(host, ref, op_name, fields) or page_window.is_view_reset(
        host, ref, op_name
    )


def _m36_op(request, config, draft, code, host, saved, op_name, ref, fields, notes) -> str:
    from apps.core import page_window

    if page_window.is_seo_edit(host, ref, op_name, fields):
        return page_window.seo_op(config, draft, host, fields, saved)
    return page_window.view_reset(draft, ref)


def _settle(request, code: str, draft: dict, saved: dict, ref: str = "") -> str:
    if "title" not in draft:  # черновик до «Seitentitel» (ревью M2d) — сравнение без него
        saved = {k: v for k, v in saved.items() if k != "title"}
    if "next" not in draft:
        saved = {k: v for k, v in saved.items() if k != "next"}
    if "seo" not in draft:  # FB-33 M3-6: черновик до SEO в окне — сравнение без него
        saved = {k: v for k, v in saved.items() if k != "seo"}
    current = {k: draft.get(k) for k in saved}
    # Вернулись к сохранённому (скрыл и снова показал) — черновика нет.
    clean = (
        _fingerprint(current) == _fingerprint(saved) == draft.get("base")
        and not _settings(draft)
        and not any(part in draft for part, _keys in SIDE_PARTS)  # M2i-5, M3-5b, …
    )
    if clean and draft.get(WINDOW_KEY):
        # FB-33 M3-1b: окно блока открыто — снимок для «Abbrechen» держится, но черновика
        # для экрана нет (`get`); у «пустого» черновика — срок
        draft[IDLE_KEY] = True
        draft[IDLE_AT] = int(time.time())
        _put(request, code, draft)
    else:
        draft.pop(IDLE_KEY, None)
        draft.pop(IDLE_AT, None)
        _put(request, code, None if clean else draft)
    return ref


def setting_op(
    request,
    tenant,
    code: str,
    setting: str,
    value,
    output: dict | None = None,
    apply_all: bool = False,
    ref: str = "",
    token: str = "",
) -> list[str]:
    """FB-27 R4: настройка типа страницы — в черновик. Возвращает коды «на все списки»,
    которым значение не подошло (их пропустили). SchemaError / PageSettingError — если
    саму настройку здесь менять нельзя или значение недопустимо."""
    from apps.core import page_settings
    from apps.tenants import siteconfig

    _pt, host, home = site_schema.resolve(tenant, code)
    codes = site_schema.setting_codes(tenant, code)
    if setting not in codes:
        raise site_schema.SchemaError("setting")
    config = siteconfig.normalize(tenant.site_config)
    saved = _saved_state(config, home, host)
    draft, _existed = _working_draft(request, code, saved, home, host)
    targets = [setting]
    if apply_all and setting in page_settings.APPLY_ALL_LAYOUTS:
        targets += [
            other
            for other in page_settings.APPLY_ALL_LAYOUTS
            if other != setting
            and page_settings.type_active(tenant, page_settings.APPLY_ALL_TYPES[other])
        ]
    before = copy.deepcopy(draft)
    pending = dict(_settings(draft))
    gate = page_settings.composition_gate(config)
    skipped = []
    for target in targets:
        shown = _apply_settings(copy.deepcopy(config), {"settings": pending})
        try:
            cleaned = page_settings.validate(tenant, target, value, gate, config=shown)
            after = page_settings.apply_override(config, target, cleaned, output)
        except page_settings.PageSettingError:
            if target == setting:
                raise
            skipped.append(target)
            continue
        # Равно сохранённому — записи в черновике нет («вернул как было»).
        same = siteconfig.normalize(after) == config
        if same:
            pending.pop(target, None)
        else:
            pending[target] = {"v": cleaned, "o": output}
    if pending:
        draft["settings"] = pending
        if "kbase" not in draft:
            tracked = sorted(set(codes) | set(pending))
            draft["kcodes"] = tracked
            draft["kbase"] = _keys_fingerprint(config, tracked)
    else:
        for key in ("settings", "kbase", "kcodes"):
            draft.pop(key, None)
    # FB-33 M3-1b: снимок окна ★/носителя — со всеми настройками, которые правка задела
    # (и «на все списки»), с состояния до неё; отказ PageSettingError его не пишет
    _snapshot(tenant, code, host, draft, ref, clean_token(token), targets, source=before)
    _settle(request, code, draft, saved)
    return skipped


def discard(request, code: str) -> None:
    _put(request, code, None)


@transaction.atomic
def commit(request, tenant, code: str, *, force: bool = False, notes: list | None = None) -> bool:
    """Записать черновик страницы на сайт. `DraftConflict`, если сохранённое успели
    изменить в другом месте (и не задан `force`). False — черновика нет (двойная
    отправка, сессия истекла): вызывающий не должен сообщать об успехе."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    draft = get(request, code)
    if not draft:
        return False
    try:
        _pt, host, home = site_schema.resolve(tenant, code)
    except site_schema.SchemaError:
        # Страницы больше нет (модуль выключен, страница удалена): черновик некуда
        # записать — убираем его, иначе он висел бы невидимым до конца сессии.
        _put(request, code, None)
        raise
    gate = None
    if _settings(draft):
        from apps.core import page_settings

        # ~10 EXISTS по таблицам тенанта — до блокировки строки, как в `write`
        gate = page_settings.composition_gate(tenant.site_config or {})
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = siteconfig.normalize(locked.site_config)
    if not force and (
        _base_fingerprint(_saved_state(config, home, host), config, draft) != draft.get("base")
        or _keys_conflict(config, draft)
    ):
        raise DraftConflict(code)
    faq_moved = faq_conflict(config, draft)  # FB-33 M3-5b: только при вопросах в черновике
    if faq_moved and not force:
        # своё сообщение: страницу никто не трогал — изменились общие вопросы (Студия, канва)
        raise site_schema.SchemaError("faq_conflict")
    from apps.core import page_window

    # FB-33 M3-6: SEO страницы
    page_window.commit(config, host, draft)

    from apps.core import hero_tiles

    old_blocks = {
        it.get("id"): it.get("data")
        for it in site_schema.load_items(config, home, host)
        if isinstance(it, dict) and it.get("id")
    }
    site_schema.store_items(config, home, host, copy.deepcopy(draft["items"]))
    # FB-33 M3-5b: переводы своих подписей плашек — только у неизменённых немецких подписей
    hero_tiles.prune_label_overlays(config, home, host, old_blocks)
    _commit_object(
        config, host, draft["items"], getattr(request, "user", None), draft, notes, force
    )
    if "title" in draft:
        _put_title(config, host, draft["title"])
    if "next" in draft:
        _put_next(config, draft["next"])
    if "faq" in draft:
        # FB-33 M3-5b: вопросы — под блокировкой строки, единственным писателем; запись
        # поверх (force) при изменённом сохранённом — по тексту и в лог (`faq_content.put`)
        from apps.core import faq_content

        pending = draft["faq"]
        if not any(_is_faq_row(draft, it) for it in draft["items"]):
            # блок FAQ из черновика убрали — правку вопросов «в тени» не публикуем
            if notes is not None:
                notes.append(faq_content.dropped_note())
        else:
            faq_content.put(
                config, pending.get("items") or [], pending.get("src"), draft.get("faq_base")
            )
            if faq_moved and notes is not None:
                notes.append(faq_content.faq_forced_note())
    if "form" in draft and host == site_schema.FORM_HOST:
        # FB-33 M2i-5: поля формы заявки — под блокировкой строки бизнеса: дельта черновика
        # поверх заблокированного сохранённого (ревью H2), номера новых вопросов — от
        # СОХРАНЁННОГО `next_id` (`form_spec.put`, единственный писатель)
        from apps.core import form_spec

        state = form_state(config, draft, notes)
        try:
            form_spec.put(config, "anfrage", state)
        except form_spec.FormSpecError as exc:
            raise site_schema.SchemaError("ids") from exc
    if host == "info" and "contact" in draft and not _has_section_rows(draft):
        # FB-32 S6a: черновик, начатый до строк разделов, — карточка контактов как раньше
        if draft["contact"]:
            config.pop("about_contact", None)
        else:
            config["about_contact"] = False
    if _settings(draft):
        # FB-27 R4: настройки типа — в той же транзакции, что блоки; каждая проверяется
        # заново по заблокированной строке. Недопустимая → PageSettingError, ничего не
        # записано, черновик остаётся.
        config = page_settings.apply_many(locked, config, _settings(draft), gate)
    locked.site_config = siteconfig.normalize(config)
    locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = locked.site_config
    _put(request, code, None)
    return True


#: R8 (ревью безопасности): разделы страницы объекта — то же право, что у формы объекта
OBJECT_EDIT_VIEWS = {
    "product": "catalog:product-edit",
    "service": "booking:service-edit",
    "stay": "stays:unit-edit",
    "event": "events:edit",
    "tour": "events:tour-edit",
}


def _object_faq():
    """FB-33 M2b-2b: свои вопросы FAQ объекта (`apps.core.object_faq`, ленивый импорт)."""
    from apps.core import object_faq

    return object_faq


def _commit_object(
    config: dict,
    host: str,
    items: list[dict],
    user=None,
    draft: dict | None = None,
    notes: list | None = None,
    force: bool = False,
) -> None:
    """R8: разделы схемы объекта — в его `page_override`, FB-33 M2b-2b: свои вопросы FAQ
    черновика — в сам объект (в транзакции `commit`, после блокировки строки бизнеса — тот же
    порядок блокировок везде). Одна блокировка объекта, у каждой части своя проверка права и
    свои поля записи."""
    from apps.core import detail_parts

    kind = detail_parts.object_kind(host)
    if not kind:
        return
    locked = _lock_object(host)
    if locked is None:
        # объект удалили, пока шла правка — блоки сохранены, разделов и вопросов больше нет
        if draft and "ofaq" in draft and notes is not None:
            notes.append(_object_faq().gone_note())
        return
    fields = _commit_sections(config, host, items, user, locked, kind)
    fields += _object_faq().commit(locked, kind, draft, user, notes, force)
    if not fields:
        return
    if any(f.name == "updated_at" for f in locked._meta.concrete_fields):
        fields.append("updated_at")  # как у формы объекта (sitemap, портал)
    locked.save(update_fields=list(dict.fromkeys(fields)))


def _lock_object(host: str):
    """Объект хоста своих блоков под `select_for_update` (None — его нет)."""
    from apps.core import detail_parts

    obj = detail_parts.object_for_host(host)
    if obj is None:
        return None
    return type(obj).objects.select_for_update().filter(pk=obj.pk).first()


def _commit_sections(config: dict, host: str, items: list[dict], user, locked, kind: str) -> list:
    """R8: разделы схемы объекта → `page_override` (состояние — по объекту, заблокированному
    в `_lock_object`: вкладка карточки могла успеть записать). Возвращает поля записи."""
    from apps.core import detail_parts, object_structure, view_perms

    _rows, state = detail_parts.object_lift(config, host, copy.deepcopy(items), obj=locked)
    if state is None:
        return []
    module = detail_parts.module_of(detail_parts.shared_host(host))
    value = object_structure.schema_value(locked, module, state)
    if value == object_structure._raw(locked):
        return []
    if user is not None and not view_perms.allowed(user, OBJECT_EDIT_VIEWS[kind], "POST"):
        # сотрудник с правом на сайт, но без права на этот объект: разделы не меняет
        raise site_schema.SchemaError("rights")
    locked.page_override = value
    return ["page_override"]


def _room_after_purge(tenant, host) -> bool:
    """FB-29.4b: места для своих блоков объекта нет — сначала убрать блоки удалённых
    объектов (хосты-призраки), затем проверить ещё раз."""
    from apps.core import object_structure
    from apps.tenants import siteconfig

    if not object_structure.purge_ghost_hosts(tenant):
        return False
    tenant.refresh_from_db(fields=["site_config"])
    return not siteconfig.object_hosts_full(siteconfig.normalize(tenant.site_config), host)


def prune(request, known_codes) -> None:
    """Убрать черновики страниц, которых на экране больше нет (тип выключен, страница
    удалена) — открыть их нельзя, а место в сессии они занимали бы до её конца."""
    known = set(known_codes)
    for code in [c for c in _all(request) if c not in known]:
        _put(request, code, None)
