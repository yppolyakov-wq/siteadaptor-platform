"""FB-25: «Website › Seitenaufbau» — схема блоков каждого типа страницы витрины.

Чтение: типы страниц реестра Студии (`studio_pages.PAGE_TYPES`), у каждого — список блоков
(главная — `sections`, прочие — `page_blocks[<хост>]` с маркером «★ Hauptliste»).
Правка (FB-25b, решение владельца 2026-11-07): показать/скрыть, выше/ниже, удалить, добавить
блок. Пишет ТОЛЬКО `sections` или один хост `page_blocks` (targeted-write W9-3) под
блокировкой строки тенанта; переводы C-блоков выравниваются по личности блока
(`siteconfig.realign_block_overlays`, иначе перестановка сдвинула бы их на чужой блок).
Тонкие настройки блока — в Студии («In Studio bearbeiten»).
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass
from fractions import Fraction

from django.db import DatabaseError, transaction
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import block_catalog, studio_pages
from apps.core import detail_parts as _sec_parts
from apps.core.page_axes_migration import read_old
from apps.core.page_title import TITLE_REF

logger = logging.getLogger(__name__)

#: Типы, у которых нет своей страницы без параметра — превью строим по первой записи.
_SAMPLES = {
    "product": ("apps.catalog.models", "Product", {"is_active": True}),
    "category": ("apps.catalog.models", "Category", {"is_active": True}),
    # FB-29 R2 (ревью): у этих типов страница открывается только по записи — без образца
    # владелец не видел бы свои блоки в превью.
    "promo": ("apps.promotions.models", "Promotion", {"status": "active"}),
    "service": ("apps.booking.models", "Service", {"is_active": True}),
    "stay": ("apps.stays.models", "StayUnit", {"is_active": True}),
    "combo": ("apps.catalog.models", "Combo", {"is_active": True}),  # FB-32 S6g-3
}


@dataclass
class PageRow:
    code: str
    label: str
    host: str  # "" у главной (у неё sections)
    count: int
    preview_url: str


def _detail_label(host: str, item: dict) -> str:
    """FB-31 P5: подпись строки раздела детали — из реестра разделов."""
    from apps.core import detail_parts, detail_sections

    module = detail_parts.module_of(detail_parts.shared_host(host or ""))  # R8: и объект
    if not module or item.get("id"):
        return ""
    label = str(detail_sections.section_labels(module).get(item.get("key"), ""))
    only = detail_sections.only_of(module, item.get("key"))
    if label and only and not detail_parts.object_kind(host or ""):
        # FB-33 M2g: общая страница событий и туров — чей это раздел
        label = f"{label} · {_ONLY_LABELS[only]}"
    return label


#: FB-33 M2g: подписи «чей раздел» на общей странице событий и туров
_ONLY_LABELS = {"event": gettext_lazy("nur Veranstaltungen"), "tour": gettext_lazy("nur Touren")}


def _fixed_section(host, item: dict) -> bool:
    """FB-32 S6a: строка раздела страницы с постоянным порядком («Über uns», «Seite»); FB-33
    M2g: и строка раздела «на месте» (группы и серия события, «Teilen» акции)."""
    if not item.get("id") and item.get("key") in _sec_parts.in_place_keys(host or ""):
        return True
    if not item.get("id") and item.get("key") in _sec_parts.pinned_keys(host or ""):
        return True  # FB-33 M2h: позиции, форма и итог корзины
    return (
        not item.get("id")
        and _sec_parts.module_of(host or "") in _sec_parts.FIXED_ORDER_MODULES
        and item.get("key") in _sec_parts.section_keys(host or "")
    )


def _sections_label(key: str) -> str:
    from apps.tenants import siteconfig

    for k, label, _default in siteconfig.SECTIONS:
        if k == key:
            return str(label)
    return str(siteconfig.CBLOCK_LABELS.get(key, key))


def _preview_url(pt) -> str:
    if pt.code == "booking_slots":
        return _slots_preview_url()
    for name in pt.url_names:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    sample = _SAMPLES.get(pt.code)
    if sample:
        import importlib

        module, model_name, flt = sample
        model = getattr(importlib.import_module(module), model_name)
        obj = model.objects.filter(**flt).order_by("pk").first()
        if obj is not None and hasattr(obj, "get_absolute_url"):
            try:
                return obj.get_absolute_url()
            except Exception:  # noqa: BLE001 — превью необязательно
                return ""
        if obj is not None:
            for name in pt.url_names:  # запись без своего адреса — маршрут типа по pk
                try:
                    return reverse(name, args=[obj.pk])
                except NoReverseMatch:
                    continue
    return ""


def _slots_preview_url() -> str:
    """FB-32 S6g-2: «Tisch reservieren», если столы онлайн есть (иначе /tisch/ — 404), либо
    страница времени первого ресурса."""
    from apps.booking import table_rules
    from apps.booking.models import Resource

    if table_rules.online_tables().exists():
        return reverse("storefront-tisch")
    res = Resource.objects.filter(is_active=True, bookable_online=True).order_by("pk").first()
    return reverse("storefront-termin-slots", args=[res.pk]) if res is not None else ""


#: FB-27 R4: страницы, у которых блоки есть, а `block_host` в реестре типов не объявлен
#: (обзор акций: хост «promos» выводится шаблоном и знает основной список). Здесь, а не
#: в `studio_pages`: объявление там изменило бы и панель Студии.
EXTRA_HOSTS = {"promos": "promos", "promo_group": "promo_group"}  # R6: «Alle Angebotsgruppen»


def _host(pt) -> str:
    # FB-30.16 R5: «Alle Kategorien» — свой хост общих блоков страниц категорий (витрина
    # берёт его у категорий без своей схемы; пока не сохранён — блоки каталога)
    if pt.code == CATEGORY:
        return "category"
    return pt.block_host or EXTRA_HOSTS.get(pt.code, "")


_STRUCT_FIELDS = ("key", "id", "enabled", "width", "pos", "newline")


#: FB-27 R8d: блоки, чьи данные — выбор, а не текст (источник и фильтры «Liste», ручной
#: состав, встроенная страница, вид карточки контактов). Их задаёт «Seitenaufbau».
OWNED_DATA_KINDS = ("list", "textpage", "contact_card")
#: То же у встроенного списка главной: что, сколько и как он показывает, правит панель
#: «Seitenaufbau» — эти поля строки входят в отпечаток и переживают устаревшую вкладку.
BUILTIN_OWNED_FIELDS = ("data", "limit", "layout", "source", "style")
#: FB-29.2: выбор места показа у блока «Banner» (баннеры и настройки слайдера).
_BANNER_CHOICE_FIELDS = ("pick", "auto", "interval", "arrows", "from_page", "single")
#: FB-33 M4b: раскладка встроенного списка, которую правит окно блока («Wie anordnen»:
#: колонки — с видом «N в строке», ряды, вывод сеткой/лентой). Остальное в `layout`
#: (хвост ряда, симметрия, колонки 📱/▭) — «Feinschliff» Студии.
WINDOW_LAYOUT_KEYS = ("preset", "cols", "rows", "scroll")
#: FB-33 M4b (ревью №2): раскладка встроенного списка, которую пишет Студия («Feinschliff»);
#: прочие ключи `layout` (отступ, ширина, размер страницы, темп…) — как сохранено.
STUDIO_LAYOUT_KEYS = ("tail", "balance", "mobile", "tablet")
#: FB-33 M4b: что из строки встроенного списка правит только окно (Was · Wie · Karte).
_BUILTIN_WINDOW_FIELDS = ("data", "source", "limit", "style")
#: FB-33 M4b: данные блока «Liste», которые по-прежнему пишет Студия; остальное — окно.
#: `scope` — служебный охват «Ansicht gilt für» (`list_blocks.apply_type_scope`, ревью №3).
LIST_STUDIO_FIELDS = ("title", "intro", "speed", "scope")


def _is_builtin_list(item: dict) -> bool:
    from apps.tenants import siteconfig

    return not item.get("id") and item.get("key") in siteconfig.BUILTIN_LIST_SOURCES


def structure_hash(config) -> str:
    """FB-27 R0: отпечаток СТРУКТУРЫ сайта — порядок, состав, видимость и ширина блоков
    главной и всех страниц. Тексты, фото и стили в него не входят.

    Нужен как предохранитель «два писателя»: Студия и «Seitenaufbau» пишут одни ключи
    (`sections`, `page_blocks`); форма с устаревшим отпечатком не должна перезаписать
    схему, сохранённую тем временем в другом месте."""
    import hashlib
    import json

    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(config if isinstance(config, dict) else {})

    def rows(items):
        # FB-27 R8d: выбор блоков-«указателей» (что показать, какие, ручной состав,
        # страница) задаёт «Seitenaufbau» — он тоже входит в отпечаток, иначе вкладка
        # Студии, открытая до такой правки, молча вернула бы прежний выбор.
        return [
            [s.get(f) for f in _STRUCT_FIELDS]
            + ([s.get("data")] if s.get("key") in OWNED_DATA_KINDS else [])
            + ([s.get(f) for f in BUILTIN_OWNED_FIELDS] if _is_builtin_list(s) else [])
            for s in (items or [])
            if isinstance(s, dict)
        ]

    blocks = cfg.get("page_blocks") if isinstance(cfg.get("page_blocks"), dict) else {}
    payload = {
        # FB-32 S2: пункты полосы доверия правит и «Seitenaufbau» — устаревшая вкладка
        # Студии не должна молча вернуть прежние (ревью)
        "usp_bar": cfg.get("usp_bar") or [],
        "usp_style": next(
            (s.get("style") for s in cfg.get("sections") or [] if _is_usp_row(s)), None
        ),
        "sections": rows(cfg.get("sections")),
        "page_blocks": {host: rows(blocks[host]) for host in sorted(blocks)},
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


#: FB-27 R8: что из строки блока принадлежит «Seitenaufbau», а не Студии (те же поля,
#: что видит отпечаток структуры, кроме состава и порядка — их задаёт сам список).
#: Положение узкого блока (`pos`: слева/по центру/справа) остаётся виду Студии: в
#: «Seitenaufbau» для него контрола нет.
_OWNED_FIELDS = ("enabled", "width", "newline")


def page_embeddable(page, host: str) -> bool:
    """FB-27 R6 / FB-33 M3-3d: страница для блока «Von einer Seite» — существует и не та,
    на которой стоит блок (`host` — хост его блоков)."""
    from apps.core import content_pages
    from apps.core.models import ContentPage
    from apps.tenants import siteconfig

    pk = (siteconfig.clean_pick([page]) or [""])[0]
    if not pk:
        return False
    slug = ContentPage.objects.filter(pk=pk).values_list("slug", flat=True).first()
    return slug is not None and not content_pages.embeds_itself(slug, host)


def textpage_page_note():
    return _("Die gemerkte Seite gibt es hier nicht (mehr) — Seite bitte neu wählen.")


def drop_unembeddable_page(data: dict, host: str, notes: list | None = None) -> dict:
    """FB-33 M3-3d (ревью): запомненная/перенесённая страница блока «Von einer Seite»,
    которой нет или которая встала бы сама в себя, снимается — блок не пропадает с сайта
    молча: владельцу сообщение «Seite bitte neu wählen». `data` — копия."""
    data = dict(data or {})
    if data.get("page") and not page_embeddable(data["page"], host):
        data.pop("page", None)
        if notes is not None:
            notes.append(textpage_page_note())
    return data


def check_changed_pages(saved: dict, merged: dict, notes: list | None = None) -> None:
    """FB-33 M3-3d (ревью): блоки «Von einer Seite» после «Speichern» Студии — страница,
    которой не было в сохранённом блоке, проверяется (`drop_unembeddable_page`). На месте."""
    from apps.tenants import siteconfig

    for host, rows in (merged or {}).items():
        before = {
            b.get("id"): (b.get("data") or {}).get("page")
            for b in (saved or {}).get(host) or []
            if isinstance(b, dict) and b.get("id")
        }
        for block in rows or []:
            if (
                not isinstance(block, dict)
                or siteconfig.cblock_type(block.get("key")) != "textpage"
            ):
                continue
            data = block.get("data") if isinstance(block.get("data"), dict) else {}
            if data.get("page") and data.get("page") != before.get(block.get("id")):
                block["data"] = drop_unembeddable_page(data, host, notes)


def window_owned(item: dict) -> dict:
    """FB-33 M4b: что строки главной правит только окно блока, а не Студия:
    `list` — выбор, лимит, раскладка окна и вид встроенного списка; `style` — вид секции
    (встроенный список, `STYLE_SECTIONS`, полоса доверия). Пусто — у Студии всё своё."""
    if not isinstance(item, dict) or item.get("id"):
        return {"list": False, "style": False}
    builtin = _is_builtin_list(item)
    return {
        "list": builtin,
        "style": builtin or _is_usp_row(item) or item.get("key") in STYLE_SECTIONS,
    }


def _keep(merged: dict, old: dict, fields) -> None:
    """Поля `fields` строки — как сохранено (нет в сохранённом — нет и после)."""
    for field in fields:
        if field in old:
            merged[field] = copy.deepcopy(old[field])
        else:
            merged.pop(field, None)


def _studio_view_only(merged: dict, old: dict, new: dict) -> None:
    """FB-33 M4b: из формы Студии (`new`) у строки остаётся только её — содержимое и
    «Feinschliff». Снятое из панели Студии (Was · Wie anordnen · Karte) — как сохранено:
    «Speichern» без этих полей их не стирает (W0), а устаревшая или подделанная форма их
    не меняет. Одинаково у свежей и у устаревшей вкладки (ревью №1)."""
    from apps.tenants import siteconfig

    owned = window_owned(old)
    if owned["style"]:
        _keep(merged, old, ("style",))
    if owned["list"]:
        _keep(merged, old, _BUILTIN_WINDOW_FIELDS)
        was = old.get("layout") if isinstance(old.get("layout"), dict) else {}
        now = new.get("layout") if isinstance(new.get("layout"), dict) else {}
        layout = copy.deepcopy(was)
        # ключ «Feinschliff» не прислан — снят (так форма шлёт выключенное и пустое)
        _keep(layout, now, STUDIO_LAYOUT_KEYS)
        if layout:
            merged["layout"] = layout
        else:
            merged.pop("layout", None)
    if siteconfig.cblock_type(old.get("key")) == "list" and old.get("id"):
        was = old.get("data") if isinstance(old.get("data"), dict) else {}
        now = new.get("data") if isinstance(new.get("data"), dict) else {}
        data = copy.deepcopy(was)
        # присланное поле Студии пишется (пустое — снимает), неприсланное остаётся (W0)
        data.update({k: copy.deepcopy(now[k]) for k in LIST_STUDIO_FIELDS if k in now})
        merged["data"] = data


def merge_structure(
    saved: list, posted: list, fixed: bool = False, keep_data: bool = False
) -> list:
    """FB-27 R8: блоки страницы после «Speichern» Студии. Порядок, состав, видимость и
    ширина — как СОХРАНЕНО (структуру правит «Seitenaufbau»); из формы Студии берётся
    только содержимое и вид блока, найденного по `id` (свой блок) или `key` (секция).

    Блок формы, которого в сохранённом нет (удалён тем временем), отбрасывается; блок,
    которого нет в форме (устаревшая вкладка, свёрнутая страница), остаётся как был.
    `fixed` — главная: встроенные секции, которых в сохранённом ещё нет, дописываются.
    `keep_data` — форма открыта до правки в «Seitenaufbau» (устаревшая вкладка): данные
    блоков-«указателей» (`OWNED_DATA_KINDS`) остаются сохранёнными — форма несёт их
    прежний выбор и откатила бы источник, фильтры и ручной состав."""
    from apps.tenants import siteconfig

    def ident(item):
        # не строка (мусор в черновике) — не ключ: по ней блок не найти
        value = item.get("id") or item.get("key")
        return value if isinstance(value, str) else None

    def kind(item):
        key = item.get("key")
        return siteconfig.cblock_type(key) or key  # легаси-ключ блока = его новый тип

    by = {}
    for item in posted or []:
        if isinstance(item, dict) and not siteconfig.is_main_marker(item) and ident(item):
            by.setdefault(ident(item), item)
    out = []
    for old in saved or []:
        if not isinstance(old, dict):
            continue
        new = None if siteconfig.is_main_marker(old) else by.pop(ident(old), None)
        if new is None or kind(new) != kind(old):
            out.append(old)
            continue
        merged = {**new, "key": old.get("key")}
        if keep_data and kind(old) in OWNED_DATA_KINDS:
            merged["data"] = old.get("data") or {}
        remembered = block_catalog.inactive_fields(kind(old))
        if remembered and isinstance(old.get("data"), dict):
            # FB-33 M2e/M3-3d: поля другого вида пары (фото «Nur Text», страница «Von einer
            # Seite», свой текст у неё) форма Студии не несёт — «Speichern» их не стирает и
            # не подсовывает: пишет их только смена вида
            data = dict(merged.get("data") or {}) if isinstance(merged.get("data"), dict) else {}
            for field in remembered:
                if field in old["data"]:
                    data[field] = old["data"][field]
                else:
                    data.pop(field, None)
            merged["data"] = data
        if kind(old) in siteconfig.PAGE_REF_BLOCKS or kind(old) == "quick_links":
            # FB-33 M2b/M2c: вид блока-ссылки и набор «Schnellzugriff» задаёт
            # «Seitenaufbau»; форма Студии их не несёт.
            # ⚠️ Если Студия когда-нибудь начнёт присылать вид ref-блока — эта строка его
            # проглотит (Студия по правилу P6 структуру и вид блоков-ссылок не пишет).
            merged["data"] = old.get("data") or {}
        if kind(old) == "banner":
            # FB-29.2: выбор баннеров и настройки слайдера задаёт «Seitenaufbau»; форма
            # Студии их не несёт вовсе — её «Speichern» выбор не трогает.
            was = old.get("data") if isinstance(old.get("data"), dict) else {}
            data = dict(merged.get("data") or {}) if isinstance(merged.get("data"), dict) else {}
            for field in _BANNER_CHOICE_FIELDS:
                if field in was:
                    data[field] = was[field]
                else:
                    data.pop(field, None)
            merged["data"] = data
        # FB-32 S2 / FB-33 M2b / M4b: вид секции, выбор и раскладку окна встроенного
        # списка, выбор «Liste» правит только окно — у свежей и у устаревшей вкладки
        # (у устаревшей тексты и «Feinschliff» тоже пишутся: ревью M4b №1)
        _studio_view_only(merged, old, new)
        # FB-29.5: ширина и «новая строка» — структура у ВСЕХ блоков, включая
        # встроенные секции главной (их задаёт «Seitenaufbau»).
        for field in _OWNED_FIELDS:
            if field in old:
                merged[field] = old[field]
            else:
                merged.pop(field, None)
        out.append(merged)
    if fixed:
        # FB-33 M4b: секции, которой ещё нет в сохранённом, Студия задаёт только своё —
        # снятое из её панели остаётся по умолчанию (пустая строка с тем же ключом)
        for item in by.values():
            if not item.get("id"):
                fresh = dict(item)
                _studio_view_only(fresh, {"key": item.get("key")}, item)
                out.append(fresh)
    return out


def _structure_signature(items: list, only: set | None = None) -> list:
    out = []
    for item in items or []:
        if not isinstance(item, dict) or item.get("key") == "main":
            continue
        ref = item.get("id") or item.get("key")
        if only is not None and ref not in only:
            continue
        row = [
            ref,
            bool(item.get("enabled", True)),
            item.get("width") or "contained",
            bool(item.get("newline")),
        ]
        out.append(row)
    return out


def structure_attempted(posted: list, merged: list) -> bool:
    """FB-27 R8: пыталась ли форма Студии изменить структуру (порядок, видимость,
    удаление, ширину своего блока) — тогда «Gespeichert» без пояснения было бы неправдой."""
    sent = _structure_signature(posted)
    refs = {row[0] for row in sent if isinstance(row[0], str)}
    return sent != _structure_signature(merged, only=refs)


def merge_pages(saved: dict, posted: dict, keep_data: bool = False) -> dict:
    """FB-27 R8: `page_blocks` после «Speichern» Студии — хосты и их состав как
    сохранено; страница, которой нет в форме, остаётся как была."""
    saved = saved if isinstance(saved, dict) else {}
    posted = posted if isinstance(posted, dict) else {}
    return {
        host: merge_structure(blocks, posted[host], keep_data=keep_data)
        if host in posted
        else list(blocks)
        for host, blocks in saved.items()
    }


def page_rows(config: dict) -> list[PageRow]:
    """Типы страниц со своими блоками (главная первой) + число видимых блоков."""
    rows = []
    for pt in studio_pages.PAGE_TYPES:
        if pt.code != "home" and not _host(pt):
            continue
        blocks = blocks_for(config, pt.code)
        rows.append(
            PageRow(
                code=pt.code,
                label=str(pt.label),
                host=_host(pt) if pt.code != "home" else "",
                # FB-31 (ревью P5): считаются только свои блоки (не разделы, не строки осей)
                count=sum(1 for b in blocks if b["enabled"] and b["cblock"]),
                preview_url=_preview_url(pt),
            )
        )
    return rows


def _page_type(code: str):
    base = code.split("@", 1)[0]
    # подстраницы есть у типа «Seite», у категорий (FB-27 R7) и у групп акций (FB-31 P3 R6)
    if "@" in code and base not in (TEXT, CATEGORY, PROMO_GROUP, *OBJECT_KINDS):
        return None
    if "@" in code:
        base = OBJECT_PAGE_TYPES.get(base, base)  # тур — строка типа «Veranstaltungsseite»
    for pt in studio_pages.PAGE_TYPES:
        if pt.code == base and (pt.code == "home" or _host(pt)):
            return pt
    return None


#: M21.11 (решение владельца): у типа «Seite» у КАЖДОЙ страницы свой набор блоков —
#: «Über uns» (хост info), «Versand» (versand) и каждая своя страница (seite:<slug>).
#: Код строки схемы: «text» = Über uns, «text@<хост>» = остальные.
TEXT = "text"


@dataclass
class SubPage:
    code: str
    label: str
    host: str
    preview_url: str


#: FB-27 R7: своя схема категории — строка «category@catalog:<slug>».
CATEGORY = "category"
#: FB-29.4b: свои блоки объекта — строка «product@product:<hex>» / «service@service:<hex>».
OBJECT_KINDS = ("product", "service", "stay", "event", "promo", "tour")
#: T1: вид объекта без своего типа страницы → тип, чьи блоки и настройки он делит.
OBJECT_PAGE_TYPES = {"tour": "event"}
#: Адрес витрины объекта, у которого он не строится по pk маршрутом типа: (маршрут, поле).
_OBJECT_PREVIEW_ROUTES = {"tour": ("storefront-tour", "slug")}
_OBJECT_MODELS = {
    # путь одной строкой: пара («модуль», «Имя») читается проверкой переводов как подпись
    "product": "apps.catalog.models.Product",
    "service": "apps.booking.models.Service",
    "stay": "apps.stays.models.StayUnit",  # R5
    "event": "apps.events.models.Event",
    "promo": "apps.promotions.models.Promotion",
    "tour": "apps.events.models.Tour",
}


def object_model(kind: str):
    """Модель вида объекта со своими блоками."""
    import importlib

    module, _dot, name = _OBJECT_MODELS[kind].rpartition(".")
    return getattr(importlib.import_module(module), name)


#: Карточка объекта в кабинете (ссылка «назад» со строки его своих блоков).
_OBJECT_EDIT_URLS = {
    "product": "catalog:product-edit",
    "service": "booking:service-edit",
    "stay": "stays:unit-edit",
    "event": "events:edit",
    "promo": "promotions:promotion-edit",
    "tour": "events:tour-edit",
}


def is_object_code(code: str) -> bool:
    return isinstance(code, str) and "@" in code and code.split("@", 1)[0] in OBJECT_KINDS


def _object_for(code: str):
    """Объект строки «<kind>@<kind>:<hex>» либо None (чужой вид, мусор, нет такого)."""

    from apps.tenants import siteconfig

    kind, host = code.split("@", 1)
    if kind not in OBJECT_KINDS or not siteconfig.is_object_host(host):
        return None
    if host.split(":", 1)[0] != kind:
        return None
    model = object_model(kind)
    try:
        return model.objects.filter(pk=uuid.UUID(host.split(":", 1)[1])).first()
    except (ValueError, TypeError):
        return None


def shared_schema_url(code: str) -> str:
    """R8: адрес общей схемы типа страницы для строки одного объекта ("" — не объект)."""
    if not is_object_code(code):
        return ""
    kind = code.split("@", 1)[0]
    return f"{reverse('site-schema')}?seite={OBJECT_PAGE_TYPES.get(kind, kind)}"


def object_back(code: str) -> dict | None:
    """S8: ссылка «назад к объекту» со строки его своих блоков: {url, label} либо None."""
    if not is_object_code(code):
        return None
    obj = _object_for(code)
    if obj is None:
        return None
    kind = code.split("@", 1)[0]
    try:
        url = reverse(_OBJECT_EDIT_URLS[kind], args=[obj.pk])
    except NoReverseMatch:
        return None
    return {"url": url, "label": _object_label(obj)}


def _object_label(obj) -> str:
    for attr in ("name_localized", "title_localized", "name", "title"):
        label = getattr(obj, attr, "")
        if callable(label):
            try:
                label = label()  # на языке кабинета
            except TypeError:
                continue
        if isinstance(label, dict):
            label = label.get("de") or next(iter(label.values()), "")
        if label:
            return str(label)
    return str(obj)


def object_row(config: dict, code: str):
    """Строка экрана для своих блоков объекта (подпись — его название) либо None."""
    if not is_object_code(code):
        return None
    obj = _object_for(code)
    pt = _page_type(code)
    if obj is None or pt is None:
        return None
    preview = ""
    try:
        if hasattr(obj, "get_absolute_url"):
            preview = obj.get_absolute_url()
    except Exception:  # noqa: BLE001 — превью необязательно
        preview = ""
    route = _OBJECT_PREVIEW_ROUTES.get(code.split("@", 1)[0])
    if route and not preview:
        try:
            preview = reverse(route[0], args=[getattr(obj, route[1])])
        except NoReverseMatch:
            preview = ""
    elif not preview:
        for name in pt.url_names:  # запись без своего адреса — маршрут типа по pk
            try:
                preview = reverse(name, args=[obj.pk])
                break
            except NoReverseMatch:
                continue
    return _row(
        config,
        pt,
        code=code,
        label=_object_label(obj),
        preview=preview,
        host=code.split("@", 1)[1],
    )


CATEGORY_ROWS_MAX = 200


def category_code(slug: str) -> str:
    from apps.tenants import siteconfig

    host = siteconfig.category_host(slug)
    return f"{CATEGORY}@{host}" if host else ""


def category_pages(config: dict) -> list[SubPage]:
    """Категории, у которых может быть своя схема: сначала те, у кого она уже есть, затем
    остальные по названию. Один запрос; адрес длиннее хоста — без строки."""
    from apps.catalog.models import Category
    from apps.tenants import siteconfig

    own, rest = [], []
    for cat in Category.objects.filter(is_active=True).order_by("slug")[:CATEGORY_ROWS_MAX]:
        host = siteconfig.category_host(cat.slug)
        if not host:
            continue
        page = SubPage(
            f"{CATEGORY}@{host}", str(cat), host, reverse("storefront-category", args=[cat.slug])
        )
        (own if siteconfig.has_own_schema(config, host) else rest).append(page)
    key = lambda p: p.label.lower()  # noqa: E731
    return sorted(own, key=key) + sorted(rest, key=key)


#: FB-31 P3 R6: строки групп акций в выборе страниц (как категории)
PROMO_GROUP = "promo_group"
PROMO_GROUP_ROWS_MAX = 40


def live_promo_groups() -> list[tuple[str, str]]:
    """(ключ, подпись) групп акций для своей схемы: свои рубрики ЛЮБОЙ акции (ревью R6:
    группа без действующих акций — сезонная, на паузе — не теряет свою схему и остаётся
    правимой) и встроенные типы с действующими акциями. До 40 своих + встроенные."""
    from apps.promotions import promo_types
    from apps.promotions.models import Promotion

    try:
        own = list(
            Promotion.objects.exclude(group="")
            .order_by("group")
            .values_list("group", flat=True)
            .distinct()[:PROMO_GROUP_ROWS_MAX]
        )
        builtin = promo_types.live_builtin_keys(Promotion.objects.filter(status="active"))
    except DatabaseError:
        logger.warning("site_schema: promo groups lookup failed", exc_info=True)
        return []
    return [(g, g) for g in own] + [(k, str(promo_types.builtin_label(k))) for k in builtin]


def promo_group_pages(config: dict) -> list[SubPage]:
    """Группы акций, у которых может быть своя схема (сначала с ней, затем по названию)."""
    from urllib.parse import urlencode

    from apps.tenants import siteconfig

    blocks = (config or {}).get("page_blocks") or {}
    own, rest = [], []
    for key, label in live_promo_groups():
        host = siteconfig.promo_group_host(key)
        preview = f"{reverse('storefront-aktionen')}?{urlencode({'gruppe': key})}"
        page = SubPage(f"{PROMO_GROUP}@{host}", label, host, preview)
        (own if host in blocks else rest).append(page)
    key = lambda p: p.label.lower()  # noqa: E731
    return sorted(own, key=key) + sorted(rest, key=key)


def promo_group_key(host: str) -> str:
    """Ключ живой группы акций по её хосту ("" — такой группы нет)."""
    from apps.tenants import siteconfig

    if not siteconfig.is_promo_group_host(host):
        return ""
    return next((k for k, _l in live_promo_groups() if siteconfig.promo_group_host(k) == host), "")


def url_for_path(tenant, path: str) -> str:
    """FB-27 R8c: адрес «Seitenaufbau» для страницы витрины `path` — ссылка «Aufbau ändern»
    из Студии открывает схему той страницы, что на холсте. Страница без своей схемы или
    незнакомый путь — экран без выбора (главная)."""
    from urllib.parse import urlencode

    base = reverse("site-schema")
    code = code_for_path(tenant, path)
    return f"{base}?{urlencode({'seite': code})}" if code else base


def code_for_path(tenant, path: str) -> str:
    """Код строки схемы для страницы витрины `path` ("" — путь не наш или у страницы нет
    своей схемы). T2: у объекта со своими блоками — его строка «Nur diese Seite».
    FB-33 M4: вынесено из `url_for_path` — им же пользуется ⚙ Студии (`window_links`)."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return ""
    try:
        ctx = studio_pages.resolve_page(path)
        # FB-33 M4: у «Aktionen» и группы акций хост блоков — не в типе Студии (EXTRA_HOSTS)
        host = getattr(ctx, "block_host", "") or EXTRA_HOSTS.get(ctx.code, "")
        pt_code = ctx.code
        group = ctx.object_ref if pt_code == PROMO_GROUP else ""
    except Exception:  # noqa: BLE001 — ссылка не должна ронять Студию
        logger.warning("site schema: page of path not resolved", exc_info=True)
        return ""
    from apps.tenants import siteconfig

    if host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        code = f"{CATEGORY}@{host}"
    elif host.startswith("seite:") or host == "versand":
        code = f"{TEXT}@{host}"
    elif host == "info":
        code = TEXT
    else:
        code = next(
            (pt.code for pt in studio_pages.PAGE_TYPES if host and _host(pt) == host),
            "home" if pt_code == "home" else "",
        )
    if not code:
        return ""
    # FB-33 M4: страница одной группы акций — её строка (живая группа; иначе общая)
    own = (
        f"{PROMO_GROUP}@{siteconfig.promo_group_host(group)}"
        if group
        else _own_code(tenant, code, _path_ref(path))
    )
    # T2: у объекта со своими блоками открываем ЕГО строку — «Nur diese Seite»
    for candidate in (own, code):
        if not candidate:
            continue
        try:
            resolve(tenant, candidate)
        except SchemaError:
            continue  # объекта уже нет — общая строка типа
        return candidate
    return ""


