"""FB-33 M2d: «Seitentitel» — свой заголовок и вступление страниц-списков и форм.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2d» и решения владельца. Заголовок
и вступление зашиты переводимыми строками в шаблонах; владелец задаёт свои в
`site_config["page_titles"][host] = {title, intro, align}`. Пустые поля — прежний текст,
пустой хост не хранится: страница байт-в-байт прежняя (замок
`test_fb33_m2d_page_title_before`).

Строка «Seitentitel» в схеме страницы — вычисляемая и неподвижная (`TITLE_REF`, как
«Buchung» у деталей): она не хранится в `page_blocks` и не влияет на разделы.
Модуль не импортирует `siteconfig` на уровне модуля (тот нормализует через него).
"""

from __future__ import annotations

import re

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

#: формы: свои блоки «сверху» рисуются НАД H1 — там строка «Seitentitel» стоит перед
#: разделом формы; у страниц-списков H1 — самое верхнее (замок M2d-0)
FORMS = frozenset({"anfrage", "event_calendar", "gift", "loyalty", "message", "passes", "teachers"})
H1_FIRST = frozenset(HEAD_HOSTS) - FORMS

ALIGNS = ("", "center")
TITLE_MAX = 120
INTRO_MAX = 400


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
