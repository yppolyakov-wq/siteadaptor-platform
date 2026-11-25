"""FB-33 M2d: «Seitentitel» — свой заголовок и вступление страниц-списков и форм.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2d» и решения владельца. Заголовок
и вступление зашиты переводимыми строками в шаблонах; владелец задаёт свои в
`site_config["page_titles"][host] = {title, intro, align}`. Пустые поля — прежний текст,
пустой хост не хранится: страница байт-в-байт прежняя (замок
`test_fb33_m2d_page_title_before`).

Поля «Seitentitel» правятся в окне ★-строки страницы (FB-33 M5b-2); строки «Seitentitel» в
схеме больше нет, `TITLE_REF` — только старый ref (закладки, сессии до деплоя), который
`site_schema.page_ref` читает как ★-строку. Заголовок не хранится в `page_blocks`.
Модуль не импортирует `siteconfig` на уровне модуля (тот нормализует через него).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

TITLE_REF = "__title"

#: FB-33 M5b-2: «Seitentitel» правится в окне ★-строки страницы (`site_schema.PAGE_REF`) —
#: снимок окна и переводы заголовка живут под `__page`, старые ключи сессии `__title`
#: переименовываются (`aufbau_draft._raw`), ref `__title` — только псевдоним
#: (`site_schema.page_ref`: закладки, открытые до деплоя окна). Строки «Seitentitel» в схеме
#: больше нет — на её месте серая метка (`site_schema.title_hint_at`).

#: страницы со своим заголовком: списки, формы и страница акций (M2d-3)
HEAD_HOSTS = (
    "services",
    "stay_rooms",
    "events",
    "tours",
    "blog",
    "reviews",
    "wishlist",
    "combos",
    "team",
    "gallery",
    "message",
    "anfrage",
    "gift",
    "loyalty",
    "passes",
    "teachers",
    "event_calendar",
    "promos",
)

#: формы: свои блоки «сверху» рисуются НАД H1 — там серая метка «Überschrift der Seite»
#: (M5b-2, `site_schema.title_hint_at`) стоит перед разделом формы; у страниц-списков H1 — самое верхнее (замок M2d-0)
FORMS = frozenset({"anfrage", "event_calendar", "gift", "loyalty", "message", "passes", "teachers"})
H1_FIRST = frozenset(HEAD_HOSTS) - FORMS

ALIGNS = ("", "center")
TITLE_MAX = 120
INTRO_MAX = 400

#: FB-33 стопка 15 M5e-2b (вариант A): шапка каталога «Produkte» — верхние ключи `site_config`
#: (H1.2, правка и на канве); выравнивания у каталога нет (§0.3 №3)
CATALOG = "catalog"
CATALOG_KEYS = {"title": "catalog_title", "intro": "catalog_intro"}
_CAPS = {"title": TITLE_MAX, "intro": INTRO_MAX}


def _s(value, limit: int) -> str:
    """Строка без лишних пробелов и переносов (они попали бы в H1 и в <title>)."""
    return re.sub(r"\s+", " ", value).strip()[:limit] if isinstance(value, str) else ""


def clean_one(raw) -> dict:
    """Одна страница: только непустые поля (пусто — прежний текст шаблона)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    title = _s(raw.get("title"), TITLE_MAX)
    intro = _s(raw.get("intro"), INTRO_MAX)
    if title:
        out["title"] = title
    if intro:
        out["intro"] = intro
    if raw.get("align") in ALIGNS and raw.get("align"):
        out["align"] = raw["align"]
    return out