def _path_ref(path: str) -> str:
    """pk или адрес объекта из пути витрины ("" — путь без объекта)."""
    from urllib.parse import urlsplit

    from django.urls import Resolver404
    from django.urls import resolve as resolve_url

    try:
        kwargs = resolve_url(urlsplit(path).path or "/", urlconf="config.urls_tenant").kwargs
    except (Resolver404, ValueError):
        return ""
    return str(kwargs.get("pk") or kwargs.get("slug") or "")


def _own_code(tenant, type_code: str, ref: str) -> str:
    """Код строки своих блоков объекта страницы (`ref` — pk или адрес из пути) либо "":
    вид без своих блоков, объекта нет, своих блоков у него нет."""
    if not ref:
        return ""
    blocks = (getattr(tenant, "site_config", None) or {}).get("page_blocks") or {}
    if not blocks:
        return ""  # своих блоков нет ни у кого — без запроса к базе
    kinds = [type_code, *(k for k, shared in OBJECT_PAGE_TYPES.items() if shared == type_code)]
    for kind in kinds:
        if kind not in OBJECT_KINDS:
            continue
        route = _OBJECT_PREVIEW_ROUTES.get(kind)
        try:
            if route:  # адрес по своему полю (тур — slug)
                obj = object_model(kind).objects.filter(**{route[1]: ref}).only("pk").first()
                hexed = obj.pk.hex if obj else ""
            else:
                hexed = uuid.UUID(str(ref)).hex
        except (ValueError, TypeError):
            continue
        host = f"{kind}:{hexed}"
        if hexed and blocks.get(host):
            return f"{kind}@{host}"
    return ""


def category_items(config: dict, host: str, items: list[dict], op: str) -> list[dict]:
    """Новый состав схемы категории: `adopt` — копия блоков каталога (новые id, маркер
    основного списка на том же месте) и ниже свои блоки категории; `reset` — пусто
    (страница снова показывает блоки каталога). Только для хоста категории."""
    from apps.tenants import siteconfig

    if not host.startswith(siteconfig.CATEGORY_HOST_PREFIX):
        raise SchemaError("category")
    marker = {"key": siteconfig.MAIN_LIST_KEY}
    if op == "reset":
        return [marker]
    # FB-30.16 R5 (ревью): «принять блоки» — из того, что категория показывает сейчас:
    # «Alle Kategorien», если сохранена, иначе каталог
    shared = siteconfig.shared_category_host(config)
    source = [
        b
        for b in siteconfig.main_list_sequence(shared, siteconfig.page_rows(config, shared))
        if b.get("id") or siteconfig.is_main_marker(b)
    ]
    own = [it for it in items if not siteconfig.is_main_marker(it)]
    copied = []
    for block in source:
        if siteconfig.is_main_marker(block):
            copied.append(dict(marker))
        elif block.get("id"):
            copied.append({**copy.deepcopy(block), "id": uuid.uuid4().hex[:12]})
    if sum(1 for b in copied if b.get("id")) + len(own) > siteconfig._MAX_CBLOCKS:
        raise SchemaError("full")
    return copied + own


def text_pages() -> list[SubPage]:
    """Страницы типа «Seite»: Über uns, Versand (если доступна) и свои страницы."""
    from apps.core import content_pages
    from apps.core.models import ContentPage

    out = [SubPage(TEXT, str(_("Über uns")), "info", reverse("storefront-about"))]
    try:
        out.append(
            SubPage(f"{TEXT}@versand", str(_("Versand")), "versand", reverse("storefront-shipping"))
        )
    except NoReverseMatch:
        pass
    pages = ContentPage.objects.exclude(slug__in=list(content_pages.SYSTEM_PAGES)).order_by(
        "sort_order", "title"
    )
    for page in pages[:200]:
        out.append(
            SubPage(
                f"{TEXT}@seite:{page.slug}",
                page.title,
                f"seite:{page.slug}",
                content_pages.content_url(page.slug),
            )
        )
    return out


