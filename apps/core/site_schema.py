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
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.core import studio_pages

#: Типы, у которых нет своей страницы без параметра — превью строим по первой записи.
_SAMPLES = {
    "product": ("apps.catalog.models", "Product", {"is_active": True}),
    "category": ("apps.catalog.models", "Category", {"is_active": True}),
}


@dataclass
class PageRow:
    code: str
    label: str
    host: str  # "" у главной (у неё sections)
    count: int
    preview_url: str


def _sections_label(key: str) -> str:
    from apps.tenants import siteconfig

    for k, label, _default in siteconfig.SECTIONS:
        if k == key:
            return str(label)
    return str(siteconfig.CBLOCK_LABELS.get(key, key))


def _preview_url(pt) -> str:
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
    return ""


def page_rows(config: dict) -> list[PageRow]:
    """Типы страниц со своими блоками (главная первой) + число видимых блоков."""
    rows = []
    for pt in studio_pages.PAGE_TYPES:
        if pt.code != "home" and not pt.block_host:
            continue
        blocks = blocks_for(config, pt.code)
        rows.append(
            PageRow(
                code=pt.code,
                label=str(pt.label),
                host=pt.block_host if pt.code != "home" else "",
                count=sum(1 for b in blocks if b["enabled"] and not b["main"]),
                preview_url=_preview_url(pt),
            )
        )
    return rows


def _page_type(code: str):
    base = code.split("@", 1)[0]
    if "@" in code and base != "text":  # подстраницы есть только у типа «Seite»
        return None
    for pt in studio_pages.PAGE_TYPES:
        if pt.code == base and (pt.code == "home" or pt.block_host):
            return pt
    return None


#: M21.11 (решение владельца): у типа «Seite» у КАЖДОЙ страницы свой набор блоков —
#: «Über uns» (хост info), «Versand» (versand) и каждая своя страница (seite:<slug>).
#: Код строки схемы: «text» = Über uns, «text@<хост>» = остальные.
TEXT = "text"
CONTACT_REF = "__contact"


@dataclass
class SubPage:
    code: str
    label: str
    host: str
    preview_url: str


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