def normalize(raw) -> dict:
    """`page_titles`: только известные страницы и непустые записи (presence-minimal)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for host in HEAD_HOSTS:
        entry = clean_one(raw.get(host))
        if entry:
            out[host] = entry
    return out


def get(site, host: str) -> dict:
    """То, что рисует страница: {title, intro, center, custom} (пусто — прежний текст)."""
    titles = site.get("page_titles") if isinstance(site, dict) else None
    entry = clean_one((titles or {}).get(host))
    from apps.core.seo_meta import DESC_MAX, TITLE_MAX, clamp

    return {
        "title": entry.get("title", ""),
        "intro": entry.get("intro", ""),
        "center": entry.get("align") == "center",
        "custom": bool(entry),
        # SEO-ревью M2d: свой заголовок — и в <title>, вступление — в meta description
        # (длины, которые показывает поисковик)
        "seo_title": clamp(entry.get("title", ""), TITLE_MAX),
        "seo_desc": clamp(entry.get("intro", ""), DESC_MAX),
    }


# ───────────── FB-33 стопка 15 M5e-2b: один писатель шапки листинга ─────────────


def has_head(host) -> bool:
    """У страницы своя шапка (H1 и вступление) в окне ★-строки: `HEAD_HOSTS` и каталог."""
    return host in HEAD_HOSTS or host == CATALOG


#: вступление с переносами строк — только там, где витрина рисует его `whitespace-pre-line`
#: (каталог: `products.html`, `category/_root_header.html`, A9). Списки и формы рисуют
#: вступление однострочным абзацем — шаблоны M2d держит замок байт-в-байт, поэтому у них
#: переносы схлопываются (`clean_one`). Правило одно и живёт здесь (`_text`).
KEEPS_BREAKS = frozenset({CATALOG})


def _text(host: str, name: str, value) -> str:
    """Текст поля шапки из формы: заголовок — одной строкой; вступление хранит переносы
    строк только у `KEEPS_BREAKS`, иначе схлопывает пробелы (как `clean_one`)."""
    if not isinstance(value, str):
        return ""
    if name == "intro" and host in KEEPS_BREAKS:
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return " ".join(value.split())


def head(config, host: str) -> dict:
    """Сохранённая шапка страницы {title?, intro?, align?} — то, что правит окно (пусто —
    прежний текст шаблона). У каталога — как есть (старое длинное значение не режется)."""
    config = config if isinstance(config, dict) else {}
    if host == CATALOG:
        out = {}
        for name, key in CATALOG_KEYS.items():
            value = config.get(key)
            value = value.strip() if isinstance(value, str) else ""
            if value:
                out[name] = value
        return out
    if host in HEAD_HOSTS:
        return clean_one((config.get("page_titles") or {}).get(host))
    return {}


def clean_head(host: str, raw, before: dict | None = None, cut: list | None = None) -> dict:
    """Шапка из правки (окно, канва, прямая правка схемы). Поле, равное прежнему (`before`),
    остаётся прежним без обрезки (A9); изменённое — по правилу `_text` и с потолком; имена
    обрезанных полей — в `cut` (сообщение «gekürzt»). `align` — только у `HEAD_HOSTS`."""
    raw = raw if isinstance(raw, dict) else {}
    before = before if isinstance(before, dict) else {}
    out = {}
    for name, cap in _CAPS.items():
        text = _text(host, name, raw.get(name))
        old = before.get(name)
        if text and isinstance(old, str) and text == _text(host, name, old):
            out[name] = old
        elif text:
            if len(text) > cap and cut is not None:
                cut.append(name)
            out[name] = text[:cap].strip()
    align = raw.get("align")
    if host in HEAD_HOSTS and align and align in ALIGNS:
        out["align"] = align
    return out


def _unknown(host: str):
    from apps.core.site_schema import SchemaError

    logger.warning("page head: host %r has no own head — not written", host)
    return SchemaError("block")


def put_head(config: dict, host: str, entry) -> None:
    """Записать шапку страницы `host` в `config` (пусто — ключа нет): `page_titles[host]` у
    `HEAD_HOSTS`, `catalog_title`/`catalog_intro` у каталога. Единственный писатель шапки;
    хост без своей шапки — `SchemaError("block")` (как `site_schema.title_op`)."""
    if not has_head(host):
        raise _unknown(host)
    clean = clean_head(host, entry, head(config, host))
    if host == CATALOG:
        for name, key in CATALOG_KEYS.items():
            if clean.get(name):
                config[key] = clean[name]
            else:
                config.pop(key, None)
        return
    titles = dict(config.get("page_titles") or {})
    if clean:
        titles[host] = clean
    else:
        titles.pop(host, None)
    if titles:
        config["page_titles"] = titles
    else:
        config.pop("page_titles", None)


#: ответ записи одного поля (`set_field`): как `home_texts.set_text` (M5e-1a)
CHANGED, CAPPED = "changed", "capped"


def inline_field(field) -> tuple[str, str] | None:
    """Поле инлайн-правки канвы → (хост, поле шапки): `catalog_title`/`catalog_intro` и
    `page_titles.<хост>.title|intro`; иначе None."""
    if not isinstance(field, str):
        return None
    for name, key in CATALOG_KEYS.items():
        if field == key:
            return CATALOG, name
    parts = field.split(".")
    if len(parts) == 3 and parts[0] == "page_titles" and parts[1] in HEAD_HOSTS:
        if parts[2] in _CAPS:
            return parts[1], parts[2]
    return None


def set_field(config: dict, host: str, name: str, value, locale: str = "") -> str:
    """Одно поле шапки с канвы — тем же правилом и потолками, что окно: немецкий текст —
    `put_head`, перевод (`locale`) — в оверлей по `tr_path`. Ответ — `CHANGED`/`CAPPED`."""
    from apps.tenants import siteconfig

    cut: list = []
    if locale:
        overlay = (config.get("i18n") or {}).get(locale) or {}
        node = overlay
        for step in tr_path(host, name):
            node = node.get(step) if isinstance(node, dict) else None
        before = {name: node} if isinstance(node, str) else {}
        text = clean_head(host, {name: value}, before, cut).get(name, "")
        siteconfig.set_overlay_value(config, locale, tr_path(host, name), text)
    else:
        current = head(config, host)
        put_head(config, host, clean_head(host, {**current, name: value}, current, cut))
    return CAPPED if cut else CHANGED


def shown_text(config, host: str, name: str) -> str:
    """Сохранённое поле шапки (ответ канве на обрезку)."""
    return head(config, host).get(name, "")


def tr_path(host: str, field: str) -> tuple:
    """Путь перевода поля шапки в оверлее `i18n[<язык>]` (A4: как у блоков)."""
    if host == CATALOG:
        return (CATALOG_KEYS[field],)
    return ("page_titles", host, field)


def catalog_shown(config, locale: str | None) -> dict:
    """Шапка каталога на витрине в языке `locale`: перевод (оверлей), иначе немецкий текст.
    Перевод не строкой (испорченный оверлей) — немецкий текст и одно предупреждение."""
    config = config if isinstance(config, dict) else {}
    overlay = config.get("i18n") if isinstance(config.get("i18n"), dict) else {}
    node = overlay.get(locale) if locale and isinstance(overlay.get(locale), dict) else {}
    out, bad = {}, []
    for name, key in CATALOG_KEYS.items():
        value = node.get(key)
        if value is not None and not isinstance(value, str):
            bad.append(key)
        if not (isinstance(value, str) and value.strip()):
            value = config.get(key)
        out[name] = value.strip() if isinstance(value, str) else ""
    if bad:
        logger.warning("catalog head: overlay %s for %s is not text — German shown", bad, locale)
    return out