def host_for(code: str, known_slugs: set[str] | None = None) -> str:
    """Хост блоков строки схемы ("" у главной). Неизвестная подстраница → "".

    `known_slugs` — слаги существующих страниц, если вызывающий уже загрузил их
    (список опций): без него каждая опция стоила бы запроса."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None or pt.code == "home":
        return ""
    if "@" not in code:
        return _host(pt)
    host = code.split("@", 1)[1]
    if is_object_code(code):
        # FB-29.4b: только существующий объект своего вида — иначе хосты-призраки.
        return host if _object_for(code) is not None else ""
    if pt.code == CATEGORY:
        # FB-27 R7: только существующая категория — иначе POST плодил бы хосты-призраки.
        slug = host[len(siteconfig.CATEGORY_HOST_PREFIX) :]
        if not host.startswith(siteconfig.CATEGORY_HOST_PREFIX) or (
            siteconfig.category_host(slug) != host
        ):
            return ""
        if known_slugs is not None:
            return host if slug in known_slugs else ""
        from apps.catalog.models import Category

        return host if Category.objects.filter(slug=slug).exists() else ""
    if pt.code == PROMO_GROUP:
        # FB-31 P3 R6: только живая группа акций — иначе POST плодил бы хосты-призраки
        return host if promo_group_key(host) else ""
    if pt.code != TEXT:
        return ""
    if host == "versand":
        return host
    if host.startswith("seite:") and siteconfig.is_page_block_host(host):
        # Ревью безопасности: только существующая страница — иначе POST плодил бы
        # хосты-призраки и вытеснял настоящие (у page_blocks общий потолок хостов).
        from apps.core.models import ContentPage

        slug = host.split(":", 1)[1]
        if known_slugs is not None:
            return host if slug in known_slugs else ""
        if ContentPage.objects.filter(slug=slug).exists():
            return host
    return ""


#: FB-27 V1 (макет Main): схематичная миниатюра строки — «bar» (баннер, фото), «cards»
#: (список карточек), «lines» (текст); прочие блоки — без миниатюры.
_THUMB_BAR = frozenset({"hero", "banner", "image", "image_text", "gallery", "gallery_ref"})
_THUMB_LINES = frozenset({"text", "about", "textpage", "faq", "faq_ref", "usp_bar"})


def _row_thumb(key: str) -> str:
    from apps.tenants import siteconfig

    kind = siteconfig.cblock_type(key) or key
    if kind == "list" or kind in siteconfig.BUILTIN_LIST_SOURCES:
        return "cards"
    if kind in _THUMB_BAR:
        return "bar"
    return "lines" if kind in _THUMB_LINES else ""


def _thumb_shape(config: dict, item: dict) -> dict:
    """FB-29.3: форма миниатюры списка — {cols, cells, out}: столько колонок и рядов,
    сколько задано блоку (у своего блока «Liste» без своих осей — вид, который он
    наследует). Без запросов в БД."""
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    key = item.get("key") or ""
    kind = siteconfig.cblock_type(key) or key
    data = block_catalog.active_data(kind, item.get("data"))  # M3-3d: только активный вид
    cols, rows, slider = 4, 1, False
    try:
        if kind == "list" and item.get("id"):
            layout = list_blocks.base_view(config, data)["layout"]
            cols = int(data.get("cols") or layout.get("cols") or 4)
            rows = int(data.get("rows") or 1)
            slider = (data.get("out") or siteconfig.output_mode(layout)) == "slider"
        elif kind in siteconfig.BUILTIN_LIST_SOURCES and not item.get("id"):
            layout = item.get("layout") if isinstance(item.get("layout"), dict) else {}
            cols = int(layout.get("cols") or 4)
            rows = int(layout.get("rows") or 1)
            slider = bool(layout.get("scroll"))
    except (TypeError, ValueError):
        pass
    cols = max(1, min(6, cols))
    rows = 1 if slider else max(1, min(3, rows))
    return {"cols": cols, "cells": range(cols * rows), "out": "slider" if slider else "grid"}


def _row_summary(config: dict, item: dict) -> str:
    """FB-27 V1: строка-сводка блока в схеме — что он показывает, без запросов в БД
    («3 Folien · Slider», «Produkte · höchstens 8 · Slider», «„Tee aus kleinen Gärten …“»)."""
    from apps.tenants import siteconfig

    key = item.get("key") or ""
    kind = siteconfig.cblock_type(key) or key
    # FB-33 M3-3d: запомненный текст другого вида (у «Von einer Seite» — свой заголовок)
    # не на сайте — и в сводке его нет
    data = block_catalog.active_data(kind, item.get("data"))
    parts: list[str] = []
    if kind == "hero" and not item.get("id"):
        # FB-29.2: баннеры выбраны из библиотеки — считаем их, иначе прежние слайды
        choice = config.get("hero_banners") or {}
        picked = choice.get("pick") or []
        slides = len(picked) or len(config.get("heroes") or [])
        if slides > 1 and picked and choice.get("single"):
            parts.append(str(_("Ein Banner")))  # FB-32 S3: первый из выбранных
        elif slides > 1:
            parts += [_("%(n)s Folien") % {"n": slides}, str(_("Slider"))]
    elif kind == "list" or (kind in siteconfig.BUILTIN_LIST_SOURCES and not item.get("id")):
        if kind == "list":
            source = data.get("source") or siteconfig.LIST_SOURCE_DEFAULT
            if data.get("title"):
                parts.append(str(data["title"]))
            elif source in siteconfig.LIST_SOURCES:
                parts.append(str(siteconfig.LIST_SOURCES[source]["label"]))
            if data.get("from_page"):
                parts.append(_("Banner dieser Seite"))  # S6: блок-место
            elif data.get("pick"):
                parts.append(_("%(n)s ausgewählt") % {"n": len(data["pick"])})
            elif data.get("limit"):
                parts.append(_("höchstens %(n)s") % {"n": data["limit"]})
            slider = data.get("out") == "slider"
        else:
            layout = item.get("layout") if isinstance(item.get("layout"), dict) else {}
            limit = item.get("limit")
            if limit:
                parts.append(_("höchstens %(n)s") % {"n": limit})
            slider = bool(layout.get("scroll"))
            cols = layout.get("cols")
            if cols and not slider and str(cols) not in ("", "1"):
                parts.append(_("%(n)s Spalten") % {"n": cols})
        style = data.get("style") if kind == "list" else item.get("style")
        if style:  # FB-32 S1: подпись строки показывает выбранный вид
            parts.append(str(siteconfig.SECTION_STYLE_LABELS.get(style, style)))
        parts.append(str(_("Slider") if slider else _("Raster")))
    else:
        text = data.get("title") or data.get("label") or data.get("caption") or data.get("body")
        if text:
            text = " ".join(str(text).split())
            parts.append("«" + (text[:48] + "…" if len(text) > 48 else text) + "»")
    return " · ".join(parts)[:80]


def _textpage_summaries(rows: list[dict], items: list[dict]) -> None:
    """FB-27 R6: в строке блока «Textseite» — название выбранной страницы. Один запрос
    на все такие блоки страницы; без них — ни одного."""
    wanted = {
        it["id"]: (it.get("data") or {}).get("page")
        for it in items
        if it.get("id") and it.get("key") == "textpage" and (it.get("data") or {}).get("page")
    }
    if not wanted:
        return
    from django.core.exceptions import ValidationError
    from django.db import DatabaseError

    from apps.core.models import ContentPage

    try:
        titles = {
            str(pk): title
            for pk, title in ContentPage.objects.filter(pk__in=set(wanted.values())).values_list(
                "pk", "title"
            )
        }
    except (DatabaseError, ValidationError, ValueError):
        return
    gone = _("Seite nicht mehr vorhanden")
    for row in rows:
        if row["ref"] in wanted:
            row["summary"] = str(titles.get(wanted[row["ref"]], gone))[:60]


# FB-27 (макет Main): встроенный список главной («Kategorien», «Produkte» …) правится в
# панели так же, как блок «Liste». Источник закреплён ключом секции; оси хранятся там же,
# где их читает витрина: «что» — `data` строки (+ легаси `source` товаров), лимит — `limit`,
# вид — `layout` (cols/rows/scroll). Второго хранилища нет.
BUILTIN_VIEW_FIELDS = ("limit", "out", "cols", "rows", "style")


def builtin_panel_data(item: dict) -> dict:
    """Данные встроенной строки в форме блока «Liste» — для панели и сводки."""
    from apps.core import list_blocks

    data = dict(list_blocks.section_data(item))
    layout = item.get("layout") if isinstance(item.get("layout"), dict) else {}
    data["out"] = "slider" if layout.get("scroll") else "grid"
    if layout.get("cols"):
        data["cols"] = layout["cols"]
    if layout.get("rows"):
        data["rows"] = layout["rows"]
    if item.get("limit"):
        data["limit"] = item["limit"]
    if item.get("style"):
        data["style"] = item["style"]  # FB-32 S1: вид секции — поле строки
    return data


def _builtin_state(item: dict) -> tuple:
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    layout = item.get("layout") if isinstance(item.get("layout"), dict) else {}
    what = siteconfig.clean_builtin_list_data(item.get("key"), list_blocks.section_data(item))
    return (
        what,
        item.get("limit"),
        layout.get("cols"),
        layout.get("rows") or 0,
        bool(layout.get("scroll")),
        item.get("style") or "",
    )


def _digit(value: str, low: int, high: int):
    value = (value or "").strip()
    if not (value.isdecimal() and value.isascii()):
        return None
    return max(low, min(high, int(value)))


def _update_builtin(item: dict, fields: dict | None) -> bool:
    """Патч встроенной строки из панели; True — строка изменилась. Мусор не пишется,
    неприсланное остаётся как было (W0)."""
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    key = item.get("key")
    names = (*list_blocks.BUILTIN_WHAT_FIELDS, *BUILTIN_VIEW_FIELDS)
    sent = {n: str(fields[n]) for n in names if fields is not None and n in fields}
    if not sent:
        return False
    before = _builtin_state(item)
    new = copy.deepcopy(item)
    what = dict(list_blocks.section_data(item))
    for name in list_blocks.BUILTIN_WHAT_FIELDS:
        if name in sent:
            what[name] = sent[name]
    if "endet" in sent:
        what.pop("phase", None)  # «Zeitraum» — один селект на срок и «Demnächst»
    new["data"] = siteconfig.clean_builtin_list_data(key, what)
    if key == "products":
        list_blocks.fold_product_source(new)
    if not new["data"]:
        new.pop("data")
    layout = dict(new.get("layout") or {})
    if sent.get("out") == "slider":
        layout["scroll"] = True
    elif sent.get("out") in ("grid", ""):  # FB-33 M3-3c: "" — «zurücksetzen»
        layout.pop("scroll", None)
    cols = _digit(sent.get("cols", ""), 1, 6)
    if cols:
        layout["cols"] = cols
        # вид «N в строке» в Студии — тот же, что число колонок здесь (одно значение)
        preset = siteconfig.preset_for_cols(layout.get("preset"), cols)
        if preset:
            layout["preset"] = preset
    elif "cols" in sent and sent["cols"].strip() == "":
        # FB-33 M3-3c: «zurücksetzen» — колонки секции по умолчанию (раньше "" молча не
        # действовало: колонки оставались прежними)
        default = siteconfig.normalize_layout(None, siteconfig.GRID_SECTION_DEFAULTS.get(key))
        if layout.get("cols") not in (None, default["cols"]):  # своих колонок нет — не писать
            layout["cols"] = default["cols"]
            layout["preset"] = default["preset"]
    if "rows" in sent:
        rows = _digit(sent["rows"], 1, 6)
        if rows:
            layout["rows"] = rows
        elif sent["rows"].strip() == "":
            layout.pop("rows", None)
    new["layout"] = layout
    if "style" in sent:  # FB-32 S1: вид секции; чужой ключ не пишется
        style = sent["style"].strip()
        if style == "":
            new.pop("style", None)
        elif style in siteconfig.SECTION_STYLES.get(key, ()):
            new["style"] = style
    if key in siteconfig.GRID_SECTION_LIMITS:
        limit = _digit(sent.get("limit", ""), 1, siteconfig._SECTION_LIMIT_MAX)
        if limit:
            new["limit"] = limit
    if _builtin_state(new) == before:
        return False
    item.clear()
    item.update(new)
    return True


def _banner_choice(config: dict, item: dict) -> dict:
    from apps.tenants import siteconfig

    raw = config.get("hero_banners") if _is_hero_row(item) else item.get("data")
    return siteconfig.clean_banner_choice(raw)


def blocks_for(
    config: dict, code: str, host: str | None = None, summaries: bool = True
) -> list[dict]:
    """Строки схемы: {ref, key, label, enabled, main, cblock, summary} по порядку страницы."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None:
        return []
    if host is None:
        host = host_for(code)
    if pt.code == "home":
        items = config.get("sections") or []
    elif not host:
        return []
    else:
        from apps.core import detail_parts

        if detail_parts.module_of(host):  # FB-31 P5: разделы детали среди блоков
            items = detail_parts.edit_rows(config, host, siteconfig.page_rows(config, host))
        elif detail_parts.object_kind(host):  # R8: своя схема одного объекта
            items = detail_parts.object_edit_rows(config, host, siteconfig.page_rows(config, host))
        else:
            items = siteconfig.main_list_sequence(host, siteconfig.page_rows(config, host))
    out = []
    main_label = _("Hauptliste")  # не внутри f-строки: xgettext её не извлекает
    names = width_names()
    for item in items:
        key = item.get("key", "")
        main = siteconfig.is_main_marker(item)
        cblock = bool(item.get("id")) and not main
        data = item.get("data") or {}
        out.append(
            {
                "ref": item.get("id") or key,
                "key": key,
                "label": f"★ {main_label}"
                if main
                else _detail_label(host, item) or _sections_label(key),
                "enabled": True if main else bool(item.get("enabled", True)),
                "main": main,
                "cblock": cblock,
                "summary": "" if main else _row_summary(config, item),
                "thumb": "cards" if main else _row_thumb(key),
                "shape": _thumb_shape(config, item),
                # FB-32 S6a: разделы текстовых страниц стоят на месте (только скрыть), текст
                # своей страницы не скрывается вовсе
                "fixed": _fixed_section(host, item),
                "pinned": _fixed_section(host, item) and not _sec_parts.hideable(host or "", key),
                "width": item.get("width") or "",
                "newline": bool(item.get("newline")),
                "width_label": WIDTH_LABELS.get(item.get("width") or "", ""),
                "flex": WIDTH_FLEX.get(item.get("width") or "", 12),
                # FB-30.3: узкий блок занимает в списке СВОЮ долю и один в ряду (раньше он
                # растягивался на весь ряд — половина была видна только значком «½»)
                # у баннера главной ширины нет — прежнее сохранённое значение не действует
                "basis": 0
                if key in _FULL_BLEED_SECTIONS and not item.get("id")
                else WIDTH_PERCENT.get(item.get("width") or "", 0),
                "widths": [
                    (v, lab, names.get(v, lab), WIDTH_PERCENT.get(v, 100))
                    for v, lab in width_choices(item)
                ]
                if cblock or (home_section(item) and not _detail_label(host, item))
                else [],
                "width_value": item.get("width") or "contained",
                "fields": panel_fields(item) if cblock else section_style_fields(item),
                # FB-33 M2e: к какой семье блок относится и на какие виды его можно сменить
                "family_label": _family_label(key),
                "view_options": block_catalog.switch_options(key) if cblock else [],
                # FB-27 R3b-2: данные блока «Liste» — вид строит панель (`list_panel`)
                "list_data": dict(data)
                if cblock and (siteconfig.cblock_type(key) or key) == "list"
                else None,
                "narrow": not main and item.get("width") in siteconfig.NARROW_WIDTHS,
                # встроенный список главной открывает ту же панель «Welche · Wie»
                # FB-29.2: место показа баннеров — выбор из библиотеки и настройки слайдера
                "banner_choice": _banner_choice(config, item) if banner_place(item) else None,
                # FB-32 S2: пункты полосы доверия — в панели (иконка, заголовок, текст)
                "usp": usp_panel(config, item) if _is_usp_row(item) else None,
                "builtin_data": builtin_panel_data(item)
                if not item.get("id")
                and not main
                and key in siteconfig.BUILTIN_LIST_SOURCES
                and key not in siteconfig.page_builtin_keys(host)
                else None,
            }
        )
        # FB-30.16 R4: блоки каталога — вид категорий и вид товаров ★ (стратегия FB-31)
        if host in ("catalog", "category") and (main or key in siteconfig.CATALOG_PART_STYLES):
            out[-1].update(_catalog_view_panel(config, host, item, main))
        elif siteconfig.part_surface(host) is not None and (
            main or (key in siteconfig.part_surface(host).keys() and not item.get("id"))
        ):
            # FB-31 P3: страницы акций — те же плитки вида у закреплённых строк и ★
            out[-1].update(_part_view_panel(config, host, item, main))
    from apps.core import detail_parts as _dp

    if _dp.has_kauf(host or ""):  # FB-32 S4/S6a: у корзины и текстовых страниц покупки нет
        # FB-31 P5: «Buchung» закреплена после разделов (так её рисует страница); блоки
        # после неё — хвост страницы, как раньше
        keys = set(_dp.flow_section_keys(host))  # FB-33 M2g: разделы «на месте» — после неё
        last = max(
            (i for i, b in enumerate(out) if b["key"] in keys and not b["cblock"]), default=-1
        )
        out.insert(
            0 if host in _dp.KAUF_FIRST else last + 1,
            {
                "ref": _dp.KAUF_REF,
                "key": _dp.KAUF_KEY,
                "label": str(_("Kaufen") if host == "product_detail" else _("Buchung")),
                "enabled": True,
                "main": False,
                "cblock": False,
                "fixed": True,
                # FB-33 M3-6: закреплённая правовая строка (🔒, без ручки; § 312j BGB)
                "pinned": True,
                # бросок на «Kaufen» в первом экране ставит блок ПОСЛЕ неё — подсветка честная
                "drop_after": host in _dp.KAUF_FIRST,
                "summary": "",
            },
        )
    from apps.core import page_title as _pt_mod

    if host in _pt_mod.HEAD_HOSTS:
        # FB-33 M2d: «Seitentitel» там, где страница рисует H1: первым, либо (свои блоки
        # «сверху» стоят над H1 — снимки M2d-0) перед основным списком/разделом
        anchors = set(_dp.section_keys(host)) if _dp.module_of(host) else set()
        # фото-шапка страницы («page_head») стоит над заголовком — строка идёт после неё
        at = next(
            (i + 1 for i, b in enumerate(out) if b["key"] == "page_head" and not b.get("cblock")),
            0,
        )
        if host not in _pt_mod.H1_FIRST:
            at = next(
                (
                    i
                    for i, b in enumerate(out)
                    if b.get("main") or (not b.get("cblock") and b["key"] in anchors)
                ),
                len(out),
            )
        out.insert(at, title_row(config, host))
    if host == _CONFIRM_HOST:
        _confirm_next_row(config, out)
    if form_of(host):
        _form_row(config, out, host)
    if _dp.object_kind(host or ""):
        out = _with_shared_rows(config, host, out)
    if summaries and host in ("catalog", "category") and not _has_combos():
        # «Sets & Menüs» — только если наборы есть (иначе строке нечего показывать)
        out = [b for b in out if b["key"] != siteconfig.CATALOG_SETS_KEY]
    if summaries:  # строке списка страниц нужен только счёт блоков — без запроса
        _textpage_summaries(out, items)
    for b in out:
        b.setdefault("width", "")
        b.setdefault("thumb", "")
        b.setdefault("newline", False)
        b.setdefault("width_label", "")
        b.setdefault("flex", 12)
        b.setdefault("widths", [])
        b.setdefault("width_value", "contained")
        b.setdefault("fields", [])
        b.setdefault("list_data", None)
        b.setdefault("narrow", False)
    # FB-27 R1: «выше/ниже» двигает блок среди ВИДИМЫХ — скрытый сосед не «съедает»
    # нажатие (раньше порядок на странице не менялся, а кнопка была активна).
    # FB-32 S6a (ревью): разделы с постоянным порядком сами не двигаются, но для своих блоков
    # они — места («над текстом», «между текстом и контактами»)
    movable = [b for b in out if (not b["fixed"] or _fixed_section(host, b)) and b["enabled"]]
    for b in out:
        b["can_up"] = b["can_down"] = False
    for i, b in enumerate(movable):
        b["can_up"] = i > 0
        b["can_down"] = i < len(movable) - 1
    for b in out:
        if b["fixed"]:
            b["can_up"] = b["can_down"] = False
    return out


#: FB-27 R1: подписи и доли ширины блока в схеме (ширины — `siteconfig.CBLOCK_WIDTHS`).
WIDTH_LABELS = {"w23": "⅔", "w12": "½", "w13": "⅓", "w14": "¼", "w15": "⅕", "w16": "⅙"}
#: Доля контейнера в процентах — полоска-образец на кнопке ширины (FB-29.5).
WIDTH_PERCENT = {"w23": 66, "w12": 50, "w13": 33, "w14": 25, "w15": 20, "w16": 16}
WIDTH_FLEX = {"w23": 8, "w12": 6, "w13": 4, "w14": 3, "w15": 2.4, "w16": 2}


#: FB-30.8: точные доли узких ширин — сумма ряда считается без округления (33 % + 66 %).
def _row_share():
    from apps.tenants import siteconfig

    return siteconfig._ROW_SHARE


#: FB-30.8: точные доли узких ширин — сумма ряда считается без округления (33 % + 66 %).
#: Один источник с группировкой рядов (`siteconfig.group_block_rows`).
ROW_SHARE = _row_share()


def row_free(row) -> Fraction:
    """Свободная доля ряда узких блоков (0 — ряд полон или в нём широкий блок)."""
    total = Fraction(0)
    for b in row:
        share = ROW_SHARE.get((b.get("width") or "") if isinstance(b, dict) else "")
        if share is None:
            return Fraction(0)
        total += share
    return max(Fraction(0), 1 - total)


def _slot_label(free: Fraction) -> str:
    """Подпись свободного места ряда: наибольшая доля, что в нём помещается."""
    for width in ("w23", "w12", "w13", "w14", "w15", "w16"):
        if ROW_SHARE[width] <= free:
            return WIDTH_LABELS[width]
    return ""