def host_for(code: str) -> str:
    """Хост блоков строки схемы ("" у главной). Неизвестная подстраница → ""."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None or pt.code == "home":
        return ""
    if "@" not in code:
        return pt.block_host
    if pt.code != TEXT:
        return ""
    host = code.split("@", 1)[1]
    if host == "versand":
        return host
    if host.startswith("seite:") and siteconfig.is_page_block_host(host):
        # Ревью безопасности: только существующая страница — иначе POST плодил бы
        # хосты-призраки и вытеснял настоящие (у page_blocks общий потолок хостов).
        from apps.core.models import ContentPage

        if ContentPage.objects.filter(slug=host.split(":", 1)[1]).exists():
            return host
    return ""


def blocks_for(config: dict, code: str) -> list[dict]:
    """Строки схемы: {ref, key, label, enabled, main, cblock, summary} по порядку страницы."""
    from apps.tenants import siteconfig

    pt = _page_type(code)
    if pt is None:
        return []
    host = host_for(code)
    if pt.code == "home":
        items = config.get("sections") or []
    elif not host:
        return []
    else:
        items = siteconfig.main_list_sequence(host, (config.get("page_blocks") or {}).get(host, []))
    out = []
    if host == "info":
        # M21.11: карточка «Kontakt & Öffnungszeiten» стоит на «Über uns» над блоками —
        # строкой схемы, которую можно выключить (порядок фиксирован, удалить нельзя).
        out.append(
            {
                "ref": CONTACT_REF,
                "key": "contact",
                "label": str(_("Kontakt & Öffnungszeiten")),
                "enabled": config.get("about_contact") is not False,
                "main": False,
                "cblock": False,
                "fixed": True,
                "summary": "",
            }
        )
    main_label = _("Hauptliste")  # не внутри f-строки: xgettext её не извлекает
    for item in items:
        key = item.get("key", "")
        main = siteconfig.is_main_marker(item)
        cblock = bool(item.get("id")) and not main
        data = item.get("data") or {}
        out.append(
            {
                "ref": item.get("id") or key,
                "key": key,
                "label": f"★ {main_label}" if main else _sections_label(key),
                "enabled": True if main else bool(item.get("enabled", True)),
                "main": main,
                "cblock": cblock,
                "summary": str(data.get("title") or data.get("label") or "")[:60],
                "fixed": False,
            }
        )
    movable = [b for b in out if not b["fixed"]]
    for i, b in enumerate(movable):
        b["can_up"] = i > 0
        b["can_down"] = i < len(movable) - 1
    return out


def add_options(code: str) -> list[tuple[str, str]]:
    """Какие блоки можно добавить на этот тип страницы (повторяемые + ссылочные на страницах)."""
    from apps.tenants import siteconfig

    keys = list(siteconfig.REPEATABLE_BLOCKS)
    if code != "home":
        keys += list(siteconfig.PAGE_REF_BLOCKS)
    return [(k, str(siteconfig.CBLOCK_LABELS.get(k, k))) for k in keys]


class SchemaError(ValueError):
    """Недопустимая операция схемы (неизвестный тип/блок/операция)."""


@transaction.atomic
def apply(tenant, code: str, op: str, ref: str = "", block_type: str = "") -> None:
    """Одна правка схемы страницы `code`. Бросает SchemaError на недопустимом."""
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    pt = _page_type(code)
    if pt is None:
        raise SchemaError("page")
    host = host_for(code)
    home = pt.code == "home"
    if not home and not host:
        raise SchemaError("page")
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = siteconfig.normalize(locked.site_config)
    if host == "info" and ref == CONTACT_REF:
        if op != "toggle":
            raise SchemaError("fixed")
        if config.get("about_contact") is False:
            config.pop("about_contact", None)
        else:
            config["about_contact"] = False
        locked.site_config = siteconfig.normalize(config)
        locked.save(update_fields=["site_config", "updated_at"])
        tenant.site_config = locked.site_config
        return
    if home:
        items = copy.deepcopy(config.get("sections") or [])
    else:
        items = copy.deepcopy(
            siteconfig.main_list_sequence(host, (config.get("page_blocks") or {}).get(host, []))
        )
    idx = next((i for i, it in enumerate(items) if (it.get("id") or it.get("key")) == ref), None)
    if op == "add":
        if block_type not in dict(add_options(code)):
            raise SchemaError("type")
        new = {
            "key": block_type,
            "id": uuid.uuid4().hex[:12],
            "enabled": True,
            "data": copy.deepcopy(siteconfig.CBLOCK_DEMO_DATA.get(block_type, {})),
        }
        items.append(new)
    else:
        if idx is None:
            raise SchemaError("block")
        item = items[idx]
        main = siteconfig.is_main_marker(item)
        if op == "toggle":
            if main:
                raise SchemaError("main")
            item["enabled"] = not item.get("enabled", True)
        elif op in ("up", "down"):
            j = idx - 1 if op == "up" else idx + 1
            if 0 <= j < len(items):
                items[idx], items[j] = items[j], items[idx]
        elif op == "delete":
            if main or not item.get("id"):
                raise SchemaError("fixed")  # фикс-секции и основной список не удаляются
            items.pop(idx)
        else:
            raise SchemaError("op")
    if home:
        siteconfig.realign_block_overlays(config, new_sections=items)
        config["sections"] = items
    else:
        # ВСЕ хосты: выравнивание сверяет каждый хост оверлея с новым набором, и
        # переданный один хост стёр бы переводы блоков остальных страниц.
        page_blocks = dict(config.get("page_blocks") or {})
        page_blocks[host] = items
        siteconfig.realign_block_overlays(config, new_page_blocks=page_blocks)
        config["page_blocks"] = page_blocks
    locked.site_config = siteconfig.normalize(config)
    locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = locked.site_config