#: Группы select «Seitentyp»: (код группы, подпись, модуль-владелец | None, типы).
_TYPE_GROUPS = (
    (
        "shop",
        gettext_lazy("Sortiment"),
        "catalog",
        (
            "catalog",
            "category",
            "product",
            "cart",
            "wishlist",
            "combos",
            "combo",
            "lookbook",
            "finder",
        ),
    ),
    (
        "termine",
        gettext_lazy("Termine"),
        "booking",
        ("services", "service", "booking_slots", "passes"),
    ),
    ("unterkunft", gettext_lazy("Unterkunft"), "stays", ("stays", "stay")),
    (
        "events",
        gettext_lazy("Veranstaltungen"),
        "events",
        ("events", "event", "tours", "event_calendar", "teachers"),
    ),
    ("anfragen", gettext_lazy("Anfragen"), "jobs", ("anfrage",)),
    # FB-31 P3 R6: страницы акций своей группой — обзор, «Alle Angebotsgruppen», акция
    ("aktionen", gettext_lazy("Aktionen"), "promotions", ("promos", PROMO_GROUP, "promo")),
    # FB-33 M2h-5: подтверждение всех сделок — одной страницей
    ("nachkauf", gettext_lazy("Nach dem Kauf"), None, ("confirmation",)),
)
_CONTENT_GROUP = gettext_lazy("Inhalte")
#: FB-30.16 R5: общая страница категорий в выборе страниц
_ALL_CATEGORIES = gettext_lazy("Alle Kategorien")
_CATEGORY_GROUP = gettext_lazy("Kategorien")
_ALL_PROMO_GROUPS = gettext_lazy("Alle Angebotsgruppen")
_PROMO_GROUP_GROUP = gettext_lazy("Angebotsgruppen")


def _category_type(tenant):
    """Тип «Kategorie», если он есть у бизнеса (иначе None)."""
    from apps.core import page_settings

    pt = _page_type(CATEGORY)
    return pt if pt is not None and page_settings.type_active(tenant, CATEGORY) else None


#: FB-27 R3 (решение владельца Q1): до ⅙ сужаются только ПРОСТЫЕ блоки. Всё остальное —
#: сетки карточек, формы, баннер, цифры, рассылка — не уже половины: в узкой колонке
#: (⅙ ≈ 128 px на планшете) карточки и поля ввода ломаются. Белый список, а не чёрный:
#: новый тип блока по умолчанию остаётся широким.
_NARROW_OK_BLOCKS = frozenset({"text", "image", "button", "spacer"})
_WIDTH_ORDER = ("contained", "w23", "w12", "w13", "w14", "w15", "w16")
_WIDE_WIDTHS = ("contained", "w23", "w12")


#: FB-27 R3b: поля содержимого, которые правятся в панели «Seitenaufbau»
#: (тип блока → [(поле данных, подпись, вид)]). Остальное — стиль, фото, оформление —
#: по-прежнему на странице («Auf der Seite bearbeiten»).
PANEL_FIELDS = {
    "text": (
        ("title", gettext_lazy("Überschrift"), "line"),
        ("body", gettext_lazy("Text"), "area"),
    ),
    "image_text": (
        ("title", gettext_lazy("Überschrift"), "line"),
        ("body", gettext_lazy("Text"), "area"),
    ),
    "button": (
        ("label", gettext_lazy("Beschriftung"), "line"),
        ("url", gettext_lazy("Link"), "line"),
    ),
    "image": (("caption", gettext_lazy("Bildunterschrift"), "line"),),
    # FB-27 R6: у блоков-ссылок в панели только выбор — что показать и как; пункты
    # селектов дополняет `fill_options` (нужен запрос — только для открытого блока).
    "textpage": (
        ("page", gettext_lazy("Welche Seite"), "select"),
        ("mode", gettext_lazy("Wie viel Text"), "select"),
    ),
    "contact_card": (("style", gettext_lazy("Darstellung"), "select"),),
    "quick_links": (("set", gettext_lazy("Welche Kacheln"), "select"),),  # FB-33 M2c
    # FB-33 M2b: блоки-ссылки на секции главной — свой вид (виды базовой секции)
    "faq_ref": (("style", gettext_lazy("Darstellung"), "select"),),
    "team_ref": (("style", gettext_lazy("Darstellung"), "select"),),
    "gallery_ref": (("style", gettext_lazy("Darstellung"), "select"),),
    "testimonials_ref": (("style", gettext_lazy("Darstellung"), "select"),),
}


def panel_fields(item: dict) -> list[dict]:
    """Поля панели блока с текущими значениями: [{name, label, kind, value}]."""
    from apps.tenants import siteconfig

    key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
    data = item.get("data") or {}
    return [
        {"name": name, "label": str(label), "kind": kind, "value": data.get(name, "")}
        for name, label, kind in PANEL_FIELDS.get(key, ())
    ]


#: FB-33 M2d: строка «Seitentitel» — вычисляемая, в `page_blocks` не хранится
TITLE_FIELDS = ("title", "intro", "align")


def title_row(config: dict, host: str) -> dict:
    """Строка схемы «Seitentitel»: неподвижная, не скрывается; поля — тексты и вид."""
    from apps.core import page_title

    entry = page_title.clean_one((config.get("page_titles") or {}).get(host))
    return {
        "ref": TITLE_REF,
        "key": "page_title",
        "label": str(_("Seitentitel")),
        "enabled": True,
        "main": False,
        "cblock": False,
        "fixed": True,
        "pinned": True,
        "style_only": False,
        "summary": entry.get("title") or str(_("Standard")),
        "fields": [
            {"name": "title", "label": str(_("Überschrift")), "kind": "line",
             "value": entry.get("title", "")},
            {"name": "intro", "label": str(_("Einleitung")), "kind": "area",
             "value": entry.get("intro", "")},
            {"name": "align", "label": str(_("Ausrichtung")), "kind": "select",
             "value": entry.get("align", "")},
        ],
    }  # fmt: skip


#: FB-33 M2h-5: «Was passiert jetzt» подтверждения — свой текст правится на строке раздела
_CONFIRM_HOST = "confirmation"
NEXT_REF = "next"


def _confirm_next_row(config: dict, out: list[dict]) -> None:
    """Поле текста у строки «Was passiert jetzt» (без своего текста раздела на странице нет)."""
    from apps.core import confirmation_page

    text = confirmation_page.clean_next(config.get(confirmation_page.NEXT_KEY))
    for b in out:
        if b["key"] == NEXT_REF and not b["cblock"]:
            b["summary"] = text[:80] if text else str(_("Nur sichtbar mit eigenem Text"))
            b["fields"] = [
                {"name": "text", "label": str(_("Was passiert jetzt")), "kind": "area",
                 "value": text,
                 "hint": str(_("Leer lassen — der Abschnitt erscheint nicht."))},
            ]  # fmt: skip


def next_op(host: str, draft: dict, op: str, fields: dict | None) -> str:
    """Правка «Was passiert jetzt» в черновике: только текст (`update`); двигать и скрывать —
    нет (строка неподвижна). Пустой текст — раздела нет (ключ не хранится)."""
    from apps.core import confirmation_page

    if host != _CONFIRM_HOST:
        raise SchemaError("block")
    if op != "update" or fields is None:
        raise SchemaError("fixed")
    if "text" in fields:
        draft["next"] = confirmation_page.clean_next(str(fields["text"]))
    return NEXT_REF


def is_next_edit(host: str, ref: str, op: str) -> bool:
    """Правка текста «Was passiert jetzt», а не строки схемы."""
    return host == _CONFIRM_HOST and ref == NEXT_REF and op == "update"


#: FB-33 M2i-5: вкладка «Felder» у закреплённой строки формы страницы «Anfrage» — режимы
#: полей, свои вопросы и варианты «Art der Veranstaltung» правятся в черновике (`draft["form"]`)
FORM_HOST = "anfrage"
FORM_REF = "form"
#: FB-33 C5: страница → форма `form_spec`, чью строку `form` наполняет вкладка «Felder»
#: (корзина — поля оформления `form_fields.checkout`, тот же черновик на своём хосте)
FORM_ROWS = {FORM_HOST: "anfrage", "cart": "checkout"}


def form_of(host) -> str:
    """Форма `form_spec` строки `form` страницы `host` (пусто — у страницы вкладки нет)."""
    return FORM_ROWS.get(str(host or ""), "")


def _form_row(config: dict, out: list[dict], host: str) -> None:
    """Модель вкладки «Felder» у строки формы (`form_spec.panel`; черновик — из превью)."""
    from apps.core import form_spec

    state = config.get(form_spec.EDIT_KEY)
    for b in out:
        if b["key"] == FORM_REF and not b["cblock"]:
            b[form_spec.PANEL_KEY] = form_spec.panel(
                config, form_of(host), state if isinstance(state, dict) else None
            )


def form_window_url(host: str = FORM_HOST) -> str:
    """Адрес окна строки формы на вкладке «Felder» (у заявки — ссылки с «Abläufe», с полосы
    заявки главной и 302 старого адреса панели; фиксированный путь, без `next`)."""
    from urllib.parse import urlencode

    query = {"seite": host, "block": FORM_REF, "tab": "felder"}
    return f"{reverse('site-schema')}?{urlencode(query)}#schema-panel"


def is_form_edit(host: str, ref: str, op: str) -> bool:
    """Правка вкладки «Felder» (поля формы заявки или корзины), а не строки схемы."""
    return bool(form_of(host)) and ref == FORM_REF and op == "update"


def form_op(
    tenant, config: dict, draft: dict, fields: dict | None, notes=None, host: str = FORM_HOST
) -> str:
    """Правка вкладки «Felder» в черновике: разбор `form_spec.parse_post` от состояния
    черновика (до среза его в черновике нет — от сохранённого). Строка неподвижна; её
    двигать/скрывать нельзя. Сообщения владельцу (`notes`) — в список вызывающего."""
    from apps.core import aufbau_draft, form_spec

    if fields is None:
        raise SchemaError("fixed")
    form = form_of(host)
    # ревью H2: правка — от черновика поверх СЕЙЧАС сохранённого (старая панель могла записать)
    saved = form_spec.edit_state(config, form)
    current = aufbau_draft.form_state(config, draft, form=form)
    preset = None
    if fields.get("do") == "preset":
        from apps.jobs.anfrage_presets import preset_for

        preset = preset_for(getattr(tenant, "business_type", ""), form=form)
    try:
        state, said = form_spec.parse_post(fields, current, form, preset)
    except form_spec.FormSpecError as exc:
        raise SchemaError("ids") from exc
    if state == saved:
        for key in aufbau_draft.FORM_KEYS:  # вернули как сохранено — правки нет
            draft.pop(key, None)
    else:
        draft["form"] = state
        draft["form_base"] = saved
    if notes is not None:
        notes.extend(said)
    return FORM_REF


def _family_label(key: str) -> str:
    """«Gehört zu: Text» — у блоков семьи из нескольких видов (иначе пусто)."""
    fam = block_catalog.family_of(siteconfig_key(key))
    if fam is None or len(fam.members) < 2:
        return ""
    return str(_("Gehört zu: %(family)s") % {"family": fam.label})


def siteconfig_key(key: str) -> str:
    from apps.tenants import siteconfig

    return siteconfig.cblock_type(key) or key


def title_op(host: str, draft: dict, op: str, fields: dict | None) -> str:
    """Правка «Seitentitel» в черновике: только `update` (двигать, скрывать, удалять — нет).
    Присланные поля заменяют прежние, неприсланные остаются (ПАТЧ, как у блоков)."""
    from apps.core import page_title

    if host not in page_title.HEAD_HOSTS:
        raise SchemaError("block")
    if op != "update" or fields is None:
        raise SchemaError("fixed")
    current = dict(draft.get("title") or {})
    for name in TITLE_FIELDS:
        if name in fields:
            current[name] = str(fields[name])
    if current.get("align", "") not in page_title.ALIGNS:
        raise SchemaError("fields")
    draft["title"] = page_title.clean_one(current)
    return TITLE_REF


#: FB-33 M2b: секции главной, вид которых выбирается в панели (раньше — только в Студии).
#: Списки (свои плитки вида) и полоса доверия (своя панель) — отдельно.
STYLE_SECTIONS = (
    "about",
    "process",
    "team",
    "cta",
    "testimonials",
    "trust",
    "reviews",
    "faq",
    "gallery",
    "contact",
)


def section_style_fields(item: dict) -> list[dict]:
    """Поле «Darstellung» встроенной секции главной из `STYLE_SECTIONS` (иначе — пусто)."""
    if not home_section(item) or item.get("key") not in STYLE_SECTIONS:
        return []
    return [
        {
            "name": "style",
            "label": str(gettext_lazy("Darstellung")),
            "kind": "select",
            "value": item.get("style") or "",
        }
    ]


def _style_options(base: str, host: str = "") -> list[tuple[str, str]]:
    """Пункты «Darstellung» секции `base` на странице `host`. FAQ — из реестра его видов
    (`faq_views`: одно имя на всех страницах, на детальной — три вида)."""
    from apps.tenants import siteconfig

    if base == "faq":
        from apps.core import faq_views

        return faq_views.choices(host)
    return [
        ("", _("Standard")),
        *(
            (k, str(siteconfig.SECTION_STYLE_LABELS.get(k, k)))
            for k in siteconfig.SECTION_STYLES.get(base, ())
        ),
    ]


def fill_options(block: dict, host: str) -> None:
    """FB-27 R6: пункты селектов панели открытого блока (на месте). Сохранённое значение,
    которого среди пунктов нет (страницу удалили), остаётся выбранным пунктом (W0)."""
    from apps.core import content_pages
    from apps.core.list_panel import _select
    from apps.tenants import siteconfig

    key = block.get("key")
    options = {}
    if key == "textpage":
        options = {
            "page": [("", _("Bitte wählen")), *content_pages.embed_choices(host)],
            "mode": [("", _("Ganzer Text")), ("teaser", _("Anfang mit „Weiterlesen“"))],
        }
    elif key == "contact_card":
        options = {
            "style": [
                ("", _("Karte")),
                ("split", _("Karte mit Lageplan daneben")),
                ("map_first", _("Lageplan oben")),
                ("compact", _("Eine Zeile, ohne Karte")),
            ]
        }
    elif key == "page_title":
        options = {"align": [("", _("Links")), ("center", _("Zentriert"))]}
    elif key == "quick_links":
        from apps.core.hero_tiles import QUICK_LINK_LABELS, QUICK_LINK_SETS

        options = {
            "set": [
                ("", _("Bitte wählen")),
                *((k, str(QUICK_LINK_LABELS[k])) for k in QUICK_LINK_SETS),
            ]
        }
        block["style_only"] = True
    elif key in siteconfig.PAGE_REF_BLOCKS:
        options = {"style": _style_options(key[: -len("_ref")], host)}
        block["style_only"] = True  # в панели только вид — подсказка про тексты не нужна
    elif key in STYLE_SECTIONS and not block.get("cblock"):
        options = {"style": _style_options(key, host)}
        block["style_only"] = True
    if key in ("faq", "faq_ref") and "style" in options:
        _keep_foreign_faq_view(block, options["style"])
    for f in block.get("fields") or []:
        if f["name"] in options:
            f["options"] = _select(f["name"], f["label"], f["value"], options[f["name"]])["options"]
            f["value"] = str(f["value"] or "")
    if key == "contact_card":
        block["source_url"] = reverse("settings")
        block["source_label"] = _("Adresse und Öffnungszeiten ändern")
    elif key == "textpage":
        block["source_url"] = reverse("content-pages")
        block["source_label"] = _("Texte der Seiten ändern")


def _keep_foreign_faq_view(block: dict, options: list) -> None:
    """FB-33 M2b-2a (W0): сохранённый вид FAQ, которого нет среди видов этой страницы
    (на детальной «Karten»), остаётся выбранным пунктом со своим именем и пометкой — страница
    рисует его как раньше, а «Übernehmen» без выбора его не сменит."""
    from apps.core import faq_views

    value = next(
        (str(f["value"] or "") for f in block.get("fields") or [] if f["name"] == "style"), ""
    )
    if value in faq_views.STYLE_KEYS and value not in {k for k, _lab in options}:
        note = _("nicht unter den Ansichten dieser Seite")
        options.append((value, f"{faq_views.label(value)} ({note})"))


#: Встроенные секции, которые сами рисуются во всю ширину экрана: доли ширины им не даём.
_FULL_BLEED_SECTIONS = frozenset({"hero"})


#: FB-29.2: настройки слайдера в панели (имена полей формы без префикса `f_`).
SLIDER_FIELDS = ("auto", "interval", "arrows")
#: FB-32 S3: показ — «Ein Banner» (первый из выбранных) или «Slider».
SHOW_FIELDS = ("single",)
#: FB-29.2 S6: источник блока «Banner» — выбранные баннеры или «баннеры этой страницы».
PLACE_FIELDS = (*SLIDER_FIELDS, *SHOW_FIELDS, "from_page")


def place_capable(host: str) -> bool:
    """Есть ли у страниц этого хоста объект, которому баннер задают в «Wo zeigen»
    (страница товара, услуги, каталог и категории, свои блоки объекта)."""
    from apps.tenants import siteconfig

    return host in (
        "product_detail",
        "service_detail",
        "stay_detail",
        "event_detail",
        "promo_detail",
        "catalog",
    ) or (
        isinstance(host, str)
        and (host.startswith(siteconfig.CATEGORY_HOST_PREFIX) or siteconfig.is_object_host(host))
    )


def _is_hero_row(item: dict) -> bool:
    return isinstance(item, dict) and item.get("key") == "hero" and not item.get("id")


def _is_usp_row(item: dict) -> bool:
    return isinstance(item, dict) and item.get("key") == "usp_bar" and not item.get("id")


#: FB-32 S2: подписи значков полосы доверия для панели (a11y).
USP_ICON_LABELS = {
    "shipping": gettext_lazy("Versand"),
    "returns": gettext_lazy("Rückgabe"),
    "payment": gettext_lazy("Zahlung"),
    "secure": gettext_lazy("Sicherheit"),
    "local": gettext_lazy("Regional"),
    "meister": gettext_lazy("Handwerk"),
    "support": gettext_lazy("Service"),
    "quality": gettext_lazy("Qualität"),
    "bio": gettext_lazy("Bio"),
    "clock": gettext_lazy("Zeit"),
    "check": gettext_lazy("Haken"),
}


def usp_panel(config: dict, item: dict) -> dict:
    """Пункты полосы доверия для панели: сохранённые + одна пустая строка «＋ Punkt»."""
    from apps.tenants import siteconfig

    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    items = siteconfig.clean_usp(data["items"] if "items" in data else config.get("usp_bar"))
    style = item.get("style") or ""
    return {
        "items": items,
        "free": len(items) < siteconfig._MAX_USP,
        "max": siteconfig._MAX_USP,
        # a11y-ревью: скринридеру — понятное имя значка, не технический ключ
        "icons": [
            (k, sym, str(USP_ICON_LABELS.get(k, k))) for k, sym in siteconfig.USP_ICONS.items()
        ],
        "style": style,
        "styles": [("", str(_("Standard")))]
        + [
            (k, str(siteconfig.SECTION_STYLE_LABELS.get(k, k)))
            for k in siteconfig.SECTION_STYLES["usp_bar"]
        ],
    }


def _update_usp(item: dict, fields: dict) -> bool:
    """Патч пунктов полосы доверия из панели: строки `usp_<i>_icon|label|text`, удаление
    (`usp_remove=i`), перестановка (`usp_move=i:up|down`), вид (`style`). Пустой заголовок —
    пункт убирается; без строк пунктов (запрос в обход формы) пункты не трогаются (ревью).
    True — изменилось."""
    from apps.tenants import siteconfig

    slots = {}
    for i in range(siteconfig._MAX_USP + 1):  # + пустая строка «＋ Punkt»
        if f"usp_{i}_label" in fields:
            slots[i] = {
                "icon": str(fields.get(f"usp_{i}_icon", "")),
                "label": str(fields.get(f"usp_{i}_label", "")).strip()[:120],
                "text": str(fields.get(f"usp_{i}_text", "")).strip()[:200],
            }
    before = (copy.deepcopy(item.get("data")), item.get("style"))
    if slots:
        remove = str(fields.get("usp_remove", ""))
        if remove.isdecimal() and remove.isascii():
            slots.pop(int(remove), None)
        order = sorted(slots)
        idx, _sep, way = str(fields.get("usp_move", "")).partition(":")
        if idx.isdecimal() and idx.isascii() and int(idx) in order:
            pos = order.index(int(idx))
            other = pos - 1 if way == "up" else pos + 1 if way == "down" else -1
            if 0 <= other < len(order):
                order[pos], order[other] = order[other], order[pos]
        item["data"] = {"items": siteconfig.clean_usp([slots[i] for i in order])}
    if "style" in fields:
        style = str(fields["style"]).strip()
        if style == "":
            item.pop("style", None)
        elif style in siteconfig.SECTION_STYLES.get("usp_bar", ()):
            item["style"] = style
    return (copy.deepcopy(item.get("data")), item.get("style")) != before


def banner_place(item: dict) -> bool:
    """Место, где показываются баннеры из библиотеки: баннер главной или блок «Banner»."""
    from apps.tenants import siteconfig

    if _is_hero_row(item):
        return True
    return (
        bool(item.get("id"))
        and (siteconfig.cblock_type(item.get("key")) or item.get("key")) == "banner"
    )


def _store_banner_data(item: dict, data: dict) -> None:
    """Данные места показа после правки выбора: у баннера главной — только выбор и
    настройки слайдера; у блока — его данные с тем же нормализатором."""
    from apps.tenants import siteconfig

    if _is_hero_row(item):
        item["data"] = siteconfig.clean_banner_choice(data) or {}
        return
    item["data"] = siteconfig._clean_cblock_data("banner", data)


def home_section(item: dict) -> bool:
    """Встроенная секция главной (не свой блок и не маркер основного списка)."""
    from apps.tenants import siteconfig

    return (
        not item.get("id")
        and not siteconfig.is_main_marker(item)
        and item.get("key") in {k for k, _label, _default in siteconfig.SECTIONS}
    )


def width_choices(item: dict) -> list[tuple[str, str]]:
    """Ширины, которые можно выбрать этому блоку: [(значение, подпись)]. Уже
    выбранная ширина остаётся в списке, даже если новой её не выбрать (W0)."""
    from apps.tenants import siteconfig

    key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
    if not item.get("id") and key in _FULL_BLEED_SECTIONS:
        # FB-30.3: баннер главной всегда во всю ширину экрана — переключатель «Ganz /
        # Randlos» ничего не менял, поэтому ширины у него нет.
        return []
    if not item.get("id"):
        # FB-29.5: встроенная секция главной — «Ganz», «Randlos» и доли до трети
        # Баннер рисуется во всю ширину экрана (`w-screen`) — узким он ломал бы вёрстку.
        narrow = () if key in _FULL_BLEED_SECTIONS else ("w23", "w12", "w13")
        allowed = ["contained", "full", *narrow]
    else:
        allowed = list(_WIDTH_ORDER if key in _NARROW_OK_BLOCKS else _WIDE_WIDTHS)
    current = item.get("width") or "contained"
    if current not in allowed and current in siteconfig.CBLOCK_WIDTHS:
        allowed.append(current)
    labels = {"contained": str(_("Ganz")), "full": str(_("Randlos")), **WIDTH_LABELS}
    return [(v, labels.get(v, v)) for v in allowed]


def width_names() -> dict[str, str]:
    """Ширина словами — для читалок (глиф «⅙» они произносят как придётся)."""
    return {
        "contained": str(_("ganze Breite")),
        "full": str(_("randlos, über die ganze Bildschirmbreite")),
        "w23": str(_("zwei Drittel")),
        "w12": str(_("die Hälfte")),
        "w13": str(_("ein Drittel")),
        "w14": str(_("ein Viertel")),
        "w15": str(_("ein Fünftel")),
        "w16": str(_("ein Sechstel")),
    }


def structure_types(tenant) -> list:
    """Типы страниц, у которых есть блоки И которые есть у этого бизнеса.

    Модуль выключен → типа нет (раньше магазин видел «Zimmer» и «Termine»). Один пункт
    на хост блоков: «Katalog» и «Kategorie» делят хост и правили одно и то же."""
    from apps.core import page_settings

    out, hosts = [], set()
    for pt in studio_pages.PAGE_TYPES:
        if pt.code != "home":
            if not _host(pt) or _host(pt) in hosts:
                continue
            if not page_settings.type_active(tenant, pt.code):
                continue
            hosts.add(_host(pt))
        out.append(pt)
    return out


def _row(
    config: dict,
    pt,
    code: str | None = None,
    label: str = "",
    preview: str = "",
    host: str | None = None,
) -> PageRow:
    code = code or pt.code
    if host is None:
        host = host_for(code)
    blocks = blocks_for(config, code, host=host, summaries=False)
    return PageRow(
        code=code,
        label=label or str(pt.label),
        host=host,
        # FB-31 (ревью P4): закреплённые строки осей (шапка, навигация) — не свои блоки
        count=sum(1 for b in blocks if b["enabled"] and b["cblock"]),
        preview_url=preview or _preview_url(pt),
    )


def type_groups(tenant, config: dict) -> list[tuple[str, list[PageRow]]]:
    """Опции select «Seitentyp» группами: главная, затем группа главного направления
    бизнеса, остальные направления, в конце «Inhalte» (вкл. каждую текстовую страницу)."""
    from apps.core import archetypes

    types = {pt.code: pt for pt in structure_types(tenant)}
    primary = archetypes.primary_module(tenant) or ""
    ordered = sorted(_TYPE_GROUPS, key=lambda g: g[2] != primary)  # стабильно: главное первым
    groups: list[tuple[str, list[PageRow]]] = []
    if "home" in types:
        groups.append((str(types["home"].label), [_row(config, types["home"])]))
    used = {"home"}
    for _key, label, _module, codes in ordered:
        labels = {CATEGORY: str(_ALL_CATEGORIES), PROMO_GROUP: str(_ALL_PROMO_GROUPS)}
        rows = [_row(config, types[c], label=labels.get(c, "")) for c in codes if c in types]
        used.update(codes)
        if rows:
            groups.append((str(label), rows))
        pt = _category_type(tenant) if "catalog" in codes and "catalog" in types else None
        if pt is not None:
            # FB-27 R7: каждая категория — своя строка (своя схема заменяет блоки каталога)
            cats = [
                _row(config, pt, code=p.code, label=p.label, preview=p.preview_url, host=p.host)
                for p in category_pages(config)
            ]
            if cats:
                groups.append((str(_CATEGORY_GROUP), cats))
        if PROMO_GROUP in codes and PROMO_GROUP in types:
            # FB-31 P3 R6: каждая живая группа акций — своя строка (своя схема «nur diese»)
            pt_group = types[PROMO_GROUP]
            promo_rows = [
                _row(
                    config, pt_group, code=p.code, label=p.label, preview=p.preview_url, host=p.host
                )
                for p in promo_group_pages(config)
            ]
            if promo_rows:
                groups.append((str(_PROMO_GROUP_GROUP), promo_rows))
    content = []
    for code, pt in types.items():
        if code in used:
            continue
        if code == TEXT:
            content.extend(
                _row(config, pt, code=p.code, label=p.label, preview=p.preview_url, host=p.host)
                for p in text_pages()
            )
        else:
            content.append(_row(config, pt))
    if content:
        groups.append((str(_CONTENT_GROUP), content))
    return groups


def schema_layout(blocks: list[dict]) -> dict:
    """Схема страницы: ряды видимых блоков (узкие соседи — в одном ряду, как на витрине)
    и отдельный список скрытых. Чистая функция."""
    from apps.tenants import siteconfig

    visible = [b for b in blocks if b["enabled"]]
    rows = []
    for g in siteconfig.group_block_rows(visible):
        rows.append(g["row"] if g.get("key") == "_row" else [g])
    # FB-30.8: у ряда узких блоков со свободным местом — место «перетащите сюда»
    lines = []
    for row in rows:
        label = _slot_label(row_free(row))
        lines.append(
            {"blocks": row, "slot": {"ref": row[-1]["ref"], "label": label} if label else None}
        )
    return {"rows": rows, "lines": lines, "hidden": [b for b in blocks if not b["enabled"]]}


def add_options(code: str) -> list[tuple[str, str]]:
    """Какие блоки можно добавить на этот тип страницы (повторяемые + ссылочные на страницах)."""
    from apps.tenants import siteconfig

    keys = list(siteconfig.REPEATABLE_BLOCKS)
    if code != "home":
        keys += list(siteconfig.PAGE_REF_BLOCKS)
    if code == "confirmation":
        # FB-33 M2h-5: на подтверждении блоков с формами нет (данные сделки рядом)
        from apps.core.confirmation_page import FORM_BLOCKS

        keys = [k for k in keys if k not in FORM_BLOCKS]
    # FB-33 M2e: подпись с семьёй («Text · Foto + Text»)
    return [(k, block_catalog.menu_label(k)) for k in keys]


#: FB-27 R8d: пункт «+ Block» для сохранённого шаблона блока — `tpl:<id шаблона>`.
TEMPLATE_PREFIX = "tpl:"


def add_groups(code: str, config: dict | None = None) -> list[dict]:
    """Пункты «+ Block» группами: [{key, title, options: [(тип, подпись)]}]. С `config` —
    ещё группа сохранённых шаблонов блоков (только типов, которые можно ставить сюда).

    FB-27 R6: группы — решение владельца; FB-33 M2a: группа каждого типа — в каталоге блоков
    (`block_catalog.LIBRARY`). Тип вне каталога попадает в первую группу: новый блок не
    должен пропасть из меню молча."""
    options = add_options(code)
    first = block_catalog.ADD_GROUPS[0][0]
    group_of = {k: block_catalog.library_entry(k) for k, _lab in options}
    out = []
    for key, title in block_catalog.ADD_GROUPS:
        mine = [
            (k, lab) for k, lab in options if (group_of[k].group if group_of[k] else first) == key
        ]
        if mine:
            out.append({"key": key, "title": str(title), "options": mine})
    allowed = dict(options)
    saved = [
        (f"{TEMPLATE_PREFIX}{tid}", str(tpl.get("label") or allowed[tpl["key"]]))
        for tid, tpl in ((config or {}).get("block_templates") or {}).items()
        if isinstance(tpl, dict) and tpl.get("key") in allowed
    ]
    if saved:
        out.append({"key": "vorlagen", "title": str(_("Eigene Vorlagen")), "options": saved})
    return out


#: FB-27 R6: «Fertige Zeilen» — несколько блоков одним действием, уже в один ряд.
#: Пресет → (подпись, [(тип, ширина, данные | None = демо типа)]).
_CARD = {"title": "Überschrift", "body": "Kurzer Text zu diesem Punkt."}
ROW_PRESETS = {
    "text_image": (gettext_lazy("Text + Foto"), (("text", "w12", None), ("image", "w12", None))),
    "image_text": (gettext_lazy("Foto + Text"), (("image", "w12", None), ("text", "w12", None))),
    "three_cards": (
        gettext_lazy("Drei Karten"),
        (("text", "w13", _CARD), ("text", "w13", _CARD), ("text", "w13", _CARD)),
    ),
    "text_contact": (
        gettext_lazy("Text + Kontakt"),
        (("text", "w12", None), ("contact_card", "w12", None)),
    ),
}


def row_options() -> list[tuple[str, str]]:
    return [(key, str(label)) for key, (label, _blocks) in ROW_PRESETS.items()]


def preset_blocks(preset: str) -> list[dict]:
    """Блоки готовой строки (новые id); первый начинает новый ряд."""
    from apps.tenants import siteconfig

    if preset not in ROW_PRESETS:
        raise SchemaError("row")
    out = []
    for i, (key, width, data) in enumerate(ROW_PRESETS[preset][1]):
        demo = siteconfig.CBLOCK_DEMO_DATA.get(key, {}) if data is None else data
        block = {
            "key": key,
            "id": uuid.uuid4().hex[:12],
            "enabled": True,
            "data": siteconfig._clean_cblock_data(key, copy.deepcopy(demo)),
            "width": width,
        }
        if i == 0:
            block["newline"] = True
        out.append(block)
    return out


class SchemaError(ValueError):
    """Недопустимая операция схемы (неизвестный тип/блок/операция)."""


def resolve(tenant, code: str):
    """(pt, host, home) строки схемы либо SchemaError. Тип, которого у бизнеса нет,
    не правится и POST'ом в обход экрана — иначе появлялись бы блоки «в запас»,
    всплывающие при включении модуля (FB-27 R1)."""
    from apps.core import page_settings

    pt = _page_type(code)
    if pt is None:
        raise SchemaError("page")
    if pt.code != "home" and not page_settings.type_active(tenant, pt.code):
        raise SchemaError("page")
    host = host_for(code)
    home = pt.code == "home"
    if not home and not host:
        raise SchemaError("page")
    return pt, host, home


def lift_hero_choice(config: dict, items: list[dict]) -> None:
    """FB-29.2: выбор баннеров главной из строки «Banner» — обратно в `hero_banners`
    (одно место хранения). Зовут запись (`store_items`) и показ черновика
    (`aufbau_draft.overlay`): панель и превью видят выбор ещё до «Speichern»."""
    from apps.tenants import siteconfig

    for item in items:
        if _is_usp_row(item) and isinstance(item.get("data"), dict):
            # FB-32 S2: пункты полосы доверия — обратно в `usp_bar` (одно место хранения)
            usp = siteconfig.clean_usp(item.pop("data").get("items"))
            if usp:
                config["usp_bar"] = usp
            else:
                config.pop("usp_bar", None)
            continue
        if _is_hero_row(item):
            if "data" not in item:
                continue  # строка без метки выбора (старый черновик) — сохранённое не трогаем
            choice = siteconfig.clean_banner_choice(item.pop("data", None))
            if choice:
                config["hero_banners"] = choice
            else:
                config.pop("hero_banners", None)


def _catalog_code(config: dict, host: str) -> str:
    """Прежний код шаблона страницы каталога/категории (то, что вид блоков перекрывает)."""
    from apps.catalog import category_styles
    from apps.tenants import siteconfig

    if host == "catalog":
        return category_styles.root_page_style(config.get("catalog_page_style", ""))
    if host == "category":  # «Alle Kategorien»: общий шаблон категорий сайта
        return category_styles.page_style(
            None, (config.get("site_defaults") or {}).get("category_page_style", "")
        )
    slug = host.removeprefix(siteconfig.CATEGORY_HOST_PREFIX)
    default = (config.get("site_defaults") or {}).get("category_page_style", "")
    try:
        from apps.catalog.models import Category

        category = Category.objects.filter(slug=slug).first()
    except Exception:  # noqa: BLE001 — экран не должен падать без схемы бизнеса
        category = None
    return category_styles.page_style(category, default) if category else ""


#: FB-30.16 R4: подписи видов блоков каталога (плитки панели; миниатюра — по коду шаблона).
CATEGORY_VIEW_CHOICES = (
    ("auto", gettext_lazy("Automatisch"), gettext_lazy("Fotokacheln oder Chips – wie bisher."), ""),
    (
        "regale",
        gettext_lazy("Regale"),
        gettext_lazy("Jede Unterkategorie als Reihe mit Pfeilen."),
        "regale",
    ),
    (
        "tabs",
        gettext_lazy("Reiter"),
        gettext_lazy("Unterkategorien als Reiter über den Produkten."),
        "tabs",
    ),
    (
        "index",
        gettext_lazy("Index"),
        gettext_lazy("Verzeichnis in Spalten – für große Sortimente."),
        "kompakt",
    ),
    (
        "side",
        gettext_lazy("Seitenspalte"),
        gettext_lazy("Kategorien und Filter links, Produkte rechts."),
        "navigator",
    ),
    (
        "wegweiser",
        gettext_lazy("Wegweiser"),
        gettext_lazy("Abteilungen als Kacheln, dann «Im Fokus»."),
        "wegweiser",
    ),
)
MAIN_VIEW_LABELS = (
    (
        "raster",
        gettext_lazy("Raster"),
        gettext_lazy("Foto, Name, Preis – die übliche Ansicht."),
        "",
    ),
    (
        "schaufenster",
        gettext_lazy("Schaufenster"),
        gettext_lazy("Erstes Produkt groß, der Rest im Raster."),
        "schaufenster",
    ),
    (
        "magazin",
        gettext_lazy("Magazin"),
        gettext_lazy("Zwei große Karten pro Reihe mit Beschreibung."),
        "magazin",
    ),
    (
        "mosaik",
        gettext_lazy("Mosaik"),
        gettext_lazy("Kacheln verschiedener Größe – für starke Fotos."),
        "mosaik",
    ),
)


#: FB-30.16 R5b: шапка и сеты страницы каталога/категорий — свои строки с видом.
PART_VIEW_CHOICES = {
    "page_head": (
        gettext_lazy("Banner · Fotos der Seite"),
        (
            (
                "aus",
                gettext_lazy("Ohne Kopfbereich"),
                gettext_lazy("Die Seite beginnt direkt mit dem Inhalt."),
                "",
            ),
            (
                "titelbild",
                gettext_lazy("Titelbild"),
                gettext_lazy("Foto und Beschreibung der Seite oben."),
                "kopfbild",
            ),
        ),
    ),
    "combos": (
        gettext_lazy("Sets & Menüs"),
        (
            (
                "below",
                gettext_lazy("Unter den Produkten"),
                gettext_lazy("Erst die Produkte, dann die Sets."),
                "",
            ),
            (
                "above",
                gettext_lazy("Über den Produkten"),
                gettext_lazy("Sets zuerst, dann einzelne Produkte."),
                "sets",
            ),
        ),
    ),
}


#: FB-31 P4: поверхности листингов в гейте `composition_gate`
_LISTING_GATES = frozenset(
    {"services", "stays", "events", "tours", "combos", "lookbook", "wishlist", "blog", "reviews"}
)


def mark_view_availability(config: dict, host: str, view: dict) -> None:
    """Плитки вида выбранного блока: вид без подкатегорий или наборов виден, но недоступен
    с причиной (то же правило, что было у плиток шаблона; гейт — `composition_gate`)."""
    from apps.core import page_settings
    from apps.tenants import siteconfig

    surface = "category" if host == "category" or host.startswith("catalog:") else "catalog"
    part = siteconfig.part_surface(host)  # FB-31 P3: акции — имя поверхности = гейт
    if part is not None:
        surface = part.name
    off = page_settings.composition_gate(config).get(surface, set())
    reason = str(
        _("Nur mit Angebotsgruppen verfügbar.")  # FB-31 P3: у акций нет подкатегорий
        if surface == "promos"
        else _("Nur mit Unterteilung der Liste verfügbar.")  # FB-31 P4: листинги
        if surface in _LISTING_GATES
        else page_settings.UNAVAILABLE_REASON
    )
    photo_reason = str(_("Nur mit Foto der Seite verfügbar."))
    view["tiles"] = [
        {
            "value": value,
            "label": label,
            "hint": hint,
            "thumb": thumb,
            "available": not thumb or thumb not in off or value == view.get("value"),
            "reason": (photo_reason if thumb == "kopfbild" else reason)
            if thumb and thumb in off
            else "",
        }
        for value, label, hint, thumb in view["choices"]
    ]
    if tuple(view.get("choices") or ()) == CATEGORY_VIEW_CHOICES:
        # FB-32 S5a: один список видов с главной — её формы плиток видны с причиной
        from apps.core import block_views

        view["tiles"] += [
            {
                "value": f"home:{u['key']}",  # своё значение — не совпадёт с видом каталога
                "label": u["label"],
                "hint": "",
                "thumb": "",
                "thumb_style": u["thumb_style"],
                "available": False,
                "synthetic": True,
                "reason": u["reason"],
            }
            for u in block_views.unavailable(block_views.CATALOG)
        ]


def check_view_available(config: dict, host: str, ref: str, value: str, op: str = "") -> None:
    """SchemaError, если вид блока каталога сейчас недоступен (нет подкатегорий/наборов)."""
    row = next((b for b in blocks_for(config, _code_of_host(host), host) if b["ref"] == ref), None)
    if op == "maingroup":
        view = (row or {}).get("groupview")
    else:
        view = (row or {}).get("catview") or (row or {}).get("mainview")
    if not view:
        return  # не прикреплённая строка — решит mutate
    mark_view_availability(config, host, view)
    tile = next((t for t in view["tiles"] if t["value"] == value), None)
    if tile is not None and (not tile["available"] or tile.get("synthetic")):
        raise SchemaError("value")


def _code_of_host(host: str) -> str:
    if host == "promos":
        return "promos"
    if host == "promo_detail":
        return "promo"
    if host.startswith("promo:"):
        return f"promo@{host}"
    if host == "promo_group" or host.startswith("promo_group:"):
        return host if host == "promo_group" else f"promo_group@{host}"
    from apps.core import listing_parts

    if host in listing_parts.SURFACE_OF_HOST:  # FB-31 P4: листинги (номера — `stay_rooms`)
        return listing_parts.SURFACE_OF_HOST[host]
    return "category" if host == "category" else "catalog"


def _has_combos() -> bool:
    try:
        from apps.catalog.models import Combo

        return Combo.objects.exists()
    except DatabaseError:  # ревью R5b: только ошибка БД, и не молча
        logger.warning("site_schema: Combo check failed", exc_info=True)
        return False


def _catalog_view_panel(config: dict, host: str, item: dict, main: bool) -> dict:
    """Панель вида блока каталога: текущий вид (сохранённый либо из прежнего шаблона)."""
    from apps.catalog import catalog_parts

    rows_cfg = config
    if host == "category" and "category" not in (config.get("page_blocks") or {}):
        # до первого сохранения витрина категорий берёт вид из шаблона — панель тоже
        rows_cfg = {}
    parts = catalog_parts.effective(rows_cfg, host, code=_catalog_code(config, host))
    if main:
        value = parts.products if parts.products in MAIN_VIEW_CHOICES else "raster"
        return {
            "label": f"★ {_('Produkte')}",
            "mainview": {"value": value, "choices": MAIN_VIEW_LABELS},
        }
    key = item.get("key")
    if key in PART_VIEW_CHOICES:
        label, choices = PART_VIEW_CHOICES[key]
        value = (parts.head or "aus") if key == "page_head" else parts.sets
        current = next((lab for v, lab, _h, _t in choices if v == value), "")
        return {
            "label": str(label),
            "pinned": True,
            "widths": [],
            "summary": str(current),
            "catview": {"value": value, "choices": choices, "title": str(label)},
        }
    value = parts.categories or "auto"
    current = next((lab for v, lab, _h, _t in CATEGORY_VIEW_CHOICES if v == value), "")
    return {
        "pinned": True,
        "widths": [],  # прикреплён к ★ — ширины и ряда нет
        "summary": str(current),
        "catview": {"value": value, "choices": CATEGORY_VIEW_CHOICES},
    }


#: FB-31 P3: плитки видов строк страниц акций (миниатюра — по коду шаблона).
PROMO_PART_CHOICES = {
    ("promos", "page_head"): (
        gettext_lazy("Banner · Fotos der Seite"),
        (
            (
                "aus",
                gettext_lazy("Ohne Kopfbereich"),
                gettext_lazy("Die Seite beginnt direkt mit dem Inhalt."),
                "",
            ),
            (
                "titelbild",
                gettext_lazy("Titelbild"),
                gettext_lazy("Foto und Beschreibung der Seite oben."),
                "kopfbild",
            ),
        ),
    ),
    ("promos", "groups"): (
        gettext_lazy("Angebotsgruppen"),
        (
            (
                "auto",
                gettext_lazy("Automatisch"),
                gettext_lazy("Gruppen als Chips – wie bisher."),
                "",
            ),
            (
                "regale",
                gettext_lazy("Regale"),
                gettext_lazy("Jede Gruppe als Reihe mit Pfeilen."),
                "regale",
            ),
            (
                "tabs",
                gettext_lazy("Reiter"),
                gettext_lazy("Gruppen als Reiter über den Aktionen."),
                "tabs",
            ),
            (
                "index",
                gettext_lazy("Index"),
                gettext_lazy("Verzeichnis der Gruppen in Spalten."),
                "kompakt",
            ),
            (
                "side",
                gettext_lazy("Seitenspalte"),
                gettext_lazy("Gruppen und Suche links, Aktionen rechts."),
                "navigator",
            ),
        ),
    ),
    ("promo_group", "page_head"): (
        gettext_lazy("Banner · Kopf der Gruppe"),
        (
            (
                "standard",
                gettext_lazy("Titel"),
                gettext_lazy("Name der Gruppe und Zahl der Aktionen."),
                "",
            ),
            (
                "prospekt",
                gettext_lazy("Prospekt"),
                gettext_lazy("Farbiges Band mit Gültigkeit."),
                "prospekt",
            ),
            (
                "countdown",
                gettext_lazy("Countdown"),
                gettext_lazy("Dunkles Band mit Zähler bis zum Ende."),
                "countdown",
            ),
        ),
    ),
    ("promo", "offer"): (
        gettext_lazy("Angebot"),
        (
            (
                "standard",
                gettext_lazy("Standard"),
                gettext_lazy("Foto, Preis und Bedingungen – wie bisher."),
                "",
            ),
            (
                "plakat",
                gettext_lazy("Plakat"),
                gettext_lazy("Großer Preis über dem Foto."),
                "plakat",
            ),
            (
                "prospekt",
                gettext_lazy("Angebotszettel"),
                gettext_lazy("Wie ein Prospekt mit Farbband."),
                "prospekt",
            ),
            (
                "kompakt",
                gettext_lazy("Kompakt"),
                gettext_lazy("Alles auf einen Blick, wenig Platz."),
                "kompakt",
            ),
            (
                "magazin",
                gettext_lazy("Magazin"),
                gettext_lazy("Großes Foto, Text darunter."),
                "magazin",
            ),
        ),
    ),
}
PROMO_MAIN_CHOICES = (
    (
        "raster",
        gettext_lazy("Raster"),
        gettext_lazy("Foto, Name, Preis – die übliche Ansicht."),
        "",
    ),
    (
        "preisliste",
        gettext_lazy("Preisliste"),
        gettext_lazy("Tabelle mit Preisen – ohne Fotos."),
        "preisliste",
    ),
    (
        "schaufenster",
        gettext_lazy("Schaufenster"),
        gettext_lazy("Erste Aktion groß, der Rest im Raster."),
        "schaufenster",
    ),
    (
        "magazin",
        gettext_lazy("Magazin"),
        gettext_lazy("Zwei große Karten mit Bedingungen."),
        "magazin",
    ),
    (
        "prospekt",
        gettext_lazy("Prospekt"),
        gettext_lazy("Dichtes Raster wie im Handzettel."),
        "prospekt",
    ),
)
PROMO_GROUP_MAIN_CHOICES = (
    (
        "raster",
        gettext_lazy("Raster"),
        gettext_lazy("Foto, Name, Preis – die übliche Ansicht."),
        "",
    ),
    (
        "schaufenster",
        gettext_lazy("Schaufenster"),
        gettext_lazy("Erste Aktion groß, der Rest im Raster."),
        "schaufenster",
    ),
    (
        "prospekt",
        gettext_lazy("Prospekt"),
        gettext_lazy("Dichtes Raster wie im Handzettel."),
        "prospekt",
    ),
    (
        "magazin",
        gettext_lazy("Magazin"),
        gettext_lazy("Zwei große Karten mit Bedingungen."),
        "magazin",
    ),
    ("countdown", gettext_lazy("Countdown"), gettext_lazy("Karten mit Restzeit."), "countdown"),
    (
        "vergleich",
        gettext_lazy("Vergleich"),
        gettext_lazy("Spalten nebeneinander, «Beliebt» markiert."),
        "vergleich",
    ),
)
PROMO_GROUPING_CHOICES = (
    ("auto", gettext_lazy("Nach Gruppen"), gettext_lazy("Aktionen in Abschnitten je Gruppe."), ""),
    ("ohne", gettext_lazy("Ohne Abschnitte"), gettext_lazy("Alle Aktionen in einer Liste."), ""),
)


def _part_view_panel(config: dict, host: str, item: dict, main: bool) -> dict:
    """FB-31 P3: панель вида строки страницы акций — текущий вид (строки либо шаблон)."""
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    surface = siteconfig.part_surface(host)
    from apps.core import listing_parts

    if surface.name in listing_parts.LISTINGS or surface in (
        listing_parts.TEAM,
        listing_parts.GALLERY,
    ):
        return _listing_view_panel(config, host, item, main)
    if host.startswith("promo:"):
        # ревью R5: своя страница акции — то же правило, что у витрины (свой шаблон
        # акции и общая строка «Angebot» под её своими блоками)
        from apps.promotions import promo_parts

        promo = _object_for(f"promo@{host}")
        sd = (config or {}).get("site_defaults") or {}
        parts = promo_parts.detail_parts(
            config,
            getattr(promo, "page_style", "") or "",
            sd.get("promo_detail_style", ""),
            host,
        )
    elif surface.name == "promo_group":
        from apps.promotions import promo_parts

        if siteconfig.is_promo_group_host(host):
            # своя группа — правило витрины (свой шаблон группы, общие строки под ней)
            parts = promo_parts.group_parts(config, promo_group_key(host))
        else:
            parts = pp.effective(surface, config, host, code=_promo_code(config, host))
    else:
        parts = pp.effective(surface, config, host, code=_promo_code(config, host))
    if main and surface.name == "promo_group":
        return {
            "label": f"★ {_('Aktionen')}",
            "mainview": {
                "value": parts.view or "raster",
                "choices": PROMO_GROUP_MAIN_CHOICES,
                "title": str(_("Wie Aktionen gezeigt werden")),
            },
        }
    if main:
        if surface.name != "promos":
            return {}
        return {
            "label": f"★ {_('Aktionen')}",
            "mainview": {
                "value": parts.view or "raster",
                "choices": PROMO_MAIN_CHOICES,
                "title": str(_("Wie Aktionen gezeigt werden")),
            },
            "groupview": {
                "value": parts.grouping or "auto",
                "choices": PROMO_GROUPING_CHOICES,
                "title": str(_("Abschnitte")),
            },
        }
    key = item.get("key")
    label, choices = PROMO_PART_CHOICES[(surface.name, key)]
    axis = next(a for a in surface.axes if a.key == key)
    value = parts.get(axis.name) or axis.off
    current = next((lab for v, lab, _h, _t in choices if v == value), "")
    return {
        "label": str(label),
        "pinned": True,
        "widths": [],
        "summary": str(current),
        "catview": {"value": value, "choices": choices, "title": str(label)},
    }


TOURS_GROUPING_CHOICES = (
    ("auto", gettext_lazy("Nach Ländern"), gettext_lazy("Reisen in Abschnitten je Land."), ""),
    ("ohne", gettext_lazy("Ohne Abschnitte"), gettext_lazy("Alle Reisen in einer Liste."), ""),
)
#: FB-31 P4: подпись строки навигации листинга (что в ней — подборки, темы, разделы)
LISTING_GROUPS_LABEL = {
    "services": gettext_lazy("Kollektionen"),
    "stays": gettext_lazy("Kollektionen"),
    "events": gettext_lazy("Themen"),
    "combos": gettext_lazy("Bereiche"),
}


def _listing_groups_choices(label) -> tuple:
    return (
        ("auto", _("Automatisch"), _("Als Chips über der Liste – wie bisher."), ""),
        ("regale", _("Regale"), _("Jede Gruppe als Reihe mit Pfeilen."), "regale"),
        ("tabs", _("Reiter"), _("Als Reiter über der Liste."), "tabs"),
        ("index", _("Index"), _("Verzeichnis in Spalten."), "kompakt"),
        ("side", _("Seitenspalte"), _("Links die Gruppen, rechts die Liste."), "navigator"),
    )


def _section_view_panel(config: dict, host: str, main: bool) -> dict:
    """FB-31 P4 R8: ★ «Team»/«Galerie» — вид списка на этой странице; «Wie auf der
    Startseite» = вид секции главной (как раньше)."""
    from apps.core import listing_parts
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    if not main:
        return {}
    surface = listing_parts.BY_HOST[host]
    rows = ((config or {}).get("page_blocks") or {}).get(host) or []
    value = pp.from_rows(surface, rows).view or listing_parts.RASTER
    choices = (
        ("raster", _("Wie auf der Startseite"), _("Ansicht des Abschnitts der Startseite."), ""),
    ) + tuple(
        (v, siteconfig.SECTION_STYLE_LABELS.get(v, v), "", "") for v in surface.axis("view").values
    )
    label = _("Team") if host == "team" else _("Fotos")
    return {
        "label": f"★ {label}",
        # шаблона Студии у этих страниц нет — подсказка про «Seitenvorlage» не нужна
        "mainview": {
            "value": value,
            "choices": choices,
            "title": str(_("Ansicht")),
            "no_hint": True,
        },
    }


def _listing_view_panel(config: dict, host: str, item: dict, main: bool) -> dict:
    """FB-31 P4: панель строки листинга — шапка и навигация (вид из строк либо шаблона).
    У ★ листинга своих полей нет: его вид — сетка и форма карточки (настройки страницы)."""
    from apps.core import listing_parts

    if host in ("team", "gallery"):
        return _section_view_panel(config, host, main)
    surface = listing_parts.SURFACE_OF_HOST.get(host)
    if surface is None:
        return {}
    parts = listing_parts.effective(config, surface)
    if main:
        if surface != "tours":
            return {}
        return {  # FB-31 P4 R6: туры — разбивка по странам
            "groupview": {
                "value": parts.grouping or listing_parts.GROUPED,
                "choices": TOURS_GROUPING_CHOICES,
                "title": str(_("Abschnitte")),
            }
        }
    key = item.get("key")
    if key == listing_parts.HEAD_KEY:
        label, choices = PROMO_PART_CHOICES[("promos", "page_head")]
        value = parts.head or listing_parts.HEAD_OFF
    else:
        label = LISTING_GROUPS_LABEL.get(surface, _("Gruppen"))
        choices = _listing_groups_choices(label)
        value = parts.groups or listing_parts.GROUPS_AUTO
    current = next((lab for v, lab, _h, _t in choices if v == value), "")
    return {
        "label": str(label),
        "pinned": True,
        "widths": [],
        "summary": str(current),
        "catview": {"value": value, "choices": choices, "title": str(label)},
    }


def _promo_code(config: dict, host: str) -> str:
    """Прежний код шаблона страницы акций (то же, что берёт витрина)."""
    from apps.promotions import group_styles

    if host == "promos":
        return group_styles.promo_page_style(read_old((config or {}).get("promo_page_style")))
    sd = (config or {}).get("site_defaults") or {}
    if host == "promo_group":
        return group_styles.group_style("", None, read_old(sd.get("promo_group_style", "")))
    return group_styles.promotion_detail_style("", read_old(sd.get("promo_detail_style", "")))


def _rows_host(code: str) -> str:
    """Хост строк схемы по коду строки (`catalog`, `promo` → `promo_detail`,
    `promo@promo:<hex>` → `promo:<hex>`) — без проверки объекта (её делает `host_for`)."""
    last = str(code).split("@")[-1]
    if ":" in last:
        return last
    pt = _page_type(last)
    return _host(pt) if pt is not None else last


def load_items(config: dict, home: bool, host: str) -> list[dict]:
    """Копия блоков страницы в том виде, в котором их правит схема."""
    from apps.tenants import siteconfig

    if home:
        items = copy.deepcopy(config.get("sections") or [])
        # FB-29.2: выбор баннеров главной хранится в `hero_banners`; на время правки он
        # едет в строке «Banner» — так его несёт черновик, как и остальные правки схемы
        choice = siteconfig.clean_banner_choice(config.get("hero_banners"))
        for item in items:
            if _is_hero_row(item):
                item["data"] = choice or {}  # ключ есть всегда: «выбор прочитан»
            elif _is_usp_row(item):
                # FB-32 S2: пункты полосы доверия едут в черновике в своей строке
                item["data"] = {"items": siteconfig.clean_usp(config.get("usp_bar"))}
        return items
    from apps.core import detail_parts

    if detail_parts.module_of(host):  # FB-31 P5: разделы детали — строками среди блоков
        return copy.deepcopy(
            detail_parts.edit_rows(config, host, siteconfig.page_rows(config, host))
        )
    if detail_parts.object_kind(host):  # R8: своя схема одного объекта
        return copy.deepcopy(
            detail_parts.object_edit_rows(config, host, siteconfig.page_rows(config, host))
        )
    return copy.deepcopy(siteconfig.main_list_sequence(host, siteconfig.page_rows(config, host)))


def _mark_sections(config: dict, kind: str, obj, out: list[dict], idx: list[int]) -> None:
    """R8 (макет): у строк разделов схемы объекта — чем он отличается от всех страниц."""
    from apps.core import detail_parts, object_structure
    from apps.tenants import siteconfig

    module = detail_parts.module_of(detail_parts.OBJECT_SHARED[kind])
    own = object_structure.clean(object_structure._state(config, obj), module)
    shared_hidden = siteconfig.detail_section_hidden(config, module)
    for i in idx:
        key = out[i]["key"]
        if key in own.get("hidden", []):
            out[i]["summary"] = str(_("nur hier ausgeblendet"))
        elif key in own.get("shown", []):
            out[i]["summary"] = str(_("hier immer sichtbar"))
        else:
            out[i]["summary"] = str(
                _("Standard: ausgeblendet") if key in shared_hidden else _("Standard: sichtbar")
            )
    if own.get("order") and idx:
        first = out[idx[0]]
        first["summary"] = f"{first['summary']} · {_('Eigene Reihenfolge der Abschnitte')}"


def _with_shared_rows(config: dict, host: str, out: list[dict]) -> list[dict]:
    """R8 (решение владельца): в схеме одного объекта общие блоки страницы видны пунктиром
    на своих местах (у раздела — перед своими), правятся на общей схеме."""
    from apps.core import detail_parts
    from apps.tenants import siteconfig

    obj = detail_parts.object_for_host(host)
    if obj is None:
        return out
    kind = detail_parts.object_kind(host)
    shared = detail_parts.shared_host(host)
    rows = siteconfig.page_rows(config, shared)
    a = detail_parts.anchors(rows, shared, detail_parts.object_order(config, kind, obj))
    by_id = {r["id"]: r for r in rows if isinstance(r, dict) and r.get("id")}
    if not by_id:
        keys = set(detail_parts.section_keys(host))
        idx = [i for i, b in enumerate(out) if b["key"] in keys and not b["cblock"]]
        _mark_sections(config, kind, obj, out, idx)
        return out
    if not a["placed"]:
        a = {"lead": [], "after": {}, "tail": list(by_id)}
    note = _("Auf allen Seiten dieser Art · dort bearbeiten")

    def rows_for(ids):
        return [
            {
                "ref": f"shared:{i}",
                "key": by_id[i].get("key", ""),
                "label": _sections_label(by_id[i].get("key", "")),
                "summary": f"{_row_summary(config, by_id[i])} · {note}".strip(" ·"),
                "enabled": by_id[i].get("enabled", True) is not False,
                "main": False,
                "cblock": False,
                "fixed": True,
                "pinned": True,
                "shared": True,
                # ширина — как на витрине (иначе ½-блок в схеме во всю ширину)
                "width": by_id[i].get("width") or "",
                "newline": bool(by_id[i].get("newline")),
                "width_label": WIDTH_LABELS.get(by_id[i].get("width") or "", ""),
                "flex": WIDTH_FLEX.get(by_id[i].get("width") or "", 12),
            }
            for i in ids
            # скрытый на общей схеме блок на витрине не виден — и здесь его нет (ревью:
            # иначе он попадал в «Ausgeblendet» ссылкой на несуществующую строку)
            if i in by_id and by_id[i].get("enabled", True) is not False
        ]

    # FB-33 M2g: и строки «на месте» — общий хвост встаёт после них (страница события рисует
    # группы и серию до хвоста блоков)
    keys = set(detail_parts.section_keys(host))
    sections = [i for i, b in enumerate(out) if b["key"] in keys and not b["cblock"]]
    if not sections:
        return out
    _mark_sections(config, kind, obj, out, sections)
    merged = list(out[: sections[0]]) + rows_for(a["lead"])
    for n, i in enumerate(sections):
        end = sections[n + 1] if n + 1 < len(sections) else len(out)
        merged.append(out[i])
        merged += rows_for(a["after"].get(out[i]["key"], []))
        if n + 1 == len(sections):
            merged += rows_for(a["tail"])
        merged += out[i + 1 : end]
    return merged


def _is_in_place(item, rows_host: str) -> bool:
    from apps.core import detail_parts

    return (
        isinstance(item, dict)
        and not item.get("id")
        and item.get("key") in detail_parts.in_place_keys(rows_host)
    )


def _past_in_place(items: list[dict], ref: str, rows_host: str) -> None:
    """FB-33 M2g (ревью): блок перед строкой «на месте» страница рисует после всей группы таких
    строк (они не якоря) — в схеме он встаёт туда же: редактор = страница."""
    at = next((i for i, it in enumerate(items) if it.get("id") == ref), None)
    if at is None:
        return
    while at + 1 < len(items) and _is_in_place(items[at + 1], rows_host):
        items[at], items[at + 1] = items[at + 1], items[at]
        at += 1


def _pinned_slide(items: list[dict], ref: str, rows_host: str, *, up: bool) -> None:
    """FB-33 M2h: между формой и итогом корзины блоков нет (§ 312j BGB) — блок, вставший
    туда, идёт дальше по ходу: «выше» — над формой («Hinweise»), иначе — под итог."""
    from apps.core import detail_parts

    pair = detail_parts.SLIDE.get(detail_parts.module_of(detail_parts.shared_host(rows_host)))
    if not pair:
        return
    at = next((i for i, it in enumerate(items) if it.get("id") == ref), None)
    keys = [None if it.get("id") else it.get("key") for it in items]
    if at is None or pair[0] not in keys or pair[1] not in keys:
        return
    first, second = keys.index(pair[0]), keys.index(pair[1])
    if not first < at < second:
        return
    moved = items.pop(at)
    items.insert(first if up else second, moved)  # после pop итог сдвинулся на одну строку


def _pinned_order_ok(items: list[dict], rows_host: str) -> bool:
    """FB-33 M2h: неподвижные строки — в порядке реестра, прочие разделы — после них."""
    from apps.core import detail_parts

    pinned = detail_parts.pinned_keys(rows_host)
    if not pinned:
        return True
    sections = set(detail_parts.flow_section_keys(rows_host))
    seq = [it.get("key") for it in items if not it.get("id") and it.get("key") in sections]
    head = [k for k in seq if k in pinned]
    if head != [k for k in pinned if k in head]:
        return False
    last = max((i for i, k in enumerate(seq) if k in pinned), default=-1)
    return all(k in pinned for k in seq[: last + 1])


def mutate(
    items: list[dict],
    code: str,
    op: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
    templates: dict | None = None,
    notes: list | None = None,
) -> str:
    """Одна правка списка блоков НА МЕСТЕ (без записи): общая для немедленной правки
    и черновика. Возвращает ref блока (у `add` — id нового).

    `templates` — сохранённые шаблоны блоков (`config["block_templates"]`): тип
    `tpl:<id>` вставляет блок шаблона с его данными (FB-27 R8d). `notes` — сюда правка
    кладёт сообщения владельцу (FB-33 M3-3d: страница снята, текст укорочен)."""
    from apps.tenants import siteconfig

    idx = next((i for i, it in enumerate(items) if (it.get("id") or it.get("key")) == ref), None)
    if op == "add":
        template = None
        if block_type.startswith(TEMPLATE_PREFIX):
            template = (templates or {}).get(block_type[len(TEMPLATE_PREFIX) :])
            if not isinstance(template, dict):
                raise SchemaError("type")
            block_type = siteconfig.cblock_type(template.get("key")) or ""
        if block_type not in dict(add_options(code)):
            raise SchemaError("type")
        if sum(1 for it in items if it.get("id")) >= siteconfig._MAX_CBLOCKS:
            # normalize молча отбросил бы лишний блок при сохранении
            raise SchemaError("full")
        new = {
            "key": block_type,
            "id": uuid.uuid4().hex[:12],
            "enabled": True,
            "data": siteconfig._clean_cblock_data(block_type, copy.deepcopy(template.get("data")))
            if template is not None
            else copy.deepcopy(siteconfig.CBLOCK_DEMO_DATA.get(block_type, {})),
        }
        if template is not None and block_type == "textpage":
            # M3-3d (ревью): шаблон с другой страницы — его страница здесь может не годиться
            new["data"] = drop_unembeddable_page(new["data"], host_for(code), notes)
        if block_type == "faq_ref" and template is None:
            from apps.core import object_faq  # FB-33 M2b-2b: на детальной — свои вопросы

            object_faq.add_default(new, host_for(code))
        items.append(new)
        return new["id"]
    if op == "add_row":
        # FB-27 R6: готовая строка — все блоки разом либо ни одного (потолок блоков).
        new_blocks = preset_blocks(value)
        own = sum(1 for it in items if it.get("id"))
        if own + len(new_blocks) > siteconfig._MAX_CBLOCKS:
            raise SchemaError("full")
        items.extend(new_blocks)
        return new_blocks[0]["id"]
    if idx is None:
        raise SchemaError("block")
    item = items[idx]
    main = siteconfig.is_main_marker(item)
    # FB-31 P0 (ревью): встроенная строка-список вне главной («Kategorien» каталога) пока
    # только двигается и скрывается — ширину/ряд/поля витрина ей ещё не рисует (R4).
    rows_host = _rows_host(code)
    from apps.core import detail_parts

    # FB-31 P5: раздел детали — двигается и скрывается, остальное ему нельзя
    # FB-32 S6f: строка оси-раздела («Angebot») — не якорь, а закреплённая строка оси
    anchor = not item.get("id") and item.get("key") in detail_parts.anchor_keys(rows_host)
    if anchor and op not in ("up", "down", "move", "toggle"):
        raise SchemaError("fixed")
    if anchor and detail_parts.fixed_order(rows_host) and op != "toggle":
        raise SchemaError("fixed")  # товар/номер: порядок разделов постоянный — только скрыть
    if anchor and op == "toggle" and not detail_parts.hideable(rows_host, item.get("key")):
        raise SchemaError("fixed")  # FB-32 S6a: текст своей страницы не скрывается
    # FB-33 M2g: раздел «на месте» только скрывается (не двигается, ширины и полей нет)
    in_place = not item.get("id") and item.get("key") in detail_parts.in_place_keys(rows_host)
    if in_place and op != "toggle":
        raise SchemaError("fixed")
    if not item.get("id") and item.get("key") in detail_parts.pinned_keys(rows_host):
        raise SchemaError("fixed")  # FB-33 M2h: позиции, форма, итог корзины — неподвижны
    before_move = list(items) if anchor and op in ("up", "down", "move") else None
    pinned = (
        not item.get("id")
        and not main
        and not anchor
        and not in_place
        and item.get("key") in siteconfig.page_builtin_keys(rows_host)
    )
    # FB-30.16 R4: блок «Kategorien» каталога прикреплён к ★ (стоит прямо над ним, как на
    # витрине) — его нельзя двигать, скрывать, менять ширину; меняется только вид.
    if pinned and op in (
        "width",
        "beside",
        "own_row",
        "newline",
        "update",
        "toggle",
        "up",
        "down",
        "move",
    ):
        raise SchemaError("fixed")
    surface = siteconfig.part_surface(rows_host)
    if surface is not None and op in ("catview", "mainview", "maingroup"):
        # FB-31 P3: вид строки страницы акций / вид и абзацы ★ — значения своей поверхности
        if op == "catview":
            if not pinned or value not in siteconfig.part_styles(rows_host, item.get("key")):
                raise SchemaError("op")
            item["style"] = value
            item["enabled"] = True
            return ref
        name = "view" if op == "mainview" else "grouping"
        axis = next((a for a in surface.axes if a.key == "main" and a.name == name), None)
        if not main or axis is None or not axis.accepts(value):
            raise SchemaError("op")
        item[axis.field] = value
        return ref
    if op == "maingroup":
        raise SchemaError("op")
    if op == "catview":
        # вид прикреплённой строки каталога: «Kategorien», шапка или сеты (R5b)
        allowed = siteconfig.CATALOG_PART_STYLES.get(item.get("key"), ())
        # FB-31 P3: строки осей акций хранятся, панели у них — позже (R5)
        catalog_page = "categories" in siteconfig.page_builtin_keys(rows_host)
        if not pinned or not catalog_page or value not in allowed:
            raise SchemaError("op")
        item["style"] = value
        item["enabled"] = True  # ревью R4: старая скрытая строка снова действует
        return ref
    if op == "mainview":
        from apps.catalog import catalog_parts

        if not main or "categories" not in siteconfig.page_builtin_keys(rows_host):
            raise SchemaError("op")
        if value not in ("raster", *MAIN_VIEW_CHOICES):
            raise SchemaError("op")
        for k in ("style", "grid"):
            item.pop(k, None)
        if value != "raster":
            item["style"] = value
            grid = catalog_parts.from_code(value).grid
            if grid:
                item["grid"] = grid
        else:
            item["style"] = "raster"  # явная сетка — поверх кода шаблона
        return ref
    if op == "switch":
        # FB-33 M2e: сменить вид блока внутри семьи без потери данных (text ↔ image_text);
        # id, ширина, оформление и переводы остаются — меняется только ключ и чистка данных
        old = siteconfig.cblock_type(item.get("key")) or ""
        if item.get("id") and not main and old == value:
            return ref  # «сменить» на текущий вид — ничего не делать (не ошибка)
        if not item.get("id") or main or not block_catalog.can_switch(old, value):
            raise SchemaError("op")
        item["key"] = value
        data = siteconfig._clean_cblock_data(value, dict(item.get("data") or {}))
        if value == "textpage":
            # M3-3d (ревью): запомненную страницу удалили (или блок теперь на ней самой)
            data = drop_unembeddable_page(data, host_for(code), notes)
        item["data"] = data
        return ref
    if op == "toggle":
        if main:
            raise SchemaError("main")
        item["enabled"] = not item.get("enabled", True)
    elif op in ("up", "down"):
        step = -1 if op == "up" else 1
        j = idx + step
        if main or item.get("enabled", True):
            # через скрытых соседей — до ближайшего видимого (см. blocks_for)
            # FB-31 P5 (ревью): скрытый раздел детали — тоже место (блок встаёт рядом с ним)
            sec = detail_parts.section_keys(rows_host)
            while 0 <= j < len(items) and not (
                siteconfig.is_main_marker(items[j])
                or items[j].get("enabled", True)
                or (not items[j].get("id") and items[j].get("key") in sec)
            ):
                j += step
        # FB-33 M2g (ревью): строки «на месте» — не места для блока (страница рисует блок у
        # соседнего раздела): «выше» перешагивает их целиком
        while step < 0 and 0 <= j < len(items) and _is_in_place(items[j], rows_host):
            j += step
        if 0 <= j < len(items):
            items.insert(j, items.pop(idx))
            _past_in_place(items, ref, rows_host)
            _pinned_slide(items, ref, rows_host, up=step < 0)
            if before_move is not None and not _pinned_order_ok(items, rows_host):
                items[:] = before_move  # раздел не встаёт выше неподвижных строк корзины
                raise SchemaError("fixed")
    elif op == "move":
        # FB-29.5b: перетаскивание — блок встаёт перед другим или после него. Та же
        # перестановка, что кнопками; мусор и «на себя» ничего не меняют.
        where, _sep, target = value.partition(":")
        if target == detail_parts.KAUF_REF and rows_host in detail_parts.KAUF_FIRST:
            # покупка в первом экране — блок встаёт в начало (над разделами)
            items.insert(0, items.pop(idx))
            return ref
        if target == detail_parts.KAUF_REF:
            # FB-31 P5 (ревью): «Buchung» стоит после последнего раздела — бросить на неё =
            # встать после последнего раздела (до неё) или в хвост (после неё)
            last = [
                it.get("key")
                for it in items
                if it.get("key") in detail_parts.flow_section_keys(rows_host) and not it.get("id")
            ]
            if not last:
                raise SchemaError("op")
            if where == "before":
                where, target = "after", last[-1]
            else:
                moved = items.pop(idx)
                items.append(moved)
                return ref
        at = next(
            (i for i, it in enumerate(items) if (it.get("id") or it.get("key")) == target), None
        )
        if where not in ("before", "after") or at is None or at == idx:
            raise SchemaError("op")
        moved = items.pop(idx)
        at = next(i for i, it in enumerate(items) if (it.get("id") or it.get("key")) == target)
        items.insert(at + (where == "after"), moved)
        _past_in_place(items, ref, rows_host)  # FB-33 M2g: бросок на строку «на месте»
        _pinned_slide(items, ref, rows_host, up=False)
        if before_move is not None and not _pinned_order_ok(items, rows_host):
            items[:] = before_move  # раздел не встаёт выше неподвижных строк корзины
            raise SchemaError("fixed")
    elif op == "delete":
        if main or not item.get("id"):
            raise SchemaError("fixed")  # фикс-секции и основной список не удаляются
        items.pop(idx)
    elif op == "width":
        # FB-27 R3 / FB-29.5: ширина — у своих блоков и у встроенных секций главной;
        # узкие соседи встают в один ряд. У основного списка страницы ширины нет.
        if main or not (item.get("id") or home_section(item)):
            raise SchemaError("fixed")
        if value not in {v for v, _label in width_choices(item)}:
            raise SchemaError("width")
        item["width"] = value
        if value not in siteconfig.NARROW_WIDTHS:
            item.pop("newline", None)
            item.pop("pos", None)
    elif op == "update":
        # FB-27 R3b: короткое содержимое простого блока — прямо в панели. ПАТЧ: меняются
        # только присланные поля, остальное (стиль, фото, оформление) остаётся (W0).
        if not main and banner_place(item) and fields and set(fields) & set(PLACE_FIELDS):
            # FB-29.2: настройки слайдера места показа — патч; без правок ничего
            data = dict(item.get("data") or {})
            before = siteconfig.clean_banner_choice(data)
            names = (*SLIDER_FIELDS, *SHOW_FIELDS) if _is_hero_row(item) else PLACE_FIELDS
            patched = {**data, **{k: str(fields[k]) for k in names if k in fields}}
            if "arrows" not in fields and set(fields) & {"auto", "interval"}:
                patched.pop("arrows", None)  # снятая галочка не приходит вовсе
            after = siteconfig.clean_banner_choice(patched)
            if after == before:
                return ref
            for key in PLACE_FIELDS:
                data.pop(key, None)
            _store_banner_data(item, {**data, **{k: after[k] for k in after if k != "pick"}})
            return ref
        if not main and _is_usp_row(item) and fields:
            _update_usp(item, fields)  # FB-32 S2
            return ref
        if not main and not item.get("id") and item.get("key") in siteconfig.BUILTIN_LIST_SOURCES:
            # встроенный список главной: патч строки секции; без правок — ничего
            _update_builtin(item, fields)
            return ref
        if not main and section_style_fields(item) and fields is not None and "style" in fields:
            # FB-33 M2b: вид встроенной секции главной — та же ось `style`, что пишет Студия
            style = str(fields["style"]).strip()
            if style == "":
                item.pop("style", None)
            elif style in siteconfig.SECTION_STYLES.get(item["key"], ()):
                item["style"] = style
            else:
                raise SchemaError("fields")
            return ref
        key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
        if key == "list":
            from apps.core import list_panel

            allowed = list(list_panel.NAMES)
        else:
            allowed = [name for name, _label, _kind in PANEL_FIELDS.get(key, ())]
        if main or not item.get("id") or not allowed:
            raise SchemaError("fields")
        sent = {n: str(fields[n]) for n in allowed if fields is not None and n in fields}
        data = dict(item.get("data") or {})
        if key == "button" and sent.get("url") and sent["url"] != data.get("url"):
            # Небезопасная схема (javascript:, data:, //host) отбрасывается уже при записи;
            # витрина дополнительно фильтрует на выводе (`safe_href`).
            from apps.tenants.templatetags.siteui import safe_href

            if safe_href(sent["url"]) == "#" and sent["url"].strip() != "#":
                raise SchemaError("url")
        if key == "textpage" and sent.get("page") and sent["page"] != data.get("page"):
            # FB-27 R6: только существующая страница и не та, на которой стоит блок.
            if not page_embeddable(sent["page"], host_for(code)):
                raise SchemaError("page")
        sent, capped = siteconfig.cap_block_texts(key, sent, stored=data)
        if capped and notes is not None:
            notes.append(siteconfig.cap_note())
        patched = {**data, **sent}
        if key == "list" and "source" in sent and sent["source"] != (data.get("source") or ""):
            # FB-27 R5: ключи записей одного источника в другом ничего не значат
            patched.pop("pick", None)
        if key == "list" and "endet" in sent:
            # «Zeitraum» — один селект на срок и «Demnächst» (хранится ключом `phase`):
            # без сброса старая фаза пережила бы выбор «Alle».
            patched.pop("phase", None)
        cleaned = siteconfig._clean_cblock_data(key, patched)
        # Ничего не прислано или не изменилось — блок не трогаем вовсе (иначе канонизация
        # данных создала бы «правку», которой владелец не делал).
        if cleaned == siteconfig._clean_cblock_data(key, data):
            return ref
        item["data"] = cleaned
    elif op in _PICK_OPS and not main and banner_place(item):
        # FB-29.2: баннеры места показа выбираются из библиотеки (один или несколько)
        from apps.core import banners
        from apps.core.models import Banner

        data = dict(item.get("data") or {})
        pick = banners.clean_pick(data.get("pick"))
        target = (banners.clean_pick([value]) or [""])[0]
        if op == "pick_clear":
            pick = []
        elif not target:
            raise SchemaError("pick")
        elif op == "pick_add":
            if target not in pick:
                if len(pick) >= siteconfig.BANNER_PICK_MAX:
                    # S8: удалённые из библиотеки записи места не занимают — их в выборе
                    # не видно, а «полно» при пяти видимых баннерах было бы необъяснимо.
                    alive = {
                        str(pk)
                        for pk in Banner.objects.filter(pk__in=pick).values_list("pk", flat=True)
                    }
                    pick[:] = [p for p in pick if p in alive]
                if len(pick) >= siteconfig.BANNER_PICK_MAX:
                    raise SchemaError("full")
                if not Banner.objects.filter(pk=target).exists():
                    raise SchemaError("pick")
                pick.append(target)
        elif target not in pick:
            raise SchemaError("pick")
        elif op == "pick_remove":
            pick.remove(target)
        else:
            i = pick.index(target)
            j = i - 1 if op == "pick_up" else i + 1
            if 0 <= j < len(pick):
                pick[i], pick[j] = pick[j], pick[i]
        if pick:
            data["pick"] = pick
        else:
            data.pop("pick", None)
        _store_banner_data(item, data)
    elif op in _PICK_OPS:
        # FB-27 R5: ручной состав блока «Liste» («Einzeln»).
        from apps.core import list_blocks

        key = siteconfig.cblock_type(item.get("key")) or item.get("key") or ""
        data = dict(item.get("data") or {})
        source = data.get("source")
        if source not in siteconfig.LIST_SOURCES:
            source = siteconfig.LIST_SOURCE_DEFAULT
        if (
            main
            or not item.get("id")
            or key != "list"
            or source not in siteconfig.LIST_PICK_SOURCES
        ):
            raise SchemaError("pick")
        pick = siteconfig.clean_pick(data.get("pick"))
        target = (siteconfig.clean_pick([value]) or [""])[0]
        if op == "pick_clear":
            pick = []
        elif not target:
            raise SchemaError("pick")
        elif op == "pick_add":
            if target not in pick:
                if len(pick) >= siteconfig.LIST_LIMIT_MAX:
                    raise SchemaError("full")
                # только существующая запись своего источника, которую сайт показывает
                if not list_blocks.is_live(source, target):
                    raise SchemaError("pick")
                pick.append(target)
        elif target not in pick:
            raise SchemaError("pick")
        elif op == "pick_remove":
            pick.remove(target)
        else:
            i = pick.index(target)
            j = i - 1 if op == "pick_up" else i + 1
            if 0 <= j < len(pick):
                pick[i], pick[j] = pick[j], pick[i]
        if pick:
            data["pick"] = pick
        else:
            data.pop("pick", None)
        item["data"] = siteconfig._clean_cblock_data(key, {**data, "source": source})
    elif op == "beside":
        _beside(items, idx, value)
    elif op == "own_row":
        _own_row(items, idx)
    elif op == "newline":
        if (
            main
            or not (item.get("id") or home_section(item))
            or item.get("width") not in siteconfig.NARROW_WIDTHS
        ):
            raise SchemaError("width")
        if item.get("newline"):
            item.pop("newline", None)
        else:
            item["newline"] = True
    else:
        raise SchemaError("op")
    return ref


def _visible_rows(items: list[dict]) -> list[list[dict]]:
    """Ряды видимых элементов списка блоков — те же, что рисуют витрина и схема."""
    from apps.tenants import siteconfig

    visible = [it for it in items if it.get("enabled", True)]
    return [
        g["row"] if g.get("key") == "_row" else [g] for g in siteconfig.group_block_rows(visible)
    ]


def _ref(it: dict) -> str:
    return it.get("id") or it.get("key") or ""


def _keep_neighbours_apart(items: list[dict], idx: int) -> None:
    """Блок `idx` уходит со своего места: ряды вокруг остаются как были — второй блок его
    ряда (если блок начинал ряд) и первый блок следующего ряда начинают свои ряды сами,
    иначе освободившееся место стянуло бы их в соседний ряд (FB-30.8, ревью)."""
    from apps.tenants import siteconfig

    item = items[idx]
    rows = _visible_rows(items)
    at = next((n for n, row in enumerate(rows) if any(b is item for b in row)), None)
    if at is None:
        return
    row = rows[at]
    if row[0] is item and len(row) > 1 and row[1].get("width") in siteconfig.NARROW_WIDTHS:
        row[1]["newline"] = True
    if at + 1 < len(rows):
        nxt = rows[at + 1][0]
        if nxt.get("width") in siteconfig.NARROW_WIDTHS:
            nxt["newline"] = True


def _beside(items: list[dict], idx: int, target_ref: str) -> None:
    """FB-30.8: поставить блок в ряд к узкому блоку `target_ref`. Ширина — своя узкая, если
    влезает, иначе наибольшая допустимая, что помещается; не помещается ни одна — блок
    встаёт своим рядом сразу после (макет 4). Сумма долей ряда не превышает единицы."""
    from apps.tenants import siteconfig

    item = items[idx]
    if siteconfig.is_main_marker(item) or not (item.get("id") or home_section(item)):
        raise SchemaError("fixed")
    target = next((it for it in items if _ref(it) == target_ref), None)
    if target is None or target is item or target.get("width") not in siteconfig.NARROW_WIDTHS:
        raise SchemaError("op")
    if not target.get("enabled", True):
        raise SchemaError("op")
    allowed = [v for v, _label in width_choices(item) if v in ROW_SHARE]
    if not allowed and item.get("width") not in ROW_SHARE:
        raise SchemaError("width")  # блоку нельзя быть узким (баннер главной и т. п.)
    _keep_neighbours_apart(items, idx)
    items.pop(idx)
    row = next(r for r in _visible_rows(items) if any(b is target for b in r))
    free = row_free(row)
    width = item.get("width") or ""
    if not (width in ROW_SHARE and ROW_SHARE[width] <= free):
        fits = [v for v in allowed if ROW_SHARE[v] <= free]
        width = max(fits, key=lambda v: ROW_SHARE[v]) if fits else ""
    last = next(n for n, it in enumerate(items) if it is row[-1])
    if width:
        item["width"] = width
        item.pop("newline", None)
        items.insert(last + 1, item)
        return
    # места нет — свой ряд сразу после этого (ширина прежняя); следующий за ним узкий
    # блок не прилипает к нему
    if item.get("width") in siteconfig.NARROW_WIDTHS:
        item["newline"] = True
    items.insert(last + 1, item)
    after = next((it for it in items[last + 2 :] if it.get("enabled", True)), None)
    if after is not None and after.get("width") in siteconfig.NARROW_WIDTHS:
        after["newline"] = True


def _own_row(items: list[dict], idx: int) -> None:
    """FB-30.8: блок — своим рядом (и следующий сосед того же ряда начинает свой)."""
    from apps.tenants import siteconfig

    item = items[idx]
    if item.get("width") not in siteconfig.NARROW_WIDTHS or not (
        item.get("id") or home_section(item)
    ):
        raise SchemaError("width")
    row = next((r for r in _visible_rows(items) if item in r), [item])
    at = row.index(item)
    if at + 1 < len(row):
        row[at + 1]["newline"] = True
    item["newline"] = True


#: FB-27 R4: чьи ещё настройки правятся на строке типа — у этих типов своей строки в
#: «Seitenaufbau» нет (категория делит блоки с каталогом, страницы акций — с обзором).
#: FB-31 P3 R6: у групп акций и страницы акции — свои строки в выборе (ведомых нет)
SETTINGS_FOLLOWERS: dict[str, tuple[str, ...]] = {}


#: FB-31 P5 R7: настройки типа, которые правятся на строке своего раздела, а не на строке
#: «Seite» (код страницы → {настройка: ref строки}); рядом — строки «Design» для этой строки.
SETTING_ROWS = {
    "product": {"product_related": "related"},
    # FB-32 S4: «Passt gut dazu» корзины — настройки на её строке, не в «Seite»
    "cart": {"cart_upsell": "upsell", "cart_upsell_layout": "upsell"},
}
SETTING_ROW_DESIGN = {"related": ("product_card_form",), "upsell": ("product_card_form",)}


def row_settings(code: str, ref: str) -> tuple[str, ...]:
    """Настройки, которые живут на строке `ref` страницы `code` (пусто — у строки их нет)."""
    if is_object_code(code):
        return ()
    owned = SETTING_ROWS.get(str(code).split("@", 1)[0], {})
    return tuple(c for c, row in owned.items() if row == ref)


_RELATED_COLS = frozenset(f"cols{n}" for n in range(2, 7))


def related_view(config: dict, key: str = "detail_related_layout") -> dict:
    """FB-31 P5 R7: текущие «Wie» · «Spalten» · «Höchstens» строки «Ähnliche Produkte»;
    FB-32 S4b — то же у «Passt dazu» корзины (`cart_upsell_layout`)."""
    from django.utils.translation import gettext_lazy as _

    from apps.tenants import siteconfig

    lay = siteconfig.normalize_related_layout((config or {}).get(key))
    return {
        "related_modes": (
            ("auto", _("Automatisch")),
            ("raster", _("Raster")),
            ("slider", _("Slider")),
        ),
        "related_mode": siteconfig.related_mode(lay),
        # колонки — по пресету «N в строке» (ревью R7): ручные cols и особые виды (Liste,
        # Galerie) не подменяются, пока владелец сам не выберет число
        "related_cols": lay["preset"][4:] if lay["preset"] in _RELATED_COLS else "",
        "related_preset": lay["preset"],
        "related_max": lay.get("max", siteconfig.RELATED_MAX_DEFAULT),
        "related_max_choices": siteconfig.RELATED_MAX,
    }


#: FB-27 V3: строка-носитель настроек типа страницы там, где основного списка нет
#: (код страницы → ref строки). Главная: вид баннера — в строке «Banner» (макет Main).
SETTINGS_CARRIERS = {"home": "hero"}


def settings_carrier(code: str) -> str:
    return SETTINGS_CARRIERS.get(str(code).split("@", 1)[0], "")


def settings_url(type_code: str, setting: str = "") -> str:
    """Адрес строки «Seitenaufbau», где правятся настройки типа `type_code` (замена
    экрана «Seitenvorlagen»). Тип без своей строки ведёт на строку-хозяина; неизвестный
    — просто на экран. `setting` — какую настройку раскрыть."""
    from urllib.parse import urlencode

    from apps.tenants import siteconfig

    owner = next((row for row, more in SETTINGS_FOLLOWERS.items() if type_code in more), "")
    code = owner or ("text" if type_code == "legal" else type_code)
    pt = _page_type(code)
    url = reverse("site-schema")
    if pt is None:
        return url
    block = (
        siteconfig.MAIN_LIST_KEY
        if _host(pt) in siteconfig.MAIN_LIST_HOSTS
        else settings_carrier(pt.code) or PAGE_REF
    )
    block = SETTING_ROWS.get(pt.code, {}).get(setting) or block  # R7: строка раздела
    query = {"seite": pt.code, "block": block}
    if setting:
        query["offen"] = setting
    return f"{url}?{urlencode(query)}#schema-panel"


def setting_types(tenant, code: str) -> list[str]:
    """Типы страниц, чьи настройки правятся на строке `code` (сам тип первым)."""
    from apps.core import page_settings

    pt, _host, _home = resolve(tenant, code)
    out = [pt.code]
    out += [t for t in SETTINGS_FOLLOWERS.get(pt.code, ()) if page_settings.type_active(tenant, t)]
    return out


def setting_codes(tenant, code: str) -> list[str]:
    """Коды настроек, которые можно менять на строке `code` (по порядку, без повторов)."""
    from apps.core import page_settings

    out: list[str] = []
    if is_object_code(code):
        return out  # настройки типа страницы — у общей строки, не у объекта
    hidden = _not_on_page(code)
    for type_code in setting_types(tenant, code):
        for s in page_settings.cabinet_settings(type_code):
            if s.code not in out and s.code not in hidden and page_settings.applies(tenant, s):
                out.append(s.code)
    return out


def _not_on_page(code: str) -> frozenset[str]:
    """Настройки типа, которых нет в панели строки `code`: их заменили блоки страницы
    либо они общие для сайта и правятся на экране «Design» (FB-31 P2)."""
    from apps.core import page_settings

    return REPLACED_BY_BLOCKS.get(code, frozenset()) | frozenset(page_settings.DESIGN_SETTINGS)


def design_codes(tenant, code: str) -> list[str]:
    """FB-31 P2: общие настройки «Design», действующие на странице `code` (без запросов)."""
    from apps.core import page_settings

    if is_object_code(code):
        return []
    wanted: list[str] = []
    for type_code in setting_types(tenant, code):
        for s in page_settings.cabinet_settings(type_code):
            if s.code in page_settings.DESIGN_SETTINGS and s.code not in wanted:
                if page_settings.applies(tenant, s):
                    wanted.append(s.code)
    return wanted


def design_rows(tenant, code: str) -> list[dict]:
    """FB-31 P2: общие настройки «Design» страницы `code` — строками «wie Design: X ·
    ändern →» в панели (только показ, правятся на «Design»)."""
    from apps.core import page_settings

    wanted = design_codes(tenant, code)
    if not wanted:
        return []
    found = page_settings.summaries(tenant, wanted, tuple(setting_types(tenant, code)))
    return [
        {**found[c], "code": c, "label": page_settings.DESIGN_LABELS.get(c, found[c]["label"])}
        for c in wanted
        if c in found
    ]


#: FB-30.16 R4 (стратегия FB-31): настройки, которые на строке страницы заменили блоки —
#: шаблон страницы каталога разложен на вид «Kategorien» и вид ★ «Produkte».
REPLACED_BY_BLOCKS = {
    "catalog": frozenset({"catalog_page_style"}),
    "category": frozenset({"category_page_style"}),
    # FB-31 P3: шаблон обзора — строки «Banner», «Angebotsgruppen» и вид ★; шаблон
    # страницы акции — вид строки «Angebot» (у страницы акции своя строка в выборе)
    "promos": frozenset({"promo_page_style", "promo_detail_style"}),
    "promo": frozenset({"promo_detail_style"}),
    "promo_group": frozenset({"promo_group_style"}),  # R6: шапка и вид ★ группы
    # FB-31 P4: шаблон листинга — строки «Banner · Fotos der Seite» и навигации
    **{s: frozenset({f"{s}_page_style"}) for s in sorted(_LISTING_GATES)},
}


#: Строка «Einstellungen der Seite» — у страниц без основного списка (главная, детали,
#: корзина, текстовые): настройки типа некуда больше положить.
PAGE_REF = "__page"


def settings_groups(tenant, code: str, config: dict, row: str = "") -> list[dict]:
    """Настройки строки `code` по значениям `config` (черновик): [{label, settings}].
    Первая группа — сам тип (без заголовка), дальше типы без своей строки. `row` — строка
    раздела со своими настройками (R7, `SETTING_ROWS`); без него — настройки строки «Seite»."""
    from apps.core import page_settings

    owned = SETTING_ROWS.get(str(code).split("@", 1)[0], {})
    seen: set[str] = {c for c, r in owned.items() if r != row}
    out = []
    for i, type_code in enumerate(setting_types(tenant, code)):
        found = page_settings.schema(tenant, (type_code,), config=config)
        if not found:
            continue
        hidden = _not_on_page(code)
        rows = [
            s
            for s in found[0].settings
            if s.code not in seen and s.code not in hidden and (not row or owned.get(s.code) == row)
        ]
        seen.update(s.code for s in rows)
        if rows:
            out.append(
                {
                    "label": "" if i == 0 else str(found[0].label),
                    "settings": [{"s": s, "current": _current_label(s)} for s in rows],
                }
            )
    return out


def _current_label(state) -> str:
    """Текущее значение настройки словами — для свёрнутой строки панели."""
    if state.kind == "bool":
        want = "1" if state.value else "0"
        return next((str(c.label) for c in state.choices if c.value == want), "")
    return next((str(c.label) for c in state.choices if c.value == state.value), str(state.value))


#: FB-30.16 R4: «Darstellung» блока товаров ★ каталога (кроме сетки «Raster»).
MAIN_VIEW_CHOICES = ("schaufenster", "magazin", "mosaik")

_PICK_OPS = frozenset({"pick_add", "pick_remove", "pick_up", "pick_down", "pick_clear"})


def store_items(config: dict, home: bool, host: str, items: list[dict]) -> None:
    """Кладёт блоки страницы в `config` (на месте) и выравнивает переводы C-блоков."""
    from apps.tenants import siteconfig

    if home:
        lift_hero_choice(config, items)
        siteconfig.realign_block_overlays(config, new_sections=items)
        config["sections"] = items
        return
    # ВСЕ хосты: выравнивание сверяет каждый хост оверлея с новым набором, и
    # переданный один хост стёр бы переводы блоков остальных страниц.
    from apps.core import detail_parts

    if detail_parts.module_of(host):  # FB-31 P5: порядок/видимость разделов — на место
        items = detail_parts.lift(config, host, items)
    elif detail_parts.object_kind(host):
        # R8: разделы объекта — в его `page_override` (пишет `aufbau_draft.commit`), здесь —
        # только якоря и свои блоки
        items, _state = detail_parts.object_lift(config, host, items)
    page_blocks = dict(config.get("page_blocks") or {})
    page_blocks[host] = items
    siteconfig.realign_block_overlays(config, new_page_blocks=page_blocks)
    config["page_blocks"] = page_blocks


@transaction.atomic
def apply(
    tenant,
    code: str,
    op: str,
    ref: str = "",
    block_type: str = "",
    value: str = "",
    fields: dict | None = None,
) -> str:
    """Одна правка схемы страницы `code` СРАЗУ в базу. Бросает SchemaError на
    недопустимом. Возвращает ref блока, с которым работали (у `add` — id нового).
    Экран «Seitenaufbau» правит через черновик (`aufbau_draft`), это — для прочих."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    _pt, host, home = resolve(tenant, code)
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = siteconfig.normalize(locked.site_config)
    if ref == TITLE_REF:
        from apps.core import aufbau_draft

        draft = {"title": (config.get("page_titles") or {}).get(host) or {}}
        title_op(host, draft, op, fields)
        aufbau_draft._put_title(config, host, draft["title"])
        locked.site_config = siteconfig.normalize(config)
        locked.save(update_fields=["site_config", "updated_at"])
        tenant.site_config = locked.site_config
        return ref
    if is_next_edit(host, ref, op):
        from apps.core import aufbau_draft, confirmation_page

        draft = {"next": confirmation_page.clean_next(config.get(confirmation_page.NEXT_KEY))}
        next_op(host, draft, op, fields)
        aufbau_draft._put_next(config, draft["next"])
        locked.site_config = siteconfig.normalize(config)
        locked.save(update_fields=["site_config", "updated_at"])
        tenant.site_config = locked.site_config
        return ref
    items = load_items(config, home, host)
    ref = mutate(items, code, op, ref, block_type, value, fields, config.get("block_templates"))
    store_items(config, home, host, items)
    locked.site_config = siteconfig.normalize(config)
    locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = locked.site_config
    return ref
